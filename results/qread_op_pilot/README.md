# Stage 2B operator-aware QREAD pilot — yolo ops 99 / 100 (boots 328–329, 2026-11-10 UTC board clock)

Contract `evidence/qread_op_pilot/contract.md` (frozen `987b3e9`, before boot 328). **TA profile 1** (MLEK
sys_dram_mid). Driver runner of `717ba5b` (boot `dfee8649`, bram `178f6c45`), checked trace modes, yolo-fastest_192_face_v4
DRWL `9f300436` (MLEK input; command stream `fa50d14e` = the 2B-3 ctl stream), original command stream, no STOP /
KERNEL_WAIT / mid-stream IRQ. 1 warm-up + 4 measured RUNs per condition and set. Both boots `campaign exit=0`, board
restored to m6 (`RESTORE VERIFIED`), postflight done, card withdrawn. Raw: `evidence/qread_op_pilot/raw_p12`, `raw_p3`.

```
python3 host/analysis/qread_op_pilot.py p12 evidence/qread_op_pilot/raw_p12/conds/yolo-fastest_192_face_v4 \
  evidence/qread_pilot/workloads/yolo-fastest_192_face_v4.drwl.cms.bin 0x20007001 results/qread_op_pilot/p12
python3 host/analysis/qread_op_pilot.py p3 evidence/qread_op_pilot/raw_p3/conds/yolo-fastest_192_face_v4 \
  evidence/qread_pilot/workloads/yolo-fastest_192_face_v4.drwl.cms.bin 0x20007001 results/qread_op_pilot/p3 \
  results/qread_op_pilot/p12/summary.json
```

## Verdicts (preregistered)

| step | verdict | basis |
| --- | --- | --- |
| P1 | **TRACE_RECOVERED** | 12/12 measured q06 RUNs RECOVERED (none INVALID, none VALID); NPU_ACTIVE vs base: set 1 −0.06 %, set 2 +0.40 %, set 3 −0.12 % (limit 1 %); every RUN valid, output = golden; ID read back 0x20007001 = capabilities `npu_id`; QSIZE 21,056 |
| P2 | **BOUNDARY_OBSERVED** | in all 12 RUNs both boundaries bracketed by first-read QREAD values and separated (a first-read QREAD inside (18,980, 19,136]) |
| P3 | **NOT_ASSOCIATED** (term: resolution) | p06: 4/4 RECOVERED, NPU_ACTIVE −0.02 % vs pbase, both boundaries observed and separated in every RUN, but the median bracket width of op 99 = 637.5 cycles > 2 × q06's 296.5 (op 100: 1,039.5 ≤ 2 × 512.5). By the rule the PMU interval values are **not used**; none are reported |

These are observation levels. Nothing here is an operator's start/end cycle or an attribution of counts to an operator.

## POST_HOC_DESCRIPTIVE

- **Rejected reads.** q06: 77 rejected attempts over 12 RUNs (3–12 per RUN): QREAD 66, STATUS 11; **every one returned
  the data of the read right before it (the ID read)**; ID reads were never wrong; all re-read and accepted (one STATUS
  slot needed both re-reads). p06: 27 (QREAD 7, STATUS 3, counters 17), same kind, all accepted. No checksum, layout or
  count error in any sample → the CPU load itself returned the preceding read's data (read path); the recording and
  transfer path showed no error. Which component of the read path (CPU bus interface, interconnect, NPU register slave):
  `UNVERIFIED`.
- **Reserve-take sample**: present and flagged in every traced RUN, outside the window; QREAD = 0 after the start: 2
  samples, STATUS running in both.
- **Commands completed between consecutive stored samples**: median 0 (QREAD unchanged), max 85; read cost per sample
  median 297 CPU cycles (q06; 6 NPU reads), 642 with 4 counters (p06).
- **Around the boundaries (q06)**: QREAD stands at 18,820 (right after op 98's kernel instruction) for ≈ 2.5–3.4 k cycles
  before op 99 is seen passed; op 99 passed → op 100 passed ≈ 1.82–1.84 k cycles (one RUN 2.25 k); bracket widths ≈ 296
  or ≈ 725 cycles (one or two polls).
- **Traffic and other events** (q06 vs base, medians per set, 18 event/set pairs; `p12/summary.json` →
  `P1_descriptive.traffic`): all SRAM/EXT transfer and beat counters within 1 %; the only one beyond is event 53 (set 2,
  +7.1 %; not in TRM 110, not interpreted).

## Judgement

QREAD with checked reads gives, on the original stream, a reliable completion-progress timeline at the op 99 / op 100
boundaries: each boundary is bracketed to one or two polls (≈ 0.3–0.7 k CPU cycles) without disturbing NPU_ACTIVE
beyond 0.4 %. It still only bounds when completion became visible (stop position "after the kernel instruction" stays
ambiguous between completion and issue). Adding PMU reads doubled the sample cost and widened op 99's bracket past the
preregistered limit, so no PMU change around the boundaries is reported. Every RUN needed re-reads: the register reads
are not trustworthy without the ID sentinel on this board.
