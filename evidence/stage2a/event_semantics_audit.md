# Stage 2A — event semantics audit (2026-10-14, before any Stage 2A contract or boot)

Guide §4 asks for this audit for the two driver-only events in the Stage 2A set before the contract is frozen. The
guide names the output `evidence/stage2/event_semantics_audit.md`; it is kept here with the other Stage 2A outputs
(guide §12). This is a document and source check only: no board run, no build, no data.

## Sources

| key | what | digest |
| --- | --- | --- |
| D | `ethosu85_interface.h`, Arm ethos-u-core-driver commit `03567073` (2025-11-05) — the copy MLEK b2c0bb2 builds against (`/opt/arm/ml-embedded-evaluation-kit/dependencies/core-driver`); the three other copies in the container are byte-identical | sha256 `8a5cbe76…` |
| T85 | Ethos-U85 TRM 102685 r0p0, PMEVTYPER EV_TYPE table, as extracted in `docs/reference/trm_events_110.json` (`docs/reference/ETHOS_U85_PMU_REFERENCE.md`) | per that document |
| T55 | Ethos-U55 TRM 102420 r2p0 issue 02 (public PDF) | pdf sha256 `8740573e…` |
| B9 | Board record on branch `refactor/unified-mlek-campaigns`, `evidence/pmu_events/boot9/PER_EVENT.md`: vendor `test_u85` convolution, 3 RUNs, **TA untouched** (not a Stage 1/2 condition; quoted only as "does it count at all") | — |
| R | Runner: `firmware/patches/patch_pmu_events_source.py` writes `PMEVTYPER<i> = event_codes[i] & 0x3FF` | — |

Excerpts with line numbers: `audit/driver_excerpts.txt` (D, and the command-stream decode), `audit/u55_trm_excerpts.txt` (T55).
Decoder: `audit/cms_ops.py` (opcode names taken from D, not hard-coded).

## The two events

### 55 `mac_stalled_by_ib`

1. **Definition location.** D `enum pmu_event` line 797 `MAC_STALLED_BY_IB = 55` (also `PMU_EVENT_MAC_STALLED_BY_IB`
   line 1437, and the X-macro list line 24387). T85 marks 55 `Reserved`. T55 Table 4-81 does not list 0x37.
2. **ID written to the register.** 55 (0x37). R writes the id unchanged into the 10-bit EV_TYPE field. EV_TYPE is a
   plain RW field on this silicon (Tier A: all 1024 values read back), so the write itself proves nothing about counting.
3. **Cycle-counting?** Not stated anywhere. Inferred, see 4.
4. **Condition / meaning.** D defines a `MAC_STATUS` register whose bit fields carry the same names as the MAC
   events, in the same order, with the same gaps:

   | MAC_STATUS bit | field (D comment) | pmu_event id |
   | --- | --- | --- |
   | 0 | `mac_active` — "Valid block command and not stalled" | 48 |
   | 1–2 | reserved | 49–50 absent from the enum |
   | 3 | `mac_dpu_active` — "At least one DPU is active" | 51 |
   | 4 | `mac_stalled_by_w_or_acc` — "MAC stalled by WB or AB (not IB)" | 52 |
   | 5 | `mac_stalled_by_w` — "MAC stalled by WB (not IB)" | 53 |
   | 6 | `mac_stalled_by_acc` — "MAC stalled by AB (not IB)" | 54 |
   | 7 | `mac_stalled_by_ib` — **"MAC stalled by IB"** | 55 |

   `AO_STATUS` follows the same rule: bit 0 `ao_active` ↔ 64, bits 3–8 ↔ 67–72. The two documented members (48 and 51)
   have T85 texts that match the status comments ("MAC is doing block traversal. Valid blk_cmd and not stalled";
   "At least one dot product unit is active…"). IB is the MAC input buffer: T85 event 177 `ecc_mac_ib` is "ECC event in
   MAC input buffer RAM". Reading: **cycles in which the MAC has a block command but is stalled by its input buffer.**
   What remains inference: that the PMU event counts the MAC_STATUS bit-7 level once per cycle (no source states the
   event ↔ status-bit rule), and whether "stalled by IB" means "IB has no valid data yet" or some other IB condition.
5. **Overlap.**
   - With 48 `mac_active`: disjoint by the D comment (active = "not stalled"). This can be checked on data:
     `mac_active + mac_stalled_by_ib ≤ npu_active` per RUN.
   - With 52–54: disjoint by the "(not IB)" comments. An IB stall is not counted as a W/ACC stall. 52–54 are not in
     the Stage 2A set.
   - With 51 `mac_dpu_active`: unknown.
   - With 35 `npu_active`: contained, presumably; the MAC can only stall while the NPU runs.
   - With 64/80/81 (other units): may coincide in any cycle.
6. **Counts on the board?** B9: COUNTED_NONZERO (332 / 342 / 337).

**Verdict 55: condition confirmed at source level (D status-register comment); event ↔ status-bit mapping and
per-cycle counting are a structural inference.**

### 33 `cc_stalled_on_blockdep`

1. **Definition location.** D line 790 `CC_STALLED_ON_BLOCKDEP = 33` (also lines 1430, 2676 and 24380). T85 marks 33
   `Reserved`. T55 Table 4-81 does not list 0x21.
2. **ID written.** 33 (0x21), unchanged by R.
3. **Cycle-counting?** Not stated anywhere. **No status-register bit** carries this name in D. Every occurrence of
   "blockdep" in D is listed in `audit/driver_excerpts.txt`: the enum, the string table, the `BLOCKDEP` register
   "State managed by NPU_SET_BLOCKDEP", and the command `npu_set_blockdep_t`. So the MAC/AO structural argument is not
   available.
4. **Condition / meaning.** Only the name is defined. Supporting documented pieces:
   - "CC" is the Central Control: T55, "the main control unit … maintains synchronization, and handles data
     dependencies".
   - D: `NPU_SET_BLOCKDEP` is the "Block number of blocks dependency between kernel operations".
   - T55: "IFM block read n in the kernel does not start until all OFM block writes of the previous kernel operation,
     except max(k−n, 0), are complete and written to memory".

   The reading "cycles in which the CC holds back a kernel operation because of that dependency" comes from the name
   alone. No source states the condition, whether it counts cycles or events, or which unit stalls.
5. **Overlap.** Unknown with every other event.
6. **Counts on the board?** B9: COUNTED_ZERO (0 / 0 / 0). That record carries no attribution: zero is not "unsupported".
7. **Where it can occur in Stage 2A.** The three command streams were decoded with `audit/cms_ops.py`; their cms
   sha256 equal the manifests. Each is
   `DMA_START, BLOCKDEP(0), DMA_WAIT(0), <OP>, DMA_START, BLOCKDEP(7), DMA_WAIT(0), <OP>, STOP`, with OP = CONV
   (conv3x3, pw1x1) or DEPTHWISE (dw3x3). So each operator is two kernel operations, and only one kernel-to-kernel
   boundary carries a dependency (k = 7). Whatever 33 counts, here it can only reflect that one boundary.

**Verdict 33: meaning NOT confirmed at source level.** Per guide §4 it may not be used as attribution evidence.
Whether to measure it at all goes back to the owner, and the guide §13 stop condition "driver-only event의 의미를
확인하지 못함" applies.

## The six TRM-documented events (for the contract)

| id | name | T85 text | overlap note |
| --- | --- | --- | --- |
| 35 | npu_active | NPU in running state | container of all others (assumed; R5/R6s check it per RUN) |
| 48 | mac_active | MAC is doing block traversal. Valid blk_cmd and not stalled | disjoint from MAC stall bits (D) |
| 51 | mac_dpu_active | At least one dot product unit is active (≥ 1 valid weight and activation pair) | relation to 48 not stated: a DPU may be active in a cycle where 48 is not, so `mac_dpu_active / mac_active` may exceed 1 and is not a sub-ratio |
| 64 | ao_active | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled | other unit; may coincide with MAC events |
| 80 | wd_active | WD is decoding weight stream. Valid blk_cmd and not stalled | other unit |
| 81 | wd_stalled | WD stalled on lack of weight stream data or lack of free WD buffer space | covers two different causes (supply vs. MAC back-pressure; D splits them as 83–85); disjoint from 80 presumably |

## Status

Stopped here, before writing the Stage 2A contract: event 33 failed the source-level check. No blob, image, deploy or
boot was made for Stage 2A.

## Owner decision (2026-10-14, after this audit)

- **Event 33** is left out of Stage 2A, and event **52** `mac_stalled_by_w_or_acc` takes its slot. 33 is kept for a
  later dependency analysis once its meaning is confirmed.
- **Events 52 and 55** are labelled driver-derived. They are auxiliary evidence: neither alone can give `SUPPORTED`,
  and the most either can give is `PARTIAL_SUPPORT`.
- **`mac_active + mac_stalled_by_ib ≤ npu_active`** is a validity gate only if the exclusivity of the two states is
  confirmed by source or TRM. It is not confirmed: only the driver comments state it, and the event ↔ bit mapping is
  inferred. So it is recorded as a diagnostic sanity check only.

Recorded in `contract.md` §2 and §4.
