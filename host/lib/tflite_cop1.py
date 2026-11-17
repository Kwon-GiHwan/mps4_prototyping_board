"""Replace the command stream of a Vela-compiled .tflite (the ethos-u custom op's COP1 payload) without re-serialising
the model (Stage 6E-X3): the new payload is appended as a fresh flatbuffer vector after the last byte and the one
Buffer.data offset that pointed at the old payload is redirected to it. Every other byte stays as it was, so a byte
comparison proves that nothing but that buffer changed. Minimal flatbuffer reader for the TFLite schema fields used here
(Model.operator_codes 1, subgraphs 2, buffers 4; SubGraph.tensors 0, operators 3; Operator.opcode_index 0, inputs 1;
OperatorCode.custom_code 1; Tensor.buffer 2; Buffer.data 0, offset 1, size 2)."""
from __future__ import annotations

import struct

COP1 = b"COP1"
DA_OPTIMIZER_CONFIG, DA_COMMAND_STREAM, DA_NOP = 1, 2, 5
DATA_ALIGN = 16


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _field(b, table, k):
    """Absolute position of field k of the table at `table`, or None if absent."""
    vt = table - struct.unpack_from("<i", b, table)[0]
    size = struct.unpack_from("<H", b, vt)[0]
    if 4 + 2 * k >= size:
        return None
    off = struct.unpack_from("<H", b, vt + 4 + 2 * k)[0]
    return table + off if off else None


def _vector(b, at):
    pos = at + _u32(b, at)
    return pos, _u32(b, pos)


def _table_at(b, vec_pos, i):
    e = vec_pos + 4 + 4 * i
    return e + _u32(b, e)


def cop1_buffer_field(model: bytes) -> tuple[int, int, int]:
    """(position of Buffer.data's offset field, data start, data length) of the ethos-u op's input 0."""
    root = _u32(model, 0)
    sg_vec, n_sg = _vector(model, _field(model, root, 2))
    if n_sg != 1:
        raise ValueError(f"{n_sg} subgraphs")
    sg = _table_at(model, sg_vec, 0)
    ops_vec, n_ops = _vector(model, _field(model, sg, 3))
    codes_vec, _ = _vector(model, _field(model, root, 1))
    found = []
    for i in range(n_ops):
        op = _table_at(model, ops_vec, i)
        f = _field(model, op, 0)
        oc = _table_at(model, codes_vec, _u32(model, f) if f else 0)
        cf = _field(model, oc, 1)
        if cf is None:
            continue
        sp, sn = _vector(model, cf)
        if model[sp + 4:sp + 4 + sn] == b"ethos-u":
            found.append(op)
    if len(found) != 1:
        raise ValueError(f"{len(found)} ethos-u ops")
    in_vec, n_in = _vector(model, _field(model, found[0], 1))
    tensor_idx = struct.unpack_from("<i", model, in_vec + 4)[0]
    t_vec, _ = _vector(model, _field(model, sg, 0))
    tensor = _table_at(model, t_vec, tensor_idx)
    buf_idx = _u32(model, _field(model, tensor, 2))
    b_vec, _ = _vector(model, _field(model, root, 4))
    buf = _table_at(model, b_vec, buf_idx)
    for k in (1, 2):
        g = _field(model, buf, k)
        if g is not None and struct.unpack_from("<Q", model, g)[0] != 0:
            raise ValueError("buffer uses offset/size (external data)")
    data_field = _field(model, buf, 0)
    pos, n = _vector(model, data_field)
    return data_field, pos + 4, n


def cop1(model: bytes) -> bytes:
    _, start, n = cop1_buffer_field(model)
    return model[start:start + n]


def cop1_with_cms(cop: bytes, cms: bytes) -> bytes:
    """The same COP1 payload with the COMMAND_STREAM action's words replaced (length field updated)."""
    if cop[:4] != COP1 or len(cop) % 4 or len(cms) % 4:
        raise ValueError("COP1 payload / command stream not word aligned")
    words = struct.unpack(f"<{len(cop) // 4}I", cop)
    out, i, done = [words[0]], 1, False
    while i < len(words):
        w = words[i]
        cmd = w & 0xFF
        if cmd == DA_OPTIMIZER_CONFIG:
            out += words[i:i + 3]; i += 3
        elif cmd == DA_COMMAND_STREAM:
            if done:
                raise ValueError("more than one COMMAND_STREAM")
            n = ((w >> 8) & 0xFF) << 16 | (w >> 16)
            m = len(cms) // 4
            if m >= 1 << 24:
                raise ValueError("command stream too long")
            out.append(DA_COMMAND_STREAM | ((m >> 16) & 0xFF) << 8 | (m & 0xFFFF) << 16)
            out += struct.unpack(f"<{m}I", cms)
            i += 1 + n; done = True
        elif cmd == DA_NOP:
            out.append(w); i += 1
        else:
            raise ValueError(f"unknown driver action {cmd} at word {i}")
    if not done:
        raise ValueError("no COMMAND_STREAM")
    return struct.pack(f"<{len(out)}I", *out)


def with_cop1(model: bytes, new: bytes) -> bytes:
    """Append `new` as a vector whose data starts 16-byte aligned and point the ethos-u op's Buffer.data at it."""
    field, _, _ = cop1_buffer_field(model)
    pad = (-(len(model) + 4)) % DATA_ALIGN
    vec = len(model) + pad
    out = bytearray(model) + bytes(pad) + struct.pack("<I", len(new)) + new
    out += bytes((-len(out)) % 4)
    struct.pack_into("<I", out, field, vec - field)
    return bytes(out)
