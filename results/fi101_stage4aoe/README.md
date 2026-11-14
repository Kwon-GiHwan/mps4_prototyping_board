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

## 보드 세션 A1 (계약 `contract_a1.md` 동결 eab77da; boot 394–401, 보드 시각 18:43–19:14Z, TA profile 1, 이미지 70090f1, DDR/EXT)

8 boot 모두 VALID: RUN 80개 전부 valid, PASS_EXACT (`output.bin` = golden), workload sha256 일치, A1 정체성 일치.
재현 Gate PASS (AO 3,534 vs 3,534, `K.reproduce` ok). 출력 불일치는 없었다 (`output_mismatch` 파일 없음).
복원: RESTORE VERIFIED (m6 digest가 이전과 같음), postflight는 세션 안에서 실행됨 (PING state 1, card withdrawn), SESSION DONE.
원시 데이터 134개 파일 (`evidence/stage4aoe/raw_a1/`, `raw_a1.sha256`, 보드와 sha256 일치).
judge 결과와 `runs.csv`를 독립 스크립트로 다시 계산한 값이 같다.

| boot | config | n_base / REGIONCFG (실측 = 기대) | AO_ACTIVE (range) | 논리 원소 / AO | 판정 | NPU_ACTIVE A / B | AO/NPU | EXT rd / wr beat | SRAM | MAC / WD |
|---:|---|---|---:|---:|---|---:|---:|---:|---|---|
| 394 | s4ao_conv1x1_h24 (재현) | 5 / 0x15F | 3,534 (20) | 15.65 | 재현 PASS | — | — | — | — | — |
| 395 | add_h24 | 6 / 0x55F | 3,456 (0) | 16.00 | NOMINAL_16 | 36,769.5 / 36,728.5 | 0.094 | 6,933 / 3,456 | 0 | 0 / 0 |
| 396 | mul_h24 | 6 / 0x55F | 3,456 (0) | 16.00 | NOMINAL_16 | 37,550 / 36,659.5 | 0.092 | 6,933 / 3,456 | 0 | 0 / 0 |
| 397 | abs_h24 | 5 / 0x15F | **1,728** (0) | **32.00** | ABOVE_NOMINAL | 19,649 / 19,169.5 | 0.088 | 3,472 / 3,456 | 0 | 0 / 0 |
| 398 | add_mul_h24 (CB) | 7 / 0x155F | 6,912 (0) | 16.00 (2N 기준); 최종 OFM 기준 8.00 | NOMINAL_16 | 55,630 / 55,427.5 | 0.124 | 10,397 / 3,456 | 0 | 0 / 0 |
| 399 | add_h72 | 6 / 0x55F | 10,368 (0) | 16.00 | NOMINAL_16 | 107,493.5 / 107,184 | 0.096 | 20,757 / 10,368 | 0 | 0 / 0 |
| 400 | mul_h72 | 6 / 0x55F | 10,368 (0) | 16.00 | NOMINAL_16 | 107,516.5 / 107,110.5 | 0.096 | 20,757 / 10,368 | 0 | 0 / 0 |
| 401 | abs_h72 | 5 / 0x15F | **5,184** (0) | **32.00** | ABOVE_NOMINAL | 55,190 / 55,316.5 | 0.094 | 10,384 / 10,368 | 0 | 0 / 0 |

- **RQ1 비례**: ADD, MUL, ABS 모두 AO(H72)/AO(H24) = 3.000 → PROPORTIONAL. 절편 0.
  ADD/MUL은 이상적 사이클 대비 기울기 1.0, ABS는 0.5.
- **RQ2**:
  - ADD·MUL: 정확히 N/16, NOMINAL_16. Conv AB→OB의 15.60 (Stage 4AO)보다 높고, TRM 공식 16과 같다.
  - ABS: 정확히 N/32, ABOVE_NOMINAL.
    - 사전 정한 규칙에 따라, 이를 SU의 물리적 최대를 넘었다고 해석하지 않는다.
    - 가능한 설명은 단항 연산이 SU당 2원소를 처리하거나, AO_ACTIVE의 단항 경로 계수 방식이 다르다는 것이다. 이 데이터로는 구분되지 않는다.
    - TRM Table 4-12에는 8 bit Unary와 Binary 모두 1/SU로 되어 있어, 이 관측과 맞지 않는다.
- **블록당 비용 vs 처리율 (Elementwise 경로 한정)**: H24·H72 모두 block 1개인데 절편 0, RUN range 0이다. 이 경로에서는 "블록당
  고정 비용"이 관측되지 않는다. Conv의 2.3 % 차이 원인은 직접 증명하지 않는다 (경로가 다름).
- **RQ3 CB (ADD→MUL)**:
  - AO 6,912 = AO(add_h24) + AO(mul_h24) = 2 × 3,456. 논리 원소 2N 기준으로 16.0이다.
  - EXT write beat 3,456 = N/16: 최종 OFM만 외부에 쓰였고, 중간 텐서 (CHAINED, NHCWB16)는 외부에 쓰이지 않았다.
  - EXT read beat 10,397: IFM 3개.
  - NPU_ACTIVE 55,630은 ADD 단독 36,770 + MUL 단독 37,550 = 74,320보다 작다 (POST_HOC_DESCRIPTIVE).
    비체인 대조군이 없으므로 CB의 인과적 이득으로 주장하지 않는다.
- **RQ4 실행 비용 (POST_HOC_DESCRIPTIVE)**:
  - AO/NPU = 0.09–0.12. NPU_ACTIVE는 AO_ACTIVE의 약 8–11배다.
  - NPU_ACTIVE / (EXT rd + wr beat): ADD/MUL 3.45–3.61, ABS 2.66–2.84, ADD→MUL 4.02 cycle/beat.
  - Elementwise의 NPU_ACTIVE는 외부 메모리 전송과 함께 늘었다 (TA profile 1 = SYS_DRAM_Mid 에뮬레이션). AO가 실행 시간의 병목이 아니라는
    정황이지만, DMA 대기를 직접 측정한 것은 아니다 (AO/DMA stall 이벤트는 Reserved).
- **세션 1과 비교**: 세션 1 boot 387 (원 계약상 INVALID)의 ADD H24 AO 3,456 (POST_HOC)은 새 공식 결과 3,456과 같다.
  재현 boot (386: 3,538, 394: 3,534)도 boot 380 (3,534)과 허용폭 안에서 같다.

## 종료 (2026-11-15, owner 결정 ChatGPT 경유)

Stage 4AO-E 결과 확정·종료: ADD/MUL AO_ACTIVE = N/16, ABS = N/32, ADD→MUL = 2N/16 (CHAINED), Conv 1×1 ≈ N/15.60.
**Open Issue AO-1: ABS의 N/32** — TRM Table 4-12 (8 bit Unary 1/SU)와 불일치, 원인 미상. 추가 실측하지 않고 보존한다. 증명되지
않은 처리율이므로 일반 AO 성능 모델로 확대 적용하지 않는다.
