# Stage 4 raw results

Originals (board logs, records, outputs) stay in `evidence/stage4/raw/` (boots 330–337, `conds/<config>/wfe/`:
`campaign.out`, `mcc_boot.log`, `raw_runs.json` = every record v2 field per RUN, `runs.csv` = per event,
`output.bin` = NPU output of the last RUN, `capabilities.json`; session log `evidence/stage4/session.log`).
`runs_per_run.csv` here: one row per RUN (warm-up included and marked) with every counter of its set, validity,
the firmware's output mismatch count / max diff against the CPU reference, the output CRC and PMCCNTR at the IRQ.
TA profile 1. Event 53 and 55 are not in TRM 110 (reported, not used for conclusions).
