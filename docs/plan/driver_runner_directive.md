# Owner directive (2026-11-09): FI101/MPS4 Ethos-U85 — 계측 환경 통합 및 Profiling 신뢰성 확보

원문 그대로 기록한다. Owner 추가 지시(같은 날): "이거 기록해놓고 끝까지 작업하자. 설계 단계에서는 너의 판단에 맡길게.
단 구조적으로 재사용성을 판단하고 해야돼. 깔끔한 아키텍처를 선호해. 끝까지 진행중 혼자서 판단한 부분이 있다면 구현 결과 및
결론에 해당 내용을 적어줘". 진행 계획과 혼자 내린 판단의 기록: `docs/plan/driver_runner_plan.md`.

---

## 0. 최종 목표와 기본 원칙

본 작업의 목표는 **Arm Ethos-U Core Driver를 기반으로 신뢰할 수 있는 FI101/MPS4 실측 환경을 구축하고, 기존 Stage 0~3 및 Stage 2B의 계측 문제를 해결하는 것**이다.

단순히 기존 Runner를 드라이버로 교체하는 것이 아니다. 기존 실험에서 발견된 문제의 원인을 분리하고, 실제 하드웨어에서 어떤 수준의 Profiling이 가능한지 검증해야 한다.

### 해결해야 할 세 가지 문제

| 문제 | 현재 상태 | 해결 목표 |
|---|---|---|
| P1. NPU 사이클 측정창 | 자체 Runner의 PMCCNTR에 CPU staging 포함 | 실제 NPU 실행 구간을 정의하여 사이클과 이벤트 측정 |
| P2. 실행 경로 차이 | 자체 Runner와 MLEK의 Reset·Power·Cache·CPU 대기 방식 등이 다름 | 동일 조건에서 두 실행 경로의 차이를 정량적으로 검증 |
| P3. 그룹별 이벤트 귀속 | PMU Mask의 명령 경계와 실제 연산 활동 경계가 일치하지 않음 | 연산별 PMU 귀속 및 Timeline 복원 가능 범위 검증 |

세 문제는 서로 독립적으로 판정한다.

- P1 해결이 P2의 실행 동등성을 보장하지 않는다.
- P2 해결이 P3의 그룹 귀속 정확성을 보장하지 않는다.
- 공식 드라이버 사용이 정확한 Profiling을 자동으로 보장하지 않는다.

**최종 목표는 공식 드라이버 기반의 통합 계측 Runner를 확보하는 것이지만, 실제 계측 정확성과 실행 동등성이 확인되기 전에는 기존 Runner를 대체하지 않는다.**

## 1. 참고자료 및 기존 작업 확인

### 1.1. Arm 공식 자료

| 자료 | 확인할 내용 |
|---|---|
| Ethos-U85 TRM — Issue 05 (support.arm.com/documentation/102685/0000) | NPU Control, PMU, QREAD, STATUS, Command Stream, BLOCKDEP, WAIT, IRQ |
| CMSIS-Ethos-U Driver (arm-software.github.io/CMSIS-Ethos-U/main/driver/) | 초기화, Invoke, Interrupt, PMU, Cache, 실행 Lifecycle |
| Driver Public API | `ethosu_init`, `ethosu_invoke_v3`, `ethosu_invoke_async`, `ethosu_wait` |
| PMU API | `Get_CCNTR`, `Get_EVCNTR`, `Get_QREAD`, Counter Enable·Reset |
| Platform-specific Functions | Cache Clean/Invalidate, Address Remap, Inference Begin/End |
| Arm Integration Guide | Vela·Linker·Memory Map·Driver 설정 정합성 |
| CMSIS-Ethos-U Source (github.com/ARM-software/CMSIS-Ethos-U) | 공식 드라이버의 실제 구현 |

반드시 **실제 사용 중인 드라이버 버전·커밋에 해당 API가 존재하는지 소스에서 확인**한다. 최신 온라인 문서의 API가 현재 프로젝트에서도 동일하게 동작한다고 가정하지 않는다.

### 1.2. 프로젝트 내부 자료

`docs/plan/equivalence_plan.md`, `docs/plan/stage2_plan.md`, `docs/plan/stage2b3_plan.md`, `results/fi101_stage2b3/`,
`evidence/runner_gap/control_flow_diff.md`, `firmware/runner/`, `host/board/run_pmu_events.py`, 기존 FI101 `test_u85()`
실행 코드, MLEK `inference_runner` 및 Ethos-U Driver 통합 코드. 파일이 없거나 경로가 변경되었다면 현재 저장소에서 추적하고
실제 경로를 기록한다. 존재하지 않는 자료를 추정해 사용하지 않는다.

### 1.3. 기존 데이터 보존

Stage 0~3 원시 데이터, Stage 2B-0b·2B-2·2B-3 계약·원시 데이터·판정, 기존 Runner 펌웨어·호스트 도구, MLEK 기준 데이터,
보드 이미지 `d0cd4775`, 기존 커밋과 실행 환경 설정을 보존한다. 재측정 결과로 덮어쓰지 않는다. 새로운 Driver Runner 측정은
별도 실험 ID와 경로에 저장한다.

## Phase 1. 기존 실행 경로 및 계측 구조 분석 (보드 없음)

1.1 실행 경로 비교 — A. MLEK `inference_runner → Ethos-U Core Driver → NPU`, B. 기존 Runner `test_u85 기반 → 레지스터 직접
제어 → NPU`. 비교 항목: NPU 초기화(Reset, Power, Clock, PROT), Command Stream, Vela 설정, 메모리 설정(REGIONCFG, MEM_ATTR,
AXI), TA 설정(실제 적용값·Read-back), CPU Cache, 메모리 배치, CPU 대기(Busy/WFE/WFI, IRQ), PMU(Reset, Enable, Start/Stop,
이벤트 설정·판독), 추론 완료(STATUS, IRQ, Wait, 오류). 차이는 `CONFIG_DIFFERENCE`로 기록하고 성능 영향이 확인되기 전에는
`PERFORMANCE_CAUSE`로 단정하지 않는다.

1.2 PMCCNTR 측정창 조사 — PMU 초기화·활성화·판독 위치 추적. Wav2Letter 전체 계측창 약 250M cycles vs `NPU_ACTIVE` 약
4.13M cycles의 차이를 (1) CPU 데이터 준비·복사 (2) NPU 작업 제출 (3) 실제 NPU 실행 (4) 완료 대기 (5) 결과 확인·수집으로
분해할 수 있는지 검토. 지표 `HOST_END_TO_END_CYCLES`(CPU 측 전체 추론 경과), `NPU_EXECUTION_CYCLES`(실제 NPU 실행 시작~완료
경과 사이클), `NPU_ACTIVE_CYCLES`(PMU가 NPU Running으로 집계한 사이클)를 독립적으로 정의하고, 두 NPU 지표가 같다고 가정하지
않는다. PMCCNTR Event Start/Stop 설정 또는 실행 전후 판독으로 어떤 측정창이 형성되는지 확인.

완료 조건: 두 경로의 호출 구조·레지스터 차이 문서화, PMCCNTR에 staging이 포함된 코드 경로 확인, 측정 정의 확정, 설명되지
않은 차이는 `UNPROVEN`.

## Phase 2. Ethos-U Core Driver 기반 Runner 설계

기존 Runner를 즉시 제거하지 않고 별도 Driver Runner를 만든다. 권장 구조: Host Experiment Controller(Workload/Input/
Configuration, Vela Command Stream: Original / PMU Mask variant / Diagnostic variant) → FI101 Firmware(Experiment Controller,
Ethos-U Core Driver: Init/Power/Reset, Memory/Cache, Invoke/Wait/IRQ, PMU interface; PMU Measurement; Optional QREAD Sampler;
Result Buffer) → Ethos-U85 1024 MAC. 원본 Command Stream을 정상 실행하는 가장 작은 Driver Runner부터.

2.2 사용 범위 검토: `ethosu_init()`, `ethosu_invoke_v3()`, `ethosu_invoke_async()`, `ethosu_wait()`, `ethosu_irq_handler()`,
`ethosu_inference_begin/end()`, `ETHOSU_PMU_Get_CCNTR()`, `ETHOSU_PMU_Get_EVCNTR()`, `ETHOSU_PMU_Get_QREAD()`. 인자·상태
전이·반환값·PMU Lifecycle 확인. PMU 원칙: 설정·Reset·Enable 책임을 한 계층으로 통일, 드라이버 PMU 계측과 직접 레지스터 계측의
충돌 방지, PMU Enable의 전원 요청 효과 확인, Cycle/Event Overflow 기록, 기본 측정에서는 공식 정의 이벤트 우선. 공식
드라이버를 쓴다는 이유만으로 측정창이 정확하다고 가정하지 않는다.

2.3 Cache·메모리: D-cache 상태, `ethosu_flush_dcache()`, `ethosu_invalidate_dcache()`, Command Stream Clean, 공유 버퍼
소유권, 정렬·Cache Line 경계, Fast Scratch 할당, CPU/NPU 주소 Remap. 기본 Cache Hook이 No-op일 수 있음.

완료 조건: 설계 문서, 실행·계측 Lifecycle, PMU 책임·데이터 구조, 재사용/제거 기능 구분, 기존 Runner와 비교 가능한 입력·설정.

## Phase 3. Driver Runner 구현 및 기본 계측 검증

최초 KWS, AD로 기본 계측 검증 후 7개 모델 전체(`kws, ad, rnnoise, vww4, yolo, mobilenet, wav2letter`)로 확대; 일부 모델로
전체를 대표하지 않는다. 지표: PMCCNTR, NPU_ACTIVE, MAC_ACTIVE, MAC_DPU_ACTIVE, AO_ACTIVE, WD_ACTIVE/WD_STALLED, SRAM/EXT
Beat, CPU Cycle, Output. Pass A~G 재사용 전 드라이버 기반 재현 검증, 이벤트 번호와 드라이버 enum 대응 검증. 비교: Driver
Baseline(계측 최소) / Driver PMU / Existing Runner / Stock MLEK — 동일 입력·동일 Vela 산출물. PMU 활성 시 실행시간·출력 변화
확인. 판정 규칙·허용오차는 보드 전에 고정.

완료 조건: 정상 출력, PMU Reset·Enable·Read 정상, 사이클 측정창 검증, 계측 전후 동등성, 작은 모델 반복 안정성, 실패 시
Fault·STATUS·QREAD·로그 보존.

## Phase 4. MLEK 및 기존 Runner와의 교차 검증

환경: Stock MLEK(기준) / Driver Runner(새 통합 계측) / Existing Runner(Stage 0~3). 동일 보드·FI101 이미지·TA profile 1.
seed-1 입력을 MLEK 입력과 같다고 가정하지 않고 MLEK 입력을 추출해 Driver Runner에 사용. 출력: 동일 입력 MLEK·Driver 일치,
독립 기준(TFLite) 일치, 독립 정답이 없으면 Reference Agreement까지만. 비교 항목: Command Stream Hash, Output, NPU_ACTIVE,
MAC/DPU/AO/WD Active, SRAM/EXT Beat, Memory Stall, PMU Counter Window, 설정 Read-back. 기존 `NPU_ACTIVE −0.79~+0.30%`는
참고자료일 뿐 최종 증거가 아님. 판정: `EQUIVALENT` / `DIFFERENT_EXPLAINED` / `DIFFERENT_UNEXPLAINED` / `UNPROVEN` /
`INVALID`. 모든 설정 차이가 INERT일 필요 없음; 영향 있는 설정은 `EFFECTIVE`로 기록하고 통제하거나 적용 범위에 포함.

완료 조건: 7개 모델 동일 절차, 모델별 출력·PMU 판정, 실행 조건 차이 목록, Stage 1·2A·3 재사용 범위 결정.

## Phase 5. 실행 조건 차이의 원인 분리

변수 하나씩: CPU Busy Loop/WFE, D-cache, Soft Reset, POWER_CTRL, CAP/AXI, TA EXT MAXR, Fast Scratch 주소. Baseline 대비 한
변수만 변경, 같은 입력·Command Stream, 출력·NPU_ACTIVE·트래픽·관련 이벤트 측정. TA `MAXR=64`와 `0`은 인코딩과 Read-back으로
확인. 관측된 차이를 설명하는 범위에서만 수행(전수 조합 금지).

완료 조건: 차이 설명 범위, EFFECTIVE/INERT/UNPROVEN, Driver Runner 기준 설정 확정, 재사용·재측정 범위 결정.

## Phase 6. Stage 2B 그룹별 Profiling 문제 해결

드라이버 전환만으로 2B 귀속 오류가 해결된다고 가정하지 않는다. 기존 문제(그룹 합 = 전체, AD Conv MAC 효율 2.85, 고정 Mask
이동으로 미해결, 발행·완료와 Mask 경계 불일치) 유지, H1/H2 무효 유지. 방법: PMU Mask, QREAD + Cycle, PMU 주기 샘플링,
PMCLUT, `NPU_OP_IRQ`, KERNEL_WAIT, STOP Prefix — 원본 유지 방법과 변경 방법을 별도 실험군으로. QREAD Timeline(CPU Timestamp,
QREAD, STATUS, PMCCNTR, MAC/DPU/AO/WD)은 비동기 실행으로; QREAD 통과 = 관측 시점까지 완료 확인이며 Kernel 종료 사이클이
아님; Polling 교란·해상도 검증. `NPU_OP_IRQ`는 드라이버가 중간 IRQ를 완료로 처리하지 않는지, 삽입 위치·Chain 제약을 TRM으로
먼저 확인; 안전하지 않으면 실행하지 않음. 판정: `EXACT_ATTRIBUTION` / `COARSE_ATTRIBUTION` / `ISOLATED_ONLY` /
`NOT_IDENTIFIABLE` / `UNPROVEN`. MAC 효율 ≤ 1이나 합계 일치만으로 EXACT 불인정. 그룹 실행 비용과 전체 지연 기여분 구분.

## Phase 7. 기존 연구 데이터 재평가

Stage 1(활성도·효율 재현), 2A(Pipeline 활동·정체), 2B(귀속 가능 여부), 3(트래픽·정체·포트), 4(연산자·형상 실험 기준 환경),
5(메모리 배치·Vela 비교 환경). 삭제·자동 수정 금지. 판정: `RETAINED` / `REVALIDATED` / `CONDITION_SPECIFIC` /
`REMEASURE_REQUIRED` / `INVALID`. 모든 모델을 새 Runner로 기본 측정하되 심층 실험은 영향받은 항목만 재측정.

## Phase 8. 최종 결과물

실행 환경 비교 보고서, Driver Runner, PMU 측정 명세, 7개 모델 검증 결과, 실행 조건 민감도, Profiling 검증 결과, 기존 데이터
재평가, 연구용 데이터셋. 모든 결과에 실행 환경, 커밋, Vela·드라이버 버전, FI101 이미지, 입력·모델 해시, TA Profile, 측정
Pass, RUN ID.

## 9. Code Agent 행동강령

9.1 주장 표기: `DOCUMENTED` / `CODE_VERIFIED` / `BOARD_MEASURED` / `INFERRED` / `UNVERIFIED`.
9.2 보드 전 계약 고정: 질문·목적, 변경 변수·고정 조건, 7개 모델, 입출력 검증, 이벤트·계산식, 반복·Pass, 기준·허용오차,
성공·실패·식별 불가 판정, 후속 단계·중단 조건. 허용오차는 사전 독립 반복 데이터나 사양으로 정하고 사후 변경 금지. 한 모델에만
다른 규칙 적용 금지.
9.3 구현·검증: 기존 코드·데이터 보존, 새 작업 브랜치, 기능별 소규모 커밋, Host 분석 단위 테스트, 정상·비정상·실패 경로
테스트, Output·PMU·Overflow 검증, 보드 전 바이너리·이미지 Hash, 실패 시 로그·상태 보존.
9.4 보드·저장소: 승인받지 않은 FPGA 이미지 교체 금지, 진행 중 실험의 이미지·조건 변경 금지, 2B-3 데이터·계약 변경 금지,
보드 실행 전 영향·복원 방법 작성, 원시 데이터 삭제·덮어쓰기 금지, 다른 브랜치 자동 Rebase·Merge 금지, 증거 보존 후에만
재생성 가능한 빌드 산출물 정리, sudo 비밀번호를 코드·명령 인자·로그에 저장 금지.
9.5 즉시 가능: 소스·문서 분석, 경로·레지스터 비교, Driver Runner 설계, 보드 없는 빌드·단위 테스트, 기존 데이터 재분석,
계약·분석 스크립트. **별도 승인 후**: 보드 이미지 교체, FPGA 설정 변경, 기존 계측 펌웨어 대체, 대규모 보드 측정,
STOP·IRQ·KERNEL_WAIT 삽입 실험, 기존 데이터를 대체하는 공식 기준값 채택. 각 Phase 완료 시 검증 결과와 다음 Phase 실행 조건
보고; 승인된 범위의 단순 수정·테스트마다 재승인 불필요.

## 10. 최종 완료 판정

공식 드라이버 실행(정상 추론·출력), NPU Cycle 계측(staging과 분리된 창), PMU 계측(의미·창·Overflow), 실행 동등성(7개 모델
MLEK·Driver 비교), 차이 원인(설명 또는 적용 범위), 그룹 Profiling(귀속 정확성 또는 한계), 기존 연구(재사용·재측정 범위),
재현성(코드·계약·원시 데이터·도구 보존)을 모두 평가한 뒤 완료 보고. 정확한 연산별 Profiling이 불가하다는 결론도 측정 실패로
숨기지 않고 한계 검증 결과로 기록. 미확인 결과를 추정값으로 채우지 않는다.

**최종 지시:** Phase 1 분석 완료 → Phase 2 상세 설계 → 공식 드라이버 정상 추론·PMU 검증 → MLEK와 동일 입력·동일 Vela로 교차
검증 → 7개 모델 기준 환경 측정과 Stage 1·2A·3 재현 평가 → Stage 2B Mask 귀속과 QREAD·IRQ Timeline. **우선순위: 정확한 실행
환경 → PMU 계측 신뢰성 → 기존 연구 재현 → 연산별 Profiling 가능성.** 도구 구현이 연구 목적을 대체해서는 안 된다.
