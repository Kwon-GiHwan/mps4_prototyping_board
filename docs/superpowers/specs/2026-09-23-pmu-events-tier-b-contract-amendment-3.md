# Amendment 3 to the Tier B contract (2026-09-23, after boot 4 refused itself, before any run)

The procedure wrote `SET_INSTRUMENTATION_MODE -> RUN`. The base runner's
state matrix (`state_accepts[]`) accepts SET_INSTRUMENTATION_MODE only in
IDLE and RUN only in INPUT_READY / RESULT_READY; RESET_RUNNER returns to IDLE
and clears the mode to OFF. The per-set sequence is therefore:

```
RESET_RUNNER -> SET_INSTRUMENTATION_MODE(EVENTS, set_id, codes)
             -> LOAD_MODEL_BEGIN/CHUNK/END (64 zero bytes) -> LOAD_INPUT(empty)
             -> RUN x3        (RESULT_READY accepts RUN; no re-arm between repeats)
```
The 64-byte dummy blob and empty input are exactly what run_pmu_diag.py and
run_pmu_qual.py stage; the fixed compiled-in inference runs regardless.

Boot 4 (host-boot-index 4): PING ok, mode 2 ACKed with count 8 (so the image
does carry EVENTS mode), RUN NACKed STATE in IDLE. Archived as a refusal with
zero runs; not reused. Campaign re-runs on boot 5. Counts of runs/sets are
unchanged (22 sets, 66 runs, one boot).
