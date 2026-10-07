# Amendment 6 to the Tier B contract (2026-09-23, after boot 7, before any counted run)

## Correction first

The boot-7 evidence commit (96c2851) says "window non-zero on all 66 runs".
That is wrong: `npu_pmu_window_cycles` is 0 on all 66 runs of boot 7. The
seven validity terms held because `cycle_valid` is armed AND enabled AND
stable AND no-overflow -- it does not require progress; the base tracks
progress separately as `cycle_progress_observed`, which this contract did
not list. Boot 7 therefore counted nothing at all, PMCCNTR included. The
171 `COUNTED_ZERO` verdicts stand as archived and mean "nothing counted",
not "these events count zero". This amendment supersedes the commit
message; the commit is not rewritten.

## New validity term

`cycle_progress_observed == 1` is added to the per-run validity terms.
A run whose window is 0 is INVALID for Tier B (its verdicts become
NOT_OBSERVED), because a zero window cannot carry a count of anything.
Boots 5, 6 and 7 are all INVALID under this term; their archives stand.

## What this leaves open

Every EVENTS-mode variant so far (boots 5, 6, 7) has a zero window; the
END_ONLY image has never had one. Two axes differ from the END_ONLY
campaigns and have not been separated: (a) the firmware's PMEVTYPER /
event-arming writes, (b) the host sequence, which issues RESET_RUNNER
before every set. (b) is testable without a deploy by running mode 1
through the Tier B host sequence on the current image; that probe is run
and archived before any further firmware change is deployed.
