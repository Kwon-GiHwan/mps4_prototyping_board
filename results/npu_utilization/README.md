# NPU utilization — collected files

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`).** MLEK models only, measured with the runner in Stage 1
(boots 65–67). The originals stay in `evidence/stage1/`, whose paths the frozen contract quotes. Each `raw/` folder
is a byte-identical copy of its original. The two CSVs keep the original rows of these three models unchanged.

| part | what | copied from |
| --- | --- | --- |
| `raw/<workload>/` | one boot (35 RUNs) per workload | `evidence/stage1/raw/s1/<w>/` (boots 65, 66, 67) |
| `summary.csv` | per workload × metric: n, median, mean, std, cv, min, max, deterministic | rows of `evidence/stage1/summary.csv` |
| `npu_utilization.csv` | MAC/cycle, peak MAC eff., MAC active ratio, MAC active-cycle eff. per workload | derived from `summary.csv` medians and `evidence/stage1/summary.json` (`n_mac`) |

Definitions (`host/analysis/stage1.py`, 1024 MAC): MAC/cycle = N_MAC / npu_active; peak MAC eff. = N_MAC /
(1024 × npu_active); MAC active ratio = mac_active / npu_active; MAC active-cycle eff. = N_MAC / (1024 × mac_active).

## Files in each `raw/<workload>/`

| file | content |
| --- | --- |
| `raw_runs.json` | records as received over UART: ping + 35 RUN records; everything else is derived from it |
| `runs.csv` | one row per RUN × event (280 rows), with validity, OFM comparison, hashes and boot index |
| `per_event.csv` | per event: the 35 values and a verdict |
| `summary.json` | blob / input / golden hashes, knobs, requested events, consistency checks |
| `campaign.out` | campaign log, one line per RUN (rc, vendor_rc, OFM mismatch, valid) |
| `mcc_boot.log` | MCC reboot and FPGA image load |
| `started_utc`, `finished_utc` | campaign start and end |

## Not here

- Isolated operators (conv3x3, dw3x3, pw1x1, fc1024): not MLEK models. Still in `evidence/stage1/`.
- MLEK models rnnoise, vww4, yolo-fastest and wav2letter: never measured with the runner. Stock-MLEK board cycle
  counts (no MAC_ACTIVE) exist on branch `refactor/unified-mlek-campaigns`, `docs/paper/evidence/board-stage-b*/`.
