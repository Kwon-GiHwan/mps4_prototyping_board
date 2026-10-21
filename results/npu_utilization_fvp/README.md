# NPU utilization (FVP) — collected files

**Simulator, not the board.** FVP Corstone SSE-320, Ethos-U85 1024 MAC, stock MLEK 26.03.0 (`inference_runner`),
Vela `Ethos_U85_SYS_DRAM_Mid_1024`, Dedicated_Sram. **TA state: ON, MLEK `ta_config_u85_sys_dram_mid`** (the same
cmake config as TA profile 1; FVP places the adapters at `0x50006000` / `0x50006800`). Input: MLEK `inference_runner`
fills the IFM with `std::rand() & 0xFF`, default seed (`A7_input_tensor_seed.md`). All seven MLEK use-case models.

Data from branch `refactor/unified-mlek-campaigns` (`fe7541b`), paper campaign 2026-08-25 (formal M1–M3) and the R1
re-measurement (R1, R2). N_MAC computed on 2026-10-21 with `host/container/workload_meta.py` on the original MLEK
tflite files (sha256 equal to the FVP records' `model_sha256`; kws, ad and mobilenet reproduce the Stage 1 values).

Same layout as `../npu_utilization/` (board, runner). Do not mix the two in one comparison without saying so.

| part | what | from |
| --- | --- | --- |
| `raw/<workload>/` | every record of the U85-1024 cell | see below |
| `summary.csv` | per workload × metric: n, median, mean, std, cv, min, max, deterministic | computed from `raw/` |
| `npu_utilization.csv` | MAC/cycle and peak MAC eff. per workload | `summary.csv` medians and `n_mac.meta.json` |

Cycle metrics use five runs (M1–M3, R1–R2); beat metrics use two (R1–R2, the formal runs did not read beats). Every
metric is identical across its runs.

**No MAC_ACTIVE.** MLEK's profiler reads only ACTIVE, IDLE, TOTAL and the four beat counters, so `mac_active_median`,
`mac_active_ratio` and `mac_active_cycle_efficiency` are empty. `boot` is empty (no board boot).

Definitions as in `host/analysis/stage1.py`, with npu_active = MLEK `NPU ACTIVE`: MAC/cycle = N_MAC / npu_active;
peak MAC eff. = N_MAC / (1024 × npu_active).

## Files in each `raw/<workload>/`

| file | content | source on `refactor/unified-mlek-campaigns` |
| --- | --- | --- |
| `formal_M1.json` … `formal_M3.json` | formal run: gates, artifact hashes, TOTAL/ACTIVE/IDLE | `docs/paper/evidence/stage{1,2,3}-formal-20260825/stage*_m*_evidence.tar.gz` |
| `remeasure_record.json` | R1 re-measurement: gates, hashes, both runs with all seven counters | `docs/paper/raw_data_report/remeasure/R1_RAW.json` |
| `remeasure_R1.uart.txt`, `remeasure_R2.uart.txt` | MLEK UART output of each re-measurement run | `docs/paper/raw_data_report/remeasure/uart/` |
| `vela_per-layer.csv`, `vela_summary.csv` | Vela per-layer and summary report for this cell | `docs/paper/raw_data_report/amendments/vela_verbose/cells/` |
| `n_mac.meta.json` | N_MAC per op from the original tflite, Vela prediction | `workload_meta.py`, 2026-10-21 |
