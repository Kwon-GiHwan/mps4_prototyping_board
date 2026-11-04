# Stage 2B-2 — activity and stalls per operator-type group — board results

Contract `evidence/s2_groups/contract.md` (frozen `da51566`, before boot 212; note 1 on group composition). Image
`d0cd4775`, **TA profile 1** in every boot. Boots 212–243, sets A/C/D × 10 RUNs (2 warm-up), 960/960 RUNs valid, no
boot failed. Raw: `evidence/s2_groups/raw/`. Verdicts:
`python3 host/analysis/s2_groups.py evidence/s2_groups/raw evidence/s2_groups/ids.txt results/fi101_stage1/vela_block_fill_per_op.csv results/fi101_stage2_groups`.
Group composition (what each group holds): `vela_op_map/README.md`.

## Preregistered outcomes

| model | deficit (unattributed npu_active) | partition A / C / D | H1 | H2 (q = DW time share / DW MAC share) |
| --- | --- | --- | --- | --- |
| kws | 0.88 % | holds / leaks / holds | `DW_NOT_LOWER` | `DW_COSTLY` (11.6) |
| ad | 0.60 % | holds / leaks / holds | `DW_NOT_LOWER` | `DW_COSTLY` (19.7) |
| rnnoise | 1.87 % | leaks / leaks / leaks | n/a | n/a |
| vww4 | 0.31 % | leaks / leaks / leaks | `DW_NOT_LOWER` | `DW_COSTLY` (3.0) |
| yolo | −0.24 % | leaks / leaks / leaks | `DW_NOT_LOWER` | `DW_NOT_COSTLY` (1.4) |
| mobilenet | 0.28 % | holds / holds / leaks | `DW_NOT_LOWER` | `DW_COSTLY` (4.5) |
| wav2letter | 0.06 % | leaks / leaks / leaks | n/a | n/a |

Overall: **H1 `DW_NOT_LOWER`**, **H2 `MIXED`**; |deficit| ≤ 5 % in all seven, so H1/H2 were judged everywhere they apply.
Partition leaks are per event (`partition.csv`): both signs occur, e.g. yolo `mac_active` +2.15 % (counted twice),
rnnoise `npu_active` −2.7 %, small events up to ±65 %.

## Attribution check — `POST_HOC_DESCRIPTIVE` (`attribution_check.csv`): **the group windows are not the groups' execution**

MAC efficiency of a group = Vela MACs of its operators / (its `mac_active` cycles × 1024). It cannot exceed 1.

| model | group | Vela MAC share | NPU-active time share | MAC efficiency (active cycles) |
| --- | --- | --- | --- | --- |
| ad | CONV | 0.969 | 0.324 | **2.845 (impossible)** |
| ad | DEPTHWISE | 0.031 | 0.603 | 0.026 |
| kws | CONV | 0.950 | 0.313 | 0.932 |
| kws | DEPTHWISE | 0.049 | 0.565 | 0.020 |
| mobilenet | CONV / DEPTHWISE | 0.931 / 0.069 | 0.530 / 0.311 | 0.855 / 0.094 |
| vww4 | CONV / DEPTHWISE | 0.901 / 0.095 | 0.497 / 0.288 | 0.670 / 0.097 |
| yolo | CONV / DEPTHWISE | 0.782 / 0.213 | 0.521 / 0.294 | 0.344 / 0.155 |
| whole model (m_all) | — | — | — | ad 0.650, kws 0.270, mobilenet 0.511 (= Stage 1) |

ad's CONV group would do 2.8× more MACs per active MAC cycle than the array can. The totals are conserved (set A
partition holds in ad: Σ groups = whole within tolerance), so the counts are **assigned to the wrong groups**: a
group's mask window, placed by command-stream position (enable before the op's setup, disable after its operation
instruction), does not cover that op's execution. The command processor issues an operation and moves on to parse
the next while the operation runs, so execution spills into the following window. A plain one-op shift does not fit
either (it gives ad POOL 1.3), so the misalignment is partial and model-dependent.

**Consequence.** H1, H2 and the per-group ratios (`groups.csv`) are mechanically what the contract computes, but they
are **not statements about operator types**: "depthwise takes 56–60 % of kws/ad time" and "DW MAC-active is not lower
than CONV" may both be artefacts of the window shift. The mask's whole-stream behaviour (2B-0b: no disturbance) is
unaffected. Stage 2B attribution needs a window that follows execution, not parsing — open question, see
`docs/plan/stage2_plan.md`.

Also recorded: `deficit` stayed small even with 55–67 windows per group (mobilenet), i.e. NPU-active cycles are
almost all attributed to *some* group — the loss is not the problem; the assignment is.
