# E2D 보드 계약 초안 — G12 Conv 배치 통제 × EXT 읽기 지연 (초안, 동결 전, 실행 미승인)

E2C(`README.md`) 결과에 따른 초안이다. 보드 측정에는 별도 승인이 필요하다. 수치 기준은 승인 때 다시 확정한다.

## 1. 대상 (통제 가능한 셀만)

| 셀 | 실행 구성 | 지연 |
|---|---|---|
| W1-P0 | A2 + `--arena-cache-size 0`(Vela `eb299685…`), placement 0 | 500, 1000 |
| W1-P1 | A2(Vela `95cf070b…`, 6B-B·E2B DRWL `928296b1…`), placement 0 | 500, 1000 |
| W0-P0 | A0(Vela `64c350eb…`), placement 0, IFM = A2 Conv 입력(`ffe04446…`) | 500, 1000 |
| W0-P1 | 같은 A0 DRWL, placement 1 | 500, 1000 |
| REF | Stage 4K `s4c2_conv_cin48` | 500 |

- 주 비교: **B_W1 배치**(보드 대 Vela, 절대·정규화 둘 다).
- 보조 비교: **B_W0 배치**(보드끼리만, Vela 값 없음).
- 래퍼 비교(W0 대 W1)는 포맷이 섞여 있으므로 기술 통계로만 쓴다(`WRAPPER_PLUS_LAYOUT`).

## 2. 예산과 순서 (9 boot / 90 RUN, 이미지 교체 1회)

- L500 이미지(`70090f1`): REF → W1-P0 → W1-P1 → W0-P0 → W0-P1.
- 복원 후 L1000 이미지(E2B와 같은 bram `fd478e2d…`): W0-P1 → W0-P0 → W1-P1 → W1-P0. 역순으로 둬서 시간 drift의 선형 성분을 균형 배치한다.
- boot마다 pass A·B 각 5 RUN(1 warm-up + 4).
- W1-P1·W0-P0는 지연 쌍의 시간 간격이 가장 짧고, W1-P0·W0-P1은 가장 길다. 이 비대칭을 판정 해석에 적는다.
- 시간 drift는 REF로 시작 때만 확인한다. W1-P1의 L500이 E2B boot 436(99,866)을 재현하는지도 확인한다.

## 3. 준비물 (승인 후, 측정 전 커밋)

- DRWL 3개를 새로 만든다: W1-P0, W0-P0(=W0-P1, IFM 지정 packing). 각 DRWL의 cms·const sha256이 E2C facts와 같아야 한다. reference 출력도 함께 둔다.
  - W1-P0·W1-P1: A2 출력 `f13d5223…`.
  - W0: A0 출력 = A2 conv_out `f13d5223…`.
- W0-P1 placement 1의 SRAM arena 크기 확인(Stage 4 placement 게이트).
- 판정 코드는 E2B judge를 일반화한다(조건별 이미지·readback·placement). 테스트와 mutation을 포함한다.

## 4. 사전 예상 (Vela, E2C facts)

| 셀 | V500 | V1000 | ΔV | R_V |
|---|---|---|---|---|
| W1-P0 | 100,310 | 200,622 | 100,312 | 2.000 |
| W1-P1 | 53,052 | 83,142 | 30,090 | 1.567 |
| W0-P0 | 107,812 | 215,624 | 107,812 | 2.000 |

## 5. 가설과 판정 규칙(안)

- 각 셀의 민감도 판정은 E2B와 같다: tol = max(1 %, ranges), 밴드 0.15·|ΔV| + tol, 식별력 tol ≤ 0.5·|ΔV|.
- **H-E2C-P (배치)**: 배치가 실행 비용과 지연 반응을 바꾼다.
  - 예상: W1-P0의 B500과 ΔB가 W1-P1보다 크다.
  - 반례: W1-P0와 W1-P1의 ΔB 차이가 tol 안이다(배치 무관).
- **H-E2C-O (Vela 중첩)**: Vela의 연산별 max·그래프 합 가정이 SRAM·DRAM 동시 사용 구간을 낙관한다.
  - 예상: 보드/Vela 비(B/V)가 W1-P1(E2B 1.88–1.91)보다 W1-P0에서 1에 가깝다. Vela는 W1-P0를 DRAM 하나가 지배한다고 보고, 이 경우 Conv 단독처럼 맞았다.
  - 반례: W1-P0의 B/V도 1.9 근처다. 그러면 배치와 무관한 래퍼 쪽 비용이 남는다.
- **H-E2C-W (래퍼)**: 이 설계로는 통제되지 않는다. W0-P0와 W1-P0의 차이는 래퍼와 포맷이 섞인 기술 값이다.
- 위 판정이 나와도 IFM과 OFM 각각, 포트, TA, 물리 메모리의 몫은 나누지 않는다.
- 래퍼 안의 메커니즘은 `MECHANISM_UNRESOLVED`로 둔다.

## 6. PMU

- pass A·B 기존 구성을 쓴다(35, 48, 51, 53*, 55*, 64, 80, 81 / 35, 128, 130, 132, 135, 384, 386, 391). *는 예약 이벤트로 탐색용이다.
- 포트별 접근량은 SRAM/EXT 집계만 있다. outstanding·요청 정체 전용 공개 이벤트는 현재 pass에 없다. 추가하려면 event 집합 변경을 별도 계약으로 다룬다.
- WD-2 미해결 문제는 그대로 둔다. WD_STALLED 증가를 메모리 대기 시간으로 바꿔 해석하지 않는다.

## 7. 유효성·중단·복원

E2B와 같다: CONFIG_MISMATCH(이미지, TA readback, placement readback 포함)이면 중단하고, 출력 PASS_EXACT, 5 % range, 실패 조건 대체 금지. deploy → restore → deploy → restore → postflight 순서로 RESTORE VERIFIED를 확인한다.
