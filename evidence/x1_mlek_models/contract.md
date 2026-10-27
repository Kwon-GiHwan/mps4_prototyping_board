# x1 — exploratory NPU utilization of the remaining MLEK models (frozen 2026-10-21, before boot 78)

**TA state: profile 1 (MLEK `ta_config_u85_sys_dram_mid`), read back every RUN.**

Owner request (2026-10-21): measure the MLEK models missing from `results/npu_utilization_mps4/` quickly, NPU
utilization items only, and add them in the same format. This is **exploratory**, outside the Stage 1 contract and
outside amendment 2: no MLEK FI101 golden is produced for these models. Every result is labelled `x1` and never
mixed into a Stage 1 table without that label.

## Scope

| boot | workload | blob | N_MAC |
| --- | --- | --- | --- |
| 78 | vww4_128_128_INT8 | `b7c15f01…` | 18,828,800 |
| 79 | wav2letter_pruned_int8 | `5b8c9d06…` | 3,491,098,000 |

`NOT_EXECUTABLE` with the current packer (1 input / 1 output only; `pack_vela_workload.py:87` path, custom op
5 in / 1 out): rnnoise_INT8 (custom op 8 in / 5 out), yolo-fastest_192_face_v4 (5 in / 2 out). Not measured.

## Protocol (unchanged from Stage 1)

- Blobs packed with `--profile config/mlek_baseline.json` (Vela 5.0.0 MLEK options, `Ethos_U85_SYS_DRAM_Mid_1024`,
  TA profile 1, knobs as in Stage 1). Both Vela outputs equal MLEK's own (sha256 equal to the FVP campaign's
  `vela_sha256`: vww4 `637711c9…`, wav2letter `4c5b6402…`).
- Image APP `2c2fa435…` (same as Stage 1 / 2A), event set `config/stage1_ids.txt`, 35 RUNs per boot, RUNs 6–35
  measured, one boot per workload.
- N_MAC: `host/container/workload_meta.py` on the original MLEK tflite (`*.meta.json` here).
- Analysis: `host/analysis/stage1.py … --add x1 <root> evidence/x1_mlek_models/manifest.x1.json`; metrics and
  definitions as in Stage 1.

## Correctness and status

Golden = tflite_runtime OFM of the original model on the seed-1 IFM (the stage-0 R3 rule). Gate as in Stage 1
(B1–B4, R1–R5, R6s).
- Gate `BASELINE_PASS` → status `VALID (x1)`.
- Gate `BASELINE_FAIL` only on R3 (OFM differs from tflite_runtime) → the counters are kept and reported as
  `UNRESOLVED (x1)`, with the mismatch count, as the `s1` operators were. No MLEK golden is made to rescue them in
  this pass.
- Any other failure → `UNRESOLVED (x1)`, not reported as a utilization value.

## Amendment 1 (2026-10-21, owner request, recorded before boot 80) — rnnoise and yolo-fastest

**TA state: profile 1, unchanged.** The owner asked to make the runner accept the two `NOT_EXECUTABLE` models and
measure them. Commit `f21cd27` adds PMWL header version 4 (an IO table: every IFM copied, every OFM poisoned and
compared, entry 0 = the header words). This changes the runner image, so it is a change of measurement condition:

| | Scope above (boots 78–79) | This amendment (boots 80–83) |
| --- | --- | --- |
| image APP | `2c2fa435…` | `26f6129a…` (VECTORS, DDR unchanged) |

Blobs (`manifest.x1.json`; both Vela outputs equal MLEK's own, sha256 = the FVP campaign's `vela_sha256`):

| boot | workload | blob | IFMs / OFMs | purpose |
| --- | --- | --- | --- | --- |
| 80 | kws_micronet_m | `f11271cb…` (Stage 1 boot 65 blob, v3) | 1 / 1 | control: the new image on an old blob |
| 81 | rnnoise_INT8 | `5c3990a9…` (v4) | 4 / 5 | measurement |
| 82 | yolo-fastest_192_face_v4 | `1f71e475…` (v4) | 1 / 2 | measurement |
| 83 | yolo-fastest_192_face_v4 | `13a9cd7f…` = boot 82's blob with golden byte 10 of OFM 1 raised by 5 | 1 / 2 | negative control |

Golden: tflite_runtime OFMs of the original model on seed-1 IFMs (one generator, IO-table order). Rules:

- **Control (boot 80)** passes only if the gate is `BASELINE_PASS`, `mac_active` is 56,450 in every measured RUN and
  the `npu_active` median lies in Stage 1 boot 65's range [89,884, 92,356]. Otherwise rnnoise and yolo results are
  `UNRESOLVED (x1)` whatever their own gate says.
- **Negative control (boot 83)** passes only if every RUN reports `ofm_mismatch_count` 1, `ofm_max_abs_diff` 5,
  `ofm_first_mismatch` 2602 (= 2,592 bytes of OFM 0 + 10) and `vendor_rc` 0 (the vendor's memcmp sees OFM 0 only).
  Otherwise the OFM comparison of version 4 is unproven and boots 81–82 are `UNRESOLVED (x1)`.
- Boots 81–82: status as in "Correctness and status" above. rnnoise's state IFMs and OFMs share arena bytes
  (Vela places them in place); the OFM poison is overwritten there by the IFM copy, as for every earlier
  overlapping IFM/OFM.

## Amendment 2 (2026-10-27, owner decisions, recorded before boot 80) — restructured runner, 10 RUNs, all remaining boots

**TA state: profile 1, unchanged.** Status of what came before:
- boot 78 (vww4, image `2c2fa435`, 35 RUNs): completed, 35/35 valid; kept on the board host, not analysed here.
- boot 79 (wav2letter): refused `RULE_RUN_TRANSPORT` — the LOAD_MODEL_END reply did not arrive within the fixed
  10 s while the runner CRC'd the 14.5 MB blob. Host fix: the wait scales with the blob (`load_end_timeout`,
  4 s/MiB, floor 10 s; wav2letter 55 s).
- Amendment 1 boots 80–83 on image `26f6129a` were never run: the owner chose to restructure the firmware first.

Owner decisions (2026-10-27): firmware restructured into purpose modules with the Arm selftest path unchanged
(commit `369fb88`); new measurements use profile `config/mlek_r10.json` = 10 RUNs, RUNs 1–2 warm-up, 8 measured.
Every boot below therefore runs on the **restructured image APP `38ce118c…`** (VECTORS `589f8b88…`, DDR unchanged)
with 10 RUNs, which replaces the image and RUN count above. Analysis: `host/analysis/stage1.py … --profile
config/mlek_r10.json`.

| boot | workload | blob | purpose |
| --- | --- | --- | --- |
| 80 | kws_micronet_m | `f11271cb…` (Stage 1 boot 65) | control |
| 81 | ad_medium_int8 | `55fa924c…` (Stage 1 boot 66) | control |
| 82 | mobilenet_v2_1.0_224_INT8 | `0d51cf9e…` (Stage 1 boot 67, MLEK input) | control |
| 83 | yolo-fastest_192_face_v4 | `13a9cd7f…` (OFM 1 golden byte 10 + 5) | negative control |
| 84 | vww4_128_128_INT8 | `b7c15f01…` | measurement |
| 85 | rnnoise_INT8 | `5c3990a9…` (v4) | measurement |
| 86 | yolo-fastest_192_face_v4 | `1f71e475…` (v4) | measurement |
| 87 | wav2letter_pruned_int8 | `5b8c9d06…` | measurement |

- **Controls (80–82)** pass only if each gate is `BASELINE_PASS` under `mlek_r10` against the Stage 1 manifest entry,
  every measured RUN's `mac_active` and four beat counters equal Stage 1's (kws 56,450 / 22,664 / 17,760 / 15,815 / 1;
  ad 93,672 / 70,538 / 41,888 / 44,084 / 1; mobilenet 574,795 / 672,948 / 401,443 / 301,217 / 47,887), and the
  `npu_active` median lies in Stage 1's range (kws [89,884, 92,356]; ad [144,372, 147,346]; mobilenet
  [1,445,735, 1,450,449]). Any failure: the restructured image is not shown equivalent and boots 84–87 are
  `UNRESOLVED (x1)`.
- **Negative control (83)**: as in amendment 1 (every RUN `ofm_mismatch_count` 1, max 5, first 2602, `vendor_rc` 0).
- Boots 84–87: status as in "Correctness and status" above.

## Amendment 3 (2026-10-27, owner decisions, recorded before boot 88) — negative control redone, wav2letter retried

**TA state: profile 1, unchanged; image `38ce118c…`, profile `mlek_r10` (10 RUNs) as in amendment 2.**

Results of amendment 2 (boots 80–87, analysis in `analysis_a2/`):
- Controls 80–82 passed every rule: the restructured image reproduces Stage 1.
- Boot 83 (yolo negative control) is **not interpretable**: its rule assumed the real output equals the golden, but
  yolo's output already differs from tflite_runtime (955 bytes, max 7, first 4 in boot 86), so the injected byte
  cannot be told apart. By the amendment-1 rule the version-4 OFM comparison stays unproven, so rnnoise (85) and yolo
  (86) are `UNRESOLVED (x1)`. vww4 (84): 1 OFM byte off by 1 LSB from tflite_runtime → `UNRESOLVED (x1)`.
- Boot 87 (wav2letter): LOAD_MODEL_END now answered, but no RUN_COMPLETE within the host's fixed 120 s.

| boot | workload | blob | purpose |
| --- | --- | --- | --- |
| 88 | rnnoise_INT8 | `eff2ba10…` = boot 85's blob with byte 0 of the LAST OFM's golden raised by 5 (int8 −87 → −82) | negative control |
| 89 | wav2letter_pruned_int8 | `5b8c9d06…` (unchanged) | measurement, RUN wait 900 s (`RUN_TIMEOUT`) |

- **Boot 88 passes** only if every RUN reports `ofm_mismatch_count` 1, `ofm_max_abs_diff` 5, `ofm_first_mismatch`
  169 (= 24 + 1 + 48 + 96, the four earlier OFMs) and `vendor_rc` 0. rnnoise's real output matched its golden in
  every RUN of boot 85, so exactly the injected byte must be caught. Pass → the version-4 comparison of every OFM is
  shown on the board, and boot 85 becomes `VALID (x1)`. Fail → boots 85–86 stay `UNRESOLVED (x1)`.
- **Boot 89**: the host waits up to 900 s for each RUN_COMPLETE. A record that arrives answers "slow"; none answers
  "stalled". Status as in "Correctness and status".

## Results of amendment 3 (recorded 2026-10-27, after boots 88–89)

- **Boot 88 (rnnoise negative control): PASS.** Every RUN: `ofm_mismatch_count` 1, `ofm_max_abs_diff` 5,
  `ofm_first_mismatch` 169, `vendor_rc` 0, read seam fired once. The version-4 comparison of every OFM is shown on
  the board, so boot 85 (rnnoise) is `VALID (x1)`.
- **Boot 89 (wav2letter): NOT_EXECUTABLE (x1).** LOAD_MODEL_END answered (the scaled wait works); the first RUN was
  acknowledged but no RUN_COMPLETE came within 900 s — stalled, not slow. Cause unknown; not investigated here.
- Final x1 statuses: rnnoise `VALID (x1)`; vww4, yolo-fastest `UNRESOLVED (x1)` (OFM differs from tflite_runtime:
  1 byte / 1 LSB and 955 bytes / max 7); wav2letter `NOT_EXECUTABLE (x1)`. Reported in `results/npu_utilization_mps4/`.
- Board restored to `evidence_m6` and postflight passed after boot 89.

## Amendment 4 (2026-10-28, owner decision, recorded before boot 93) — wav2letter re-measured with the fixed host

**TA state: profile 1, unchanged; image `38ce118c…`, profile `mlek_r10` (10 RUNs) as in amendment 2.**

Correction to the results of amendments 2 and 3: boots 87 and 89 did **not** wait 120 s / 900 s. The host's
`RunnerLink.run()` gave up after ~5 s of silence whatever the timeout (`evidence/w2l_stall/contract.md`, step 2;
fixed in `52254b9`). On the diagnostic image the firmware was found in `ST_RESULT_READY` after such a refusal, and
two RUNs with the fixed host completed in 6.6 s. "Stalled" and `NOT_EXECUTABLE (x1)` for wav2letter are withdrawn.

| boot | workload | blob | purpose |
| --- | --- | --- | --- |
| 93 | wav2letter_pruned_int8 | `5b8c9d06…` (unchanged) | measurement, host with the `52254b9` fix, RUN wait 120 s |

- Analysed like every x1 boot (`stage1.py --profile config/mlek_r10.json`), status by "Correctness and status":
  golden = tflite_runtime (no MLEK FI101 golden), so an exact OFM → `VALID (x1)` and a differing OFM →
  `UNRESOLVED (x1)`, counters kept. A refusal → recorded as is.
- Report in `results/npu_utilization_mps4/` replaces the wav2letter row.

## Results of amendment 4 (recorded 2026-10-28, after boot 93)

Deploy `~/evsweep/evidence_w2l_meas` (APP `38ce118c`, VECTORS `589f8b88`, DDR `81d37a21`, read back). Raw data
`raw_a4/`, analysis `analysis_a4/`. **TA state: profile 1.**

- **Boot 93 (wav2letter): `UNRESOLVED (x1)`.** 10/10 RUNs complete and valid: `vendor_rc` 2 (OFM ≠ golden),
  `read_seam_fired` 1, QREAD 5,632 (= cms_len), STATUS `0xFFFF0020`, `knobs_honoured`. OFM vs tflite_runtime:
  2 bytes, max |diff| 6, first at 3,262, identical in every RUN. The Stage 1 gate gives `BASELINE_FAIL` (R2 rc, R3
  output) as for vww4 and yolo; the counters are kept.
- Measured RUNs 3–10: `npu_active` median 4,132,039 (4,131,205–4,133,546; MLEK board 2026-08-25: 4,141,085; FVP
  U85-1024: 4,114,227), `mac_active` 3,521,802 in every RUN, peak MAC efficiency 82.51 %, MAC active ratio 85.2 %,
  active-cycle efficiency 96.8 %.
- Final x1 statuses: rnnoise `VALID (x1)`; vww4, yolo-fastest, wav2letter `UNRESOLVED (x1)` (need an MLEK FI101
  golden). No MLEK model is `NOT_EXECUTABLE` on the board any more.

**Correction (2026-10-28):** "MLEK board 4,141,085" above is MLEK's NPU **TOTAL** for wav2letter; its **ACTIVE** was 4,135,110 (IDLE 5,975; one qualification inference on 2026-08-25, `BOARD_EXECUTABILITY_QUALIFICATION.md` on branch `refactor/unified-mlek-campaigns`, commit `eaa1fa7`). The runner's `npu_active` (4,130,710–4,133,546) is therefore within 0.11 % of MLEK ACTIVE.
