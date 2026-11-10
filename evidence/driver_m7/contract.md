# Driver runner m7 — all seven models on MLEK's input (frozen 2026-11-10, before boot 308)

Owner request 2026-11-10 (item 1): the five remaining models with the kws/ad rules, then all seven verified; outputs,
NPU_ACTIVE, MAC/DPU/AO activity and SRAM/EXT traffic. Directive `docs/plan/driver_runner_directive.md` Phases 3–4 and 7.
**TA: MLEK's own `ta_config_u85_sys_dram_mid` = TA profile 1** (programmed by the MLEK platform at boot, read back in the
capabilities). FI101 Ethos-U85 1024 MAC. Approval: the owner's request of 2026-11-10 (board image replacement for this
run); sudo only through `board/sudo_session.sh`, typed by the owner.

## Judgement made here (also in the final report)

- **Input = MLEK's own (equivalence C-a dump) for all seven, kws and ad included**, not the seed-1 input of the first
  validation (`evidence/driver_p3/`). Reasons: amendment 2 makes the MLEK FI101 OFM on MLEK's input the golden for every
  run after Stage 1, and only vww4/yolo/wav2letter's seed-1 OFMs have no accepted golden (`UNRESOLVED (x1)`), so D2 could
  not be judged on seed-1 for them; on MLEK's input the same boots also give the driver↔MLEK comparison (Phase 4). The
  D1–D6 rules are unchanged; D5's legacy reference is the legacy runner on the same (MLEK) input.

## Image

Driver runner of commit `65cf963` (the DRWL IO limit per side, so rnnoise's 4 inputs + 5 outputs load; the run-time path
is unchanged from the first-validation image `964ced9c`), built by `host/container/build_driver_runner.sh` (gate PASS
required). Its digests are written to `image.sha256` here before boot 308; the card gets the 16-byte zero `ddr.bin` as in
the first validation (J11). Deployed with `deploy_mlek.sh`, undone with `restore_mlek.sh`.

## Workloads

DRWL, `pack_vela_workload.py --profile config/fi101_s013.json --format drwl --ifm <MLEK ifm> --golden <MLEK OFM>`
(`workloads/*.drwl.json`). `workloads_check.txt`: for every model the Vela output equals the manifest's `vela_sha256`
and the IFMs / goldens, in the Vela op order, equal `golden.input_sha256` / `golden.ofm_sha256` of
`evidence/equiv_c/manifest.json` (branch `refactor/firmware-modules` `4e8a7b5`; mobilenet: its amendment-1 entry). Note:
the manifest's per-tensor `ifms`/`ofms` lists for rnnoise and yolo are carried over from their x1 (seed-1) entries and do
not describe the MLEK input; the `golden` digests do.

## Boots

`plan.txt`: 308 kws, 309 ad, 310 vww4, 311 rnnoise, 312 yolo, 313 mobilenet, 314 wav2letter (root `raw/`);
`plan_r2.txt` 315 vww4 (root `raw_r2/`), `plan_r3.txt` 316 vww4 (root `raw_r3/`) for `evidence/var_w2l_vww4/`.
Sets `ids.txt`: 1 BASE (35 17), 2 A, 3 B (as the first validation), then 4–8 = passes C–G (`config/fi101_passes.txt`),
10 RUNs per set, 2 warm-up, WFE. A boot that fails is recorded, not repeated under changed rules.

## Rules

**D1–D6** — `host/analysis/driver_p3.py` unchanged (`evidence/driver_p3/contract.md`), on `raw/wfe/`. D6 uses sets 1–3
only, as before. D5 legacy reference (same MLEK input, legacy image `d0cd4775` unless stated): kws, ad, yolo,
wav2letter `evidence/equiv_c/raw_cd/cd/`; vww4, rnnoise `evidence/equiv_c/raw_cd_a1/cd/`; mobilenet
`evidence/fi101_s013/raw/ctl/` (boot 99, image `2bb04bfa`, MLEK input — equivalence C amendment 2).

**M1–M4 (driver vs MLEK)** — `host/analysis/equiv_c.py` unchanged, MLEK root = the seven model folders of
`evidence/equiv_c/raw_bc/` (stock B1–B3, instrumented B1–B3; kws/ad/mobilenet stock = stage-B reference), runner root =
`raw/wfe/`. Same meaning as in equivalence C; wav2letter M4 stays UNPROVEN by its rule if the instrumented build is not
shown inert (that is `evidence/var_w2l_vww4/` W).

**R (Phase 7, Stage 1 / 2A / 3 re-evaluation)** — `host/analysis/driver_reval.py`, tests `test_driver_reval.py`
(11 mutations RED). Stage value = the published table (`results/fi101_stage1`, `fi101_stage2a`, `fi101_stage3`); its
recomputation from `evidence/fi101_s013/raw` with the same functions matches all 392 published values exactly.

| rule | content |
| --- | --- |
| R1 class | STATIC (n_mac, Vela) → RETAINED; POLLUTED (`runner_window`: CPU staging inside) → INVALID; WINDOW (`infer_cycles`, `active_over_infer`: the legacy seam window) → CONDITION_SPECIFIC |
| R2 rule | DET metrics (fixed by the command stream) must be equal; a declared DET metric that moves RUN to RUN in the stage data is judged as JITTER. JITTER: within max(1 % of the stage value, the stage's RUN range, the driver's RUN range). Verdict strings (COUNTED_ZERO, …) must be equal; missing data is never a difference |
| R3 same input | mobilenet (driver m7) and kws/ad metrics whose events are in driver_p3's sets (seed-1): driver = stage → REVALIDATED, else CONDITION_SPECIFIC (execution path) |
| R4 bridged | other models, metrics whose events are all in sets A/B: path = driver m7 vs legacy C-d (both MLEK input); input = legacy seed-1 (stage) vs legacy C-d. path differs → CONDITION_SPECIFIC (path); path agrees and input agrees → REVALIDATED; path agrees, input differs → CONDITION_SPECIFIC (input) |
| R5 cross-input | metrics with events outside A/B on seed-1 models: driver m7 vs stage directly; agree → RETAINED (input and path not separable), differ → REMEASURE_REQUIRED |

Stage 2A rows follow the same metric of Stage 1 / unit stalls (identical values). Stage 3 channel shares (PMCAXI_CHAN,
not a driver-runner condition): RETAINED if that model's `sram_bytes` and `ext_bytes` are REVALIDATED, else
REMEASURE_REQUIRED. Stage 2B group H1/H2 verdicts stay INVALID (owner, 2026-11-09); nothing here re-opens them.

**Descriptive (preregistered, not judged)**: NPU_EXECUTION − NPU_ACTIVE per model (P1 window), HOST_END_TO_END,
driver vs legacy-window ratio, D4 per event set, the power reference count.

## What the outcomes mean and do not mean

- D1–D6 and M1–M3 hold on MLEK's input, these sets and this image only. M4 (and R for C–G events on seed-1 models) has the
  limits stated in its rule.
- R verdicts classify the published numbers; nothing is deleted or rewritten. REMEASURE_REQUIRED means "a same-input
  driver measurement is needed before the number is used for MLEK-path claims", not "wrong".
- Missing data → UNPROVEN. A failed boot keeps its raw data and log.
