# Board verification of the refactored tools — report

Criteria `docs/specs/tools-verification.md` (frozen `a877d10`, before boot 57). **TA state: profile 1 (MLEK
sys_dram_mid).** Image APP `2c2fa435…` (unchanged since deploy `evidence_m9`). Boots 57 (kws) and 58 (ad_medium),
35 RUNs each, launched by the new `board/run_campaign.sh` after `sh sync.sh board`.

Outcome (preregistered): **TOOLS_VERIFIED** — `OUTCOME.md`. Both workloads: 35/35 valid, run_rc 0, mac_active
and EXT beats identical to boots 50/53, npu_active +0.43 % (kws) / −0.20 % (ad), SCREENED.

POST_HOC_DESCRIPTIVE: kws npu_active 91,446 vs MLEK board 91,431; ad 146,252 vs MLEK 145,976.

Raw data (runs.csv, summaries, blob metadata, fingerprints, boot logs) removed from the tree in the cleanup after `2ce4512`; recover with `git show 2ce4512:evidence/tools_check/<path>`.
