# Stage 6B — 그룹화·정적 재현·대표 형상 선정 규칙 (정적 컴파일 전에 고정, 2026-11-15)

지시: ChatGPT 경유 owner 지시 "Stage 6B — Model-informed 1×1 DepthFirst MAC Characterization" (보드 없음, 계약 동결 없음).
이 문서는 후보 정적 컴파일을 하기 **전에** 커밋한다. 컴파일 결과를 본 뒤 규칙을 바꿔야 하면 개정 A로 기록하고 원래 결과도 보고한다.
구현: `host/analysis/stage6b.py` (Mac), `host/container/stage6b_models.py` (컨테이너).

## 1. 대상 연산 (Phase 1)

- 출처: `results/fi101_stage4/stage4_operator_inventory.csv` (Stage 6 기준, Vela 5.0.0, MLEK 옵션, 7개 모델 591행).
- 조건: `cpu == 0`, `npu_op == Conv2D`, `kernel == 1x1`, `traversal == DepthFirst`, `mac_count > 0`,
  출력 INT8 (`results/fi101_stage6/tflite_dtypes.json`).
- 행 하나 = Vela scheduled operation 하나. TFLite 연산 하나가 여러 scheduled operation으로 나뉘면 각 행을 따로 두고,
  `tflite_op_index`로 출처를 남긴다. MAC은 scheduled operation의 Vela `mac_count`만 더한다 (중복 없음).
- 모델 MAC 분모 = 그 모델의 NPU 행 (`cpu == 0`) Vela `mac_count` 합 (Stage 6과 같음).

## 2. 실행 그룹 (Phase 2)

그룹 키 (모델과 무관, 모두 같아야 한 그룹):
`npu_op, kernel, stride, padding, npu_ifm_hwc, npu_ofm_hwc, ifm_block, ofm_block, ofm_ublock, traversal, ifm_memory,
ofm_memory, ifm_format, ofm_format, cascade, tflite_activation`.

- weight 값·encoded 크기·per-channel scale은 키에 넣지 않는다. 그룹 안의 weight_bytes 범위를 따로 기록한다.
- 대표 연산 (컴파일에 쓸 실제 weight의 출처): 그룹에서 `mac_count`가 가장 큰 행. 같으면 모델 이름 순, 그다음 scheduled_id 순.

## 3. 후보 (선정 절차 1–3)

1. 모델마다 그룹을 그 모델 안의 MAC 비중 순으로 정렬한다 (같으면 그룹의 가장 작은 scheduled_id).
2. 모델마다 상위 5개 그룹이 정적 컴파일 후보다.
3. 여러 모델의 후보가 같은 그룹이면 하나로 합친다.

## 4. 정적 재현 (Phase 3)

후보마다 대표 연산의 원본 tflite 텐서 (weight, bias, per-channel scale, IFM/OFM quantization, fused activation, padding,
stride)를 그대로 써서 두 형태를 만든다. IFM 값은 `S6B_SEED = 20261118`로 뽑는다.

- **F_PLAIN**: CONV_2D 하나 (IFM = 그래프 입력, OFM = 그래프 출력).
- **F_CTX**: ADD(a, b) → CONV_2D → ADD(conv 출력, c).
  - 앞 ADD의 출력 quantization = Conv IFM의 quantization이고, a·b도 같은 quantization이다.
  - c는 Conv OFM의 quantization이고, 마지막 출력 scale은 2 × OFM scale, zero point는 OFM의 것이다.
  - 근거: Stage 4AO-E (TA profile 1)에서 INT8 ADD는 MAC_ACTIVE 0, WD 0이었다. 그래서 MAC 축과 WD 축은 Conv만의 활동이다.
  - AO_ACTIVE, NPU_ACTIVE, beat 수는 ADD 두 개를 포함한다.

비교 항목 (Vela debug DB, 원본 행과 같아야 한다):

| 항목 | 분류 |
|---|---|
| npu_ifm_hwc, npu_ofm_hwc, kernel, stride, padding, mac_count | 형상 (다르면 NOT_REPRODUCIBLE) |
| Conv가 scheduled operation 하나이고 CPU 연산이 없음, 패킹 성공, CPU reference 생성 | 실행 가능 (아니면 NOT_REPRODUCIBLE) |
| 러너 한도: fast scratch ≤ 0x60000, arena ≤ 0x200000, 모델 + arena ≤ 32 MiB | 실행 가능 (아니면 NOT_REPRODUCIBLE) |
| traversal, ifm_block, ofm_block, ofm_ublock | 실행 구성 |
| ifm_memory, ofm_memory, ifm_format, ofm_format, cascade | 배치 |
| weight_bytes (대표 연산과), staging_usage, tflite_activation | weight 스케줄·fusion |

- **EXACT_STATIC_MATCH**: 모든 항목이 같다.
- **PARTIAL_STATIC_MATCH**: 형상과 실행 가능은 통과했지만, 실행 구성·배치·weight 스케줄·fusion 중 하나 이상이 다르다.
- **NOT_REPRODUCIBLE**: 형상 또는 실행 가능 항목이 실패했다.
- 후보 등급 = 두 형태 중 좋은 쪽 (EXACT > PARTIAL > NOT). 둘 다 EXACT이면 F_PLAIN을 쓴다 (ADD 오염 없음).
- vela_npu_cycles·vela_mac_cycles 추정값은 진단으로만 비교한다 (판정에 쓰지 않음).
- 반복 컴파일: 모든 후보를 두 번 컴파일하고, tflite·Vela 출력·DRWL sha256이 같아야 한다. 다르면 NOT_REPRODUCIBLE.
- EXACT도 모델 레이어의 PMU 활동이 같다는 뜻이 아니다. Stage 6의 T0를 자동으로 주지 않는다.

## 5. 선정 (절차 4–6, 최대 10개)

- 적격 = EXACT_STATIC_MATCH만이다. PARTIAL은 목록에 남기되 선정하지 않고, coverage에도 넣지 않는다.
- (a) 모델 이름 순으로 각 모델을 본다. 이미 선정된 그룹이 그 모델의 연산을 포함하면 건너뛴다.
  아니면 그 모델의 적격 그룹 중 그 모델 안의 MAC 비중이 가장 큰 그룹을 선정한다.
- (b) 남은 자리는 점수 순으로 채운다. 점수 = Σ_모델 (그 그룹이 그 모델에서 차지하는 Vela MAC ÷ 그 모델 전체 Vela MAC)이고,
  모델마다 가중치는 같다.
- 동률이면 다음 순서로 정한다.
  1. 적용 모델 수가 많은 쪽
  2. 7개 모델 합 Vela MAC에서 차지하는 비중이 큰 쪽
  3. Cin이 기존 측정 범위 [40, 128] 안인 쪽
  4. 대표 연산의 (모델 이름, scheduled_id) 순
- 적격 그룹이 없는 모델은 이유와 함께 보고한다 (RNNoise는 대상 연산이 0개).
- 기준 재현 1개는 별도: Stage 4K `s4c2_conv_cin48` (1×1 DepthFirst Cin48 Cout96, MAC_ACTIVE 3,456, boot 369–378,
  이미지 70090f1). DRWL sha256이 4K 원시 데이터와 같아야 쓴다.

## 6. Coverage 기회 (Phase 4, 측정값 아님)

모델마다 다음을 보고한다.
- Stage 6 calibrated MAC coverage: 고치지 않는다.
- 1×1 DepthFirst MAC 비중.
- 후보 그룹 비중과 그 등급별 비중 (EXACT / PARTIAL / NOT).
- 선정 그룹 비중.
- 상한 = Stage 6 coverage + (선정 그룹 중 Stage 6에서 T0·T1_INTERP가 아니었던 연산의 비중).
- 남는 주요 미측정 연산: MAC 비중 상위 3개.
- 그룹이 여러 모델에 걸쳐도, 모델마다 자기 연산만 센다. 그래서 중복이 없다.
- 그룹 안 weight 값 차이는 MAC에 영향이 없다고 가정한다 (근거: Stage 4WD 실험 A MAC_SAME. 다만 PartKernel 형상에서 얻은 근거다).
  이 가정은 조건으로 표시한다.
