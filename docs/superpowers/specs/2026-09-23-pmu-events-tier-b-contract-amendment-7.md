# Amendment 7 to the Tier B contract (2026-09-23, after boots 5-7 and the END_ONLY control)

## The mechanism, from the vendor source (u85.c, container copy)

`TEST_PROT = 0`, `TEST_CPM = 1`. The fixed test does not reset the NPU before
the run. It stops the NPU (`CMD = 0`), prints `"Testing CPM signals\n"`, then
writes `CMD = 0xC` (clock-Q / power-Q release). After that release the PMU
reads 0 -- PMCCNTR and every event counter. The runner's post-return
readout is therefore always 0, in END_ONLY too: the deploy-free control on
the boot-7 image showed END_ONLY through the Tier B sequence with armed=1,
enable=1 and window 0 on six runs. The V13-V15 lineage reads at exactly
this printf for the same reason.

## What changes (edits 8-12; END_ONLY untouched)

- Arming and event selects stay as in the boot-7 image (before the call,
  under cnt_en=1); the arm readback was 1.
- A read seam: in the clean-profile `__wrap_printf`, when
  `measurement_active && mode == EVENTS && fmt == "Testing CPM signals\n"`,
  snapshot PMCCNTR (stable read), PMOVSSET and PMEVCNTR[0..count) into
  static storage and count the arrival. Nothing else in printf changes.
- After the call, EVENTS mode copies the seam snapshot into the record in
  place of the post-return (dead) reads and recomputes
  `cycle_progress_observed` / `npu_pmu_cycle_valid` from it.
- One record word is appended: `read_seam_fired` (field 103). The host
  parser already tolerates and counts trailing words; it now also exposes
  them. New validity term: `seam_fired == 1` (exactly one arrival).

## Static gate additions

`RULE_SEAM_HOOK`: the generated source's `__wrap_printf` carries the literal
`"Testing CPM signals\n"`, and `__wrap_printf` is linked (nm). The vendor
file carries that literal exactly once (checked at authoring: 1).

## Unchanged

Sets, repeats, verdicts, the two consistency checks, refusal rules. Boots
5-7 stay archived as INVALID (amendment 6 term). Re-run on boot 8.
