# E2B 계약 초안 — TA 읽기 지연 단일 변수 A/B (초안, 동결 전, 실행 미승인)

E2A(`README.md`)에 따른 초안이다. 별도 승인 전에는 측정·빌드·동결을 하지 않는다. 수치 기준은 승인 때 다시 확정한다.

## 1. 왜 이 변수인가

- Vela 민감도에서 A·B 두 군을 함께 크게 움직인 것은 Dram 읽기 경로(read_latency, burst_length)뿐이다.
- 소스상 Dram read 채널은 지연이 한계인 식이다. BW = 128·32/500·0.8 = 6.55 B/cycle.
- 정적 자료로는 "보드의 바이트당 서비스 비용이 Vela와 다른가"(H-E2-1b)를 판정할 수 없었다.
- 보드에서 이 경로의 지연만 바꾸면 다음 두 기울기를 같은 command stream에서 비교할 수 있다.
  - 보드 NPU_ACTIVE의 지연 기울기
  - Vela의 지연 기울기(민감도로 이미 알려짐)

## 2. 설계 (최대 5 boot)

| boot | 내용 |
|---|---|
| 1 | 기준 형상 재현 게이트(Stage 4K boot 375 DRWL, TA profile 1) |
| 2–3 | B군 형상 1개(e1r_c200_h37w37_o96, Conv 단독, IFM/OFM Dram): TA profile 1 / **TA_EXT rlatency만 1000**(새 profile, 나머지 11개 레지스터 동일) |
| 4–5 | A군 형상 1개(G12, A2 그래프): 같은 두 조건 |

- 고정: 이미지 `70090f1`, DDR/EXT 배치, Vela 5.0.0 MLEK 옵션. blob은 기존 것과 바이트 동일하고 header의 TA word만 다르다. command stream sha256이 같은지 확인한다.
- 단일 변수: TA_EXT RLATENCY 500 → 1000. MODE bit 0(동적 클럭)은 그대로 둔다. 바꾸면 에뮬레이션 자체가 바뀐다(S0-3).
- 세트당 5 RUN(1 warm-up + 4), pass A·B 모두. 이벤트는 6B-B와 같다: 35, 48, 51, 64, 80, 81 / 128, 130, 132, 135, 384, 386, 391.
- 같은 형상 안에서만 비교한다. A와 B 형상의 차이로 몫을 정하지 않는다. A·B는 래퍼와 배치가 함께 다르다.

## 3. 사전 예상 (승인 때 정수로 고정)

- Vela 예측(이미 계산됨, `sensitivity.csv`): 지연 ×2에서 total 비 = e1r_c200_h37w37_o96 ×2.00(85,815 → 171,630), G12 ×1.57(53,052 → 83,142).
- 판정 후보(closed set, 안):
  - `SERVICE_SLOPE_MATCHES_VELA`: 보드 NPU_ACTIVE 증가비가 Vela 비의 ±15 % 안.
  - `SERVICE_SLOPE_LOWER`: 보드 증가비가 Vela보다 작다. 겹침이나 다른 한계가 있다는 뜻이다.
  - `SERVICE_SLOPE_HIGHER`: 보드 증가비가 Vela보다 크다.
  - `UNRESOLVED`: 측정 범위 안에서 구분되지 않는다.
- MAC_ACTIVE는 두 조건에서 같아야 한다(H1-UC). 다르면 그 세트는 무효다.

## 4. 유효성·중단

- NPU_ACTIVE pass A range ≤ 5 %. 벗어나면 그 세트만 5 RUN을 더 하고, 그래도 벗어나면 UNSTABLE로 둔다.
- knob read-back 불일치, OFM 불일치, command stream digest 불일치가 나오면 무효로 하고 중단한다.
- TA 레지스터 read-back(11개)이 의도한 값과 다르면 중단한다.
- 5 boot로 구분되지 않으면 실험을 늘리지 않고 UNRESOLVED로 보고한다.

## 5. 하지 않을 것

Vela 옵션 변경, H1-UC 수정, TA MODE 변경, 래퍼·배치 동시 변경, 기존 판정의 소급 변경.
