# Stage 4 — proposals for 4C / 4D (not started; each needs its own contract and approval)

From Stage 4A/4B (`stage4_analysis.md`, TA profile 1). Proposals and open hypotheses only.

## Open hypotheses

| id | hypothesis | why open |
| --- | --- | --- |
| H4-a | Channel counts that are not a multiple of 16 make NHWC rows in DRAM cost about twice the beats (seen: Cout 95 writes, DW 143 reads and writes) | one shape each; mechanism `UNVERIFIED`; Cin 15 did not show it |
| H4-b | The penalty belongs to DRAM-resident feature maps and disappears when the maps are in SRAM (as inside the models) | Stage 4 placed every IFM/OFM in DRAM |
| H4-c | MAC time is quantized by a channel granularity (≥ 16), so per-MAC cost rises step-wise below a boundary | only −1 steps from 16/96/144/288 measured |
| H4-d | DWConv's fixed 128 MACs per active cycle contributes to low MAC-cycle efficiency in yolo/vww4/mobilenet | shown in isolation only |
| H4-e | Large convolutions (AD, Wav2Letter) reach high MAC activity because MAC time grows faster than fixed and memory costs | the 1×1 Conv tested had small Cin and 10.9 % MAC activity |
| H4-f | Vela 5.0.0's memory estimate for DRAM feature maps overstates the board's cost and misses the alignment cost | 8 shapes |

## Stage 4C — scaling (priority order)

1. **Channel sweep across boundaries** (H4-a, H4-c): Conv 1×1 and DW 3×3 at one H×W with C ∈ {128, 136, 143, 144, 152, 160}
   (and Cout for Conv); look for the beat doubling and MAC_ACTIVE steps at 8- vs 16-channel granularity.
2. **Cin scaling for Conv** (H4-e): Cin ∈ {16, 32, 64, 128} at fixed Cout and H×W — MACs per MAC_ACTIVE cycle (384 at
   Cin 16) and MAC activity share.
3. **Spatial scaling** (H4-e): H×W ∈ {12², 24², 48²} for the Conv base and DW base — fixed vs size-proportional costs.

## Stage 4D — data size and placement (priority order)

1. **Same operators with feature maps in SRAM** (H4-b): the Stage 4 base/−1 pairs compiled so the IFM/OFM sit in SRAM
   (e.g. a preceding/following layer inside a tiny graph, or Vela memory options), keeping Vela 5.0.0 and the TA profile.
2. **Weight size for FC** (rnnoise link): FC with weights 8–128 KB to separate weight fetch from MAC time; FC repeat count
   (several FCs in one graph) to reduce the 7–9 % RUN range of short runs.
3. **Vela estimate check** (H4-f) on the 4C/4D shapes, with the same scope caveats.

Constraints to carry over: driver runner, TA profile 1, 1 warm-up + 4 measured RUNs, CPU-reference output check
(PASS_EXACT / ≤ 1 LSB, owner rule for isolated operators), at most the configurations a contract names.
