# Stage 6B-E2B 계약 — TA EXT 읽기 지연 단일 변수: Vela 대 FI101 민감도

지시: Stage 6B-E2B 공식 지시(2026-11-17). 이 계약, 예측값, 판정 코드, 테스트, manifest, 세션 파일은 **보드 측정 전에** 커밋한다.
E3, Stage 6C, KWS G23/G24, 추가 MAC 형상 측정은 하지 않는다. 기존 자료는 수정하지 않는다.

## 0. E2A 초안과 달라진 점

| 항목 | E2A 초안 | 이 계약 | 이유 |
|---|---|---|---|
| TA 변경 방법 | "새 TA profile(blob header word)" | **새 이미지**: `70090f1` 소스를 MLEK cmake 캐시 변수 `-DEXT_RLATENCY=1000`만 바꿔 빌드 | driver runner는 TA를 blob header가 아니라 MLEK 플랫폼 초기화(빌드 때 `TA_CONFIG_FILE` 값)로 설정한다. header word 27은 legacy runner용이다 |
| boot 순서 | 기준 → Conv 500/1000 → G12 500/1000 | 기준 → G12-L500 → Conv-L500 → (이미지 교체) → G12-L1000 → Conv-L1000 | 이미지 교체(deploy)를 한 번으로 줄인다. 시간 순서와 지연 조건이 겹치는 한계를 §6에 적는다 |
| MAC_ACTIVE 변화 | 다르면 세트 무효 | **무효가 아니라 관측으로 기록**(보조 분류) | 지시 Phase 6이 MAC_ACTIVE 변화 여부를 결과로 비교하라고 한다 |
| 판정 이름 | SERVICE_SLOPE_* | 지시 §9의 closed set | 지시 |

RUN 수는 같다: boot마다 pass A·B 각 5 RUN(1 warm-up + 4 측정) = 구성당 warm-up 2, 측정 8. 5 boot, 50 RUN.

## 1. 대상과 고정 조건

| 키 | DRWL | 기존 기록 | 이미지 | boot |
|---|---|---|---|---|
| REF | `s4c2_conv_cin48` (Stage 4K 기준 형상) | boot 375 (E1-R `ref/`) | L500 | 435 |
| G12-L500 | `s6bb_g12` (A2: ADD → Conv → ADD) | 6B-B boot 411 | L500 | 436 |
| CONV-L500 | `e1r_c200_h37w37_o96` (Conv 단독, IFM/OFM Dram) | E1-R boot 429 | L500 | 437 |
| G12-L1000 | `s6bb_g12` | — | L1000 | 438 |
| CONV-L1000 | `e1r_c200_h37w37_o96` | — | L1000 | 439 |

- 워크로드별로 DRWL(입력, 가중치, bias, scale, activation, command stream, 메모리 region)이 바이트 단위로 같다. sha256은 manifest에 고정한다.
- Vela 5.0.0, MLEK 옵션. TA profile 1이 기준이다. 지연 조건만 다르다.
- **L500 이미지** = 기존 `70090f1` 이미지 파일 그대로(boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…`).
- **L1000 이미지** = 같은 소스, 같은 빌드 스크립트에 `DRV_EXTRA_CMAKE=-DEXT_RLATENCY=1000`만 더한 빌드.
- G12와 Conv의 절대 실행시간 차이로 ADD 래퍼의 효과를 판정하지 않는다. 형상·래퍼·배치가 함께 다르다.

## 2. Phase 1 — TA 변경 가능성 (보드 전 확인 → `preflight.md`)

1. RLATENCY는 12-bit다(core-platform `timing_adapter.c`의 `TA_RLATENCY_MASK 0xFFF`, 헤더 주석, MLEK cmake 주석). 1000 < 4096이다.
2. L500 이미지를 같은 방법으로 다시 빌드해 기록된 `70090f1` digest와 같아야 한다(빌드 재현성). 같지 않으면 L1000 이미지의 "TA만 다름"을 증명할 수 없으므로 보드를 측정하지 않는다.
3. L1000 이미지와 L500 재빌드 이미지의 차이가 생성된 `timing_adapter_settings.h`의 `EXT_RLATENCY` 상수(500 → 1000)뿐이어야 한다. 확인 대상은 cmake 캐시와 ELF 디스어셈블리 차이, 그리고 boot/bram/ddr 바이너리의 바이트 차이(상수 위치만)다.
4. TA 인스턴스: `TA_EXT` 0x51102400 = MLEK mps4 `TA_EXT_BASE`. EXT 포트는 DDR(model/arena 0x70000000)을 덮는다. 6B-B·E1-R의 EXT beat 실측이 이 경로의 트래픽을 보여 준다.
5. readback: runner는 boot마다 **RUN 전에** capabilities(두 TA의 11개 레지스터 전부)를 읽는다. L1000 boot의 기대 capabilities = L500 기준 capabilities와 같고 `ta_ext_rlatency`만 1000이다. 하나라도 다르면 그 boot는 CONFIG_MISMATCH이고, 그 boot의 RUN은 쓰지 않으며 세션을 멈춘다. readback이 일치하지 않은 boot의 측정은 결과로 쓰지 않는다.
6. 복원: 세션은 deploy(L500) → 측정 → restore → deploy(L1000) → 측정 → restore → postflight다. 실패하면 `sudo_session.sh`가 열린 deploy를 restore한다. 카드는 원래 이미지로 돌아간다(RESTORE VERIFIED, postflight).

## 3. Phase 2 — Vela 예상값 (E2A facts에서, 측정 전 고정 → `predictions.json`)

E2A의 `E2A_Dram_read_latency_1000` 변형은 기준과 **Vela 출력 tflite sha256까지 같다**(command stream, 상수, arena·fast 크기, IO, 블록·ublock·traversal 모두 같음). 따라서 같은 바이너리에 대한 estimator-only 비교다.

| 워크로드 | V500 | V1000 | ΔV | R_V | Slope_V (/cycle) |
|---|---|---|---|---|---|
| G12 | 53,052 | 83,142 | 30,090 | 1.5672 | 60.18 |
| CONV | 85,815 | 171,630 | 85,815 | 2.0000 | 171.63 |

V500은 6B-R(G12)과 E2A(CONV)의 기존 값과 같다. 성분: G12의 dram_ac는 44,709 → 82,680, npu는 33,314 → 34,564(bias 지연 항), sram은 28,800으로 그대로다. CONV는 total = dram_ac이고 85,815 → 171,630이다.

## 4. 유효성 (구성별, 6B-B 판정 함수 그대로 + 이미지·readback만 조건별)

- CONFIG_MISMATCH: workload sha256, **조건별 이미지 digest**, FPGA, boot index, condition, NPU MAC 수, identity(capabilities = 조건별 기대값, RUN 정체성).
- INVALID_OUTPUT: 출력이 reference와 바이트 단위로 다름(REF는 Stage 4K PASS_EXACT, 나머지는 `ref_ofm.bin`).
- INVALID_PMU: RUN 배치(2 pass × (1+4)), RUN 유효, 카운터 누락, overflow, window.
- UNSTABLE: MAC/DPU가 RUN마다 다름, NPU_ACTIVE pass A 대 B, **pass A range > 5 %**.
- REF 재현 게이트: 6B-B·E1-R과 같은 `stage4k.reproduce`(boot 375 대비).

## 5. 판정 지표와 규칙 (워크로드별, Primary = 증가량)

- B_L = 조건 L의 NPU_ACTIVE pass A 중앙값(측정 4 RUN), r_L = 그 range.
- ΔB = B1000 − B500, ΔV = V1000 − V500, R_B = B1000/B500, R_V = V1000/V500, Slope = Δ/500.
- 측정 허용폭 tol = max(0.01·B500, r500 + r1000). REF 재현 게이트와 같은 형식이다(boot 사이 변동 1 % 바닥 + 두 조건의 RUN range).
- **식별력:** tol > 0.5·|ΔV|이면 `INSUFFICIENT`. 예측 변화가 측정 변동에 묻힌다.
- **Primary(증가량):** |ΔB − ΔV| ≤ 0.15·|ΔV| + tol이면 `CONSISTENT`, 넘으면 `DISCREPANT`.
- **Secondary(비율, 보고만):** |R_B − R_V| ≤ 0.15·(R_V − 1) + tol/B500이면 CONSISTENT, 넘으면 DISCREPANT.
- 절대 오차(보고만): (B_L − V_L)/V_L.
- 두 조건 중 하나라도 VALID가 아니면 그 워크로드는 `NOT_EVALUABLE`(UNSTABLE이면 INSUFFICIENT로 셈)이다.

보조 분류(워크로드별, 판정 입력 아님):
- `MEMORY_SERVICE_RESPONSE`: MAC_ACTIVE·MAC_DPU_ACTIVE가 두 조건에서 같고, SRAM·EXT read/write beat(130, 135, 386, 391)가 각각 1 % 안에서 같고, ΔB > tol인 경우. 증가량을 메모리 대기의 정확한 몫으로 해석하지 않는다.
- 그 밖에는 바뀐 항목을 나열한다.

기존 기록과의 일관성(보고만, 지시 Phase 6 첫 단계): L500 조건의 NPU_ACTIVE가 기존 boot(411, 429)와 |차| ≤ max(1 %, 두 range 합)이면 REPRODUCED, 아니면 DIFFERENT. DIFFERENT이면 환경·입력·데이터·컴파일부터 조사하고 그 결과를 보고한다.

## 6. 최종 판정 (closed set, 위에서부터)

1. `MEASUREMENT_INVALID`: REF 재현 게이트 FAIL, 또는 어떤 구성이 CONFIG_MISMATCH / UNMEASURED / INVALID_OUTPUT / INVALID_PMU.
2. `SENSITIVITY_DISCREPANCY_OBSERVED`: 워크로드 하나 이상이 Primary DISCREPANT.
3. `INSUFFICIENT_EVIDENCE`: 워크로드 하나 이상이 INSUFFICIENT 또는 UNSTABLE.
4. `SENSITIVITY_CONSISTENT`: 두 워크로드 모두 Primary CONSISTENT.

한계(판정과 함께 항상 적는다):
- 조건마다 boot가 하나다. boot 사이의 독립 반복이 없어서 통계적 인과를 주장하지 않는다.
- L1000 boot는 L500 boot보다 시간상 뒤다. 시간 drift는 REF가 시작 때 한 번만 확인한다.
- 이 실험은 지연 하나의 민감도다. 메모리·파이프라인의 개별 기여를 분리했다고 하지 않는다. E2A의 원인 판정(CAUSE_UNRESOLVED)은 새 근거에 따라 다시 평가하되 자동으로 바꾸지 않는다.

## 7. 중단 규칙

- 세션은 `STOP_ON_INVALID=1`로 돈다. REF 게이트 FAIL이나 boot-check rc 1(CONFIG_MISMATCH, UNMEASURED)이면 즉시 멈추고 카드를 복원한다.
- 실패한 조건을 다른 형상이나 다른 지연으로 바꾸지 않는다. 추가 boot는 하지 않는다.
- L500 재빌드가 `70090f1`과 다르거나 L1000 이미지 차이가 TA 상수 밖에 있으면 보드에 가지 않는다.

## 8. 검증

판정 코드 `host/analysis/stage6be2b.py`, 테스트 `host/tests/test_stage6be2b.py`(손으로 쓴 기대값), mutation `evidence/stage6b/stage6be2b/mutate.py` 전부 KILLED, `test.sh` ALL PASS. 보드 `~/evsweep`의 판정 코드 = Mac(sha256). 로컬 커밋만 한다(push 안 함).
