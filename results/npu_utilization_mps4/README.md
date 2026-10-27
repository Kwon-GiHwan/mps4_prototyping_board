# NPU utilization on the board (MPS4 FI101, Ethos-U85 1024 MAC) — all seven MLEK models

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.** Runner measurements, not stock
MLEK. Two measurement sets, stated per row (`dataset`, `status`, `measured_runs`):

| dataset | models | boots | image | RUNs (warm-up) | correctness | source |
| --- | --- | --- | --- | --- | --- | --- |
| `s1` (Stage 1) | kws, ad, mobilenet | 65–67 | APP `2c2fa435` | 35 (5) | byte-exact vs golden (gate `BASELINE_PASS`) | `evidence/stage1/raw/s1/` |
| `x1` (exploratory) | vww4, rnnoise, yolo-fastest, wav2letter | 84–86, 93 | APP `38ce118c` (restructured runner) | 10 (2), profile `mlek_r10` | see `status` | `evidence/x1_mlek_models/raw_a2/`, `raw_a4/` |

The two images are shown equivalent for these counters by the x1 controls (boots 80–82): kws, ad and mobilenet run on
`38ce118c` reproduce Stage 1's `mac_active` and beat counters exactly, with `npu_active` medians inside Stage 1's
ranges (`evidence/x1_mlek_models/analysis_a2/`).

## Status per model

| model | status | why |
| --- | --- | --- |
| kws, ad, mobilenet | `VALID (s1)` | Stage 1 gate passed |
| rnnoise | `VALID (x1)` | gate passed; the multi-OFM comparison is shown on the board by the negative control (boot 88: 1 mismatch, 5, at 169 in every RUN) |
| vww4 | `UNRESOLVED (x1)` | 1 OFM byte differs by 1 LSB from tflite_runtime; counters kept |
| yolo-fastest | `UNRESOLVED (x1)` | 955 OFM bytes differ (max 7 LSB) from tflite_runtime; counters kept |
| wav2letter | `UNRESOLVED (x1)` | 2 OFM bytes differ (max 6 LSB) from tflite_runtime; counters kept (boot 93). The earlier `NOT_EXECUTABLE` (boots 87, 89) was a host defect: `RunnerLink.run()` gave up after ~5 s of silence whatever its timeout, and wav2letter's RUN takes 6.6 s (`evidence/w2l_stall/`, fixed in `52254b9`) |

`UNRESOLVED` rows need an MLEK FI101 golden (amendment-2 rule) before they can be called correct; their counters are
reported as measured. Do not average `UNRESOLVED` rows into a headline number without saying so.

## Files

| part | what |
| --- | --- |
| `raw/<workload>/` | one boot per workload: `raw_runs.json`, `runs.csv`, `per_event.csv`, `summary.json`, `campaign.out`, `mcc_boot.log`, `started_utc`, `finished_utc` (byte-identical copies of the evidence folders above) |
| `summary.csv` | per workload × metric: n, median, mean, std, cv, min, max, deterministic. s1 rows are Stage 1's; x1 rows are computed with `host/analysis/stage1.py`'s `derive`/`stats` over measured RUNs 3–10 (rnnoise equals the tool's own output on all 20 metrics) |
| `npu_utilization.csv` | MAC/cycle, peak MAC eff., MAC active ratio, MAC active-cycle eff., `status`, `measured_runs` per workload |

Definitions (`host/analysis/stage1.py`, 1024 MAC): MAC/cycle = N_MAC / npu_active; peak MAC eff. = N_MAC /
(1024 × npu_active); MAC active ratio = mac_active / npu_active; MAC active-cycle eff. = N_MAC / (1024 × mac_active).
N_MAC from the original MLEK tflite (`workload_meta.py`). FVP counterparts: `../npu_utilization_fvp/`.

Open items that bound what these numbers mean (runner vs MLEK execution path): `evidence/runner_gap/open_equivalence_items.md`.
