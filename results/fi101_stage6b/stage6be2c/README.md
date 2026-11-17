# Stage 6B-E2C — 같은 Conv(G12)에서 래퍼·배치 통제 가능성 (보드 없음)

- 계약 `evidence/stage6b/stage6be2c/contract.md`(`f66b544`, 후보 컴파일 전 동결). 보드는 쓰지 않았다.
- facts: 원격 컨테이너(Vela 5.0.0)에서 6개 후보 × 지연 500/1000을 2회 컴파일했다. 두 파일의 sha256이 같다(`822802e5…`).
- 판정을 두 번 실행한 결과도 바이트 단위로 같다.

## 판정: **`READY_FOR_BOARD_REVIEW`** (배치 효과만 통제됨; 래퍼 효과는 통제 불가)

| 비교 | 분류 | 수치 정합성 | 근거 |
|---|---|---|---|
| B_W1 배치 (W1-P0 대 W1-P1, A2 그래프) | **PLACEMENT_ONLY** | **검증됨** | Conv 레지스터 차이는 ADDRESS뿐이다(IFM/OFM region, ADD에서 남은 IFM2_BASE0). weight·scale 바이트, kernel 수(1), 연산 목록, 블록·ublock·traversal, 포맷(NHCWB16)이 같다. Conv IFM/OFM은 Dram/Dram 대 Sram/Sram이다. 양쪽 Vela 500/1000 값은 estimator-only로 비교 가능하다 |
| B_W0 배치 (W0-P0 대 W0-P1, Conv 단독) | PLACEMENT_ONLY | **Vela 값 없음** | 같은 A0 blob에 runner placement만 다르다(command stream 동일, Stage 4 방식). Vela 쪽 출처로 정한 Shared_Sram 컴파일은 Conv를 6 kernel과 weight DMA로 다시 나눠 같은 실행 구성이 아니다. 그래서 보드 비교는 통제되지만 Vela 비교는 없다 |
| A_P0 래퍼 (W0-P0 대 W1-P0, Dram) | NOT_CONTROLLED | — | Conv IFM/OFM 포맷이 다르다(NHWC: PRECISION 1, stride 276/4416 대 NHCWB16: PRECISION 65, stride 16/4608/256). 고정 규칙상 ADD에서 남은 IFM2_*·IFM_SCALE·IFM_BROADCAST 레지스터도 COMPUTE 차이로 셌다 |
| A_P1 래퍼 (W0-P1 대 W1-P1, Sram) | NOT_CONTROLLED | — | 같은 이유 |

- 상호작용(4셀 모두 통제)은 식별할 수 없다.
- 사후 참고(판정 입력 아님): 남은 ADD 레지스터를 빼도 래퍼 비교는 LAYOUT 차이 때문에 `WRAPPER_PLUS_LAYOUT`이다.
  - Conv 단독 그래프는 그래프 IO가 NHWC로 정해진다. A2의 중간 텐서는 Vela가 NHCWB16으로 둔다.
  - 이번 후보 목록 안에서는 래퍼만 바꾸는 비교를 만들 수 없다.

## 1. 기존 자료 재현

- Revision A 기록과 Vela sha256이 같다: A0 `64c350eb…`, A2 `95cf070b…`.
- E2B 재계산이 기존 summary와 같다.
  - G12: ΔB 58,841.5, R_B 1.589 (ΔV 30,090, R_V 1.567).
  - CONV: ΔB 97,747, R_B 1.936 (ΔV 85,815, R_V 2.000).
- 절대 민감도(Δ)와 정규화 민감도(R)를 나눠 본다. G12는 절대값은 불일치하고 비율은 비슷하다. 이를 "지연 민감도를 전혀 예측하지 못함"으로 해석하지 않는다.
- G12(276→276, 16×16)와 E1-R Conv(200→96, 37×37)는 다른 형상이다. 둘의 차이를 래퍼 효과로 재해석하지 않는다.

## 2. G12 Conv 정체성과 셀별 실행 구성

| 셀 | 구성 | Vela sha | Conv kernel | Conv IFM/OFM | 포맷 | arena / fast |
|---|---|---|---|---|---|---|
| W0-P0 | A0, placement 0 | `64c350eb` | 1 | Dram/Dram | NHWC | 141,312 / 0 |
| W0-P1 | 같은 A0 blob, placement 1(region 1 → SRAM 포트) | `64c350eb` | 1 | Sram/Sram(runner) | NHWC | 141,312 / 0 |
| W1-P0 | A2 + `--arena-cache-size 0` | `eb299685` | 1 | Dram/Dram | NHCWB16 | 215,040 / 0 |
| W1-P1 | A2 (6B-B·E2B와 같음) | `95cf070b` | 1 | Sram/Sram | NHCWB16 | 141,312 / 147,456 |

- 쓰지 않은 후보: cache 16384(Conv 16 kernel, IFM Sram/OFM Dram), cache 65536(3 kernel, IFM Sram/OFM Dram), Shared_Sram(6 kernel).
- W1-P0는 계약 순서상 처음 성공한 cache 0이다.
- Conv 블록 8×16×64, ublock 2×2×32, DepthFirst, weight 4 stream + scale 바이트(상수 버퍼 sha256)가 네 셀에서 같다.
- **H1-UC MAC_ACTIVE 예상은 네 셀 모두 20,736**이다(6B-B·E2B 실측과 같은 값).
- W1-P0에서 Dram으로 옮겨지는 것은 Conv IFM/OFM, 즉 래퍼의 중간 텐서 두 개다. ADD 두 개의 입출력 배치도 함께 바뀐다. 이것은 IFM과 OFM을 함께 옮기는 복합 배치 변수다.

## 3. 입력·출력 검증 (CPU, tflite_runtime)

- A2를 6B-B 입력(a, b)으로 실행해 Conv 입력 중간 텐서를 얻었다(sha256 `ffe04446…`).
- 같은 값을 A0의 IFM으로 넣으면 A0 출력이 A2의 conv_out과 바이트 단위로 같다(`f13d5223…`). 양자화도 같다(scale 0.02353, zp −128).
- A2 출력은 기존 `ref_ofm.bin`과 같다.
- 두 tflite의 weight·bias 바이트가 같다.
- W1-P0는 A2와 같은 tflite라 reference가 같다.
- 보드용 DRWL은 아직 만들지 않았다(후속 계약 단계). W0 셀은 A0 IFM을 위 Conv 입력으로 다시 packing해야 한다.

## 4. Vela 예상값 (지연 500 → 1000, estimator-only 확인됨)

| 셀 | total 500 | total 1000 | ΔV | R_V | npu / sram_ac / dram_ac (500) |
|---|---|---|---|---|---|
| W0-P0 | 107,812 | 215,624 | 107,812 | 2.000 | 24,521 / 0 / 107,812 |
| W0-P1 | 없음 | — | — | — | Vela로 같은 구성을 만들 수 없음 |
| W1-P0 | 100,310 | 200,622 | 100,312 | 2.000 | 33,374 / 0 / 100,310 |
| W1-P1 | 53,052 | 83,142 | 30,090 | 1.567 | 33,314 / 28,800 / 44,709 |

- Vela는 A2의 중간 텐서를 Dram으로 옮기면 total이 1.89배가 되고, 지연 민감도가 3.3배가 된다고 본다.
- 연산별 값: Conv 24,290 → 56,249, 뒤 ADD 7,200 → 22,499.
- 이 값은 예상일 뿐이다. 보드 실측이 없으므로 새 예측 오차는 계산하지 않았다.

## 5. 식별 가능한 것과 아닌 것

- **식별 가능**
  - A2 그래프 안에서 Conv IFM/OFM(= 래퍼 중간 텐서) 배치 Dram 대 Sram의 효과(B_W1). 절대 실행시간과 지연 500/1000 반응, 보드 대 Vela 모두 비교할 수 있다.
  - Conv 단독에서 IFM/OFM 배치 효과(B_W0). 보드끼리만 비교할 수 있다.
- **혼재**
  - B_W1은 IFM과 OFM을 함께 옮긴다. 두 ADD의 메모리 경로도 바뀐다.
  - B_W0의 SRAM 이동은 그래프 IO 이동이고, region 1이 SRAM 포트로 가면서 가중치와 같은 SRAM 포트를 공유한다(Stage 4 placement와 같은 한계).
  - 물리 메모리(DDR 대 ISRAM)·AXI 포트·TA(EXT 대 SRAM)가 함께 바뀐다.
- **식별 불가**: 래퍼 단독 효과(H-E2C-W), 상호작용. 래퍼 효과에 포맷(NHWC 대 NHCWB16) 차이가 섞인다.
- **메커니즘**: 래퍼 안의 명령 비용·추가 데이터 이동·중첩은 `MECHANISM_UNRESOLVED`이다.

## 6. 후속 보드 계약 초안

`e2d_board_contract_draft.md` (9 boot / 90 RUN, 이미지 교체 1회, 실행 미승인).
