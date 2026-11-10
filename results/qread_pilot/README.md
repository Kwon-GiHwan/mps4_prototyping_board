# QREAD pilot on the driver runner — rnnoise, yolo (boots 325–326, 2026-11-10 UTC board clock)

Contract `evidence/qread_pilot/contract.md` (frozen `67eb2e5` with amendment 1, before boot 325). **TA: MLEK's own
sys_dram_mid set-up = TA profile 1.** Driver runner of commit `c1b9b79` (boot `cfb36fb0`, bram `39959e8a`, ddr 16-B zero,
images.txt `af688281`), MLEK-input DRWLs (= the m7 bytes), original command stream; no STOP, KERNEL_WAIT or mid-stream
IRQ. One boot per model, six conditions in it (`conditions.txt`), 5 RUNs per condition and set (1 warm-up + 4 measured).
Both boots: 40/40 RUNs valid, OFM = MLEK golden in every RUN (WFE, busy and every trace condition). One owner sudo
session; board restored to m6 (`RESTORE VERIFIED`), postflight done, card withdrawn. Raw: `evidence/qread_pilot/raw/`.

## Contract verdicts

| | rnnoise_INT8 | yolo-fastest_192_face_v4 |
| --- | --- | --- |
| P0 D2–D6 (vs the m7 image, same input) | EXEC_OK, WINDOW_OK, STABLE, REPRODUCES (NPU_ACTIVE −0.75 %), PMU_INERT | EXEC_OK, WINDOW_OK, STABLE, REPRODUCES (−0.27 %), PMU_INERT |
| P0 D1 | **UNPROVEN** (the conditions layout writes `capabilities.json` one level above the condition folder; the rule found none) | **UNPROVEN** (same) |
| P1 busy vs WFE | UNRESOLVED (+0.46 %, tolerance 4.6 %) | UNRESOLVED (−0.17 %, tolerance 1.0 %) |
| P2 t06 / t10 / t14 | **TRACE_INVALID** ×3 (perturbation UNRESOLVED in all) | **TRACE_INVALID** ×3 (perturbation UNRESOLVED) |
| P3 p10 | **TRACE_INVALID**; EVENTS_AT_END | **TRACE_INVALID**; EVENTS_AT_END |

`python3 host/analysis/driver_p3.py <link root wfe/<model> → conds/<model>/wfe> evidence/driver_m7/raw/wfe results/qread_pilot/p0 1`;
`python3 host/analysis/qread_pilot.py evidence/qread_pilot/raw/conds/<model> evidence/qread_pilot/workloads/<model>.drwl.cms.bin results/qread_pilot/<model>`.

Why every trace RUN is `TRACE_INVALID` (integrity, `results/qread_pilot/<model>/<cond>/summary.json`):
1. **The first sample of every traced RUN (40/40) still reads the previous RUN's stream end** (QREAD = stream length:
   rnnoise 7,296, yolo 21,056), the next sample reads 0 → `qread_decreasing`. The wait starts after the driver started
   the NPU, so QREAD is not yet reset when the job's first poll reads it (`BOARD_MEASURED`; why: `UNVERIFIED`).
2. **yolo, fast polling: QREAD reads 0xFFFF0001** (outside the stream, STATUS-like) in the second QREAD read of some
   samples — 9 of 10 t06/t10 RUNs (warm-up included; 7 of 8 measured); with PMU reads, counters read lower than the
   sample before in 2 of 4 measured p10 RUNs. A register read during execution is not always a valid value
   (`BOARD_MEASURED`; cause `UNVERIFIED`). Not seen on rnnoise.

Also measured: the record's `qsize` now equals the stream length (the `afceaa8` offset fix holds on the board); D1 with
the same boot's capabilities file gives `PLATFORM_AS_MLEK`, `E2_SAME` (labelled apart: `p0_with_boot_capabilities/`).

## POST_HOC_DESCRIPTIVE — the owner's five questions (`describe.py` → `describe.json`; not verdicts)

View `usable`: a RUN is used only if, after dropping that stale first sample, every integrity check passes; RUNs with
other problems are counted, never repaired. Usable measured RUNs: rnnoise 4/4 in every condition; yolo t06 0/4, t10 1/4,
t14 4/4, p10 2/4. Medians over the usable RUNs; cycles are CPU cycles (DWT).

| model / condition | kernels | samples kept | distinct QREAD | resolved ratio | kernels first seen together (max) | completion-bracket width median (max) | sample gap | read cost | polls / loop passes |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| rnnoise t06 (2^6) | 48 | 47 | 43 | 0.385 | 3 | 341 (3,764) | 473 | 95 | 284 / 283 |
| rnnoise t10 (2^10) | 48 | 29 | 26 | 0.198 | 5.5 | 1,422 (4,336) | 1,063 | 95 | 49 / 2,081 |
| rnnoise t14 (2^14) | 48 | 5 | 5 | 0.021 | 16 | 16,516 (16,518) | 16,414 | 95 | 5 / 2,451 |
| rnnoise p10 (2^10 + 8 events) | 48 | 28 | 25 | 0.198 | 5 | 1,403 (4,584) | 1,062 | 342 | 49 / 1,482 |
| yolo t10 (1 RUN) | 112 | 170 | 93 | 0.634 | 4 | 2,206 (4,334) | 4,214 | 95 | 527 / 23,206 |
| yolo t14 | 112 | 35 | 33 | 0.071 | 9.5 | 16,519 (16,548) | 16,424 | 95 | 35 / 27,349 |
| yolo p10 (2 RUNs) | 112 | 171 | 95 | 0.656 | 3.5 | 2,194 (4,623) | 4,209 | 345 | 525 / 16,309 |

1. **Kernel boundaries.** Even at the fastest interval the completion of most kernel commands is not seen alone:
   rnnoise 38.5 % at 2^6 (a sample every ~470 cycles, cost 95 per read — polling cannot go much faster), 20 % at 2^10,
   2 % at 2^14; yolo 63–66 % at 2^10 (longer kernels), 7 % at 2^14. QREAD stops mostly **right after** a kernel
   instruction (yolo 89–91 of ~92 stop positions, rnnoise 11–21 of 24–41) and sometimes on it — so the stop position
   itself does not tell "kernel k complete" from "parser waiting after issuing k" (the TRM's two descriptions;
   `UNVERIFIED`).
2. **Misses, time uncertainty, overhead.** Up to 3 (2^6), 5–6 (2^10) and 10–16 (2^14) kernels become visible in one
   sample. A completion is located only within a bracket of ~340 (2^6), ~1.4–2.2 k (2^10), ~16.5 k (2^14) CPU cycles,
   up to ~4.6 k at 2^10 — for rnnoise's ~50 k-cycle run that is 0.7–33 %. Overhead: no change of NPU_ACTIVE or
   NPU_EXECUTION detected against busy or WFE beyond the spread (all `UNRESOLVED`; tolerance 4.6 % on rnnoise, 1 % on
   yolo); a QREAD-only read costs 95 cycles, with 8 PMU counters ~345.
3. **PMU vs completion progress.** 46 % (rnnoise) and 58 % (yolo) of the MAC_ACTIVE counted between samples falls in
   intervals in which QREAD did not move: MAC work happens while no command completes, i.e. it belongs to kernels
   already issued and not yet passed — which one is not observable. The last sample's counters equal the IRQ read
   (`EVENTS_AT_END`): the counters stop with the NPU.
4. **Per-operator time and event attribution: not possible from these traces.** No start time exists in QREAD; the
   completion of most kernels is bracketed together with neighbours; the stop position is ambiguous between completion
   and issue; about half of the MAC activity occurs while QREAD stands still (overlapping kernels, at most two
   outstanding); on yolo the register reads are not reliable at fast polling.
5. **Why QREAD alone is not enough, and what would be needed** (not done, each needs its own approval): (a) a hardware
   event per command boundary — `NPU_OP_IRQ`/mid-stream completion marks, or PMU counters started/stopped by command
   events (PMCCNTR_CFG start/stop, untested), to get a time *at* a boundary instead of a polled bracket; (b) a way to
   tell completion from issue — e.g. KERNEL_WAIT barriers or STOP prefixes, which serialize execution and so measure
   isolated cost, not in-pipeline timing; (c) an explanation of the 0xFFFF0001 reads (register access while the NPU
   runs) before any fast polling is trusted.

## Judgement on the current method

On the original command stream, QREAD polling on the driver runner gives a **completion-progress timeline with
brackets of hundreds to thousands of cycles and grouped kernels; it does not give per-operator start/end times or
per-operator PMU attribution** (`NOT_IDENTIFIABLE` for exact attribution; at most coarse progress). The contract's
trace verdicts are all `TRACE_INVALID` (stale first sample; invalid register reads on yolo) and stand as judged. Per the
owner: no correction, no repeat extension, no wav2letter, no new method was started.
