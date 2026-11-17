# Stage 6E-X3 Amendment B 세션 결과 — boot 489(kws B2)의 GS 실패로 중단 (2026-11-17 UTC 보드 시계)

- **세션**: `board_b/session.log`. 순서는 deploy → 487 kws B0 VALID → G1 **PASS** → 488 kws B1 VALID → 489 kws B2 **UNSTABLE** → GS 실패(rc 1) → 중단이다.
- **중단 처리**: RESTORE VERIFIED 뒤 postflight를 수동 실행했다("card withdrawn, board on restored image").
- **원시 자료**: `raw_b/`(sha256 일치). boot 490–496은 실행하지 않았다.
- **사용량**: 이 세션 3 boot / 45 RUN이고, X3 누적 4 boot(477, 487–489) / 60 RUN이다.
- **측정 조건**: **TA profile 1**, EXT RLATENCY 500, 이미지 f0baf8c, placement 0.

## 판정 (계약 + Amendment B, 동결 기준 그대로)

| boot | 키 | 상태 | gate |
|---|---|---|---|
| 487 | kws B0 | VALID | G1 PASS: NPU 91,444.5 대 m7 91,824.5, Δ −380(−0.41 %), 허용폭 4,016(range_B0 1,593 ≤ cap 2,423). 결정적 카운터 13개 정확 일치 |
| 488 | kws B1 | VALID | GS PASS(pmu_flags 1, pmcr_after_arm 0x4009 → mask_en 1, 출력 CRC = B0) |
| 489 | kws B2 | **UNSTABLE**("NPU_ACTIVE pass A range": 1,741 = 6.7 % > 5 %) | **GS FAIL** → 중단 |

계약상 Measurement는 `MEASUREMENT_INVALID`다. 그룹 귀속, PMU_MASK 기능, 가설은 판정하지 않는다(GM gate 전에 중단).

## 기술 (POST_HOC_DESCRIPTIVE, 판정 아님)

| 값 (pass A 측정 RUN 중앙값) | B0 원본 | B1 직렬 | B2 G_V 창 |
|---|---|---|---|
| NPU_ACTIVE (range) | 91,444.5 (1,593) | 105,074.5 (2,169) | 25,798.5 (1,741) |
| MAC_ACTIVE | 56,450 | 56,450 | **11,700** |
| DPU | 49,495 | 49,495 | 10,530 |
| AO / WD | 17,825 / 11,383.5 | 17,780.5 / 11,125.5 | 4,032 / 3,885.5 |
| 출력 CRC | 3471423486 | 같음 | 같음 |

- **직렬화(B1)**: MAC·DPU는 원본과 같다. NPU_ACTIVE는 +13,630(+14.9 %)이다. SRAM·EXT beat도 같다(EXT rd 15,815 → 15,814). EXT 포트 분배만 바뀌었다(642/658: 7,832/7,983 → 7,931/7,883).
- **G_V 창(B2)**:
  - MAC_ACTIVE 11,700은 6-M h1uc 예측 합(연산 2·4·6) 11,700과 정확히 같다.
  - 창 NPU_ACTIVE는 직렬 전체의 24.6 %로, 마스크가 계수를 나눈다는 것과 일관된다(판정은 GM 몫이므로 하지 않음).
- **불안정의 성격**:
  - NPU_ACTIVE의 RUN 간 range는 창 크기와 관계없이 절대값 약 1,000–2,800 사이클이다(B0 1,593 / B1 2,169 / B2 1,741; m7 세트별 1,497–2,423).
  - 그래서 상대 5 % 기준은 작은 창(25.8k)에서 넘기 쉽다. B3(op0, 약 30k 예상)과 B4도 같은 위험이 있다.
  - 이 관찰로 boot 489를 다시 판정하지 않는다.
