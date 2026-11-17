# E2E 보드 계약 초안 — A2 graph IO 배치(B0 대 B3) × EXT 읽기 지연 (초안, 동결 전, 실행 미승인)

## 1. 고정

- 그래프: G12 A2(ADD → Conv → ADD(self)). DRWL `928296b1…`(E2D W1-P1과 같은 파일).
- 중간 텐서: fast region 2, on-chip SRAM. 가중치·scale: region 0, DDR/EXT.
- 입력·golden: 6B-B fixture, `b9341e6f…`.
- 이미지: L500 `70090f1`, L1000 bram `fd478e2d…`(EXT RLATENCY만 다름). TA profile 1.
- 판정 코드: E2D Amendment A(`placement_identity`)를 그대로 쓴다.

## 2. 변수

| 조건 | DRWL | graph IO | 지연 |
|---|---|---|---|
| B0 | `928296b1…`(placement 0) | DDR/EXT | 500, 1000 |
| B3 | 같은 DRWL, header word 7 = 1 | on-chip SRAM/SRAM 포트 | 500, 1000 |

B0는 E2D boot 453/454에서 측정된 값이 있다. 같은 세션 안에서 시간 균형을 맞추기 위해 다시 잰다. 이전 값은 재현 확인에만 쓴다.

## 3. 예상(보드 전 동결 대상)

- MAC_ACTIVE = H1-UC 20,736(두 조건 모두).
- Vela: B0 53,052 / 83,142. B3는 `NO_COMPARABLE_VELA_ESTIMATE`.
- EXT read: B0 27,066 beat(E2D). B3 ≈ 11,321 beat(가중치 174,752 + scale 5,760 + A2 command stream 628 = 181,140 B; W0-P1의 같은 가중치 경로 실측 180,864 B 참고). ±1 %를 정적 기대값으로 동결한다.
- EXT write: B3 0. SRAM write는 B0의 EXT write(그래프 출력)만큼 늘어난다.

## 4. 순서와 예산 (5 boot / 50 RUN, 이미지 교체 1회)

| boot | 조건 |
|---|---|
| 1 | REF (L500) |
| 2 | B0 L500 |
| 3 | B3 L500 |
| 4 | B3 L1000 |
| 5 | B0 L1000 |

boot마다 pass A·B 각 5 RUN(1 + 4). pass C(EXT 요청 정체·지연 히스토그램)는 별도 결정 사항이다. 넣으면 RUN이 boot당 15로 는다.

## 5. 판정(안, E2D와 같은 형식)

- 유효성: VALID / PARTIAL_VALID / MEASUREMENT_INVALID. placement·REGIONCFG·TA readback·출력·5 % 기준.
- IO 효과(L) = B_B0(L) − B_B3(L). tol = max(1 %, ranges). 두 지연 모두 |효과| > tol이고 같은 부호이면 `IO_EFFECT_OBSERVED`.
- 지연 효과: B0, B3 각각. B3의 지연 효과 > tol이면 "가중치 경로만 남은 상태에서도 지연 반응 있음"(H-WEIGHT와 일관)으로 기록한다. 원인 확정은 하지 않는다.
- IO 몫(기술): (LE_B0 − LE_B3)과 LE_B3의 비. EXT read 바이트 변화와 나란히 보고한다.
- Mechanism: `MECHANISM_UNRESOLVED` 고정(DMA 중첩 대 AO/WD 역압력을 가르는 측정이 없음).
- 금지: Active/Stalled 합으로 분해, WD_STALLED를 대기 총량으로 보기, Vela 값이 없는 B3에 Vela 오차 계산.

## 6. 중단·복원

E2D와 같다: REF 게이트 FAIL, CONFIG_MISMATCH, UNMEASURED이면 멈추고 카드를 복원한다. 재측정·대체·추가 boot는 하지 않는다. RESTORE VERIFIED와 postflight를 기록한다.
