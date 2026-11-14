# Stage 4AO-E — Elementwise·Chaining Buffer·LUT AO 특성: 분석·설계 (보드 없음)

상태: **2026-11-15 보드 없는 단계 완료. 판정 `READY_FOR_BOARD_CONTRACT_REVIEW`** (Group A + ADD→MUL). Conv를 포함한 CB·LUT
후보 3개는 golden 규칙이 결정될 때까지 보류 (`NEEDS_GOLDEN_RULE`).
조건: TA profile 1, 이미지 `70090f1`, DDR/EXT, Vela 5.0.0 (MLEK 옵션). 계약 초안 `evidence/stage4aoe/contract_draft.md`.

## 0. Stage 4AO 최종 요약 (확정, `results/fi101_stage4ao/README.md`)

- INT8 Conv 1×1 AB→OB (H 24/36/54/72, block 6×12×96): AO_ACTIVE ≈ N_OFM / 15.60. 기울기 1.0253 → `RATE_NOT_CONSISTENT`
  (±2 %), 절편 ≈ 0. M1·M2 NOT_CONSISTENT, M3 CONSISTENT. 이 sweep에서는 블록 수가 N에 비례하므로 "블록당 비용"과
  "지속 처리율 97.5 %"는 구분되지 않는다.
- Phase C: **INCONCLUSIVE**. act_none 1 LSB 불일치의 원인은 보드 없이 특정했다 (§2).

## 1. 공식 자료: AO 경로별 처리율 (TRM 102685 issue 05 §4.2, U85-1024 NUM_SU = 16)

| 경로 | 이번 후보 | TRM (SU당 원소/cycle) | U85-1024 원소/cycle | 근거 |
|---|---|---|---:|---|
| AB → OB_8 | Conv (+ LUT), TANH·LOGISTIC 융합 | 1 | 16 | Table 4-11 |
| AB → CB_8/16 | Conv→ADD의 Conv 부분 | 1 | 16 | Table 4-11 |
| CB_8/16 → OB_8 (Unary·Binary) | ADD, MUL, ABS, 체인의 마지막 단계 | 1 | 16 | Table 4-12 |
| CB_8/16 → CB_8/16 | ADD→MUL의 ADD 부분 | 1 | 16 | Table 4-12 |
| CB_32 → OB_8 Binary | (해당 없음) | 1/2 (CB) | 8 | Table 4-12 |
| OB_16 (INT16 출력) | (이번 범위 밖) | 1/2 (DMA) | 8 | Table 4-11/12/13 |

- 메모리에서 읽는 Elementwise 입력도 CB를 거친다고 본다. TRM §2.6.3: "The chaining buffer is an input buffer for elementwise
  operations". 이것은 공식 문장에서 추론한 것이며, 메모리 IFM의 경로를 명시한 성능표는 없다.
- 이번 후보의 모든 경로는 8 bit이므로 공식 상한은 모두 16 elem/cycle이다. 32 bit CB나 16 bit 이상 OB 경로는 판정 대상에서 뺀다
  (선정 규칙 `path_not_covered`).
- LUT: "ReLU and LUT can be applied directly to the output of any AO operation" (§2.6). LUT의 처리율 감소는 표에 없다.
  activation_function = lut_s8_s8 (§3.10.14).
- 공식 성능표의 일반 규칙: "Partial SBs might be used at block edges", AB 읽기 시 grant delay bubble ≤ 1 cycle.
  AO stall 이벤트(65–79)는 Reserved이므로 정체를 직접 관측할 수 없다.

## 2. 이전 1 LSB 불일치: 증거와 원인 분류 (보드와 분리된 진단, `results/fi101_stage4aoe/rounding.json`, `refcheck.json`)

| 후보 원인 | 판정 | 근거 |
|---|---|---|
| **반올림 규칙 차이 (CPU reference 쪽)** | **정적 근거로 특정** | NPU 명령의 OFM_SCALE = double_symmetric, dbl_rnd 0, shift 40. TRM 의사코드 에뮬레이션은 BUILTIN_REF와 0개 차이이고, 기본 커널 golden과는 act_none에서 57개 (모두 −1, 모두 음수 .5 경계) 다르다. 보드 관측(57, 최대 1)과 같다 |
| Saturation | 배제 | 차이 원소는 −13.5, −39.5 같은 중간값이며 ±128 경계가 아니다 |
| OFM scale·zero point 차이 | 배제 | act_none, RELU, RELU6의 scale·shift·zp가 같고, RELU/RELU6은 보드에서 PASS_EXACT였다 |
| 다른 round_mode (natural, symmetric) | 배제 | 이 모드로 에뮬레이션하면 RELU6에서도 28개가 달라야 하는데, 보드는 RELU6을 PASS_EXACT로 측정했다 |
| 하드웨어 오류 | 근거 없음 | 에뮬레이션과 reference 커널이 정확히 일치한다 |

- 기존 workload 53개 (Stage 4, 4C, 4C-2, 4K, 4AO)는 기본 커널과 reference 커널의 출력이 같았다 → 이미 보고한 결과에는 영향이 없다.
- 남은 증명: 보드의 NPU 출력 자체는 저장되지 않았다. 이번에 출력 보존 기능을 추가했다: `host/board/run_driver_events.py`는
  출력 불일치로 fail-fast할 때, 이미 측정이 끝난 그 RUN의 출력을 `output_mismatch.bin`으로 받고 CRC를 검사한다
  (`--outputs`일 때만; 측정 창은 바뀌지 않는다). 시뮬레이터 테스트를 붙였다.
- **출력 검증 기준은 그대로 PASS_EXACT다.** golden을 바꿔서 통과시키지 않았다. 기본 커널과 reference 커널이 다른 후보는
  `NEEDS_GOLDEN_RULE`로 보류하고, golden을 BUILTIN_REF로 정할지는 owner 결정 사항으로 남긴다 (§6).

## 3. Phase 2 — Vela 정적 분석 (`results/fi101_stage4aoe/static.json`, `stage4aoe_static.csv`)

생성 규칙 (`host/container/stage4aoe_models.py`):
- IFM은 `AOE_SEED = 20261116`에서 H 72로 한 번 뽑고 잘라 쓴다 (H24 IFM = H72 IFM의 첫 24행).
- Conv 부분은 `s4_conv_base` 텐서를 그대로 쓴다.
- 양자화: IFM 1/128. ADD OFM 2/128, MUL·ABS 1/128. TANH 1/128, LOGISTIC 1/256 zp −128 (TFLite int8 고정 범위).
- 두 번 빌드한 40개 파일이 바이트 동일하다.

| config | 그룹 | N_OFM | IFM 수 | Vela 커널 | AO 패스 (원소) | 논리 AO 원소 | block | CB | LUT | default vs REF | 선정 |
|---|---|---:|---:|---|---|---:|---|---|---|---:|---|
| add_h24 / h72 | A | 55,296 / 165,888 | 2 | ELEMENTWISE | IFM→OB (N) | N | 24×42×96 / 72×42×96 (1 block) | — | — | 0 | SELECTED |
| mul_h24 / h72 | A | 55,296 / 165,888 | 2 | ELEMENTWISE | IFM→OB (N) | N | 같음 | — | — | 0 | SELECTED |
| abs_h24 / h72 | A | 55,296 / 165,888 | 1 | ELEMENTWISE | IFM→OB (N) | N | 같음 | — | — | 0 | SELECTED |
| add_mul_h24 | B | 55,296 | 3 | ELEMENTWISE ×2 | IFM→CB (N), CB→OB (N) | 2N | 24×42×96 | 예 | — | 0 | SELECTED |
| conv_add_h24 | B | 55,296 | 2 | CONV, EW, CONV, EW | AB→CB (16ch), CB→OB, AB→CB (80ch), CB→OB | 2N | 6×12×96 | 예 | — | **48** | NEEDS_GOLDEN_RULE |
| tanh_h24 | C | 55,296 | 1 | CONV ×2 | AB→OB + LUT (16ch, 80ch) | N | 6×12×96 | — | 예 (lut_s8_s8, LUT DMA 256 B) | **49** | NEEDS_GOLDEN_RULE |
| logistic_h24 | C | 55,296 | 1 | CONV ×2 | 같음 | N | 6×12×96 | — | 예 | **55** | NEEDS_GOLDEN_RULE |

- CPU fallback은 없다. 10개 모두 패킹에 성공했다 (DRWL golden = BUILTIN_REF 출력, IFM 2–3개, DRWL_IO_MAX 8 이내).
- CB 사용은 명령 스트림의 activation_storage = CHAINED(2)로 확인했다. 중간 텐서는 NHCWB16 형식이고 메모리에는 쓰지 않는다.
  Vela의 메모리 표는 IFM·IFM2·OFM 모두 DRAM이다.
- Elementwise의 OFM scale은 per-tensor(global, OFM precision word bit 8)이고, Conv는 per-channel이다.
- **Elementwise H24·H72는 각각 block 하나다** (block이 OFM 전체를 덮는다). Stage 4AO Conv에서는 블록 수가 N에 비례해 구분할 수
  없었던 두 모델("블록당 비용" vs "지속 처리율 저하")을 Elementwise 경로에서는 가를 수 있다: 블록 수가 1로 같기 때문이다.
  단, Conv 경로의 원인을 직접 증명하지는 않는다.
- Vela AO 추정: Group A = N/16 (3,456 / 10,368). add_mul 6,912 (= 2N/16). conv_add 7,680. LUT 4,224 (Conv와 같음).
- 메모리 영향: arena 55,296–331,776 B (2 MiB 이내). fast scratch는 Group A 0, Conv 포함 4,032 B. ADD/MUL은 IFM 읽기가 2배라
  NPU_ACTIVE 차이를 AO 산술 비용으로 해석하지 않는다.

## 4. 예측과 비교 지표 (`results/fi101_stage4aoe/predictions.json`, 보드 전 고정)

- 논리 AO 원소 = 커널마다 OFM h×w×depth를 더한 값 (CB 체인은 2N).
- P_TRM = 논리 원소 / 16. P_CONV = 논리 원소 / 15.605 (Stage 4AO 실측). P_VELA = Vela ao_cycles 합.
- 관측 처리율 q = 논리 원소 / AO_ACTIVE. 분류: NOMINAL_16 (16의 ±1 %), CONV_LIKE (15.605의 ±1 %; 두 범위는 겹치지 않는다),
  BETWEEN, BELOW_CONV, ABOVE_NOMINAL.
- 비례 (RQ1): AO(H72)/AO(H24)가 3의 ±2 % 이내이면 PROPORTIONAL. 기울기와 절편도 보고한다.
- 정규화: CB 체인은 최종 OFM 원소가 아니라 **논리 원소 (2N)**로 나눈다. 최종 OFM 기준 값도 함께 보고한다.
- AO_ACTIVE는 SU 점유율이 아니다. 모든 경로에 16을 쓰는 것은 공식표에서 해당 경로가 8 bit, SU당 1이라고 확인했기 때문이다.

## 5. Phase 3 — 측정 대상 선정 (규칙 고정, `stage4aoe.select`)

- SELECTED: CPU fallback 없음, 패킹 성공, 모든 패스가 공식 처리율이 있는 8 bit 경로, 기본 커널 = reference 커널 (golden이 모호하지 않음).
- NEEDS_GOLDEN_RULE: 마지막 조건만 실패. owner가 golden 규칙을 정하기 전에는 측정하지 않는다.
- EXCLUDED: 그 밖 (이유 기록). LEAKY_RELU (Pool+LUT, MAC 사용)와 INT16 (패킹 실패)은 이번 후보 목록에 없다.
- 결과: SELECTED 7개 (Group A 6 + add_mul). NEEDS_GOLDEN_RULE 3개 (conv_add, tanh, logistic).

## 6. 승인이 필요한 것

1. 보드 측정 대상: 재현 boot 1개 + SELECTED 7개 = 8 boot, 80 RUN (계약 초안).
2. Golden 규칙: Conv를 포함한 CB·LUT 후보와 act_none은 CPU reference를 **tflite_runtime BUILTIN_REF**로 정할지 여부.
   근거: §2 (정적 근거; 보드 출력 파일로 확인한 것은 아님). 승인되면 별도 그룹 (conv_add, tanh, logistic, 선택: act_none
   진단 1 boot)으로 추가 계약을 만든다.
3. `run_driver_events.py`의 출력 보존 변경을 보드 `~/evsweep`에 반영하는 것 (실패 경로에서만 동작).

## 7. 후속 WD Characterization 연결 (정리만, 신규 실험 없음)

| 관측 | 수치 (TA profile 1) | 아직 설명되지 않은 점 |
|---|---|---|
| Stage 4K: 커널 크기에 따른 WD_ACTIVE | 1×1 1,052–1,954, 3×3 1,886–7,637. weight B / WD_ACTIVE: 1×1 2.6–3.7, 3×3 8.1–8.7 | 커널에 따라 디코딩 처리율이 다른 이유 (weight stream 형식, 압축률) |
| Stage 4AO: 같은 weight(2,752 B)인데 OFM에 따라 WD 증가 | WD_ACTIVE 1,052 → 2,993.5, WD_STALLED 7,270 → 24,302 (H24→H72) | 블록·패스마다 weight를 다시 스트리밍하는지 (재스트리밍 가설) |
| Stage 4 배치 비교 (DDR→SRAM) | WD_STALLED 6,583.5 → 2,414 (`CHANGED`) | 메모리 지연에 따른 공급 부족인지, 다른 경로의 영향인지 |
| MLEK 모델 (Stage 2A/3) | wd_stalled 비율 0.57–0.84 (Conv 모델 전부), wav2letter WD 72 % 정체 | Reserved 이벤트(wd_stalled_by_wd_buf)에 의존한 해석이 있어 재검증 필요 |

WD_STALLED는 "weight stream 데이터 부족 또는 WD 버퍼 공간 부족" (TRM 정의)이다. 공급 부족 (supply)과 소비 측
backpressure (buffer full)가 하나의 카운터에 섞여 있으므로, 가중치 공급 시간으로 바로 해석하지 않는다.
원인 후보: 디코딩 처리율, 재스트리밍, 버퍼 backpressure, 메모리 지연.

## 8. 제한 사항

- NPU가 reference 커널 의미론을 따른다는 것은 Conv OFM rescale에 대해서만 TRM 에뮬레이션으로 확인했다.
  ADD/MUL의 IFM scaling, LUT 생성 값, CB 경로의 bit-exactness는 에뮬레이션하지 않았다 (Group A는 두 커널이 같아서 영향 없음).
- 메모리 IFM이 CB를 거친다는 것은 공식 문장에서 추론한 것이다.
- ADD/MUL/ABS는 IFM 수와 데이터 이동량이 다르다. NPU_ACTIVE 차이는 AO 산술 비용이 아니다.
- CB 체인과 같은 계산의 비체인 기준군은 Vela 강제 없이 만들 수 없다. 그래서 add_mul과 add_h24 + mul_h24의 비교는 기술 통계로만 한다.
