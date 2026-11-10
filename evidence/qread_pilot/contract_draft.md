# QREAD pilot on the driver runner — DRAFT (2026-11-10, not approved, no board run)

Owner decision 2026-11-10 (item 4): integrate the 2B-4 QREAD analysis into the driver runner; static checks and
off-board tests first, then a minimal pilot for QREAD resolution and measurement disturbance; report the contract and
cost before any board step. Design: `docs/plan/driver_profiling_design.md` §4 (P0–P3 here; P4 PMCCNTR_CFG, P5 PMU Mask
variant and anything that changes the command stream are not in this pilot). **TA: MLEK's own sys_dram_mid set-up =
TA profile 1.** Profile `config/driver_r5.json`: 5 RUNs per condition and set, 1 warm-up. This file becomes the frozen
contract only after the owner's approval, unchanged or as amended then; numbers below are fixed now, before data.

## Question

On the original command stream, with the official driver: (P0) does the trace-capable image measure like the m7 image;
(P1) does the CPU's busy wait (the trace loop's kind of wait) change the NPU's run against the driver's WFE wait; (P2) at
which poll interval does QREAD sampling show the completion of individual kernel commands, and does sampling disturb the
run; (P3) can PMU counters be read alongside, consistently. **Not asked and not claimed: operator start or end times,
attribution of PMU counts to operators.** A `TRACE_VALID` timeline bounds when completion became visible, nothing more.

## Image and workloads

Driver runner of commit `c1b9b79` (trace in WAIT_TRACE; `qsize` = QSIZE fixed): boot `cfb36fb0…`, bram `39959e8a…`,
ddr 16-B zero `374708ff…`, images.txt `af688281…`; built by `build_driver_runner.sh`, GATE OK, 0 warnings from runner
sources, trace buffer 128 KiB in BRAM (0x120a18e0), `ethosu_semaphore_take` calls `trace_wait`. Workloads: the m7 DRWLs
(MLEK input, `evidence/driver_m7/workloads_check.txt`) and their command streams (`*.drwl.cms.bin`, sha256 =
`cms_sha256` of the DRWL meta).

## Boots (`plan.txt`) — one boot per model, every condition inside it (`conditions.txt`, `ids.txt`)

| boot | model | why | command stream |
| --- | --- | --- | --- |
| 325 | rnnoise_INT8 | shortest run (≈ 50 k cycles); 2B-3 `WINDOW_LOCALIZED(+2)` | 7,296 B |
| 326 | yolo-fastest_192_face_v4 | many ops, mixed MAC/AO; 2B-3 `WINDOW_AMBIGUOUS` | 21,056 B |
| 327 | wav2letter_pruned_int8 | longest run (≈ 4.1 M cycles): buffer and resolution at length | 5,632 B |

| condition | wait | trace word | sets | used by |
| --- | --- | --- | --- | --- |
| wfe | WAIT_WFE (MLEK's wait) | off | BASE, A, B | P0, P1 reference |
| busy | WAIT_BUSY | off | BASE | P1, P2 reference |
| t06 / t10 / t14 | WAIT_TRACE | QREAD_ONLY, poll 2^6 / 2^10 / 2^14 cycles, store on QREAD change or every 2^12 cycles | BASE | P2 |
| p10 | WAIT_TRACE | QREAD_PMU, poll 2^10, same store policy | A | P3 (and P2) |

Store policy: a sample is kept when QREAD changed since the last kept sample, else at most every 4,096 cycles, so the
128 KiB buffer bounds the trace by the number of commands, not the run length (yolo ≤ 5,264 QREAD values × 5 words).
A full buffer is recorded (`buffer_overflow`) and makes that RUN `TRACE_INVALID`.

## Rules (`host/analysis/qread_pilot.py`, `host/analysis/driver_p3.py` with warm-up 1; tests; mutations RED: pilot and conditions 12, trace firmware and host 15)

| step | rule | outcomes |
| --- | --- | --- |
| P0 | `driver_p3.py <link root> <m7 raw/wfe> <out> 1`, link root `wfe/<model>` → `conds/<model>/wfe`: D1–D4, D6 as before; D5 against the m7 image's same-input data (MAC_ACTIVE and beats equal, NPU_ACTIVE within the m7 RUN-width tolerance) | D-rule values; D5 `REPRODUCES_LEGACY` here means "reproduces m7" |
| P1 | busy vs wfe, NPU_ACTIVE and NPU_EXECUTION medians: \|diff\| > max(1 % of wfe, either RUN range) | `EFFECTIVE` / `UNRESOLVED` (inside the spread: no difference claimed) |
| P2 | each trace condition: the P1 rule against busy → `EFFECTIVE` = perturbed; every measured RUN through `qread_timeline` (integrity; resolved ratio = share of kernel commands whose completion is first seen alone, bounded on both sides); condition verdict = worst RUN | `TRACE_INVALID` > `TRACE_PERTURBED` > `TRACE_UNOBSERVABLE` (ratio < 0.10) > `TRACE_COARSE` (< 0.90) > `TRACE_VALID` |
| P3 | p10: the P2 verdict; last sample's counters = the IRQ read in every measured RUN | `EVENTS_AT_END` / `EVENTS_MOVED_AFTER_IRQ` / `UNPROVEN` |

Thresholds 0.10 / 0.90 are the 2B-4 plan's (`feat/stage2b4-qread` §8). Missing data → `UNPROVEN`. Descriptive (not
judged): read cost per sample, polls per hook call, distinct QREAD values, per-kernel completion brackets, ΔPMU
between samples during QREAD stalls — reported as observations, never as per-operator values.

## Stop conditions and what follows

- A boot that fails or a P0 D-rule that is not as in m7: stop after that boot, keep its data, report; no rule change.
- If t06 is `TRACE_PERTURBED` on a model, the faster interval is not pursued there. If t10 is not better than t14 in
  resolved ratio, no faster interval is proposed (2B-4 plan §5).
- Next steps (each its own contract and approval): all seven models with the chosen interval; P4 PMCCNTR_CFG; P5 Mask
  variant on the same image; methods that change the stream (STOP prefix, KERNEL_WAIT, mid-stream IRQ) — not before
  separate approval.

## Cost (estimate from boots 308–316)

| item | time |
| --- | --- |
| deploy / restore / postflight (one owner sudo session) | ≈ 5 min |
| rnnoise boot: reboot + upload 127 KB + 45 RUNs + trace download | ≈ 3 min |
| yolo boot: upload 455 KB (≈ 1 min) + RUNs + traces (≤ 26 k words each) | ≈ 8 min |
| wav2letter boot: upload 14.5 MB (≈ 33 min) + RUNs + traces | ≈ 40 min |
| **total, three models** | **≈ 55 min**; without wav2letter ≈ 16 min |

Disk: about 15 MB of staging and < 20 MB of raw output (2.9 GB free).
