# E2 계약 초안 — Vela 예측 오차의 분해 (초안, 동결 전, 실행 미승인)

Stage 6-M §9에 따른 초안이다. 별도 승인 전에는 측정·컴파일·동결을 하지 않는다. 값과 기준은 승인 때 다시 확정한다.

## 1. 질문

Vela가 1×1 DepthFirst Conv의 NPU 사이클을 예측할 때 생기는 오차를 셋으로 나눈다.
1. MAC 계산 비용 오차
2. 그 밖의 비용(AO, weight decode, DMA·메모리) 오차
3. 측정 범위·단위 차이

## 2. 이미 있는 것 (Stage 6-M `e2_link.csv`, TA profile 1, 이미지 70090f1)

| 양 | 출처 | 단위 | 상태 |
|---|---|---|---|
| H1-UC MAC_ACTIVE | 식, 13개 형상에서 실측과 정확히 같음 | NPU 사이클 | 6B-B VALID 7 + E1-R 6 |
| 실측 MAC_ACTIVE | PMU event 48 | NPU 사이클 | 같음 |
| Vela Conv `mac_cycles` | Vela debug DB | NPU 사이클(Vela 시스템 설정 기준) | 6B-B: H1-UC의 1.09–2.42배, E1-R: 0.90–1.17배 |
| Vela Conv `op_cycles`, 그래프 `cycles_total` | Vela | 위와 같음 | 그래프 범위가 서로 다름(A2 vs Conv 단독) |
| 실측 NPU_ACTIVE | PMU event 35 | NPU 사이클 | 6B-B는 ADD 2개와 DMA 포함 |

## 3. 검증할 가정 (각각 사전 고정된 판정을 둔다)

- **E2-a MAC 항**: Vela `mac_cycles`와 H1-UC의 차이가 어떤 H1-UC 인자(F_sp, F_cout, F_cin)와 함께 움직이는가.
  - 보드 측정 없이 기존 13개 형상과 원본 93개 연산의 정적 값으로 먼저 할 수 있다.
- **E2-b 비MAC 항**: NPU_ACTIVE − MAC_ACTIVE를 Vela의 AO·weight·메모리 사이클 추정과 비교한다.
  - 메모리 대기라고 해석하지 않는다.
  - Vela 메모리 모델(SYS_DRAM_Mid)과 보드 TA profile 1 에뮬레이션이 같다는 것은 증명되지 않았다(6B-R `vela_configuration_audit.md`의 UNKNOWN 항목).
- **E2-c 그래프 범위**: Conv 단독(E1-R)과 A2 그래프(6B-B)의 오차 차이가 ADD·DMA 몫으로 설명되는가.
  - 보드 측정이 필요하다면 Conv 단독과 A2를 같은 형상으로 짝지어 잰다.

## 4. 고정할 것 (승인 시)

- 측정 조건: TA profile 1, 이미지 70090f1, DDR/EXT, 기준 형상 재현 게이트(Stage 4K boot 375 DRWL), 세트당 5 RUN(1 warm-up + 4 측정), NPU_ACTIVE pass A range ≤ 5 %, NPU 사이클 하한(예: Vela ≥ 50 k)
- 비교 단위: NPU 사이클. Vela 값은 Vela 시스템 설정(`Ethos_U85_SYS_DRAM_Mid_1024`, 1 GHz) 기준임을 함께 적는다.
- 오차 정의: (실측 − Vela)/Vela. 부호 규칙은 6B-B와 같게 한다.
- 판정 closed set(안): `DECOMPOSED_MAC_DOMINANT` / `DECOMPOSED_NON_MAC_DOMINANT` / `NOT_DECOMPOSABLE` / `INSUFFICIENT_EVIDENCE`. 임계값은 승인 때 정한다.

## 5. 하지 않을 것

- Vela 옵션 변경, H1-UC 수정, 모델 전체 NPU_ACTIVE를 독립 연산의 합으로 복원하기
- WD_STALLED·AO 병목을 MAC 결과로 설명하기
- 기존 판정(6B-B FIDELITY_PARTIAL, Stage 6 INSUFFICIENT_EVIDENCE)의 소급 변경
