# Stage 4WD — Weight Decoder 보드 측정 계약 (**동결 2026-11-15, boot 402 전**)

초안 `contract_draft.md`를 대체한다. 측정 조건 (모든 숫자): FI101 Ethos-U85 1024 MAC, **TA profile 1**, 이미지 `70090f1`, DDR/EXT
(DRWL word 7 = 0), Vela 5.0.0 (MLEK 옵션), pass A/B 각 warm-up 1 + 측정 4 RUN.
근거: `docs/plan/stage4wd_characterization_plan.md`. 코드: `host/analysis/stage4wd.py` (test_stage4wd 16개, mutation 32/32),
`host/container/stage4wd_models.py`. 유효성은 Stage 4AO-E A1과 같은 `stage4aoe.config_result` (A1 정체성, workload sha256,
PASS_EXACT, RUN validity, 안정성)를 쓴다.

## 0. owner 결정 (ChatGPT 경유 "Stage 4WD — WD 처리 특성 실보드 측정 승인 및 실행")

- 실험 A·B 8 boot / 80 RUN 승인. 재현 Gate에 WD_ACTIVE 허용폭 추가 승인. 실험 C 제외. WD-1·AO-1은 보존만 한다.
- 동결 때 더한 조건:
  1. 실험 A의 계산 활동을 따로 판정한다 (`verdict_mac`): 모든 RUN에서 MAC_ACTIVE가 dense와 같으면 MAC_SAME, 아니면 MAC_CHANGED. MAC_DPU_ACTIVE도 같은 방식 (DPU_SAME / DPU_CHANGED).
  2. 실험 A의 모델 우선순위: ENCODED_PROPORTIONAL > STAGED_PROPORTIONAL > CONSTANT. 여러 모델이 맞으면 우선순위의 첫 번째를 판정으로 하고, 나머지는 `also_satisfied`에 함께 보고한다. MONOTONE은 방향만 말하는 보조 범주이고 byte 모델을 증명하지 않는다.
  3. 결과를 본 뒤 모델 계수 (4AO fit, dense 기준 비례)를 다시 추정하지 않는다.
  4. golden = BUILTIN_REF 출력 (8개 모두 기본 커널과 바이트 동일, sha256 확인). 서로 다른 weight 구성의 출력은 같을 필요가 없다.
  5. SRAM 읽기 바이트 ÷ WD_ACTIVE를 WD의 실제 디코딩 처리율로 해석하지 않는다 (bias/scale 포함, 32 B/cycle과 일치해도 최대 처리율 도달로 단정하지 않음).

## 1. 대상 (고정 순서)

| 순서 | config | 실험 | DRWL |
|---:|---|---|---|
| 1 | `s4ao_conv1x1_h24` | 재현 Gate (Stage 4AO-E boot 394 기준) + A·B 공통 기준 | 4AO `bee0fbcb…` |
| 2 | `s4wd_w_small` | A | `evidence/stage4wd/workloads` |
| 3 | `s4wd_w_sparse75` | A | 같음 |
| 4 | `s4wd_w_sparse90` | A | 같음 |
| 5 | `s4wd_h23` | B | 같음 |
| 6 | `s4wd_h32` | B | 같음 |
| 7 | `s4wd_h34` | B | 같음 |
| 8 | `s4ao_conv1x1_h36` | B | 4AO `da5b9049…` |

- 8 boot / 80 RUN, **boot 402–409** (마지막 사용 번호 401 확인).
- 정적 전제 (`static.json` `_checks`) 모두 true:
  - A: 같은 schedule, encoded 크기와 staged 크기가 서로 다름.
  - B: 같은 block과 같은 stream, block 묶음 16 / 24.
  - golden이 모호하지 않음 (기본 커널 = BUILTIN_REF).
- A1 manifest: `evidence/stage4wd/workloads/expected_identity.json`. 8개 모두 n_base 5, placement 0 → REGIONCFG 0x15F.

## 2. 재현 Gate (boot 1)

`stage4aoe.repro_gate`와 같은 검사로, 기준을 Stage 4AO-E boot 394 (`s4ao_conv1x1_h24`) 사본으로 둔다.
- K.reproduce: MAC, DPU, 출력, 상수 카운터, NPU.
- AO 허용폭 35.34.
- **WD_ACTIVE |차이| ≤ max(25, 2 %, range 합)** (boot 394 WD_ACTIVE 1,051, range 36).

FAIL이면 중단한다.

## 3. 판정 (데이터 전 고정, `stage4wd.py judge`; 예측 `results/fi101_stage4wd/predictions.json`)

- 같음의 기준: |a − b| ≤ max(25, 2 % × 평균, pass-A WD_ACTIVE range_a + range_b).
- **실험 B** (`verdict_b`):
  - BLOCK_LIKE: {H23, H24}와 {H32, H34, H36} 안에서 각각 같고, 두 묶음이 다르다.
  - N_LIKE: 각 묶음 안에서 N 순서대로 증가하고, 그 차이가 허용폭을 넘는다.
  - 그 밖은 NEITHER, 값 누락은 INCOMPLETE.
- **실험 A** (`verdict_a`, 이 순서로 검사):
  - ENCODED_PROPORTIONAL (WD = WD_dense × encoded/encoded_dense, 모든 구성)
  - STAGED_PROPORTIONAL (staged 비율)
  - CONSTANT (모두 dense와 같음)
  - MONOTONE (encoded가 줄면 WD도 허용폭을 넘어 줄어듦)
  - OTHER / INCOMPLETE
- **보조 (정확 규칙, `verdict_sram`)**: 8개 모두 SRAM rd beat = spatial block × staged/16이면 HOLDS, 아니면 FAILS.
- WD_STALLED, NPU_ACTIVE, MAC_ACTIVE, AO_ACTIVE, beat는 기술 통계로만 낸다 (원인 배정 없음).
  WD_STALLED로 공급 부족과 backpressure를 분류하지 않는다.
- 해석 제한:
  - A에서는 encoded 크기와 staged (bias/scale) 크기가 함께 바뀐다. 두 비례 가설을 모두 판정 집합에 넣었다.
  - B에서 block 형상은 Vela가 고른 6×12×96로 같지만, IFM 행 수와 MAC 양도 N과 함께 바뀐다.

## 4. 실행·Gate·fail-fast·복원

Stage 4AO-E A1 계약 (`evidence/stage4aoe/contract_a1.md`)과 같다.
- 실행 전 G0: sha256 대조, 8개 정적 정체성, 보드 dry run.
- boot마다 boot-check (A1). boot 1 뒤에 repro-gate.
- 실패하면 즉시 중단하고 복원한다. 실패 경로에서는 postflight를 따로 실행한다.
- 원시 데이터와 sha256을 보존한다. m6 복원 → PING state 1 → 카드 분리.
- push는 하지 않는다.

## 5. 실패·불확실 결과 처리

| 결과 | 처리 |
|---|---|
| 재현 Gate FAIL | 해석하지 않는다 |
| INVALID / 출력 불일치 | 재측정하지 않는다. `output_mismatch.bin`을 분석한다 |
| MEASUREMENT_UNSTABLE | 그 구성은 판정에서 빠진다 (INCOMPLETE). 추가 RUN은 승인 사항이다 |
| NEITHER / OTHER | 관측값과 예측값을 보고한다. 모델은 바꾸지 않는다 |
| SRAM 규칙 FAILS | 재스트리밍 해석을 보류하고, 어긋난 구성을 보고한다 |

## 6. 승인 필요

1. 실험 A·B 보드 측정 (8 boot / 80 RUN).
2. 재현 Gate에 WD_ACTIVE 허용폭을 추가하는 것.
3. 실험 C는 제안으로만 둔다.
