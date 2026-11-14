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

## 보드 세션 1 (2026-11-15, 보드 시각 18:24–18:31Z, TA profile 1) — boot 386–387, 중단

| boot | config | 결과 |
|---:|---|---|
| 386 | `s4ao_conv1x1_h24` | VALID. **재현 Gate PASS**: MAC·DPU·출력·상수 카운터 동일, NPU 허용폭 1,228 안, AO 3,538 vs 3,534 (허용폭 35.34) |
| 387 | `s4aoe_add_h24` | **INVALID (정체성 검사 `regioncfg`)**. RUN 10개 valid, PASS_EXACT, workload sha 일치, capabilities 동일. 그러나 REGIONCFG at IRQ가 0x55F여서, `K.identity`의 고정 기대값 0x15F와 다름 → boot-check FAIL → fail-fast 중단 |
| 388–393 | 나머지 6개 | NOT_MEASURED |

- 원인: 펌웨어는 RUN마다 `placement_regioncfg(n_base, placement)`로 REGIONCFG를 검사한다 (REGION0 3, REGION1_DDR 3, REGION2–7 1; 2 bit/region). n_base는 Conv 5, ADD(IFM 2개) 6이다. 이 RUN들은 펌웨어 검사(REGIONCFG_MATCH)를 통과했다. 호스트 쪽 `K.identity`는 n_base 5일 때의 값 0x15F를 고정 상수로 갖고 있어 Elementwise에 맞지 않았다. G0 dry run을 Conv blob으로만 해서 이 가정을 잡지 못했다 (검증 누락).
- n_base 규칙은 기존 원시 데이터 전부 (4K 100, 4AO 61, placement 20 (SRAM 0x153 포함), 이번 30 RUN)와 일치한다.
- 복원: RESTORE VERIFIED (m6 digest 4개가 이전과 같음). postflight는 user 단계로 따로 실행: PING state 1, 카드 분리.
  원시 데이터 73개 파일 (`raw.sha256`, 보드와 sha256 일치).
- **POST_HOC_DESCRIPTIVE (계약상 INVALID인 구성의 값; 판정에 쓰지 않음)**: ADD H24 AO_ACTIVE 3,456 (4 RUN 모두, range 0) = N/16.
  MAC_ACTIVE 0, WD 0, NPU_ACTIVE 36,644 / 37,180.5 (A/B), EXT rd beat 6,933 (IFM 2개 ≈ 2 × 3,456), EXT wr 3,456, SRAM 0.
