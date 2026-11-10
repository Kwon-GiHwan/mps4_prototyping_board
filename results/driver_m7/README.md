# Driver runner m7 — all seven models on MLEK's input (boots 308–316, 2026-11-10 UTC board clock)

Contract `evidence/driver_m7/contract.md` (frozen `26c59b0`, image digests `10d2ee2`, both before boot 308). **TA: MLEK's own
sys_dram_mid set-up = TA profile 1**, read back in every boot's capabilities. FI101 Ethos-U85 1024 MAC. Image: driver
runner of commit `65cf963` — boot `82ab2439` / bram `967c65e5` / ddr 16-B zero `374708ff` / images.txt `af688281`, gate OK.
MLEK-input DRWLs (`evidence/driver_m7/workloads_check.txt`), sets BASE + A–G, 10 RUNs (2 warm-up), WFE. Run in one owner
sudo session (`evidence/driver_m7/session.txt`, `board/sudo_session.sh`). Every boot: 80/80 RUNs valid, OFM mismatch 0.

Commands (scratch roots = symlinks, as listed in the contract):
`driver_p3.py evidence/driver_m7/raw <legacy MLEK-input root> results/driver_m7/d_rules`,
`equiv_c.py <raw_bc seven model folders> evidence/driver_m7/raw/wfe results/driver_m7/m_rules`,
`driver_reval.py <main>/evidence/fi101_s013/raw <legacy root> evidence/driver_m7/raw/wfe evidence/driver_p3/raw/wfe <main>/results results/driver_m7/reval`.

## D1–D6 (driver runner itself; the kws/ad first-validation rules unchanged)

| model | D1 platform | D2 exec | D3 window | D4 repeat | D5 legacy, same input (NPU_ACTIVE) | D6 PMU load |
| --- | --- | --- | --- | --- | --- | --- |
| kws_micronet_m | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (+0.36 %) | PMU_INERT |
| ad_medium_int8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (+0.15 %) | PMU_INERT |
| mobilenet_v2_1.0_224_INT8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (+0.05 %) | PMU_INERT |
| vww4_128_128_INT8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (−0.59 %) | PMU_INERT |
| rnnoise_INT8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (−0.43 %) | PMU_INERT |
| yolo-fastest_192_face_v4 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (−0.13 %) | PMU_INERT |
| wav2letter_pruned_int8 | PLATFORM_AS_MLEK | EXEC_OK | WINDOW_OK | STABLE | REPRODUCES_LEGACY (+0.04 %) | PMU_INERT |

TA_EXT MAXR reads 0 (E2_SAME) on all seven. D5 = MAC_ACTIVE and four beats identical to the legacy runner on the same
(MLEK) input in every RUN; NPU_ACTIVE within the legacy RUN-width tolerance.

## M1–M4 (driver vs MLEK, the equivalence-C rules unchanged)

All seven: M1 output, M2 four beats, M3 NPU_ACTIVE **EQUIVALENT**. M4 MAC_ACTIVE / MAC_DPU_ACTIVE / AO_ACTIVE
**EQUIVALENT** on six; wav2letter **UNPROVEN** (the instrumented MLEK build is not shown inert on this input — the same
reason as in equivalence C; `evidence/var_w2l_vww4/` W tests it).

## P1 window (preregistered descriptive, `descriptive.txt`)

| model | NPU_ACTIVE median (64 RUNs) | MLEK stock median | driver − MLEK | NPU_EXECUTION − NPU_ACTIVE (median [range]) | legacy PMCCNTR window ÷ ACTIVE |
| --- | ---: | ---: | ---: | --- | ---: |
| kws | 91,262 | 91,431 | −0.19 % | 534 [534–573] | 28.9× |
| ad | 146,040 | 145,976 | +0.04 % | 534 [534–534] | 55.1× |
| mobilenet | 1,449,070 | 1,448,049 | +0.07 % | 542 [535–542] | 44.8× |
| vww4 | 234,489 | 233,394 | +0.47 % | 534 [534–541] | 27.8× |
| rnnoise | 50,436 | 50,603 | −0.33 % | 666 [666–666] | 43.1× |
| yolo | 447,982 | 446,355 | +0.36 % | 585 [574–586] | 18.2× |
| wav2letter | 4,132,806 | 4,133,890 | −0.03 % | 534 [534–573] | 60.6× |

The driver runner's window (PMU armed right before the NPU starts, read at the completion IRQ) exceeds NPU_ACTIVE by a
model-independent 534–666 cycles, constant RUN to RUN; the legacy PMCCNTR window holds CPU staging (18–61× ACTIVE). The
driver's power reference count is 2 during every RUN (`BOARD_MEASURED`: MLEK keeps power requested; no per-job soft
reset). The first-validation image (`964ced9c`, boots 298–299) gave +526; this image +534 (one image change between).

## Phase 7 — Stage 1 / 2A / 3 re-evaluation (`reval/reval.csv`, counts in `reval/summary.json`)

| stage | REVALIDATED | RETAINED | CONDITION_SPECIFIC | REMEASURE_REQUIRED | INVALID |
| --- | ---: | ---: | ---: | ---: | ---: |
| Stage 1 (16 metrics × 7) | 76 | 14 (n_mac, Vela) | 15 | 0 | 7 |
| Stage 2A (15 × 7) | 56 | 43 | 1 | 5 | 0 |
| Stage 3 traffic (30 × 7) | 63 | 93 | 13 | 41 | 0 |
| Stage 3 unit stalls (10 × 7) | 22 | 43 | 0 | 5 | 0 |
| Stage 3 channel shares (7) | — | 7 | — | — | — |

- **INVALID**: Stage 1 `runner_window` (the legacy PMCCNTR window with CPU staging) — it was never reported as a model
  time, now formally invalid as one.
- **CONDITION_SPECIFIC, window**: Stage 1 `infer_cycles` and `active_over_infer` (the legacy seam window, ACTIVE + ~2.4 k;
  the driver's window is ACTIVE + 534–666). Both windows are valid for their own runner; neither is MLEK's TOTAL.
- **REVALIDATED (all seven)**: NPU_ACTIVE, MAC / DPU / AO / WD active and WD stalled ratios, MAC efficiencies,
  ACTIVE/Vela, total SRAM and EXT bytes, bytes per MAC, bandwidth per cycle, SRAM read burst — every Stage 1 measured
  number except vww4 `wd_active_ratio` (path, below).
- **CONDITION_SPECIFIC, execution path** (same input): EXT read burst (beats ÷ transactions) on six (rnnoise equal); per-port EXT
  bytes, EXT port imbalance and SRAM write-beat stall on mobilenet; vww4 WD active. **The EXT port split moves while
  the EXT total is exact** (mobilenet: ext0+ext1 identical, each port ±528 B). `INFERRED` cause: the legacy runner places
  the model and arena at other DDR addresses (const from 0x70100000) than MLEK/driver (model at 0x70000000), and EXT
  traffic is spread over the two ports by address — not board-verified.
- **REMEASURE_REQUIRED** (cross-input, input and path not separable): per-port EXT bytes / imbalance and some rare EXT
  stalls / limits on the six seed-1 models, ad `sram_rd_req_stall`, a few unit stalls (vww4 AO by BS/OB, wav2letter/yolo
  AO by OB, yolo blockdep, ad MAC by ACC). Given the mobilenet same-input result, the port split is expected to be
  placement-dependent; a same-input driver measurement is needed before using these for MLEK-path claims.
- **RETAINED**: compile-time numbers, Stage 3 channel shares (unfiltered beats revalidated), and set C–G metrics that agree
  across input and path.
- Stage 2B group H1/H2: stay INVALID (owner decision); not re-opened.

## What this does not show

MLEK's input only; one boot per model (vww4 three: `evidence/var_w2l_vww4/`); the counters listed. Not a per-operator
result. The `qsize` record field holds PROT (offset 0x24) on this image — diagnostic only, fixed in `afceaa8` for the next
image.
