# Stage 2B operator-aware QREAD pilot — yolo ops 99 / 100 (frozen 2026-11-10, before boot 328)

Owner directive 2026-11-10 ("Stage 2B — Operator-aware QREAD Pilot") and the owner's answer on the read method after
P0 (same day, recorded below). **TA: MLEK's own sys_dram_mid set-up = TA profile 1.** Ethos-U85 1024 MAC on FI101.
Official Ethos-U core driver (driver runner). Model **yolo-fastest_192_face_v4 only** (the owner fixed the scope; no
other model). Original command stream: no command-stream change, no STOP, no KERNEL_WAIT, no mid-stream IRQ.
Profile `config/driver_r5.json`: per condition and set 1 warm-up + 4 measured RUNs.

## Question (and what is not asked)

Can command-completion progress at the boundaries of kernel ops 99 (Conv2D) and 100 (Resize) be observed with QREAD on
the original stream, and can PMU activity be read in the same intervals? **Not asked and not claimed:** an op's start
or end cycle, per-layer cycles, attribution of PMU counts to an op. `BOUNDARY_OBSERVED` and `PMU_ASSOCIATED` are
observation levels; without a direct check of where the counts come from, results are reported only as a temporal
association of command progress and PMU activity.

## P0 — static checks before any board step (done, 2026-11-10)

| item | result | how |
| --- | --- | --- |
| register offsets | ID 0x00, STATUS 0x04, QREAD 0x18, QSIZE 0x20, PROT 0x24 = core driver `ethosu85_interface.h` (MLEK `b2c0bb2`, core driver `0356707`) | container source |
| QSIZE/PROT confusion | fixed in `afceaa8` (record `qsize` = stream length on the board, boots 325–326); the constant now lives in `trace.h` beside QREAD/STATUS/ID | source, pilot records |
| driver API vs direct read | `ETHOSU_PMU_Get_QREAD()` reads `drv->dev.reg->QREAD`; the trace reads `ethosu_drv.dev.reg + 0x18` (`trace_bind(ethosu_drv.dev.reg, …)`): the same register | source (static; not compared on the board) |
| QREAD / STATUS meaning | QREAD = completion position (TRM; "current command" wording kept as a tension); STATUS bit 0 running, bit 5 cmd_end_reached, 31:16 IRQ history | interface header |
| op mapping | the DRWL command stream (`evidence/qread_pilot/workloads/yolo-fastest_192_face_v4.drwl.cms.bin`, 21,056 B) is byte-identical to the 2B-3 ctl blob's stream (`1f71e475`, board host `~/evsweep_s2probe`); op 99 = CONV kernel instruction at byte 18,980, op 100 = RESIZE at 19,136 (the 2B-3 timeline column `offset` = instruction + 4); no DMA, BLOCKDEP > 0 or WAIT between them (op 99 blockdep 0, op 100 blockdep 0; op 101 blockdep 5) | `cms_timeline`, byte compare |
| first sample = previous stream end (pilot, 40/40 RUNs) | **instrumentation:** `ethosu_reserve_driver()` (ethosu_driver.c:752) also takes a semaphore; the hook ran the trace there, found the count already 1 and stored its final sample: NPU stopped (STATUS 0xFFFF0020), QREAD = last RUN's end, ≈ 9.5 k cycles before `dwt_arm`. The register value itself was correct | driver source, pilot raw |
| 0xFFFF0001 in QREAD (pilot, yolo) | a read **returned the immediately preceding NPU register read's data**: every detectable anomaly (yolo: QREAD slot = preceding STATUS 22×, STATUS slot = preceding QREAD 5×; p10 counter "decreases" = a stale value in the sample before) fits; ≈ 1 % of back-to-back reads on yolo, none on rnnoise; one-shot (the next read is right). 0xFFFF0001 is a normal STATUS (running, IRQ history 0xFFFF). Old image `sample()`: three separate `ldr` in program order, each stored at once, buffer filled by `memcpy` — no software path visible that writes a neighbour's value. NPU region: no MPU set-up in MLEK mps4 → default Device memory. Which component returns the stale data: `UNVERIFIED` (not excluded on the CPU side by the memory type alone) | pilot raw, disassembly of `driver_trace_img` |

## Change to the runner (owner's choice "1: detection + limited re-read", commit of this contract)

- Trace modes 3 (QREAD_CHECKED) and 4 (QREAD_PMU_CHECKED); modes 1–2 unchanged.
- Every register read is preceded by a read of ID (constant 0x20007001 on this board = capabilities `npu_id`). An
  attempt is accepted when the ID read returned ID, the value is not the ID read's data, and the value is plausible:
  QREAD 4-byte aligned, ≥ the job's last accepted QREAD, ≤ QSIZE; QSIZE aligned, > 0; a counter ≥ its last accepted
  value. A rejected slot is re-read **at most twice**. Every attempt (ID read, value read) is stored in read order with
  the attempt count and the accepted flag: the first value, the re-read values, the order and the count are raw data.
- Samples carry `job` (the inference semaphore) — the reserve take's sample is kept, flagged, and outside the window;
  QREAD = 0 after the start is kept. The job's first sample reads QSIZE. Each sample ends with a checksum.
- Store policy 2^12: a sample is kept when QREAD changed (together with the sample right before the change), when it
  has a rejected attempt, or every 4,096 cycles; polling at 2^6 over the whole run (P2's adaptive sampling is not used:
  the full run fits the 128 KiB buffer).
- Record schema 3: `trace_words`, `trace_rejected`, `trace_unaccepted`, `trace_id`.

Image: driver runner of this commit, built by `build_driver_runner.sh` (digests in `image.sha256`, written before the
board step).

## Boots — `plan_p12.txt` (328) and, only after P2 = BOUNDARY_OBSERVED, `plan_p3.txt` (329)

| condition | wait | trace word | sets (`ids.txt`) | used by |
| --- | --- | --- | --- | --- |
| base | WAIT_WFE (MLEK's wait), no trace | off | 1 BASE, 2 A, 3 B | P1 baseline |
| q06 | WAIT_TRACE checked QREAD-only, poll 2^6, store 2^12 | `0x000c0603` | 1, 2, 3 | P1, P2 |
| pbase | WAIT_WFE, no trace | off | 4 (35 48 81 387) | P3 baseline |
| p06 | WAIT_TRACE checked QREAD+PMU, poll 2^6, store 2^12 | `0x000c0604` | 4 | P3 |

Sets: 1 = 35 17, 2 = 35 48 51 53 55 64 80 81, 3 = 35 128 130 132 135 384 386 391 (as the QREAD pilot),
4 = `NPU_ACTIVE` 35, `MAC_ACTIVE` 48, `WD_STALLED` 81, `EXT_RD_TRAN_REQ_STALLED` 387 (owner's list; all in TRM 110).

## Rules (`host/analysis/qread_op_pilot.py`, `host/lib/qread_checked.py`; tests `test_qread_op_pilot`, `test_qread_checked`, `test_driver_runner_sim`, `test_driver_runner_contract`; mutation results below)

Applied to every measured RUN alike; failing RUNs are never dropped to improve a verdict.

| step | rule | outcomes |
| --- | --- | --- |
| RUN | `TRACE_INVALID`: RUN not valid, output ≠ golden, or a trace check fails (checksum, layout, an unaccepted slot, ID ≠ capabilities `npu_id`, QSIZE ≠ stream length, accepted QREAD out of the stream / misaligned / decreasing, counter decreasing, final QREAD ≠ stream end, buffer overflow, counts not adding up); else `TRACE_RECOVERED` if any attempt was rejected and re-read; else `TRACE_VALID` | per RUN |
| P1 | `TRACE_INVALID` if any measured q06 RUN is; else `TRACE_PERTURBED` if in any set \|median NPU_ACTIVE(q06) − median NPU_ACTIVE(base)\| > 1 % of base; else `TRACE_RECOVERED` if any RUN is; else `TRACE_VALID`. Missing data → `UNPROVEN` | P2 runs only on `TRACE_VALID` / `TRACE_RECOVERED` |
| P2 | op k passed when QREAD > o_k (o_99 = 18,980, o_100 = 19,136). Bracket: lo = last job sample with QREAD-before ≤ o_k, hi = first with QREAD-after > o_k; observed when both QREAD reads were accepted at the **first** read (a re-read value never decides a boundary or a stall). Separated when some first-read QREAD r satisfies o_99 < r ≤ o_100 | `BOUNDARY_OBSERVED` if every measured RUN observes both and separates them, else `TRACE_VALID_COARSE`; `NOT_RUN` if P1 failed |
| P3 | only after `BOUNDARY_OBSERVED` (boot 329). p06 RUNs by the RUN rule (counters included); P1's 1 % rule against pbase; P2's boundary rule on p06; resolution kept when each op's median bracket width ≤ 2 × q06's | `PMU_ASSOCIATED` if p06 has no INVALID RUN, is not perturbed, observes and separates both boundaries in every measured RUN and keeps the resolution; else `NOT_ASSOCIATED` with the failing term, PMU values not used; `NOT_RUN` |

Descriptive, labelled `POST_HOC_DESCRIPTIVE` (no verdict): QREAD advance; STATUS of samples with QREAD = 0; commands
completed between consecutive samples; read cost per sample; every rejected attempt with its kind (value = ID read →
"preceding read's data"; ID read ≠ ID → the ID read took the preceding read's data; else implausible value); medians of
every event in q06 vs base (traffic); bracket widths, QREAD stalls around the two boundaries; in P3, Δt and Δcounters
of consecutive sample intervals from op 99's lo to op 100's hi (first-read values only), and the read-time uncertainty
(counters are read between the two QREAD reads of a sample).

**Hardware read vs recording.** A rejected attempt is found by the CPU right after the load, before the buffer; a
checksum-valid sample holding it means the load itself returned that value (read path: CPU bus interface, interconnect
or NPU register slave — which one stays `UNVERIFIED`). A checksum failure, a layout error, or an implausible stored
value the firmware did not flag would be the recording or transfer path. The new image's `read_slot` disassembly is
checked before the board step (one load per register, program order).

## Stop conditions

- A boot failing before its RUNs, or P0 assumptions contradicted on the board (ID ≠ 0x20007001, QSIZE ≠ 21,056): stop,
  keep the data, report.
- P1 not `TRACE_VALID`/`TRACE_RECOVERED` → no P2, no boot 329. P2 not `BOUNDARY_OBSERVED` → no boot 329, and per the
  owner the QREAD experiment ends. No other model, no new method, no further repeats are started automatically.

## Cost (from boots 325–326)

| item | time |
| --- | --- |
| deploy / restore / postflight (one owner sudo session per boot) | ≈ 5 min each |
| boot 328: upload 455 KB + 30 RUNs (15 traced, ≲ 10 k words each) | ≈ 8 min |
| boot 329 (conditional): 10 RUNs (5 traced) | ≈ 5 min |

Disk: < 10 MB staging, < 15 MB raw.

## Mutation test

`evidence/qread_op_pilot/mutate_op_pilot.py` (35 mutations of the firmware checks in `trace.c`/`hooks.c`, the host
checks in `qread_checked.py` and the rules in `qread_op_pilot.py`; suite = `test_qread_checked`, `test_qread_op_pilot`,
`test_driver_runner_sim`, `test_driver_runner_contract`; restore by sha256). First pass 31/35 RED; the 4 survivors
(ID-read check, the stored sample before a QREAD change, the in-sample QREAD bound, P2's separation term) got fixtures
(simulator `SIM_STALE_AT` on an ID read, a one-poll gap bound, `SIM_QREAD_DIP`, a non-separated synthetic RUN), not
deletions; rerun of the four: 4/4 RED → **35/35 RED**, files restored by digest, suite green after.
