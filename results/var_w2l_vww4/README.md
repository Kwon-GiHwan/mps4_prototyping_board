# wav2letter instrumented-build shift (W) and vww4 boot-to-boot spread (V) — boots 310/315/316 and 317–324 (2026-11-10)

Contract `evidence/var_w2l_vww4/contract.md` (frozen `26c59b0`, before boot 308). **TA profile 1 everywhere** (MLEK's own
set-up on MLEK and the driver runner, profile 1 on the legacy runner). `python3 host/analysis/var_w2l_vww4.py <main repo>
<driver repo> results/var_w2l_vww4` → `summary.json`. All eight new MLEK captures valid (one profile, both TA lines,
program end); images re-checked on the board host before deploy (stock `9dc61053`/`4e112520`, instrumented
`5dc56b13`/`5c5728c0`, ddr `e57a6546`).

## W — wav2letter, MLEK stock vs instrumented build, interleaved S E E S E S S E

| | NPU_ACTIVE per boot |
| --- | --- |
| new stock (W1, W4, W6, W7 = boots 317, 320, 322, 323) | 4,134,401 · 4,133,924 · 4,131,584 · 4,132,531 |
| new instrumented (W2, W3, W5, W8 = boots 318, 319, 321, 324) | 4,133,856 · 4,130,833 · 4,133,675 · 4,132,286 |
| equivalence C stock / instrumented (separate sessions) | 4,132,211 · 4,133,890 · 4,133,959 / 4,130,708 · 4,131,099 · 4,131,728 |

- **W1 `NO_SHIFT`**: the new instrumented boots are not separated from the new stock boots (ranges overlap; medians
  4,132,981 (instrumented) vs 4,133,228 (stock) differ by 247 cycles, within the ranges 2,817 / 3,023). The 2,791-cycle difference of
  equivalence C is **not reproduced** when the two builds are interleaved → reading (Wb) of the contract: it was
  session/boot variation of single-inference boots, not a build effect.
- **W2 `BEATS_FIXED`**: the four beats of all eight new boots equal stock B1's exactly.
- Driver runner, same model and input, one image (boot 314): NPU_ACTIVE median per PMU set 4,132,059–4,133,870; the
  set with MAC/MAC_DPU/AO events (A) 4,133,298 vs BASE (35, 17 only) 4,132,786 — no sign that counting those events lowers
  ACTIVE (D6 PMU_INERT; its tolerance ≥ 1 % is coarse, the per-set medians are the finer view).
- **W3 (supplementary, not a verdict change)**: with all 7 stock and 7 instrumented boots the equivalence-C rule finds the
  instrumented build inert, and M4 MAC_ACTIVE / MAC_DPU_ACTIVE / AO_ACTIVE EQUIVALENT against both the legacy runner (C-d)
  and the driver runner (boot 314). The frozen equivalence-C verdict (wav2letter M4 `UNPROVEN`, 3+3 boots) stands as
  judged; this line says what the same rule gives with the interleaved data added.

## V — vww4 NPU_ACTIVE between boots

| environment (input) | boots | boot medians | between-boot range | within-boot RUN range |
| --- | --- | --- | ---: | ---: |
| MLEK, one inference per boot (MLEK) | 6 (stock 3 + instrumented 3) | 232,761 … 236,774 (median 233,578) | 4,013 | — |
| driver runner (MLEK) | 310, 315, 316 | 234,489 · 234,158 · 233,979 | 510 | 4,205–4,278 |
| legacy runner (seed-1, same blob) | 97, 192, 196, 281, 287 | 235,265 … 235,837 | 572 | 3,144–3,558 |
| legacy runner (MLEK) | 306 | 235,893 | — | 3,525 |

- **V2 `DRIVER_WITHIN_MLEK_RANGE`**: every driver boot median lies inside the six MLEK boots' range.
- Descriptive: the runners' boot medians move by ~0.2 % between boots, while one RUN moves by ~1.8 % (within-boot range).
  An MLEK boot is one inference, i.e. one draw from that RUN-to-RUN spread: its boot-to-boot range (4,013) is the size of
  one boot's RUN range, not a sign of a less stable platform. Driver first RUN after boot: 235,157 · 233,605 · 234,854,
  inside the RUN range (no first-inference offset seen on three boots).
- Driver median − MLEK 6-boot median: **+0.25 %**; legacy (MLEK input) − MLEK: +0.99 %; driver vs legacy same input
  −0.59 % (D5 within tolerance). The equivalence-C "+1.07 %" (legacy vs 3 MLEK stock boots) combines a small legacy-path
  offset (~0.6 %, inside the D5 tolerance, cause not separated) with the low median of three single-inference draws.
- V3 (POST_HOC_DESCRIPTIVE, computable before the contract): the legacy MLEK-input median lies inside the MLEK 6-boot range.

## Limits

No build variant separating counter selection from code layout was needed (no shift to explain). No new MLEK vww4 or
legacy boots. The legacy-path offset on vww4 is described, not separated (Phase 5).
