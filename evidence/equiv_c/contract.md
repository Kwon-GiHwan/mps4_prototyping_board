# Equivalence C — runner vs MLEK on the same input (frozen 2026-11-09, before any MLEK run of this experiment)

Plan: `docs/plan/equivalence_plan.md` §8 (criteria R/M) and §9 (execution). Owner 2026-11-09 approved the following:
- C1·C2: the four models with no MLEK reference, plus kws and ad on the same input.
- The MLEK instrumented build (C-c), keeping the original MLEK run.

**TA profile 1 on both sides** (runner knob word 27 = 1; MLEK `ta_config_u85_sys_dram_mid`, its UART must show
"Configured TA_SRAM/TA_EXT"). FI101 Ethos-U85 1024 MAC. MLEK `b2c0bb2`, Vela 5.0.0 with the packer's options.

## Same input, same Vela output

- **Input:** MLEK's own input (`std::rand`, default seed), dumped by the VERIFY build (C-a). Seed-1 inputs cannot be fed to MLEK without moving the model (`evidence/mobilenet_ofm/REPORT.md`).
- **Runner blobs:** repacked with that IFM and MLEK's OFM as golden (`pack_vela_workload.py --profile config/fi101_s013.json --ifm --golden`). Several tensors are split by the graph order and stored in the Vela op order.
- **Acceptance:** a golden is accepted only through `host/analysis/mlek_golden.py` G1–G5 (G2: MLEK's Vela output = the blob's). Its hashes go into `evidence/equiv_c/manifest.json` before the runner boot.
- **Assumption, stated rather than tested:** the stock and instrumented builds see the same input as the VERIFY build (same source, same seed). Only the VERIFY build's input is hashed.

## Steps (one MLEK image deployed at a time with `deploy_mlek.sh`, undone with `restore_mlek.sh`)

| step | build (`host/container/build_mlek_equiv.sh`) | models | boots per model |
| --- | --- | --- | --- |
| C-a | `verify` | vww4, rnnoise, yolo, wav2letter, kws, ad | 1 (capture IFM/OFM dump) |
| C-b | `stock` | vww4, rnnoise, yolo, wav2letter (kws, ad, mobilenet: stage-B B1–B3 reused) | 3 (one deploy, 3 reboots) |
| C-c | `events` | all seven | 3 |
| C-d | runner `d0cd4775`, MLEK-golden blobs, `ids.txt` sets A and B, 10 RUNs (2 warm-up) | kws, ad, vww4, rnnoise, yolo, wav2letter (mobilenet: blob `0d51cf9e` = MLEK input already) | 1 |

- Every MLEK capture opens the app UART before REBOOT (`mlek_app_capture.py`). Its counters come from `host/analysis/mlek_counters.py`.
- A capture without exactly one profile block, or without the TA lines, is invalid. It is re-run once (amendment).
- MLEK images, Vela outputs and digests are kept under `evidence/equiv_c/mlek/<model>/<build>/`.

## Rules (`host/analysis/equiv_c.py`, tests `host/tests/test_equiv_c.py`; 13 mutations RED (three redundant guards removed, a fixture added))

| item | EQUIVALENT | NOT_EQUIVALENT | UNPROVEN |
| --- | --- | --- | --- |
| M1 output | every measured runner RUN valid, OFM mismatch 0 against the accepted MLEK golden | a mismatch | no golden, no RUN, or an invalid RUN |
| M2 each beat (SRAM rd/wr, EXT rd/wr) | every stock boot and every runner RUN show one and the same value | anything else | a side missing |
| M3 NPU_ACTIVE | \|runner median − MLEK median\| ≤ max(MLEK boot range, runner measured-RUN range) | outside | a side missing |
| M4 MAC_ACTIVE, MAC_DPU_ACTIVE, AO_ACTIVE | the M3 rule against the instrumented build | outside | the instrumented build missing, or it disturbs the stock counters on this input (beats not equal to stock, or ACTIVE outside the M3 rule against stock) |

- R (runner validity) for C-d: the same rules as every runner campaign (model mode including `knobs_honoured`, seam once per RUN, no overflow).
- A runner RUN that is not valid is not used for M1–M4.
- Results are reported per (model, metric) side by side. No metric is assumed equal from another one or from another input.

## What the outcomes mean, and limits

- **EQUIVALENT** means: on this input, these counters and this output equal MLEK's within the rule. It does not extend to other inputs or to metrics not listed.
- **NOT_EQUIVALENT** is recorded with its size. Its cause is separated (plan §8.2); no result is discarded.
- **IDLE and TOTAL are not compared** (different PMU windows, E4). MLEK's printed `NPU TOTAL` is reported only.
- **What the instrumented build checks:** that it leaves the five stock counters unchanged. It does not check whether counting MAC_ACTIVE affects anything the stock build cannot see.
