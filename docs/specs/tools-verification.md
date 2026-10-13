# Board verification of the refactored tools (criteria)

Frozen 2026-10-13, **before the run**. Authorization: owner, 2026-10-13 ("그래 검증해봐").

What changed since the last board run (boots 49–56, old tools): `run_pmu_events.py` (blob required, golden check
removed, header via `pmwl.parse_header`), `runner_proto.py` (diag/qual/cfg code removed), `pmu_events_parse.py`
(event lists via `reference.py`), `board/run_campaign.sh` (new generic launcher), `sync.sh` (new). Firmware image
unchanged: APP `2c2fa435…` (deploy `evidence_m9`), staging `~/evsweep_m9`.

## Protocol

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`)**, blobs `kws_micronet_m.ta1.pmwl` and
`ad_medium_int8.ta1.pmwl` — the same files as boots 50 and 53. `sh sync.sh board` then
`sh ~/evsweep/run_campaign.sh ~/evsweep_m9 ~/evsweep/evidence_tools_check ~/evsweep/config/screening_ids.txt <plan>`,
plan = boot 57 kws ta1, boot 58 ad ta1. 35 RUNs, same 8 events.

## Criteria (reference = boots 50 / 53, `evidence/ta_ab/ta1/`)

Per workload:
1. 35/35 RUNs valid, refusal none, every `run_rc` 0 (TA read-back honoured).
2. mac_active, EXT rd beats, EXT wr beats: median within 0.1 % of the reference median (work and traffic unchanged).
3. npu_active median within ±3 % of the reference median (reference CV 0.6–1.0 %).
4. `screening_metrics.py` on the result gives `SCREENED`.

Outcome: `TOOLS_VERIFIED` if both workloads meet 1–4; `TOOLS_REGRESSED` if any of 1–3 fails with a complete run;
`UNPROVEN` if the run does not complete (transport, board) — then the tools are not judged.
