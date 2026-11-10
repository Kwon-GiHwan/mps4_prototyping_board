# Stage 4C-2b — MAC activity of the DepthFirst 1×1 Conv at Cin 40 and 48 (frozen 2026-11-11, before boot 348)

Owner approval 2026-11-11 (minimal board comparison after the Stage 4C-2 compile-only sweep). **TA: MLEK's own
sys_dram_mid set-up = TA profile 1.** FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (boot `1b5c0adb`, bram
`4f592f24`), WAIT_WFE, Vela 5.0.0 with MLEK's options, INT8, the 4C-2 1×1 Conv (24×24, Cout 96, VALID, RELU6; data:
first Cin channels of the 128-channel extension, base bias and OFM scale), graph I/O in DRAM, pass A + pass B, 1
warm-up + 4 measured RUNs: 3 configs × 2 × 5 = **30 RUNs**. No new firmware, no schedule forcing, no further configs.

## Question

With DepthFirst chosen by Vela at Cin 40 and 48, does MAC activity follow the actual Cin, a rounded-up amount, or
none of the candidates?

## Configurations (artifacts `evidence/stage4c2b/workloads/` = the 4C-2 sweep / 4C-2 builds, Gate B PASS)

| config | Cin | MACs (= 24·24·96·Cin = Vela) | traversal / IFM block | OFM ublocks | IFM steps | DRWL |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| s4c2_conv_cin40 | 40 | 2,211,840 | DepthFirst / 64 | 576 | 1 / 1 | `9f26fefd` |
| s4c2_conv_cin48 | 48 | 2,654,208 | DepthFirst / 64 | 576 | 1 / 1 | `6eb390be` |
| s4c2_conv_cin64 (reference) | 64 | 3,538,944 | DepthFirst / 64 | 576 | 1 / 1 | `46a87532` (4C-2 boot 346) |

Cin 40's IFM pixel stride (40 B) is not a multiple of 16: whole-run time is not used to judge the MAC behaviour.

## Pre-registered hypotheses (`results/fi101_stage4c2b/predictions.json`, `host/analysis/stage4c2b.py predict`)

| hypothesis | formula | Cin 40 | Cin 48 |
| --- | --- | ---: | ---: |
| H1 | MACs / 768 | 2,880 | 3,456 |
| H2 | 4,608 (as Cin 64) | 4,608 | 4,608 |
| H3 | MACs / 384 | 5,760 | 6,912 |
| H4 | 24·24·96·roundup(Cin, 16) / 768 | 3,456 | 3,456 |

Independently recomputed from the compiled MACs (equal to the owner's table). Cin 40 separates all four; at Cin 48 H1 and
H4 coincide (3,456), so Cin 48 alone cannot tell them apart. The four do not cover all behaviours. H4 is a computational
hypothesis, not derived from a 16-channel processing unit or from the 16-byte write rule.

## Rules (`host/analysis/stage4c2b.py judge`; tests `host/tests/test_stage4c2b.py`; mutation below)

- Output and RUN validity as Stage 4 (PASS_EXACT / PASS_TOLERANCE ≤ 1 LSB vs the CPU reference / FAIL / INVALID;
  `record_v2.validity`; output CRC identical across RUNs).
- **Reference gate:** Cin 64 must give MAC_ACTIVE = MAC_DPU_ACTIVE = 4,608 in every measured RUN, the 4C-2 boot-346 output
  sha256 and every counter constant in both; otherwise `REFERENCE_MISMATCH` and no hypothesis verdict.
- **Per config** (each of the 4 measured pass-A RUNs compared, no median): `INVALID` > `MEASUREMENT_UNSTABLE` (RUNs
  differ) > `MATCH:<every hypothesis equal to all RUNs>` > `NONE_MATCHED`. No coefficient is fitted afterwards and no
  config is added.
- Primary results: MAC_ACTIVE, MAC_DPU_ACTIVE, MACs / MAC_ACTIVE, MACs / MAC_DPU_ACTIVE, MAC_DPU_ACTIVE / MAC_ACTIVE (no
  value of 768 or 1.0 assumed), OFM ublocks and IFM steps. Secondary: NPU_ACTIVE (Stage 4 pair rule 40→48, 48→64, pass B
  check, opposite signs → UNRESOLVED) and SRAM/EXT traffic.
- Interpretation limits: H1 → "high MACs per active cycle observed below Cin 64", not a causal schedule effect; H2 → not
  IFM block 64 as the cause (other roundings predict the same); H4 → "consistent with rounding Cin up to 16 in the tested
  range"; no claim of MAC-circuit occupancy or invalid-channel computation; Cin / traversal / IFM block / weight order not
  separated.

## Boots — `plan.txt`: 348–350 (Cin 40, 48, 64), conditions `wfe 0 0 off 1,2`, `OUTPUTS=1`

End: board restored to m6, postflight PING of the restored image, card withdrawn. The experiment ends with this run.

## Mutation test

`evidence/stage4c2b/mutate_stage4c2b.py`: 7 mutations (H4 rounding, H3, unstable check, output validity, reference
output, reference MAC, distinct flags) → 7/7 RED after one fixture (reference MAC wrong while the old reference's MAC is
not a constant counter). An 8th mutation (compare only the first RUN) was equivalent once the unstable check precedes it;
the code was simplified to that form and the mutation dropped.
