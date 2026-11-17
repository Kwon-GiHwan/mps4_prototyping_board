# Stage 6E-X3 세션 결과 — G1 FAIL로 중단 (boot 477만 측정, 2026-11-17 UTC 보드 시계)

- **세션**: `board/session.log`. 순서는 deploy → boot 477(kws B0) → boot-check VALID → gate-g1 **FAIL**이다.
- **중단 처리**: SESSION FAILED(step 8) 뒤 RESTORE VERIFIED, 이어서 postflight("card withdrawn, board on restored image")를 수동 실행했다.
- **원시 자료**: `raw/`(sha256 일치). boot 478–486은 실행하지 않았다.
- **사용량**: 1 boot / 15 RUN(측정 12)이며 X3 예산 10 boot 중 1이다.
- **측정 조건**: **TA profile 1**, EXT RLATENCY 500, 이미지 f0baf8c(bram 9b1844a3), placement 0, pmu_flags 0(mask_en 0, pmcr_after_arm 0x4001), record schema 5.

## G1 판정 (계약 §4, 동결 기준 그대로)

| 항목 | kws B0 (boot 477) | m7 (65cf963, 측정 RUN) | 차이 | 기준 | 결과 |
|---|---|---|---|---|---|
| NPU_ACTIVE pass A 중앙값 | 90,380.5 (range 1,675; RUN 90,294 / 91,667 / 90,467 / 89,992) | 91,824.5 (range 2,423; 8 RUN 89,991–92,414) | −1,444 (−1.57 %) | ±1 % | **FAIL** |
| MAC / DPU | 56,450 / 49,495 | 56,450 / 49,495 | 0 | max(1 %, range) | PASS |
| AO / WD / WD_STALLED | 17,823 / 11,507 / 64,136.5 | 17,825 / 11,415 / 64,094 | −0.01 % / +0.81 % / +0.07 % | 〃 | PASS |
| SRAM·EXT beat·트랜잭션, 포트별 beat (128 130 132 135 384 386 391 640 642 656 658) | m7와 같음 | — | 0 | 〃 | PASS |
| 요청 정체 131 / 387 | 777 / 17,038 | 777 / 17,579 | 0 / −3.1 %(range 안) | 〃 | PASS |
| 출력 | golden 일치(OUTPUT_MATCH, ofm_mismatch 0), CRC 1개 | — | — | — | PASS |

- **판정**: 계약대로 **G1 FAIL**, 측정 중단. 계약상 X3 Measurement = `MEASUREMENT_INVALID`이고 나머지 판정은 하지 않는다.
- **기술**(POST_HOC_DESCRIPTIVE, 판정에 쓰지 않음):
  - 결정적 카운터(MAC, DPU, 전송·포트 계수)는 m7과 정확히 같다.
  - B0 NPU_ACTIVE 측정 RUN 4개는 모두 m7 pass A RUN 범위(89,991–92,414) 안에 있다.
  - m7 pass A 자체의 RUN 범위가 2.6 %라서, 동결한 ±1 % 중앙값 기준은 기준값의 RUN 간 변동보다 좁았다.
  - boot 477 자료를 새 기준으로 다시 판정하지 않는다(사후 기준 변경 금지).
