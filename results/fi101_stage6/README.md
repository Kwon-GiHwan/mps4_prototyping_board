# fi101_stage6 — Model-level Hardware Characterization (보드 RUN 없음)

기준: driver_m7 (boot 308–316, TA profile 1, FI101 U85-1024, 이미지 65cf963), Vela 5.0.0 MLEK 옵션. 판정 규칙은 `evidence/stage6/rules.md`
(계산 전에 고정, `cbf8e23`). 출처와 매핑 검증: `evidence/stage6/README.md`. 계획: `docs/plan/stage6_model_level_characterization.md`.
최종 상태: **READY_FOR_RESEARCH_REVIEW** (7개 모델 분석·검증 완료). 이 상태는 이상 현상을 설명했다는 뜻이 아니다.
다음 단계 판단은 **C** (아래).

## Whole-model 비교 (`whole_model_comparison.csv`)

| 모델 | NPU_ACTIVE | MAC_ACTIVE | AO_ACTIVE | WD_ACTIVE | WD_STALLED | Vela NPU cycles | MAC cal. cov | AO cal. cov | WD cal. cov | MAC | AO | WD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| kws | 91,824.5 | 56,450 | 17,825 | 11,415 | 64,094 | 86,324 | 0.000 | 0.656 | 0.000 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| ad | 145,949.5 | 93,672 | 41,503.5 | 21,319 | 117,221.5 | 140,277 | 0.000 | 0.667 | 0.000 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| mobilenet_v2 | 1,450,096 | 574,795 | 440,984.5 | 169,343 | 1,212,443.5 | 1,737,984 | 0.219 | 0.658 | 0.000 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| vww4 | 234,669 | 56,512 | 64,555 | 13,413 | 134,171.5 | 222,478 | 0.196 | 0.574 | 0.000 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| rnnoise | 50,508 | 548 | 300 | 2,815 | 12,573 | 31,334 | 0.000 | 0.000 | 0.000 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| yolo-fastest | 447,601.5 | 171,576 | 206,935 | 27,266.5 | 323,342 | 478,546 | 0.220 | 0.654 | 0.143 | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT |
| wav2letter | 4,133,297.5 | 3,521,802 | 59,762 | 1,133,549 | 2,982,162.5 | 5,233,545 | 0.000 | **0.975** | 0.000 | INSUFFICIENT | **CONSISTENT (−3.5 %)** | INSUFFICIENT |

- INSUFFICIENT = INSUFFICIENT_EVIDENCE (calibrated coverage < 0.80).
- 정량 비교가 성립한 곳은 **wav2letter AO 하나**다. Conv INT8 AB→OB 모델 (N/15.60)로 구한 추정 57,692는 실측 59,762와 −3.5 %로, 허용폭 10 % 안이다.
  - 단, wav2letter는 M4 (AO 포함)의 MLEK 동등성이 UNPROVEN이다 (driver runner 측정 자체는 유효).

## 현상별 판정 (`anomaly_attribution_matrix.csv`)

P1 (kws), P2 (ad, wav2letter), P3 (yolo, vww4), P4·P5 (rnnoise), P6 (ad), P7 (7개 모두): **모두 INSUFFICIENT_EVIDENCE**.
- 관련 축의 calibrated coverage가 0.50 미만이기 때문이다. P3의 AO는 0.57–0.65이지만 MAC이 0.20–0.22다.

## 이번 분석에서 새로 나온 것 (POST_HOC_DESCRIPTIVE, 판정 아님)

1. **측정 범위 밖 MAC의 주인은 1×1 DepthFirst Conv다.**
   - 비중: kws 85 %, ad 95 %, mobilenet 69 %, vww4 65 %, yolo 43 %.
   - 단일 연산 측정의 DepthFirst 처리율 (Cin40 640, 48·64·128 768)이 일정하지 않아 외삽이 금지된다.
   - wav2letter는 큰 1D 커널 PartKernel (1×32, 1×7, 1×48; 81 %), rnnoise는 FC (99 %)다. 셋 다 측정하지 않은 계열이다.
2. **WD 구조 지표**:
   - Σ(spatial block × encoded weight bytes) ÷ 실측 WD_ACTIVE가 7개 모델 모두 24–36 B/cycle 안에 있다 (Spearman 0.96).
   - Stage 4WD의 block 재스트리밍 관측과 방향이 맞는다.
   - 다만 4WD 실험 A (encoded 크기를 바꿔도 WD 일정)를 보면, encoded bytes는 원인이 아니라 weight 수와 함께 움직이는 상관 변수로 봐야 한다. 보정된 추정이 아니다.
3. AO coverage가 부분적인 이유는 DW (T2)와 FC (T2)다. DW의 AO는 사후 관측 (Stage 4 DW 0.991)만 있다.

## 다음 단계 판단 (지시 §13): **C. 구조적 한계** → 우선순위를 둔 측정 제안 (B 성격, 계약 초안은 승인 후)

1. **1×1 DepthFirst Conv 처리율 지도**: 모델에 실제로 나오는 (Cin, Cout, OFM 형상, block) 대표점을 측정한다.
   MAC coverage에 가장 크게 기여한다 (5개 모델에서 43–95 %).
2. **DW 3×3 (여러 채널·해상도)**: AO와 MAC coverage를 함께 올린다 (DW는 지금 T2).
3. **큰 1D 커널 PartKernel (wav2letter 1×32/1×7)**와 **FC (rnnoise)**: 각 모델의 주 계열이다.
4. WD 수치 모델을 DepthFirst와 DW로 넓힌다 (블록 재스트리밍 규칙과 4WD 실험 A 결과를 바탕으로).

모두 보드 측정이 필요하고, 각각 별도 승인과 계약이 필요하다. 층별 PMU 귀속 없이 whole-model 수치 모델을 완성하려 하지 않는다.

## 파일과 명령

`python3 host/analysis/stage6.py run results/fi101_stage6`가 아래 파일과 `summary.json`을 만든다. dtype은 컨테이너에서 원본 tflite로 추출했다 (`tflite_dtypes.json`).
- `model_operator_inventory.csv`, `vela_kernel_mapping.csv`, `unit_model_applicability.csv`
- `model_activity_estimates.csv`, `whole_model_comparison.csv`, `anomaly_attribution_matrix.csv`
