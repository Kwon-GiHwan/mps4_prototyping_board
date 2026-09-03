# U65 binary instrumentation backend — audit (E0/E1)

Authority (source, never byte-pattern inference):
- `ethosu65_interface.h` (pinned core-driver 25.11): C-enums `CMD0_OPCODE_*`
  (120 entries, `NPU_OP_IRQ=1`) / `CMD1_OPCODE_*` (74); **no branch opcode
  exists in the U65 command space** — displacement risk VERIFIED_NOT_PRESENT
  structurally. STATUS bit layout confirms `cmd_end_reached` at bit 5.
- Vela 5.0.0 legacy emitter (`register_command_stream_generator.py`
  L184–224): cmd0 word = `(param&0xFFFF)<<16 | opcode`; cmd1 sets the
  Payload32 mode bit (bit 14) and carries one 32-bit offset word.
- Container framing: the shared COP1 driver-action format (identical to the
  U85 audit; same driver parses both).

Backend implementation (`bridge_e01.py`, frozen in evidence): mechanical
enum extraction; fail-closed decoder (unknown opcode, nonzero reserved
bits, truncated CMD1 all STOP); identity serializer; deep-copy container
writer reused from the qualified U85 tooling (force_align:16 preserved).

**Stack fact (Amendment 1)**: Vela 5.0.0 default-routes U55/U65 through
regor; the compiler-internal insertion exists only on the deprecated
legacy core (`--debug-force-legacy-core`). C0 is the forced-legacy output,
identity frozen at generation; both methods derive from it.

Method B semantic rule, derived independently of Method A's source: NNG
operations materialize as compute launches and `NPU_OP_DMA_START` launches
(KERNEL/EVENT/DMA-wait commands are dependency mechanics, not operations);
`op_index` enumerates {compute, DMA_START} in stream order; one
`NPU_OP_IRQ(param=op_index)` is inserted after each compute launch.

## E1 verdict

For both cells (kws 14 IRQs, rnnoise 46 IRQs):
zero-modification roundtrip byte-identical; strip(A)=C0 and strip(B)=C0
exact; boundary positions 14/14 and 46/46 identical; params identical; and
**the instrumented streams are byte-identical (A == B)** — the strongest
implementation-evidence case anticipated by the plan. Two intermediate
fail-closed catches are recorded in the evidence log: the initial Method-A
zero-IRQ run (regor routing, → Amendment 1) and the initial Method-B
numbering basis (launch-count vs NNG index), both fixed before any
runtime data existed.
