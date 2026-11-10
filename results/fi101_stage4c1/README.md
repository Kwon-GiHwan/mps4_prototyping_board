# Stage 4C-1 — output-write beat prediction on new channel counts (boots 338–343, 2026-11-10 UTC board clock)

Contract `evidence/stage4c1/contract.md` (frozen `a80e28f`, before boot 338). **TA profile 1** (MLEK sys_dram_mid),
FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (the Stage 4 image; boot `1b5c0adb`, bram `4f592f24`), WAIT_WFE,
Vela 5.0.0 with MLEK's options, INT8, graph I/O in DRAM, pass A + pass B, 1 warm-up + 4 measured RUNs each = 60 RUNs.
All boots `campaign exit=0`; board restored to m6 (`RESTORE VERIFIED`), postflight: PING of the restored image
(state 1), card withdrawn. Raw: `evidence/stage4c1/raw/`, session log `evidence/stage4c1/session.log`.

```
python3 host/analysis/stage4c1.py judge evidence/stage4c1/raw evidence/stage4c1/workloads \
  results/fi101_stage4c1/predictions.json evidence/stage4/raw results/fi101_stage4c1     -> summary.json
```

## Validity

- Output: 6/6 **PASS_EXACT** against the CPU reference, output CRC identical in every RUN; 60/60 RUNs valid.
- Region-1 base (OFM arena) of every RUN = the address predicted from the artifacts (6/6).
- Bases re-confirmed: NPU output sha256 equal to Stage 4's and all constant counters equal (conv 10, DW 11 compared, 0
  differ) → `baseline_ok`.

## 1. Prediction (primary; pre-registered)

| config | C mod 16 | rule A (pre-registered) | measured EXT write beats, 4 pass-B RUNs | verdict | discriminates A from B–D |
| --- | ---: | ---: | --- | --- | --- |
| s4_conv_base | 0 | 3,456 | 3,456 ×4 | `PREDICTION_MATCH` | no (A = B = C = D) |
| s4c_conv_cout94 | 14 | 6,408 | 6,408 ×4 | `PREDICTION_MATCH` | **yes** (B 3,888, C 4,392, D 3,384) |
| s4c_conv_cout97 | 1 | 7,272 | 7,272 ×4 | `PREDICTION_MATCH` | **yes** (B 4,032, C 4,572, D 3,492) |
| s4_dw_base | 0 | 28,224 | 28,224 ×4 | `PREDICTION_MATCH` | no |
| s4c_dw_c142 | 14 | 52,528 | 52,528 ×4 | `PREDICTION_MATCH` | **yes** (B 30,576, C 33,320, D 27,832) |
| s4c_dw_c145 | 1 | 57,820 | 57,820 ×4 | `PREDICTION_MATCH` | **yes** (B 31,360, C 34,300, D 28,420) |

**Rule A's output-write prediction held on the new channel conditions** (remainders 14 and 1, Conv and DWConv, one with
a changed Vela schedule), in addition to the remainder-15 cases it was derived from. Four configs discriminate A from
B–D; the bases do not count. The internal DMA/AXI implementation is not claimed to be rule A.

## 2. Execution and transfers (secondary; Stage 4 pair rule, pass A primary, pass B check)

| pair | MACs | MAC_ACTIVE cycles | NPU_ACTIVE pass A / pass B | verdict | EXT read beats | EXT write beats | Vela schedule |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| Conv 96 → 94 | −2.1 % | 2,304 → 2,304 | +5.1 % / +7.4 % | `NOT_PROPORTIONAL_TO_MAC` | 1,437 → 1,435 | 3,456 → 6,408 | same |
| Conv 96 → 97 | +1.0 % | 2,304 → **2,016** | **+23.0 % / +24.9 %** | `NOT_PROPORTIONAL_TO_MAC` | 1,437 → 1,420 | 3,456 → 7,272 | **changed** (block 6×12×112, ublock 2×4×16, slices 16 + 81) |
| DW 144 → 142 | −1.4 % | 31,752 → 31,752 | +5.4 % / +5.7 % | `NOT_PROPORTIONAL_TO_MAC` | 31,556 → 58,675 | 28,224 → 52,528 | same |
| DW 144 → 145 | +0.7 % | 31,752 → **35,280** | **+17.3 % / +17.5 %** | `NOT_PROPORTIONAL_TO_MAC` | 31,556 → 64,477 | 28,224 → 57,820 | same |

Vela `npu_cycles` (compute estimate) changed −2.0 % (Conv 94), +0.9 % (Conv 97), 0 % (DW 142), +10.8 % (DW 145); in this
setting it did not reproduce the measured increases (`stage4c1_changes.csv`).

Both passes moved in the same direction in every pair (no `UNRESOLVED`). Four measured RUNs per pass; the tolerances
(1,047 conv, 1,598 DW) are the RUN ranges/1 % floor, so only the sign and approximate size are claimed.

Observations (`OBSERVED`, these shapes only):
- **MAC_ACTIVE** (deterministic): unchanged for −2 (Conv, DW), as for −1 in Stage 4; **rose for DW +1** (31,752 →
  35,280 = ×10/9, i.e. as if 160 instead of 144 channels) and **fell for Conv +1** (2,304 → 2,016) where Vela also chose
  a different block/ublock. A step pattern consistent with 16-channel groups for DW is seen here; it is not generalised
  to a channel unit.
- **EXT write beats** rose to rule A's values in every non-multiple-of-16 config; **EXT read beats** rose only where the
  IFM has the changed channel count (DW: 31,556 → 58,675 / 64,477); for Conv (IFM Cin 16 unchanged) reads did not rise.
  Rule A was not evaluated for reads; the read increase is reported, not explained.
- NPU_ACTIVE rose in all four pairs beyond the MAC change; the largest rises (Conv +1 +23 %, DW +1 +17 %) are where
  MAC_ACTIVE or the schedule also changed. Which part of the time comes from transfers is not measured; the write-beat
  match is not evidence of a cause of the time increase.

## 3. Status

- Prediction verification: **extended** — rule A predicted the output-write beats for remainders 14 and 1 (4/4
  discriminating configs), `POST_HOC` hypothesis now with a pre-registered confirmation; mechanism `UNVERIFIED`.
- Execution-time effects: observed with consistent direction in both passes; causes `UNRESOLVED`.
- Not done (proposals only): other remainders, address changes, SRAM placement, FC, Stage 4D, a read-beat rule.
