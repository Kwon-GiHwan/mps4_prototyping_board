# Stage 2B-2 — activity and stalls per operator-type group (frozen 2026-11-04, before boot 212)

Plan: `docs/plan/stage2_plan.md` (2B-1 groups, 2B-2 measurement). Owner 2026-11-03: "큰 작업 말고는 끝날 때까지 … 알아서
작업하자". **TA profile 1** (MLEK sys_dram_mid) in every boot. Cost clock = NPU cycles (S0-3). All seven MLEK models.

Basis: 2B-0b (`results/fi101_stage2_mask/`): the mask does not disturb execution (7/7) but a split loses counts
(`MASK_NOT_ADDITIVE`; always a deficit, 12–1,980 cycles per split). The 2B-0b contract read that outcome as "Stage 2B
needs another path"; the alternatives (split streams, STOP+IRQ) remove the overlap between operators, i.e. change
execution. This contract keeps the mask and **measures the loss**: the unattributed share is a preregistered quantity,
and the group comparisons are judged only where it is small.

## Groups (2B-1)

Group = kernel-operation type in the command stream (`host/lib/cms.py kernel_types`): CONV, DEPTHWISE, POOL,
ELEMENTWISE, RESIZE. Each kernel op belongs to exactly one group; a group's blob counts its ops from setup to
operation instruction (`cms.gate_ops`; consecutive ops share one window). Vela operators are not used as groups:
the stream has more kernel ops than Vela has operators (stripes; mobilenet 69 → 208), and the mapping is not built.
FullyConnected compiles to CONV; Vela's MemoryCopy/Quantize/Relu6 appear as POOL/ELEMENTWISE ops.

## Image and blobs

- Image `d0cd4775` (as 2B-0/2B-0b). Blobs from the fi101_s013 blob of each model by `make_group_blobs.py`: `m_all`
  (byte-identical to the 2B-0b `m_all`) and one `g_<TYPE>` per type present. Digests (first 12 hex), windows = number of
  enable windows:

| model | m_all | g_CONV | g_DEPTHWISE | g_POOL | g_ELEMENTWISE | g_RESIZE |
| --- | --- | --- | --- | --- | --- | --- |
| kws | `5f1a7dc75647` | `26777ef595fe` (8 ops, 7 w) | `c98f177a363e` (5, 5) | `c56ca50523aa` (1, 1) | — | — |
| ad | `7175ee5bbd18` | `984505b87b61` (8, 7) | `0cd987006534` (5, 5) | `0d7a4627afe7` (1, 1) | — | — |
| rnnoise | `ce47cdff0b61` | `acdec4156485` (9, 7) | — | `f83a2b574a63` (15, 6) | `e8023e1cc59a` (24, 3) | — |
| vww4 | `db2a354cb503` | `4f7dc31e61a8` (39, 29) | `556dc49f80b8` (17, 17) | `63319ebd34b9` (19, 11) | `baa7b821d332` (10, 10) | — |
| yolo | `89c350e789dc` | `713f63dac838` (56, 47) | `d7513dda7413` (28, 28) | `f6a8a043df0d` (9, 3) | `ec967a5135d7` (18, 18) | `bbbe4d815c53` (1, 1) |
| mobilenet | `6673ec377dca` | `675c29863043` (113, 67) | `1cbb504d3eed` (57, 55) | `fc93e0864081` (3, 3) | `7ffdb936860c` (35, 12) | — |
| wav2letter | `5388e4b951fe` | `57032fe7082f` (11, 1) | — | `605fac45d702` (3, 2) | `f62d1850905c` (25, 2) | — |

## Boots (`plan.txt`): boots 212–243, sets A, C, D (`ids.txt`, from `config/fi101_passes.txt`), 10 RUNs per set, 2 warm-up

One boot per (model, arm), models in the order kws, ad, rnnoise, vww4, yolo, mobilenet, wav2letter; arms in name order.
A boot that fails before any RUN is re-run once after the campaign into the same root (amendment, rules unchanged).

## Rules (preregistered; `host/analysis/s2_groups.py`, tests `host/tests/test_s2_groups.py`, 37 mutations RED)

Validity as fi101_s013 (model mode incl. `knobs_honoured`); an invalid measured RUN or missing boot makes the
affected verdicts `UNPROVEN`. Medians over measured RUNs.

1. **Partition, per model and PMU set** (descriptive verdict): for every event (NPU cycles excluded), sum of the
   groups' medians = `m_all` median within max(1 %, the width of `m_all`'s RUNs); events with width > 5 % not judged.
   `PARTITION_HOLDS` / `PARTITION_LEAKS` / `UNPROVEN`.
2. **Deficit** d = 1 − Σ groups' median `npu_active` / `m_all` median `npu_active` (set A). Reported per model.
3. **H1** (models with CONV and DEPTHWISE groups): median over RUNs of `mac_active / npu_active` (set A) of the
   DEPTHWISE group < the CONV group's → `DW_LOWER`, else `DW_NOT_LOWER`.
4. **H2** (models with a DEPTHWISE group and Vela depthwise MACs): q = (DEPTHWISE `npu_active` / Σ groups'
   `npu_active`) / (Vela DepthwiseConv2D MACs / all Vela MACs, `results/fi101_stage1/vela_block_fill_per_op.csv`);
   `DW_COSTLY` if q ≥ 2, else `DW_NOT_COSTLY`.
5. H1 and H2 are judged only if |d| ≤ 5 %; otherwise `UNPROVEN`. Overall per hypothesis: the common verdict of the
   judged models, `MIXED` if they differ, `UNPROVEN` if any applicable model is.
6. Per group and set: every event / `npu_active` (same RUN), reported (`groups.csv`) — the Stage 2A table per group.

## What the outcomes mean

- d small (|d| ≤ 5 %): the groups account for the inference's NPU-active time; group ratios describe where each
  operator type spends its time. d large: overlapped execution across type boundaries is a large share of the time
  and has no single owner; the group numbers are lower bounds.
- H1 `DW_LOWER`: depthwise ops keep the MAC array busy a smaller share of their time than convolutions.
  H2 `DW_COSTLY`: depthwise ops take at least twice the share of NPU-active time that their share of MACs would give.
- Partition per set shows whether memory-stall (C) and unit-stall (D) events are gated by the mask like set A.

## Limits

- Boundary cycles: a group's count misses cycles of overlapped execution at its window edges (2B-0b); `PMCCNTR`
  (NPU cycles) in a group run counts only while gated and is reported, not summed.
- Type groups mix very different operators (e.g. POOL holds Vela MemoryCopy in rnnoise/vww4). Not Vela operators.
- vww4, yolo, wav2letter OFM correctness not claimed (MLEK goldens pending).

## Note 1 (2026-11-04, during the campaign; rules unchanged) — group composition

The section "Groups (2B-1)" said the Vela→stream mapping "is not built" and quoted "mobilenet 69 → 208". The mapping
was built afterwards from Vela's debug database (`results/fi101_stage2_groups/vela_op_map/`): mobilenet has 65 TFLite
operators → 91 Vela optimised operators → 208 stream kernel ops (69 was the `--verbose-schedule` count). It describes
what each group holds (e.g. ELEMENTWISE in wav2letter is entirely the Softmax decomposition); groups, blobs and rules
are unchanged.

## Results (recorded 2026-11-05, after boots 212–243) — `results/fi101_stage2_groups/`

960/960 RUNs valid. |deficit| ≤ 1.9 % in all seven. H1 `DW_NOT_LOWER` (5/5 applicable), H2 `MIXED` (`DW_COSTLY` kws,
ad, vww4, mobilenet; `DW_NOT_COSTLY` yolo). Post-hoc attribution check: ad's CONV group shows a MAC efficiency of 2.85
(> 1, impossible) while the set-A partition holds → counts are conserved but assigned to the wrong groups; the
group windows do not follow the operators' execution. H1/H2 stand as computed but are not read as operator-type
findings.
