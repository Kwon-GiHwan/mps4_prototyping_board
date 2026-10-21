# Stage 1 NPU utilization — collected files

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`).** A copy for reading, grouped in three parts. The
originals stay in `evidence/stage1/`, whose paths the frozen contract quotes; every copy here is byte-identical to its
original.

| part | what | copied from |
| --- | --- | --- |
| `raw/<workload>/` | one boot (35 RUNs) per workload | `evidence/stage1/raw/s1/<w>/` (boots 65, 66, 67, 69); `evidence/stage1/a2/raw/a2/<w>/` (boots 72–74, folders `<w>@a2`) |
| `summary/summary.csv` | per workload × metric: n, median, mean, std, cv, min, max, deterministic | `evidence/stage1/summary.csv` |
| `npu_utilization/` | MAC/cycle, peak MAC eff., MAC active ratio, MAC active-cycle eff. per workload | derived from `summary.csv` and `summary.json` (`n_mac`) |

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

Left out: the three `s1` BASELINE_FAIL boots (68, 70, 71; still in `evidence/stage1/raw/s1/`), the campaign-level
`ids.txt` / `plan.txt` / `campaign.nohup.out`, MLEK goldens and the workload manifest.
