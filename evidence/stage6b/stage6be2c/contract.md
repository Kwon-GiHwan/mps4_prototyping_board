# Stage 6B-E2C 계약 — 같은 Conv(G12)에서 래퍼·배치 통제 가능성 (보드 없음)

지시: Stage 6B-E2C 공식 지시(2026-11-17). 보드 측정은 하지 않는다. 이 계약과 판정 코드는 **후보 구성을 컴파일하기 전에** 커밋한다.
기존 실험 결과와 판정은 바꾸지 않는다.

## 0. 이미 아는 것 (계약 전 노출)

- E2B: G12(A2) 99,866 → 158,707.5, CONV(E1-R c200 h37 o96) 104,393.5 → 202,140.5(TA profile 1).
- G12의 기존 구성(Revision A, 컴파일만 된 것 포함):
  - A0(Conv 단독, IFM/OFM Dram, NHWC, n_base 5, fast 0)
  - A1
  - A2(ADD→Conv→ADD(self), Conv IFM/OFM Sram, NHCWB16, n_base 6, fast 147,456)
  - A0·A2의 Conv는 블록 8×16×64, ublock 2×2×32, DepthFirst로 같다. **IFM/OFM 포맷은 다르다(NHWC 대 NHCWB16).**
- driver runner의 `PLACEMENT_SRAM`(Stage 4 placement, 이미지 `70090f1`)은 region 1(TFLM arena = 그래프 IO와 Vela arena)을 SRAM 포트의 on-chip SRAM으로 옮긴다. command stream은 바꾸지 않는다.
- G12와 E1-R 단독 Conv는 **같은 Conv 형상이 아니다**(276→276 16×16 대 200→96 37×37). 둘의 차이를 래퍼 효과로 재해석하지 않는다.

## 1. 목표 구성과 후보 (고정 목록, 이 밖의 후보는 만들지 않는다)

| 셀 | 의미 | 후보 실행 구성 | Vela 예상값 출처 |
|---|---|---|---|
| W0-P0 | Conv 단독, Conv IFM/OFM DRAM | A0 tflite, MLEK 옵션, placement 0 | 같은 컴파일 |
| W0-P1 | Conv 단독, SRAM | **같은 A0 blob**, runner placement 1 | `--memory-mode Shared_Sram`(arena = Axi0) 컴파일. Conv 레지스터가 ADDRESS 밖에서 A0와 같을 때만 쓴다 |
| W1-P0 | A2, Conv IFM/OFM DRAM | A2 tflite + `--arena-cache-size` ∈ {0, 16384, 65536}(이 순서, 처음 성공한 것). Conv IFM/OFM이 Dram인 것만 | 같은 컴파일 |
| W1-P1 | A2, Conv IFM/OFM SRAM | A2 기존(MLEK 옵션), placement 0 | 같은 컴파일 |

- 각 Vela 컴파일은 지연 500(기준)과 `Dram_read_latency` 1000(E2A 변형 방식, 한 줄만 바꿈)에서 한다. 두 결과가 command stream·상수·IO가 같아야(ESTIMATOR_ONLY_COMPARABLE) 지연 예상값으로 쓴다.
- IFM과 OFM을 함께 옮기는 것은 복합 배치 변수다. IFM 몫과 OFM 몫을 따로 식별했다고 하지 않는다.

## 2. 레지스터 비교 규칙 (Conv kernel 명령 시점의 전체 cmd0/cmd1 상태; 이름은 Vela 5.0.0 `ethos_u85_interface.hpp`)

등록 분류:
- **ADDRESS**: `*_BASE*`, `*_REGION`, `DMA0_SRC`, `DMA0_DST`, `DMA0_*_REGION`.
- **LAYOUT**: `IFM_STRIDE_*`, `OFM_STRIDE_*`, `IFM_PRECISION`, `OFM_PRECISION`. PRECISION의 포맷 비트는 NHWC/NHCWB16을 정한다.
- **DEPENDENCY**: `BLOCKDEP`.
- **COMPUTE**: 나머지 전부. 형상, 블록, kernel, stride, padding, acc, activation, zero point, scale, weight·scale 길이, weight format, DMA 길이·stride를 포함한다.

추가 비교:
- Conv kernel 수
- Conv weight·scale 바이트. 상수 버퍼에서 base·length로 잘라 sha256을 구한다. 상수 밖(staging 등)에 있으면 길이와 DMA 원본 슬라이스로 비교한다.
- Conv IFM/OFM 메모리(debug DB `perf_debug`의 ifm/ofm memory).
- 그래프 연산 목록

비교 분류(closed set):
- `PLACEMENT_ONLY`: 같은 래퍼에서 COMPUTE·LAYOUT·DEPENDENCY·weight 바이트·kernel 수·연산 목록이 같고 ADDRESS만 다르며, Conv IFM/OFM 메모리가 의도대로 Dram↔Sram으로 바뀜. 같은 blob에 runner placement만 다른 경우(W0-P0 대 W0-P1)는 command stream 동일로 자동 충족한다.
- `WRAPPER_ONLY`: 같은 배치에서 Conv의 COMPUTE·LAYOUT·weight 바이트가 같고 Conv IFM/OFM 메모리가 같음. DEPENDENCY 차이와 추가 ADD 연산은 래퍼 효과의 일부로 기록한다.
- `WRAPPER_PLUS_LAYOUT`: 위와 같지만 LAYOUT이 다름. 통제된 래퍼 비교가 아니다.
- `NOT_CONTROLLED`: COMPUTE나 weight 바이트가 다르거나, 메모리가 의도와 다름.
- `UNAVAILABLE`: 어느 한쪽 구성을 만들지 못함.

수치 정합성(통제 비교가 "검증됨"이 되는 조건):
- 양쪽 모두 지연 500·1000 Vela 예상값이 ESTIMATOR_ONLY_COMPARABLE이다.
- 양쪽 Conv의 H1-UC가 같다(같은 블록이면 같다).
- 출력 reference가 있다(blob 입력에 대한 TFLite CPU 출력).
- W0-P1의 Vela 출처가 쓸 수 없으면 그 셀은 보드 측정은 통제되지만 Vela 비교는 `NO_VELA_ESTIMATE`다.

## 3. 판정 (closed set)

1. `INVALID`: 기존 기록 재현 실패(A0·A2 기준 컴파일의 Vela sha256이 Revision A 기록과 다름, E2B 재계산이 기존 summary와 다름) 또는 도구 오류.
2. `READY_FOR_BOARD_REVIEW`: 수치 정합성까지 검증된 PLACEMENT_ONLY 또는 WRAPPER_ONLY 비교가 하나 이상.
3. `PARTIAL_IDENTIFIABILITY`: 구성은 만들었지만 검증된 통제 비교가 없음(WRAPPER_PLUS_LAYOUT, NO_VELA_ESTIMATE 등만).
4. `NOT_IDENTIFIABLE`: 어떤 비교도 통제할 수 없음.

READY라도 래퍼 안의 명령 비용·추가 데이터 이동·중첩을 더 나누지 못하면 그 메커니즘은 `MECHANISM_UNRESOLVED`로 남긴다.

## 4. 후속 보드 계약 초안 (작성만)

통제 가능한 셀만 쓴다. 지연 500·1000, 기준 형상 1개, 최대 9 boot / 90 RUN 안에서 줄인다. 교차·균형 순서, 기준 재현, 이미지 교체 횟수, TA readback, 중단·복원 규칙을 포함한다. 가설 H-E2C-W/P/O의 예상 관측과 반례를 쓴다.

## 5. 검증

판정 코드 `host/analysis/stage6be2c.py`, 레지스터 해석 `host/lib/cms_full.py`, 테스트(손으로 쓴 기대값), mutation 전부 KILLED, `test.sh` ALL PASS. 컴파일 facts는 2회 추출해 sha256이 같아야 한다. 로컬 커밋만 한다.
