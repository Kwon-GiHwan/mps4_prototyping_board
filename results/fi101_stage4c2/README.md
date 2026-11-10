# Stage 4C-2 — MAC activity of the 1×1 Conv vs input channels (boots 344–347, 2026-11-10/11 UTC board clock)

Contract `evidence/stage4c2/contract.md` (frozen `a064593`, before boot 344); plan `docs/plan/stage4c2_plan.md`.
**TA profile 1** (MLEK sys_dram_mid), FI101 Ethos-U85 1024 MAC, driver runner image `83398c7` (boot `1b5c0adb`, bram
`4f592f24`), WAIT_WFE, Vela 5.0.0 with MLEK's options, INT8, graph I/O in DRAM, pass A + pass B, 1 warm-up + 4 measured
RUNs each = 40 RUNs. All boots `campaign exit=0`; board restored to m6 (`RESTORE VERIFIED`), postflight PING of the
restored image (state 1), card withdrawn. Raw `evidence/stage4c2/raw/`; table `stage4c2_table.csv`; static
`static.json`, compile table `stage4c2_compile_table.csv`; `python3 host/analysis/stage4c2.py judge evidence/stage4c2/raw
evidence/stage4c2/workloads evidence/stage4/raw results/fi101_stage4c2` → `summary.json`.

## Validity

4/4 configs `VALID`: outputs **PASS_EXACT** vs the CPU reference, output CRC identical in every RUN, 40/40 RUNs valid.
Base (Cin 16) reproduced Stage 4 boot 330: same output sha256, all 10 commonly constant counters equal. Saturation at the
RELU6 cap rises with Cin under the base's OFM scale (1 / 39 / 637 / 2,963 of 55,296 elements): recorded, inputs not changed.

## Table (pass A medians unless noted; MAC_ACTIVE / MAC_DPU_ACTIVE had RUN range 0 everywhere)

| Cin | MACs | kernels / traversal | OFM block (IFM block) / ublock | OFM ublocks | ublock × IFM steps | MAC_ACTIVE | MAC_DPU_ACTIVE | MAC_ACTIVE / ublock | MAC_DPU / ublock | MACs / MAC_ACTIVE | MAC_ACTIVE / NPU_ACTIVE | NPU_ACTIVE (range) A / B | EXT rd / wr beats | SRAM rd / wr beats | output |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| 16 | 884,736 | 2 / PartKernel | 6×12×96 (16) / 2×2×32 | 576 | 576 | 2,304 | 1,152 | 4.0 | 2.0 | 384 | 10.7 % | 21,480 (1,299) / 21,065 | 1,437 / 3,456 | 2,016 / 252 | PASS_EXACT |
| 32 | 1,769,472 | 2 / PartKernel | 6×12×96 (16) / 2×2×32 | 576 | 1,152 | 4,608 | 2,304 | 8.0 | 4.0 | 384 | 18.0 % | 25,623 (407) / 25,783 | 2,725 / 3,456 | 3,104 / 388 | PASS_EXACT |
| 64 | 3,538,944 | 2 / **DepthFirst** | 6×12×96 (**64**) / 2×2×32 | 576 | 576 | 4,608 | 4,608 | 8.0 | 8.0 | **768** | 19.1 % | 24,183 (997) / 24,515 | 5,177 / 3,456 | 4,288 / 536 | PASS_EXACT |
| 128 | 7,077,888 | 2 / DepthFirst | 6×12×96 (64) / 2×2×32 | 576 | 1,152 | 9,216 | 9,216 | 16.0 | 16.0 | 768 | 30.0 % | 30,728 (396) / 30,830 | 10,230 / 3,456 | 7,848 / 981 | PASS_EXACT |

Kernel-level static structure (both kernels of every config): OFM slices 16 + 80, IFM depth = Cin, ACC_INPUT_RESET
(no accumulation across kernels); OFM ublocks 144 + 432; IFM depth steps 1/2/1/2 (`static.json`).

## Pairs (Stage 4 pair rule on NPU_ACTIVE; pass A primary, pass B check)

| pair | class | MACs | MAC_ACTIVE | MAC_DPU_ACTIVE | NPU_ACTIVE pass A / pass B | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 16 → 32 | `SAME_SCHEDULE` | ×2 | ×2.00 | ×2.00 | +19.3 % / +22.4 % | `NOT_PROPORTIONAL_TO_MAC` |
| 32 → 64 | `SCHEDULE_CHANGED` (PartKernel → DepthFirst, IFM block 16 → 64) | ×2 | **×1.00** | ×2.00 | **−5.6 % / −4.9 %** | `NOT_PROPORTIONAL_TO_MAC` |
| 64 → 128 | `SAME_SCHEDULE` | ×2 | ×2.00 | ×2.00 | +27.1 % / +25.8 % | `NOT_PROPORTIONAL_TO_MAC` |

Both passes moved in the same direction in every pair. Four RUNs within one boot per config: no cross-boot or
cross-input reproducibility is claimed.

## Answers

**1. MAC activity and effective throughput as Cin 16 → 32 → 64 → 128.** Within one schedule MAC_ACTIVE grew exactly in
proportion to the MACs (16 → 32: ×2; 64 → 128: ×2), so the effective MACs per MAC-active cycle stayed constant (384 with
PartKernel / IFM block 16; 768 with DepthFirst / IFM block 64). At the schedule change (32 → 64) MAC_ACTIVE stayed at
4,608 while the MACs doubled: the effective MACs per active cycle doubled (384 → 768). MAC_DPU_ACTIVE doubled at every
step; its ratio to MAC_ACTIVE was 0.5 under PartKernel and 1.0 under DepthFirst (activity counts; not an occupancy).

**2. The 4-cycles-per-ublock relation.** MAC_ACTIVE / OFM ublocks = 4 held only at Cin 16 (the condition it was read
from): 8 at Cin 32 and 64, 16 at Cin 128, since the OFM ublock count (576) does not change with Cin. Normalised by
OFM ublocks × IFM depth steps it is 4 under PartKernel (Cin 16, 32) and 8 under DepthFirst (Cin 64, 128). These are
normalisations of whole-run counts by quantities computed from the artifacts — they describe the four configs, they
are not a measured per-ublock time or a hardware constant, and a value read from the data is not a validated model. The
change from 4 to 8 coincides with the traversal change (PartKernel → DepthFirst), IFM block depth 16 → 64, weight order
part-kernel-first → depth-first; which of these, if any, sets the rate is not separated here.

**3. Computation vs whole NPU cost.** Not the same direction in general. Within one schedule the MAC-active throughput
was unchanged while NPU_ACTIVE rose far less than the MACs (+19 %, +27 % for ×2 MACs), so the MAC share of NPU_ACTIVE
rose (10.7 % → 18.0 %; 19.1 % → 30.0 %). At the schedule change the throughput per active cycle doubled and NPU_ACTIVE
fell slightly (−5.6 % / −4.9 %) while the MACs doubled — there both improved together. What makes up the non-MAC part of
NPU_ACTIVE is not measured; it is not assigned to memory waiting.

Descriptive (supporting, not modelled): EXT read beats grew with the IFM and weights (1,437 → 2,725 → 5,177 → 10,230),
EXT write beats stayed 3,456 (same OFM); EXT read transactions were 171 / 2,339 / 429 / 2,952 — higher under PartKernel
at Cin 32 than under DepthFirst at Cin 64 — reported, not explained.

## Limits and next question (proposal only)

One shape family (1×1, 24×24, Cout 96), four Cin values, one boot each, graph I/O in DRAM; schedule and Cin not separated
at the 32 → 64 step. No DW / FC / spatial changes, no placement or TA change, nothing about the seven models' causes.

Proposal (not started): **is the 384 → 768 MACs-per-active-cycle step tied to Vela's schedule (DepthFirst, IFM block 64)
rather than to Cin itself?** — e.g. Cin 48 (and/or 40, 56) to find where Vela switches traversal and whether the
throughput per active cycle switches with it, without forcing a schedule.
