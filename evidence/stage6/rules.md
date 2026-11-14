# Stage 6 — 적용 규칙과 판정 기준 (잔차를 보기 전에 고정, 2026-11-15)

이 문서는 모델 활동 추정과 whole-model 비교를 계산하기 **전에** 커밋한다. 계산 결과를 본 뒤 이 값과 규칙을 바꾸지 않는다.
바꿔야 하면 개정 A로 기록하고, 원래 판정도 함께 보고한다. 구현은 `host/analysis/stage6.py`.

## 1. 기준 데이터

- 모델 매핑: `results/fi101_stage4/stage4_operator_inventory.csv` (Vela 5.0.0, MLEK 옵션, debug DB). 7개 모델 모두 Vela 출력
  sha256이 driver_m7에서 측정한 DRWL의 `vela_sha256`과 같아야 사용한다. 다르면 그 모델은 BASELINE_NOT_COMPARABLE이다.
- Whole-model PMU: `evidence/driver_m7/raw/wfe/<model>/runs.csv` (boot 308–316, TA profile 1, 이미지 65cf963).
  - pass A (set 2, 이벤트 35 48 51 53 55 64 80 81)와 pass B (set 3, 이벤트 35 128 130 132 135 384 386 391)의 측정 RUN (rep > 2) 중앙값.
  - 모든 RUN이 valid여야 한다. 아니면 BASELINE_NOT_COMPARABLE.
- 조건 차이 (기록만, 판정에 반영):
  - 이미지: driver_m7은 65cf963, Stage 4K–4WD는 70090f1.
  - 독립 연산과 모델은 SRAM 배치·fast scratch 크기·fusion이 다르다.
  - wav2letter M4는 UNPROVEN이다 (driver_m7 README).

## 2. 측정 카탈로그 (Stage 4–4WD 실측, TA profile 1)

| 축 | 계열 (npu_op, kernel, stride, traversal) | 측정 범위 | 관측 |
|---|---|---|---|
| MAC | Conv2D 1×1 s1 PartKernel | Cin 16, 32 (Cout 96, 95, 94) | 384 MAC/MAC_ACTIVE (범위 안 일정) |
| MAC | Conv2D 1×1 s1 DepthFirst | Cin 40, 48, 64, 128 | 640 (40), 768 (48, 64, 128) — **범위 안에서 일정하지 않음** |
| MAC | Conv2D 3×3 s1 PartKernel | Cin 16–64 | 768 (nominal, 범위 안 일정) |
| MAC | DepthwiseConv2D 3×3 s1 | 채널 142–145, 56×56 | 128 |
| MAC | FullyConnected | 96→287/288, 95→288 | 256 |
| AO | Conv INT8 AB→OB (1×1, 3×3) | OFM 24–72×24×96 | N/15.60 (N = H·W·⌈C/16⌉·16) |
| AO | Elementwise ADD/MUL INT8, 체인 아님 | 24/72×24×96 | N/16 |
| AO | ABS | 같음 | N/32 (Open Issue AO-1 → 수치 적용 안 함) |
| WD | Conv 1×1 PartKernel Cin16 Cout96, block 6×12×96 | spatial block 8–24 | WD = 60.6 × block + 96.7, BLOCK_LIKE |
| WD 재스트리밍 | Conv·DW, DDR 배치, staging 사용 | 35/35 정확 | SRAM rd = spatial block × staged / 16 (구조 지표로만) |

## 3. 적용 등급 (스케줄된 NPU 연산마다, 축별)

- **T0 DIRECT_MATCH**: 계열이 같고, Cin·Cout·OFM block이 측정 구성과 정확히 같음.
- **T1_INTERP**: 계열 (npu_op, kernel, stride, traversal)이 같고 Cin이 측정 범위 [min, max] 안에 있으며, 그 범위에서 관측값이 일정함 → 수치 추정 허용.
- **T1_EXTRAP**: 계열은 같지만 Cin이 범위 밖이거나, 범위 안에서 관측값이 일정하지 않음 → 수치 없음 (구조 지표만).
- **T2 QUALITATIVE_ONLY**: npu_op만 같음 (Conv2D / DepthwiseConv2D / FullyConnected / ADD·MUL), kernel·stride·traversal이 다름.
- **U UNSUPPORTED**: 그 밖의 연산 (LUT, MemoryCopy, Mul by scalar 등 측정하지 않은 경로, CPU 연산, 0-cycle fused 활성화).
- AO 축: Conv2D INT8 (모든 kernel)는 **T1_INTERP**다 (1×1·3×3, 여러 block에서 15.5–15.9로 일정).
  DepthwiseConv2D·FullyConnected는 T2 (사후 관측만), 체인이 아닌 ADD/MUL INT8은 T1_INTERP, 그 밖은 U.
  체인 여부는 Vela ofm_format NHCWB16 + 다음 연산 elementwise로 판정하며, 판정할 수 없으면 U다.
- WD 수치 축: T0 계열 (§2 마지막에서 두 번째 줄)만 수치를 낸다. 나머지 weight 연산은 구조 지표 (spatial block × weight bytes)만.

## 4. 집계와 비교

- Coverage는 축마다 따로 보고한다. MAC은 Vela mac_count 비중, AO는 OFM 원소 비중, WD는 (spatial block × weight bytes) 비중이다.
  T0, T1_INTERP, T1_EXTRAP, T2, U로 나누고, 서로 다른 축의 coverage를 합치지 않는다.
- Calibrated estimate = T0 + T1_INTERP 연산의 (MAC / 관측 rate) 또는 (N / 관측 rate)의 합.
- **정량 비교 조건**: 그 축의 calibrated coverage가 0.80 이상일 때만 측정값과 비교한다. 아니면 INSUFFICIENT_EVIDENCE.
- **허용폭**: |estimate − measured| / measured ≤ 0.10이면 CONSISTENT, 아니면 NOT_CONSISTENT.
  모델 전체 합은 fusion·중첩 때문에 정확한 합이 아니므로 10 %로 넉넉하게 두었다.
- Vela 원래 MAC (mac_count, nn_macs)과 TFLite MAC은 구분한다. 이번 단계는 **Vela mac_count**를 쓴다.

## 5. 현상별 판정 (anomaly_attribution_matrix)

| 현상 | 모델 | 관련 축 |
|---|---|---|
| P1 MAC 활성 비율은 높은데 유효 처리율이 낮음 | kws | MAC |
| P2 MAC 효율이 높고 WD_STALLED도 높음 | ad, wav2letter | MAC + WD |
| P3 AO_ACTIVE > MAC_ACTIVE | yolo, vww4 | AO + MAC |
| P4 MAC 활동이 매우 낮음 | rnnoise | MAC |
| P5 NPU 비용과 Vela 예측의 차이 | rnnoise (+ 모든 모델 기술 통계) | 전체 |
| P6 SRAM 예산에 따른 성능 변화 | ad (Stage 5 근거) | WD 재스트리밍 |
| P7 MAC 수가 비슷해도 사이클이 다름 | 모델 간 | MAC + AO + WD |

판정 순서:
1. BASELINE_NOT_COMPARABLE (기준 조건 실패)
2. INSUFFICIENT_EVIDENCE: 관련 축의 calibrated coverage < 0.50, 또는 주장이 층별 PMU 귀속을 필요로 함
3. coverage ≥ 0.80이고 정량 비교가 CONSISTENT이면 SUPPORTED_WITHIN_SCOPE, NOT_CONSISTENT이면 NOT_SUPPORTED
4. 0.50 ≤ coverage < 0.80이면 PARTIALLY_SUPPORTED (방향성 설명만)

SUPPORTED_WITHIN_SCOPE는 인과적 병목을 증명했다는 뜻이 아니다.
