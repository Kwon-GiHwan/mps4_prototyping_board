# Runner ↔ MLEK equivalence — open items (recorded 2026-10-27, to be resolved later)

Source: an external review of the runner against the MLEK reference configuration chain (FI101 U85-1024 → `Z1024` →
`Ethos_U85_SYS_DRAM_Mid_1024` → `ta_config_u85_sys_dram_mid` → Dedicated_Sram driver settings). Its verdict: the
configuration values follow the reference and are not tuned by hand; the **execution path** differs, and these
differences are not yet shown to leave the measurements unchanged. Nothing below is done yet.

**What the runner is, stated exactly:** a custom PMU measurement runner built on a modified copy of Arm's FI101
selftest driver, reproducing MLEK `b2c0bb2`'s compilation and main hardware settings. Arm's original files are
unchanged; the build compiles a patched copy of `u85.c` and redirects calls with `--wrap`, so "vendor driver used
unmodified" is **not** a valid claim. **TA state for every item: profile 1.**

How to word the existing evidence until these are closed: "for the models and conditions measured, NPU active was
within ±0.4 % of MLEK and the compared beat counters were equal (Stage 0). This supports reproduction of those
metrics; it does not separate the effect of each remaining difference, nor show other PMU metrics equivalent."
±0.4 % is a measured difference, not an error bound.

## Already settled (no action)

- Vela output: byte-identical to MLEK's for all seven MLEK models (`vela_sha256`).
- AXI limits: `AXI_SRAM 0x20F0B` (12 reads / 16 writes / max_beats 2), `AXI_EXT 0x21F3F` (64 / 32 / 2) = driver
  defaults with MLEK's `MAX_BEATS=2`; read back every RUN.
- QCONFIG / REGIONCFG select MEM_ATTR 2 / 0 where MLEK selects 3 / 1; MEM_ATTR is 0/0/4/4 in both, so the selected
  attributes are equal. Holds only while MEM_ATTR0 = MEM_ATTR1 and MEM_ATTR2 = MEM_ATTR3.
- Per-RUN OFM check exists: every RUN compares every OFM with its golden (`ofm_mismatch_count`); Stage 1/2A and the
  x1 controls are byte-exact against MLEK FI101 or tflite_runtime goldens (see each dataset's gate).

## Open items

| # | item | known now | to do | closes when |
| --- | --- | --- | --- | --- |
| E1 | CFG_SRAM_CAP / CFG_EXT_CAP | Arm's `u85.c` (lines 215–216) writes `0x00021F3F` to NPU base + `0x60` / `0x64` (`interface.h` `NPU_REG_CFG_*_CAP`); the public U85 header defines these read-only (configuration pins). MLEK does not write them. | Record absolute address, value before, value written, read-back after, and the value just before the NPU starts — in the runner and in an MLEK run on FI101. | Both runs show the same CAP values at NPU start (then the write is inert), or the difference is measured. |
| E2 | TA EXT MAXR | Runner writes 0 and reads 0. MLEK's file sets 64 and its own comment says "6-bit field, 0 = infinite"; 64 & 0x3F = 0 is a hypothesis. 0 means TA-unlimited, so the 64-read limit comes from `AXI_EXT`, not the TA. | Read back both TA instances (all 11 registers, and any bypass/version state) after MLEK's `ta_set_all()` on FI101; compare with the runner's read-back. | MLEK's read-back equals the runner's. |
| E3 | Executed model = compiled model | Vela output identical; the packer extracts cms/const/IO offsets; OFM compared every RUN. Not yet traced: the blob's cms/const hashes and lengths, and the base pointers the NPU actually received. | For each model, link Vela file → blob cms/const sha256 and lengths → BASEP0–2 / QBASE / QSIZE read at NPU start; compare OFMs of all seven models on the same input against MLEK FI101 output. | Every model's chain is traced and its OFM equals MLEK's (x1 models need MLEK goldens; vww4 and yolo currently differ from tflite_runtime). |
| E4 | PMU counting window | Runner: hold clock/power (`CMD=0`), reset and arm counters, run, read the counters at the vendor's "Testing CPM signals" printf before power release (`CMD=0xC`); `read_seam_fired` is recorded per RUN. MLEK: enable at `ethosu_inference_begin`, disable at `_end`. PMCCNTR already known to include staging copies (latency uses `npu_active`, never PMCCNTR). The reviewer notes `CMD=0` is not a stop/reset command; what it holds must be confirmed against the TRM. | Write down start/stop points of both paths; check whether counters are stopped before reading; report PMCCNTR and NPU_ACTIVE separately; confirm event selection/overflow handling match; confirm the seam fires exactly once per RUN in every boot and keeps its position relative to NPU start and power release. | Both windows are defined, and every ratio uses a denominator whose window is the same in both paths (or the difference is quantified). |
| E5 | Remaining execution differences, one at a time | Untested: CPU busy-poll with D-cache off (MLEK: `__WFE()`, caches on); no soft reset before a job (MLEK resets to a known state; PROT is read-only, so the gap is "secure/privileged state not set by reset and not compared", not "PROT not written"); fast scratch at `0x31100000` instead of `0x31000000` (`CFG_SRAM_HASH*` may map addresses to SRAM0/1 differently). | Separate verification runs on the seven MLEK models, one change each, never overwriting the baseline: wait mode / cache; reset policy (A→A vs A→B→A); scratch base (compare per-port SRAM0/SRAM1 beats, not only totals; confirm the reserved fast-scratch region ≥ the Vela budget from the memory map). | Each change leaves the reported metrics unchanged within run-to-run spread, or its effect is recorded. |

Priority: E1 and E2 are single read-backs; E3 and E4 decide what the numbers mean; E5 is the longest. E1, E2 and
the MLEK side of E3 need MLEK runs on FI101 (fresh authorization, CLAUDE.md standing constraints).

## Changes to the vendor path, for the record

| change | how | purpose |
| --- | --- | --- |
| `BUSY_SLEEP_TIMEOUT` 10,000 → 200,000,000 | generated copy (`firmware/vendor/patch_u85_vendor_timeout.py`) | large models are not cut off; a timeout must stay distinguishable from completion |
| POWER_CTRL 2 → 0 (MLEK's value) | copy routes the write through `u85_power_ctrl_value()` | match MLEK; read back at the CPM seam |
| REGIONCFG / QCONFIG / MEM_ATTR / AXI | overwritten after the vendor writes them, just before NPU start (printf seam), read back | apply MLEK's values |
| `test_u85` | `--wrap`: the blob replaces test3's tensors; the runner places cmd/const/arena/fast | run real models |
| PMU | armed and read by the runner (see E4) | event counting |
| printf family | `--wrap`, suppressed | no UART traffic inside the window |
