# Stage 4C-2b — MAC activity of the DepthFirst 1×1 Conv at Cin 40 and 48 (boots 348–350) — closed

Contract `evidence/stage4c2b/contract.md` (frozen `c63c557`, before boot 348). **TA profile 1** (MLEK sys_dram_mid),
FI101 Ethos-U85 1024 MAC, driver runner image `83398c7`, WAIT_WFE, Vela 5.0.0 with MLEK's options, INT8, the 4C-2 1×1
Conv (24×24, Cout 96), graph I/O in DRAM, pass A + B, 1 warm-up + 4 measured RUNs = 30 RUNs. All boots `campaign exit=0`;
board restored to m6 (`RESTORE VERIFIED`), postflight PING of the restored image (state 1), card withdrawn. Raw
`evidence/stage4c2b/raw/`; `python3 host/analysis/stage4c2b.py judge evidence/stage4c2b/raw evidence/stage4c2b/workloads
evidence/stage4c2/raw results/fi101_stage4c2b/predictions.json results/fi101_stage4c2b` → `summary.json`.

## Validity and reference

3/3 outputs **PASS_EXACT** vs the CPU reference, output CRC identical across RUNs, 30/30 RUNs valid. Reference Cin 64:
MAC_ACTIVE = MAC_DPU_ACTIVE = 4,608 in every measured RUN, output sha256 and all commonly constant counters equal to
4C-2 boot 346 → reference gate passed.

## Primary result (each of the 4 measured pass-A RUNs; RUN range 0 for MAC and DPU everywhere)

| Cin | MACs | MAC_ACTIVE (4 RUNs) | MAC_DPU_ACTIVE | MACs / MAC_ACTIVE | MACs / MAC_DPU_ACTIVE | DPU / MAC | OFM ublocks / ublock × IFM steps | H1 | H2 | H3 | H4 | verdict |
| ---: | ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 40 | 2,211,840 | 3,456 ×4 | 3,456 ×4 | **640** | **640** | 1.0 | 576 / 576 | 2,880 | 4,608 | 5,760 | **3,456** | **`MATCH:H4`** |
| 48 | 2,654,208 | 3,456 ×4 | 3,456 ×4 | 768 | 768 | 1.0 | 576 / 576 | **3,456** | 4,608 | 6,912 | **3,456** | `MATCH:H1+H4` (not separable here) |
| 64 (ref.) | 3,538,944 | 4,608 ×4 | 4,608 ×4 | 768 | 768 | 1.0 | 576 / 576 | 4,608 | 4,608 | 9,216 | 4,608 | reference |

## Answer

In the DepthFirst configs tested (Cin 40, 48, 64), **MAC activity did not follow the actual channel count**:
Cin 40 and Cin 48 gave the same MAC_ACTIVE (3,456), and Cin 40 matched only H4. The values are **consistent with the
computation rounded up to a multiple of 16 input channels** (40 → 48: 24·24·96·48 / 768 = 3,456; 48 → 3,456; 64 → 4,608)
at 768 effective MACs per active cycle for the rounded amount, in the tested range. H1 (proportional to actual Cin) and H2
(64-channel amount) and H3 (384 per cycle) were rejected for Cin 40; H1 survives only at Cin 48, where it coincides with H4.

- MAC_DPU_ACTIVE equalled MAC_ACTIVE in every DepthFirst RUN (ratio 1.0), so the effective MACs per DPU-active cycle were
  640 at Cin 40 and 768 at Cin 48 / 64 — the DPU-based 768 of 4C-2 did not hold at Cin 40.
- Not claimed: that the Conv's processing unit is 16 channels, that invalid channels are computed, or any MAC-circuit
  occupancy; that IFM block 64 or the traversal causes anything; any link to the 16-byte memory-write rule A.
  Cin, traversal, IFM block depth and weight order remain unseparated (they switch together between Cin 32 and 40 in the
  compiled set).

## Secondary (whole run and traffic; not used to judge the MAC behaviour)

| Cin | NPU_ACTIVE pass A (range) / pass B | MAC_ACTIVE / NPU_ACTIVE | EXT rd / wr beats | EXT rd trans | SRAM rd beats |
| ---: | --- | ---: | --- | ---: | ---: |
| 40 | 22,455 (101) / 21,782 | 15.4 % | 3,305 / 3,456 | 300 | 3,136 |
| 48 | 22,331 (887) / 22,766 | 15.5 % | 3,929 / 3,456 | 327 | 3,520 |
| 64 | 24,554 (449) / 24,070 | 18.8 % | 5,177 / 3,456 | 429 | 4,288 |

- 40 → 48: pass A −0.6 %, pass B +4.5 % — opposite directions → `UNRESOLVED`.
- 48 → 64: +10.0 % / +5.7 % → `NOT_PROPORTIONAL_TO_MAC` (×1.33 MACs).
- Cin 40's IFM pixel stride (40 B) is not a multiple of 16; its traffic and time are not compared as a MAC effect.
- RELU6-cap saturation 116 / 244 / 637 elements (base OFM scale kept).

## Status

Stage 4C-2b closed (owner): no further channels, DW, FC, spatial size or placement experiments started. Remaining
questions (not pursued): whether the rounding is to 16 or to another granularity at other Cin values (only 40 tested
below a multiple of 16 under DepthFirst); whether PartKernel configs (Cin 16, 32 — both multiples of 16) round the same
way; what sets the step between 384 and 768 MACs per active cycle across the schedule switch.
