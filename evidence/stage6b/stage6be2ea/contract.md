# Stage 6B-E2E-A 계약 — Track A(과거 판정 결함 감사)와 Track B(메모리·파이프라인 비용 분리 설계)

지시: Stage 6B-E2E-A 공식 지시(2026-11-17). 보드 측정은 하지 않는다. 기존 Stage 4–E2D 파일과 판정은 바꾸지 않는다.
이 계약, 감사·판정 코드, 테스트는 결과를 만들기 전에 커밋한다. Track A와 Track B는 계약·판정·산출물을 나눈다.

## 계약 전 노출

- 호출 경로를 grep으로 확인했다.
  - `stage4k.identity`를 직접 부르는 곳: `stage4k.config_result`, `stage4ao`, `stage4aoe.identity_a1`.
  - `identity_a1`을 거치는 곳: `stage4wd`, `stage6bb.identity_of`.
  - `identity_of`를 거치는 곳: 6B-B, E1, E1-R, E2B, E2D.
  - `stage4p`(Stage 4 placement)는 자기 placement 검사를 쓴다.
- W0-P0(E2D)의 Vela 값을 E2A 소스식으로 대략 계산해 보았다. IFM이 OFM 깊이 블록 5개마다 다시 읽히고, NHWC burst 64 B가 128 B로 부풀어 2배가 되며, Dram read 채널은 6.55 B/cycle이다. 그 결과 107,812 근처가 나왔다. 보드 EXT read 처리율(약 8.6 B/cycle)이 Vela 채널 상한보다 크다는 것도 E2D 표에서 계산했다. 아래 B3 규칙은 이 노출 뒤에 정했다.

---

## Track A — `stage4k.identity`의 `placement == 0` 고정 항 영향 감사

### A1. 수집 (산출물 `trackA/`)

1. 정적 호출 그래프: 위 모듈들의 import·호출 줄(grep 결과 그대로).
2. 실험별 판정 경로 표: 실험, 판정 모듈, `stage4k.identity` 실행 여부(코드 경로상 config 판정마다 호출되는지), 원시 자료 위치.
3. **원시 자료 전수 스캔**: 저장소 `evidence/` 아래 모든 `raw_runs.json`의 RUN 기록에서 `placement` 값 집합, 원시 자료 묶음(run root), 그 묶음을 판정한 실험을 모은다.
4. E2D 원래 세션(boot 440–442)을 정정 판정 코드(Amendment A, `347712c`의 `stage6be2d.placement_identity`)로 따로 재판정한 결과. 원래 판정은 바꾸지 않는다.

### A2. 실험별 분류 (closed set)

- `UNAFFECTED`: 그 실험의 판정 경로가 `stage4k.identity`를 쓰지 않거나, 쓰더라도 판정한 모든 RUN 기록의 placement가 0이다(고정 항이 참이므로 판정에 영향 없음).
- `JUDGE_FALSE_REJECTION`: `stage4k.identity`를 거쳐 판정한 RUN 중 placement ≠ 0이 있다. 그 placement가 계약상 의도된 값이고 다른 identity 항이 통과하면 해당한다.
- `REJUDGE_REQUIRED`: 위 경우이면서, 정정 판정을 별도 산출물로 아직 만들지 않았다.
- `REMEASUREMENT_REQUIRED`: 거부 때문에 세션이 멈춰 계약상 필요한 측정이 빠졌고, 그 측정이 다른 승인 세션으로 채워지지 않았다.
- `UNRESOLVED`: 원시 자료가 저장소에 없거나 기록에 placement 필드가 없다.

### A3. 종합 판정 (위에서부터 처음 성립)

1. `HISTORICAL_REMEASUREMENT_REQUIRED`: REMEASUREMENT_REQUIRED가 하나 이상.
2. `HISTORICAL_REJUDGE_REQUIRED`: REJUDGE_REQUIRED가 하나 이상.
3. `HISTORICAL_IMPACT_UNRESOLVED`: UNRESOLVED가 하나 이상.
4. `NO_HISTORICAL_IMPACT`: 그 밖. JUDGE_FALSE_REJECTION이 있어도 재판정과 재측정이 이미 끝났으면 여기에 해당한다.

### A4. 공유 모듈

`stage4k`는 바꾸지 않는다. 변경안 문서만 쓴다(기대 placement를 명시 인자로 받고, 기본값 0으로 하위 호환). 현재 동작을 고정하는 특성 테스트를 추가한다: placement 0이면 통과, 1이면 `placement` 항이 거짓.

---

## Track B — E2E-A 정적 설계

### B1. E2D 재계산

Amendment A 세션(boot 449–457) 원시 자료에서 구성별 표를 다시 만든다. E2D summary와 1e-9 안에서 같아야 한다(I1).
- 열: NPU, MAC, DPU, AO, WD, WD_STALLED, SRAM/EXT beat·트랜잭션, Vela compute/SRAM/DRAM/total, kernel 수, IO 경로
- 차이: 배치, 지연, 상호작용

### B2. A2 graph IO 후보 (고정 목록)

| 조건 | 방법 | 비고 |
|---|---|---|
| B0 | W1-P1 DRWL(`928296b1…`), placement 0 | 기준 |
| B3 | **같은 DRWL**, header word 7 = 1(runner PLACEMENT_SRAM: region 1 = 그래프 IO arena → SRAM 포트) | command stream 동일 |
| B1·B2 | 입력만 또는 출력만 SRAM. runner placement는 region 1 전체를 옮기므로 불가능하다. 컴파일 후보는 `--separate-io-regions`(Vela 출력, COP2) 하나만 본다 | driver runner·TFLM이 COP2를 받는지는 확인하지 않았다. 컴파일이 되어도 실행 경로가 검증되지 않으면 `UNAVAILABLE` |

판정 규칙:
- 통제 비교 `IO_PLACEMENT_ONLY`: 같은 command stream(또는 E2C 규칙상 ADDRESS만 다름)이고, 중간 텐서(fast region)·가중치(region 0) 경로가 같으며, 바뀌는 것이 region 1 그래프 IO뿐이다.
- B3의 SRAM 용량: runner의 SRAM arena(fast 뒤 64 KiB 정렬 + DDR arena 오프셋, 2 MiB)가 0x31400000 아래에 들어가야 한다. `placement.h`와 같은 계산이다.
- `WEIGHT_ONLY_EXT_PATH`: 그 조건에서 EXT 포트에 남는 region이 region 0(가중치·scale)과 command stream뿐임을 region 표로 확인한 경우에만 쓴다.
- Vela 값: B3와 같은 실행 구성의 Vela 컴파일(`--memory-mode Shared_Sram`)이 ADDRESS 밖에서 A2와 같을 때만 쓴다. 아니면 `NO_COMPARABLE_VELA_ESTIMATE`.

Track B 판정:
- `READY_FOR_BOARD_REVIEW`: 출력 reference가 있는 `IO_PLACEMENT_ONLY` 비교(B0 대 B3 등)가 하나 이상이고, SRAM 용량 검사를 통과한다.
- `PARTIAL_IDENTIFIABILITY`: 비교는 있지만 위 검증 중 하나가 빠짐.
- `NOT_IDENTIFIABLE`: 통제 비교 없음.
- `INVALID`: 재계산 I1 실패, 또는 도구·입력 오류.

### B3. W0-P0 Vela 과대예측 (원인 후보별 SUPPORTED / CONTRADICTED / UNRESOLVED)

자료:
- A0 기준 컴파일과 E2A 방식 26개 변형의 debug DB 전체(컨테이너 2회 추출, 같은 sha256)
- E2D W0-P0 보드 값(TA profile 1)

후보와 판정 규칙:
- **C1 Dram 읽기 처리율 가정**: 보드 실측 EXT read 바이트 ÷ NPU_ACTIVE(지연 500·1000 각각)가 Vela의 Dram IFM 채널 BW(`ChannelBW`, 500: 6.5536, 1000: 3.2768 B/cycle)보다 크면, 보드가 Vela 상한보다 빠르게 읽었다는 직접 모순이다.
  - 두 지연 모두 크면 SUPPORTED.
  - 두 지연 모두 Vela BW 이하이면 CONTRADICTED.
  - 그 밖에는 UNRESOLVED.
- **C2 burst 부풀림**: Vela의 Dram read 바이트(debug DB, burst 효율 반영)가 Vela의 실제 원소 바이트(`readTransferOverhead`를 뺀 값)의 1.3배 이상이고, 보드의 평균 EXT read burst(beat/트랜잭션 × 16)가 Vela가 가정한 burst(NHWC read에서 `블록 깊이 × 8 bit / 8`)보다 크면 SUPPORTED. 부풀림 배수가 1.1 미만이면 CONTRADICTED. 그 밖에는 UNRESOLVED.
- **C3 IFM 반복 읽기 수(element 수)**: Vela의 Dram read 원소 바이트와 보드 EXT read 바이트의 비가 0.8–1.25이면 일치(SUPPORTED: Vela가 읽는 양 자체는 맞음). 그 밖에는 CONTRADICTED.
- **C4 max 선택**: Vela에서 Conv의 total = dram_ac이고 dram_ac > 2 × npu이면 "DRAM 비용이 지배한다"는 정적 사실로 기록한다(판정 없음).

종합 원인 판정(`overprediction_cause`):
- C1과 C2가 모두 SUPPORTED이면 `SUPPORTED`(Vela의 Dram 읽기 비용 모델: 처리율·burst 가정이 실측보다 비관적).
- C1이 CONTRADICTED이면 `CONTRADICTED`.
- 그 밖에는 `UNRESOLVED`.

민감도(estimator-only만, `POSTHOC_SENSITIVITY`, 판정 입력 아님): 변형별 W0-P0 Vela total 대 보드. 최적값을 찾아도 사후 보정이다.

### B4·B5

파이프라인 계측 계획과 후속 보드 계약 초안(통제 비교가 있을 때만)을 쓴다. 지연 500/1000, 9 boot / 90 RUN 상한 안에서 줄인다. 실행 승인은 없다.

## 검증

판정 코드 `host/analysis/stage6be2ea.py`, 테스트, mutation 전부 KILLED, `test.sh` ALL PASS, 컨테이너 facts 2회 동일, 판정 2회 바이트 동일, 기존 파일 불변. 로컬 커밋만 한다.
