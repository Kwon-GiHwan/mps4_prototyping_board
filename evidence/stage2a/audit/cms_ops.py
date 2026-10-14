"""List kernel ops, waits and BLOCKDEP values in a PMWL blob's command stream (opcode names from the driver header)."""
import re, struct, sys, hashlib
hdr = open(sys.argv[1]).read()
names = {}
for kind, n, v in re.findall(r"^\s+CMD([01])_OPCODE_(NPU_[A-Z0-9_]+) = (\d+),", hdr, re.M):
    names[(int(kind), int(v))] = n
for path in sys.argv[2:]:
    b = open(path, "rb").read()
    off, ln = struct.unpack_from("<II", b, 8)
    cms = b[off:off + ln]
    print(path.split("/")[-1], "cms sha", hashlib.sha256(cms).hexdigest()[:8], "len", ln)
    i, ops = 0, []
    while i < len(cms):
        w = struct.unpack_from("<I", cms, i)[0]
        op, ctrl, param = w & 0x3FF, (w >> 14) & 3, w >> 16
        n = names.get((ctrl, op), f"?{ctrl}:{op}")
        if n.startswith("NPU_OP_") or n == "NPU_SET_BLOCKDEP":
            ops.append(f"{n}({param})" if n in ("NPU_SET_BLOCKDEP", "NPU_OP_KERNEL_WAIT", "NPU_OP_DMA_WAIT") else n)
        i += 8 if ctrl == 1 else 4
    print("  ", " ".join(ops))
