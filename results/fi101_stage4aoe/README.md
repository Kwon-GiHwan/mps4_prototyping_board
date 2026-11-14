# fi101_stage4aoe — Elementwise·CB·LUT AO 경로: 정적 분석과 정확성 진단 (보드 측정 없음)

조건: TA profile 1, 이미지 `70090f1`, DDR/EXT, Vela 5.0.0 (MLEK 옵션). 이 단계의 보드 RUN은 없다.
해설: `docs/plan/stage4aoe_characterization_plan.md`. 계약 초안: `evidence/stage4aoe/contract_draft.md`.
판정: `READY_FOR_BOARD_CONTRACT_REVIEW` (Group A + add_mul). conv_add, tanh, logistic은 `NEEDS_GOLDEN_RULE`.

| 파일 | 내용 | 만든 명령 |
|---|---|---|
| `static.json`, `stage4aoe_static.csv` | 10개 후보의 AO 패스, 논리 원소, CB·LUT, block, exactness, 선정 | `python3 host/analysis/stage4aoe.py static evidence/stage4aoe/workloads results/fi101_stage4aoe` |
| `predictions.json` | P_TRM (/16), P_CONV (/15.605), P_VELA, 허용폭 (보드 전 고정) | `… predict …` |
| `rounding.json` | Stage 4AO act_none 진단: OFM_SCALE 디코딩, TRM 반올림 에뮬레이션 대 golden·BUILTIN_REF | 컨테이너 `stage4aoe_models.py <out> rounding /work/s4ao_compile2` |
| `refcheck.json` | 기존 workload 53개 + 4AO probe: 기본 커널 대 BUILTIN_REF 출력 | 컨테이너 `stage4aoe_models.py <out> refcheck <dirs>` |

요점:
- act_none 1 LSB 불일치: NPU 반올림 (double_symmetric = TFLite reference)과 packed golden (tflite_runtime 최적화 커널, .5를 +∞ 쪽으로)의
  차이. 에뮬레이션 57개 = 보드 57개. 기존에 보고한 PASS_EXACT 결과 (53개 workload)에는 영향이 없다. NPU 출력 파일로 확인한 것은 아니다.
- Elementwise ADD/MUL/ABS: ELEMENTWISE 커널 하나, block 하나 (H24·H72 모두), Vela 추정 N/16.
- 체인: Conv→ADD와 ADD→MUL은 CB(CHAINED)를 사용한다. 논리 AO 원소는 2N이다.
- LUT: TANH·LOGISTIC은 Conv의 AO에 lut_s8_s8로 융합되고, LUT DMA 256 B가 추가된다.
