# Stage 2A-F2 (PMCLUT) and 2B-0 (NPU_OP_PMU_MASK) — board feasibility and stall/activity overlap (frozen 2026-11-03, before boot 158)

Plan: `docs/plan/stage2_plan.md`. Owner 2026-11-03: "2A에서 못한것도 채우고 진행하자". **TA profile 1** (MLEK
sys_dram_mid) in every boot. Cost clock = NPU cycles (S0-3, `results/fi101_s0_3_clk/`).

Questions:
- **2A-F2:** Stage 2A found stall events counted while their unit is not active (rnnoise AO stalled 41–56 % with AO
  active 0.6 %; `results/fi101_stage2a/`). Is a stall counted while the unit is active, while it is idle, or both?
  Measured with `PMCLUT` (TRM: counter 0 counts cycles where bit k of `PMC_LUT_0` is set,
  k = 8·e3 + 4·e2 + 2·e1 + e0 of the events of `PMEVTYPER0..3`; documented, never used on this board).
- **2B-0:** can `NPU_OP_PMU_MASK` in the command stream, with `PMCR.mask_en = 1`, gate counting so that a part of the
  command stream is counted alone (TRM: debug feature; never used on this board)? Needed for group-level Stage 2B.

## Image and blobs

- Image `d0cd4775` (APP `d0cd47756c0b…c191`, VECTORS `4c11ff9874f3…2bc8a`, DDR `81d37a219a6b…de98`), built from
  `400a2a9`/`08717c5` (runner `a7e9feeb` + knob words 29 PMCLUT and 30 PMCR.mask_en, written after the PMU is armed and
  read back; mismatch → `PMWL_KNOB_NOT_HONOURED`); gates PASS, no warnings in our sources.
- Blobs = the fi101_s013 blob of the model, changed by `make_probe_blobs.py`:

| arm | change | purpose |
| --- | --- | --- |
| `lut_id` | word 29 = `0xCCCC0001` (LUT: counter 0 = event 1) | identity check of PMCLUT |
| `lut` | word 29 = `0x88880001` (LUT: event 0 AND event 1) | overlap |
| `ctl` | none (byte-identical to the s013 blob) | unmasked control on this image |
| `m_none` | word 30 = 1, command stream unchanged | default state of the mask |
| `m_all` | word 30 = 1, `PMU_MASK(1)` before the first instruction | gating on for the whole stream |
| `m_a` / `m_b` | word 30 = 1, kernel ops `[0, n/2)` / `[n/2, n)` gated on (`host/lib/cms.py gate`) | split |

kws: n = 14 kernel ops (split after op 7); mobilenet: n = 208 (split after op 104). Blob digests (first 12 hex):
kws lut_id `f97dc87ef44d`, lut `8b1d577d6f69`, ctl `f11271cb6a2d`, m_all `5f1a7dc75647`, m_none `bb2283e5a891`, m_a
`c2218c4bd526`, m_b `9e3841eaae36`; mobilenet lut `484ee69f310b`, ctl `0d51cf9eaf86`, m_all `6673ec377dca`, m_none
`19dfa326afc0`, m_a `4e5adb4741f8`, m_b `c472e082eff4`; ad lut `2fad9fac91ba`, rnnoise lut `e6c1bfb599cb`, vww4 lut
`f6dea22f99c6`, yolo lut `4f613e11a839`, wav2letter lut `535a6bf6ad43`.

## Boots and PMU sets (10 RUNs, 2 warm-up, 8 measured per set)

- Campaign LUT (`plan_lut.txt`, sets `ids_lut.txt`): boot 158 kws `lut_id`; boots 159–165 `lut` for all seven models.
  Sets (slot 0 = composite, slot 1 = event 1 raw): 1 `mac_active` ∧ `mac_stalled_by_ib`; 2 `mac_active` ∧
  `mac_stalled_by_w`; 3 `ao_active` ∧ `ao_stalled_by_bs_or_ob`; 4 `wd_active` ∧ `wd_stalled`; 5 `npu_active` ∧
  `cc_stalled_on_blockdep`; 6 `mac_active` ∧ `ao_active`.
- Campaign MASK (`plan_mask.txt`, set A `ids_a.txt`): boots 166–175, kws then mobilenet, arms ctl, m_all, m_none,
  m_a, m_b. Subset (two models) on purpose: a mechanism test, not a model measurement; kws (14 ops, short) and
  mobilenet (208 ops, long, BLOCKDEP overlap between ops).

## Rules (preregistered; `host/analysis/s2_probe.py`, tests `host/tests/test_s2_probe.py`, committed with this contract)

Validity: as fi101_s013 (model mode incl. `knobs_honoured`, `start_seam_once`). Any invalid measured RUN in a boot →
that boot's verdicts `UNPROVEN`.

**2A-F2**
1. Identity (boot 158): in every measured RUN of every set, counter 0 = event 1's own counter → `LUT_IDENTITY_EXACT`;
   all within 0.1 % → `LUT_IDENTITY_CLOSE`; otherwise `LUT_FAILS`. A zero or missing event-1 count → `UNPROVEN`.
2. Overlap (boots 159–165), per model and set, only if identity is EXACT or CLOSE (else `UNPROVEN`):
   f = median over RUNs of counter 0 / event 1. `STALL_WHILE_ACTIVE` f ≥ 0.9; `STALL_WHILE_IDLE` f ≤ 0.1;
   `PARTLY_WHILE_ACTIVE` otherwise; `COUNTED_ZERO` / `INCONSISTENT` if event 1 is 0 in all / some RUNs.
   (Set 6 asks "MAC active while AO active", set 5 "blockdep stall while the NPU is active"; the class names are kept.)

**2B-0**, per model:
3. `passthrough`: every event median and the NPU-cycle median (`infer_npu`) of `m_all` within 1 % of `ctl`.
4. `additive`: for every event, |median(m_a) + median(m_b) − median(m_all)| ≤ 1 % of median(m_all). NPU cycles are
   not part of the sum (PMCCNTR may not be gated); they are reported.
5. Model verdict: `MASK_DISTURBS` if not passthrough; else `MASK_WORKS` if additive, else `MASK_NOT_ADDITIVE`;
   `UNPROVEN` if either is unknown. Overall: `MASK_WORKS` only if both models work; else the worst of DISTURBS >
   NOT_ADDITIVE; `UNPROVEN` if any is.
6. Default state (descriptive verdict): `m_none` all events 0 → `MASK_DEFAULT_OFF`; all within 1 % of `ctl` →
   `MASK_DEFAULT_ON`; else `MASK_DEFAULT_OTHER`.

## What the outcomes mean

- `LUT_IDENTITY_*` + overlap classes: whether Stage 2A stall ratios can be read as "the unit is held up while working"
  (`STALL_WHILE_ACTIVE`) or count waiting while idle (`STALL_WHILE_IDLE`).
- `MASK_WORKS`: the mask partitions counting along the command stream; Stage 2B can gate groups. It does **not** show
  that a gated part equals the work of those operators: with BLOCKDEP, ops overlap and the command processor parses
  ahead, so boundary attribution is a separate question (2B-1). `MASK_NOT_ADDITIVE` / `MASK_DISTURBS`: Stage 2B needs
  another path (split streams or STOP+IRQ, plan review).

## Limits

- An event that can fire more than once per cycle counts once in the LUT (TRM) but more in its own counter; the
  identity check would show it (CLOSE/FAILS) for event 1 of each set.
- The `m_*` blobs add one to three command words; `passthrough` bounds their effect for `m_all` only.
- vww4, yolo, wav2letter OFM correctness not claimed (MLEK goldens pending).

## Amendment 1 (2026-11-03, during the MASK campaign, before any 2B-0 verdict was computed)

Boot 170 (kws `m_b`) failed before any RUN: the runner did not answer the first PING after REBOOT
(`ProtocolError: timed out waiting for a frame`; boot log shows DDR test PASSED and CPUWAIT cleared; the blob was never
uploaded). It is re-run as **boot 176** with the same image and the same blob (`9e3841eaae36`), after boot 175, into
the same evidence root (the failed boot's folder is kept as `m_b_boot170_failed/`). Rules unchanged.

## Results (recorded 2026-11-03, after boots 158–176) — `results/fi101_stage2_probe/`

`LUT_IDENTITY_EXACT`; overlap: every unit stall ∧ its active = 0 in all seven models (`STALL_WHILE_IDLE`), blockdep ∧
NPU active = 1.000 (`STALL_WHILE_ACTIVE`). Mask: kws `MASK_DISTURBS` (passthrough fails the 1 % band: npu_active −1.5 %,
mac_stalled_by_ib +3.9 %, NPU cycles −1.9 %), mobilenet `MASK_WORKS` → overall **`MASK_DISTURBS`**; default state OFF in
both. Recorded limit: the 1 % band is narrower than kws's own RUN-to-RUN spread; the control and treatment RUN ranges
overlap for every kws event (descriptive).
