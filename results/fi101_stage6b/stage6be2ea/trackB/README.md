# Stage 6B-E2E-A Track B — 남은 EXT 접근 비용과 Vela 오차의 원인 분리 설계 (보드 없음)

- 계약 `evidence/stage6b/stage6be2ea/contract.md`(`603ed72`).
- Vela facts: 원격 컨테이너 Vela 5.0.0, MLEK 옵션, 2회 추출해 같은 sha256(`3dc618db…`).
- 판정을 두 번 실행한 결과가 바이트 단위로 같다.
- 보드 값은 모두 E2D Amendment A(boot 449–457, **TA profile 1**, EXT RLATENCY 500 = `70090f1` / 1000 = L1000 이미지)다.

## 판정

| 항목 | 결과 |
|---|---|
| Track B | **`READY_FOR_BOARD_REVIEW`**. A2에서 graph IO만 옮기는 통제 비교(B0 대 B3) 확보 |
| W0-P0 Vela 과대예측 원인(`overprediction_cause`) | **`SUPPORTED`**(C1·C2·C3 모두 SUPPORTED). 단, C1은 약하다(§3) |

## 1. E2D 재계산 (B1)

- 원시 자료로 E2D 판정을 다시 실행했다. summary가 커밋된 파일과 바이트 단위로 같다(I1).
- 구성별 PMU·Vela 표: `e2d_table.csv`.
- 배치·지연·상호작용 값은 E2D README와 같다.
  - A2 배치 효과 21,512 / 68,247
  - 지연 효과 P0 106,007, P1 59,272
  - 상호작용 46,735

Vela 합산 방식이 포함하는 것과 빠뜨리는 것(E2A 소스):
- 포함: 연산마다 max(npu, SRAM 접근, DRAM 접근)를 그래프에서 단순 합한다.
  - npu = MAC·AO·명령 발행 균형식 + 가중치 DMA/LUT
  - 메모리 = 채널별 바이트 ÷ 지연 한계 BW, burst 효율로 바이트를 부풀림
- 빠뜨리는 것:
  - 연산 사이의 겹침이나 대기
  - 같은 연산 안에서 SRAM과 DRAM, 계산과 메모리가 동시에 쓰일 때의 경합(max로 하나만 셈)
  - 고정 비용

## 2. A2 graph IO 경로 (B2)

| 조건 | 생성 | 내용 |
|---|---|---|
| B0 | 있음 | E2D W1-P1 DRWL `928296b1…`, placement 0 |
| **B3** | **있음** | 같은 DRWL, header word 7 = 1. command stream이 바이트 단위로 같다. runner가 region 1(그래프 IO arena)만 SRAM 포트로 옮긴다 |
| B1·B2 | **UNAVAILABLE** | 입력·출력을 따로 옮기려면 `--separate-io-regions`가 필요하다. Vela가 COP2 형식을 요구하며 거부했다. runner의 placement는 region 1 전체를 옮긴다 |

검증:
- **실행 구성**: B0와 B3의 command stream이 같다. Conv·ADD kernel 3개, 블록·ublock·traversal, 가중치, 양자화, activation, 연산 순서가 모두 같다. 중간 텐서는 fast region(2, SRAM)으로 두 조건에서 같다.
- **region 표**(A2 n_base 6):
  - placement 0에서 EXT 포트의 region은 {0, 1}이고, placement 1에서는 {0}이다.
  - kernel이 쓰는 region: IFM/IFM2/OFM ∈ {1, 2}, WEIGHT·SCALE = {0}.
  - 따라서 B3에서 EXT에 남는 것은 가중치·scale(그리고 NPU가 DDR에서 가져오는 command stream)뿐이다 → **`WEIGHT_ONLY_EXT_PATH`**.
- **보드 근거(같은 메커니즘, Conv 단독)**:
  - E2D W0-P1(graph IO SRAM)의 EXT read는 180,864 B다. Vela의 가중치 + scale 실제 바이트 180,512 B와 command stream 348 B를 더한 값과 4 B 차이다.
  - EXT write는 0이다.
  - placement 1이 가중치만 EXT에 남긴다는 것이 보드에서 확인된 셈이다.
- **SRAM 용량**: SRAM arena `0x31076770` + 2 MiB < `0x31400000`(fast memory 끝 0x31060000 뒤). 중간 텐서 fast region(0x31000000–0x31024000)과 겹치지 않는다.
- **출력 reference**: B0와 같은 golden `b9341e6f…`(BUILTIN_REF). CPU 결과 회수는 runner의 OUTPUTS 경로이고, Stage 4 placement와 E2D W0-P1에서 검증됐다.
- **Vela 값**: B3와 같은 실행 구성을 Vela로 만들 수 없다. `--memory-mode Shared_Sram`은 Conv를 3 kernel로 나눈다. 그래서 `NO_COMPARABLE_VELA_ESTIMATE`이고, B0의 Vela 값(53,052 / 83,142)만 쓴다.

## 3. W0-P0 Vela 과대예측 (B3)

| 항목 | Vela (A0, 지연 500) | 보드 (W0-P0) |
|---|---|---|
| DRAM FM read | 706,560 B(burst 효율 반영). 실제 원소 353,280 B → **2.0배 부풀림** | — |
| 가중치 + scale read | 174,752 + 5,760 B | — |
| DRAM read 합 | 887,072 B(효율 0.6017) → 실제 533,792 B | **477,824 B**(EXT read beat × 16) |
| burst | NHWC read: 블록 깊이 64 × 8 bit → 64 B(최대 128 B 대비 2배) | 평균 **79.3 B**(beat/트랜잭션) |
| 채널 BW | IFM 6.5536 B/cycle(500), 3.2768(1000). 지연 한계 = 128 B × 32 / 지연 × 0.8 | 전체 read 처리율 8.61(500), 4.66(1000) |
| 비용 | FM ac 107,812 = 706,560 / 6.5536. total = DRAM(npu 24,521) | 55,466.5 / 102,615.5 |

규칙 판정:
- **C1 SUPPORTED**: 보드 EXT read 처리율 > Vela IFM 채널 BW, 두 지연 모두.
- **C2 SUPPORTED**: 부풀림 1.66배(전체 read), 보드 burst 79.3 B > Vela 가정 64 B.
- **C3 SUPPORTED**: 보드/Vela 실제 바이트 0.895.
- **C4**: DRAM 지배(total = dram_ac > 2 × npu).
- → **원인 SUPPORTED**(Vela의 DRAM 읽기 비용 모델이 실측보다 비관적).

**C1의 약점(정직하게 적음)**:
- C1은 고정 규칙대로 EXT read 전체(가중치 포함)를 IFM 채널 BW와 비교했다.
- Vela처럼 가중치를 별도 채널로 빼면, 보드 IFM 처리율은 5.36(500) / 2.90(1000) B/cycle로 Vela BW보다 **낮다**.
- 따라서 "Vela의 채널 처리율 가정 자체가 비관적"이라는 근거는 강하지 않다.

**사후 기술(`POST_HOC_DESCRIPTIVE`, 판정 입력 아님)**:
- burst 부풀림만 빼고 Vela 자신의 채널 BW로 실제 FM 바이트를 나누면 53,906(500) / 107,813(1000)이다. 보드 55,467 / 102,616과 +2.9 % / −4.8 % 차이다.
- 같은 결과를 estimator-only 민감도에서도 본다(`w0p0_sensitivity.csv`): `Dram_burst_length 64`(부풀림 해제) 또는 `Dram_read_latency 250`이면 total 53,906, 보드/Vela 1.028.
- 26개 변형 모두 command stream이 같다. 다른 변수는 W0-P0를 움직이지 않는다.
- 이 일치는 사후 보정이며 하드웨어 검증 결과가 아니다.
- 그래도 2배 과대예측의 주된 출처가 **NHWC IFM read의 burst 효율 가정(64 B burst를 128 B 비용으로 셈)**이라는 해석과 가장 잘 맞는다.

## 4. 파이프라인 가설 (B 단계, 보드 전 정의)

| 가설 | B0 대 B3에서 예상 | 반례 |
|---|---|---|
| H-IO(그래프 IO EXT 비용) | B3의 NPU_ACTIVE와 지연 효과가 B0보다 작다. EXT read beat가 27,066 → 약 11,321(가중치+scale+A2 cms 628 B)로 준다 | 지연 효과 차이가 tol 안이면 IO 몫은 식별되지 않는다 |
| H-WEIGHT(남은 가중치 공급) | B3의 지연 효과가 tol보다 크다. W0-P1(가중치만 EXT)은 이미 +13,545(+50 %)였다 | B3 지연 효과가 tol 안이면 가중치 공급 지연은 작다 |
| H-OVERLAP(중첩·의존성) | B0 대 B3 차이가 IO 바이트 변화에서 기대되는 것과 다르게 나온다(예: IO 바이트는 크게 줄어도 NPU 차이가 작음) | 정적·현 PMU로 직접 가를 수 없음 → 결과가 무엇이든 `MECHANISM_UNRESOLVED` 유지 |

B3에서 지연 반응이 남아도 그것만으로 WD를 원인으로 정하지 않는다.

## 5. 계측 계획 (B4) — 8카운터, 각 pass에 NPU_ACTIVE

- pass A·B는 E2D와 같다(35 48 51 53* 55* 64 80 81 / 35 128 130 132 135 384 386 391).
- **pass C 후보(공개 TRM 110 이벤트만)**: 35, 385 ext_rd_trans_completed, 387 ext_rd_tran_req_stalled, 398 ext_rd_stall_limit, 643 ext0_rd_tran_req_stalled, 659 ext1_rd_tran_req_stalled, 160 axi_latency_any, 166 axi_latency_1024.
  - axi_latency 히스토그램의 정확한 의미(bin 정의, 대상 포트)는 TRM 문구로 확인한 뒤 공식 지표로 쓴다.
  - 그 전까지는 탐색용이다.
- pass C를 넣으면 boot당 RUN이 15가 된다. 쓰려면 별도 결정이 필요하다(아래 초안은 pass A·B만 씀).
- 유닛 Active/Stalled를 더하거나 빼서 대기시간을 만들지 않는다. 통제 변수 변화에 대한 NPU_ACTIVE와 활동의 변화를 함께 본다.

## 6. 후속 보드 계약 초안 (B5, 실행 미승인): `e2e_board_contract_draft.md`

5 boot / 50 RUN: REF, B0·B3 × 지연 500/1000.

## 7. 연구 방향 권고

1. B0 대 B3 보드 측정(5 boot): A2 SRAM 배치의 EXT 지연 비용 중 그래프 IO 몫과 가중치 몫을 가른다.
2. Vela의 NHWC burst 효율 가정은 정적 결과로 충분히 좁혀졌다. 보드 확인을 하려면 같은 Conv에서 IFM 포맷만 바꾸는 비교가 필요하다. 그러나 E2C에서 본 대로 Conv 단독 그래프의 IO 포맷은 Vela가 정하므로 통제가 어렵다. 우선순위는 낮게 둔다.
3. Stage 6C는 1 결과 뒤에 판단하기를 권고한다.
