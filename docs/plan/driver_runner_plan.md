# Driver Runner — Phase 1 분석과 Phase 2 설계 (2026-11-09)

지시: `docs/plan/driver_runner_directive.md`. 브랜치 `feat/driver-runner`(`refactor/firmware-modules` `0c15eb1`에서 분기).
**TA profile 1**, FI101 Ethos-U85 1024 MAC. 주장 표기(지시 9.1): `DOCUMENTED` / `CODE_VERIFIED` / `BOARD_MEASURED` /
`INFERRED` / `UNVERIFIED`.

**기준 버전 (`CODE_VERIFIED`, 컨테이너 `benchmark-runner`)**: MLEK `b2c0bb2`; ethos-u core driver `03567073fe2b`
(2025-11-05, "Clear interrupt properly in timeout case", 추적 파일 무수정 — S4 실험이 남긴 미추적 `.bak` 3개뿐); Vela 5.0.0.
온라인 CMSIS-Ethos-U 문서의 API는 아래에서 이 커밋 소스로 하나씩 확인했다.

---

## Phase 1. 실행 경로와 측정 창

### 1.1 호출 구조

**A. MLEK** (`CODE_VERIFIED`: `source/app/main/Main.cc`, `hal.c`, `platform_drivers.c`, `ethosu_npu_init.c`,
`ethosu_profiler.c`, `ethosu_cpu_cache.c`, core driver `ethosu_driver.c`, `ethosu_device_u85.c`)

```
main → hal_platform_init → platform_init: UART0(0x59303000) init → I-cache·D-cache enable → RW vector table
        → TA init (ta_config_u85_sys_dram_mid) → arm_ethosu_npu_init: NVIC vector 16 + enable,
          ethosu_init(base 0x50004000, fast mem = cache_arena .bss.NoInit.ethos_u_cache @SRAM 0x31000000, 0x60000 B,
          secure 1, privileged 1) → ethosu_dev_init → soft reset (RESET CPL/CSL), PROT 검증, AXI·MEM_ATTR, POWER_CTRL 0
     → hal_pmu_init → platform_reset_counters: SysTick init, ethosu_pmu_init (EVTYPER 0..4, mask = CCNT + CNT1..5, reset)
     → MainLoop (inference_runner): TestModel.Init(arena = activation_buf_dram, model = nn_model @0x70000000)
     → RunInference → TFLM ethos-u op → ethosu_invoke_v3(drv, COP1 payload, base_addr[], sizes, n)
        = ethosu_invoke_async: COP1 해석, base_addr[2] ← fast memory, OPTIMIZER_CONFIG 검증, COMMAND_STREAM:
            ethosu_flush_dcache (MLEK: SCB_CleanDCache 전체) → ethosu_request_power (첫 요청이면 soft reset:
            RESET, AXI, POWER_CTRL 재설정 → CMD clock/power Q off) → ethosu_inference_begin (MLEK profiler:
            cache state clear, CNTR_Disable/Enable(mask)) → ethosu_dev_run_command_stream: QBASE, QSIZE,
            QCONFIG(=3), BASEP[i], REGIONCFG(0:3, 1:3, 2..7:1), CMD |= run
        + ethosu_wait(block): ethosu_semaphore_take → while(count==0) __WFE() (weak 기본, MLEK 미정의)
            ← IRQ: arm_ethosu_npu_irq_handler → ethosu_irq_handler (weak 기본): CMD clear_irq, STATUS 오류 검사,
               semaphore_give (__SEV)
          → ethosu_invalidate_dcache (MLEK: SCB_InvalidateDCache 전체) → ethosu_inference_end (MLEK profiler:
            CNTR_Disable(mask)) → ethosu_release_power (clock/power Q on) → 결과
```

**B. 기존 runner** (`CODE_VERIFIED`: `firmware/runner/measure.c` `handle_run`, `pmwl.c` `__wrap_test_u85`,
`io_wrap.c` seam, `firmware/Drivers/u85_driver/u85.c` + `firmware/vendor/patch_u85_vendor_timeout.py`)

```
handle_run → (EVENTS) CMD=0, 대기, PMU reset+enable (EVTYPER 0..N, PMCNTEN, PMCR) → t_pmu_enable
  → run_fixed_inference → __wrap_test_u85: blob 헤더 검사, cms/const DDR 복사(0x70100000~), OFM poison, IFM 복사,
     TA profile 적용·되읽기, knob 설정 → __real_test_u85 (vendor): IRQ vector, reset 대기만(reset 미발행),
     CMD=0, AXI_SRAM/EXT=0x21F3F, CFG_*_CAP=0x21F3F, MEM_ATTR=0, BASEP, QBASE/QSIZE, QCONFIG=0, REGIONCFG=0
     → printf seam (knob 덮어쓰기: REGIONCFG/QCONFIG/MEM_ATTR/AXI, 되읽기; Stage 0 시작 seam: PMCCNTR·DWT 기록)
     → POWER_CTRL(hook, knob 0) → CMD|=1 → busy loop (irq_triggered 폴링, D-cache off)
     ← IRQ (vendor handler, runner wrapper로 시각 기록): CMD=2 → QREAD 검사 → CMD=0 → printf CPM seam
        (PMEVCNTR·PMCCNTR·STATUS·QREAD 판독) → CMD=0xC
  → OFM 비교 → PMU disable·판독
```

### 1.2 비교 (분류: 지시 1.1 — 차이는 `CONFIG_DIFFERENCE`, 성능 영향 확인 전 `PERFORMANCE_CAUSE`로 단정하지 않음)

| 항목 | MLEK | 기존 runner | 분류 | 근거 |
| --- | --- | --- | --- | --- |
| NPU reset | 작업마다 soft reset(첫 power 요청 시), PROT 검증 | reset 발행 없음 | CONFIG_DIFFERENCE | CODE_VERIFIED |
| 보안·특권 | CSL secure, CPL privileged (RESET pending 필드) | reset 안 함 → 리셋 후 상태 그대로 | CONFIG_DIFFERENCE | CODE_VERIFIED |
| POWER_CTRL | 0 (`NPU_MAC_PWR_RAMP_CYCLES` 기본) | knob 0 (vendor 2 대체) | 같음 | CODE_VERIFIED, 되읽기 |
| Clock/Power Q | 작업 중 Q disable(유지), 끝나면 enable | CMD=0(유지), 끝나면 0xC | 같은 효과 | CODE_VERIFIED |
| AXI_SRAM / AXI_EXT | 0x20F0B / 0x21F3F (soft reset마다) | knob 0x20F0B / 0x21F3F | 같음 | CODE_VERIFIED |
| CFG_*_CAP | 쓰지 않음 | 0x21F3F 씀 | CONFIG_DIFFERENCE (실험 A로 적용값 확인 예정) | CODE_VERIFIED |
| MEM_ATTR | 0/0/4/4 | knob 0/0/4/4 | 같음 | CODE_VERIFIED |
| QCONFIG / REGIONCFG | 3 / (0:3, 1:3, 2..7:1) | knob 2 / (0:2, 1:2, 2:0) | 선택된 MEM_ATTR 값이 같음 | CODE_VERIFIED |
| TA | `ta_config_u85_sys_dram_mid` (EXT MAXR 64) | profile 1 (EXT MAXR 0) | 64 & 0x3F = 0 가설 → 실험 A | CODE_VERIFIED / UNVERIFIED |
| Command stream | Vela COP1 payload 그대로 | 같은 payload에서 추출한 stream | 같은 바이트 | CODE_VERIFIED (vela_sha256) |
| OPTIMIZER_CONFIG 검증 | 드라이버가 NPU CONFIG/ID와 비교 | 없음 | 실행 무관 | CODE_VERIFIED |
| 모델·arena 위치 | nn_model 0x70000000, arena = 다음 16 B 경계 | const 0x70100000~, arena 그 뒤 | CONFIG_DIFFERENCE (같은 DDR 블록, 오프셋만) | CODE_VERIFIED (MLEK map) |
| fast scratch | SRAM 0x31000000 (0x60000) | SRAM 0x31100000 | CONFIG_DIFFERENCE | CODE_VERIFIED |
| CPU 코드·데이터 | BRAM 0x12000000, 스택 DTCM | on-chip SRAM 0x31000000~ (fast scratch와 같은 SRAM) | CONFIG_DIFFERENCE | CODE_VERIFIED |
| CPU 대기 | `__WFE` 루프 + SysTick 인터럽트 | busy loop | CONFIG_DIFFERENCE | CODE_VERIFIED |
| D-/I-cache | 둘 다 on, 전체 clean/invalidate | off | CONFIG_DIFFERENCE | CODE_VERIFIED |
| IRQ 후 | clear_irq, 오류 시 soft reset | CMD=2, 0, 0xC | 작업 뒤 | CODE_VERIFIED |
| PMU 설정 | 부팅 시 1회(EVTYPER 0..4, reset); 작업마다 begin에서 Disable/Enable(mask) — reset 없음 | RUN마다 reset+enable (power hold 후) | 창이 다름(1.3) | CODE_VERIFIED |
| 추론 반복 | 부팅당 1회 | 부팅당 10–35 RUN | 프로토콜 차이 | CODE_VERIFIED |

### 1.3 측정 창 (P1)

**기존 runner의 PMCCNTR 창에 staging이 들어가는 경로** (`CODE_VERIFIED`, `measure.c`): `npu_pmu_enable()` →
`run_fixed_inference()` → `__wrap_test_u85`의 `memcpy`(cms, const, IFM)와 OFM poison(`memset`) → vendor 설정 → NPU 시작.
PMCCNTR는 enable부터 disable까지 센다.

**기존 데이터로 분해** (`BOARD_MEASURED`, 2B-0b ctl, 이미지 `d0cd4775`, TA profile 1, 측정 RUN 중앙값, cycles):

| 모델 | PMCCNTR 창 | enable → 시작 seam (staging) | 시작 seam → CPM seam (PMCCNTR) | 같은 구간 CPU DWT | NPU_ACTIVE | CPM seam → 호출 반환 (CPU) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| wav2letter | 250,337,603 | 246,203,058 (98.3 %) | 4,134,551 | 4,146,976 | 4,132,070 | 368,009 |
| mobilenet | 64,972,002 | 63,520,819 | 1,451,143 | 1,796,606 | 1,448,680 | 74,491 |
| kws | 2,626,982 | 2,533,810 | 93,172 | 101,980 | 90,711 | 4,092 |

지시 1.2의 다섯 구간과 대응: (1) CPU 준비·복사 = enable→시작 seam(wav2letter는 14 MB const 복사); (2) 제출 = 시작 seam
뒤 POWER_CTRL·CMD 쓰기(수십 사이클, 분리 판독 없음); (3)+(4) 실행+완료 대기 = 시작 seam→CPM seam(IRQ 이후 CMD=2, QREAD
검사, CMD=0 포함); (5) 결과 확인 = CPM seam 뒤(OFM 비교). (2)와 (3)·(4)의 경계는 기존 데이터로 나눌 수 없다(`UNPROVEN`).
Stage 0 S0-3: 같은 구간에서 PMCCNTR가 CPU DWT보다 0–31 % 적다(모델 의존) — NPU 클록 게이팅 가설, `UNVERIFIED`.

**지표 정의 (이 계획 전체에 적용)**

| 지표 | 정의 | Driver Runner에서 재는 법 |
| --- | --- | --- |
| `HOST_END_TO_END_CYCLES` | CPU DWT, 추론 호출 진입 → 반환 (TFLM·캐시·reset·대기 포함) | `RunInference()` 앞뒤 DWT |
| `NPU_EXECUTION_CYCLES` | NPU PMCCNTR, NPU 시작 직전 → 완료 IRQ 진입 | PMU를 시작 직전에 reset·enable, IRQ 진입에서 판독 |
| `NPU_ACTIVE_CYCLES` | PMU 이벤트 35 (NPU running) | 같은 창의 event 35 |
| (보조) `NPU_EXECUTION_DWT` | CPU DWT, 같은 두 시점 | 같은 hook에서 DWT |
| (변형) `PMCCNTR_HW_WINDOW` | PMCCNTR_CFG start/stop 이벤트로 하드웨어가 정한 창 | TRM에 필드만 있고 의미 서술 없음 → `UNVERIFIED`, 보드 확인 |

`NPU_EXECUTION_CYCLES = NPU_ACTIVE_CYCLES`를 가정하지 않는다. MLEK의 TOTAL은 begin→end 창(캐시 invalidate·IRQ 처리 포함)이며
`NPU_EXECUTION_CYCLES`와 다른 창이다.

---

## Phase 2. Driver Runner 설계

### 2.1 구조 판단 (혼자 내린 판단 — 결과·결론에 다시 적는다)

| # | 판단 | 이유 | 대안과 버린 이유 |
| --- | --- | --- | --- |
| J1 | Driver Runner를 **MLEK의 out-of-tree use case** `pmu_runner`로 만든다(우리 저장소 `firmware/driver_runner/`, MLEK cmake에 `-DUSE_CASES_SEARCH_DIR_LIST`로 지정). MLEK 트리는 바꾸지 않는다 | 플랫폼 초기화(캐시, TA, NPU init, IRQ, SysTick), 드라이버 컴파일 정의(QCONFIG 3, REGIONCFG, AXI), 링커·메모리 배치가 **stock MLEK과 같은 코드**가 된다. 동등성(P2)의 기준점을 새로 만들지 않고 MLEK 자체를 쓴다 | selftest 플랫폼에 드라이버만 넣기: 캐시·링커·TA·드라이버 정의를 손으로 맞춰야 하고, 맞췄다는 것 자체를 다시 검증해야 함 |
| J2 | 실행은 MLEK의 TFLM 경로(`fwk::tflm::TestModel` → ethos-u op → `ethosu_invoke_v3`). Vela tflite를 UART로 받아 **0x70000000(nn_model 자리)**에 두고 arena는 MLEK 링커와 같은 규칙(모델 끝의 다음 16 B 경계, 0x200000 B) | NPU가 받는 base address·COP1 payload·호출 순서가 stock MLEK과 같아진다. 7개 모델을 이미지 하나로 돌린다(MLEK는 모델마다 이미지) | `ethosu_invoke_v3` 직접 호출: base address를 손으로 재현해야 함 → **변형 실행용으로만** 남김(J6) |
| J3 | PMU는 runner의 `pmu_session` 한 곳이 소유한다. 판독·설정 시점은 드라이버의 공식 weak hook: **`ethosu_address_remap(addr, -1)`**(QBASE 쓰기 직전 = NPU 시작 직전, begin 뒤, soft reset 뒤 power 유지 상태)에서 EVTYPER·reset·enable, **`ethosu_irq_handler`** 진입에서 판독, `RunInference` 반환 뒤 재판독 | MLEK HAL은 profiler의 `ethosu_inference_begin/end`를 strong으로 링크한다(`hal_pmu_init` → `timer_mps4.c` → `ethosu_pmu_init`, CODE_VERIFIED) → 같은 이름으로 덮을 수 없다. remap hook은 문서화된 platform callback이고 주소를 그대로 돌려주므로 실행을 바꾸지 않는다 | MLEK profiler 소스 패치: 매 빌드 MLEK 트리 수정 필요 / profiler 창 사용: reset 없고 이벤트 5개 고정 |
| J4 | MLEK profiler의 begin/end는 **그대로 둔다**(stock 플랫폼의 일부). 우리 PMU 설정은 begin **뒤**(remap hook)에서 하므로 begin의 Disable/Enable이 우리 설정을 지우지 않는다. end의 Disable은 IRQ 판독 뒤라 창에 영향 없음 | stock MLEK과의 차이를 최소화 | — |
| J5 | CPU 대기는 기본 `__WFE` 루프와 **같은 코드**를 우리 `ethosu_semaphore_take`(weak override)에 두고, 변형(busy poll, QREAD 샘플러)을 RUN 설정으로 고른다 | Phase 5(WFE vs busy)와 Phase 6(QREAD)을 같은 이미지에서 한 변수로 비교 | 이미지별로 따로 빌드: 이미지 차이가 변수에 섞임 |
| J6 | 변형 command stream(PMU Mask 등, Phase 6)은 **같은 이미지의 direct 모드**: TFLM 실행에서 기록한 base address와 크기를 그대로 써서 `ethosu_invoke_v3`를 직접 호출 | flatbuffer를 다시 쓰지 않고, 주소는 TFLM 실행과 같게 유지 | tflite 재작성: 도구가 커지고 오류 지점이 늘어남 |
| J7 | 와이어 프로토콜은 기존 프레임(magic NUR1, CRC32, 명령 id)을 그대로 쓰고, 측정 기록은 **새 스키마 v2**(필드 이름이 있는 고정 배열)로 한다. 펌웨어 쪽 프로토콜은 플랫폼과 무관한 새 모듈로 짠다 | 호스트 `RunnerLink`(프레임·재전송·텍스트 수집)를 재사용, runs.csv 형식을 같게 하면 기존 분석 스크립트를 그대로 씀. 기존 runner 소스는 고정(지시 1.3)이라 공유 리팩터를 하지 않음 | 기존 122필드 기록 재사용: seam 의미가 runner 고유라 억지 대응이 됨 |
| J8 | 워크로드 형식 **DRWL**: Vela tflite + IFM들 + golden들 + 설정. 호스트 `host/lib/drwl.py`가 단일 출처, 펌웨어가 독립 선언, 계약 테스트로 묶음(기존 PMWL과 같은 방식). staging은 DDR4 블록 1(0x9000_0000대, 블록 0과 다른 물리 메모리 — `mem_regions.h`) | 모델 바이트를 MLEK과 똑같이(Vela 출력 파일 그대로) 둔다 | PMWL 확장: cms/const 분리 형식이라 tflite를 담기에 의미가 겹침 |
| J9 | **(수정)** 로그 수준은 stock MLEK 그대로(INFO). 부팅 배너만 프로토콜 전에 나오고 호스트 `RunnerLink`가 프레임 밖 텍스트로 모은다. 플랫폼 상태(TA·NPU·PMU·캐시)는 capability에서 레지스터 되읽기로 준다 | 로그 수준을 바꾸면 MLEK 소스가 다르게 컴파일돼 stock과의 차이가 하나 늘어난다. use case는 실행 중 출력이 없음 | ERROR로 낮추기(처음 안) |
| J10 | PMU는 `ETHOSU_PMU_*` 대신 TRM 오프셋 레지스터를 직접 쓴다(`firmware/common/npu_pmu_regs.h` 재사용) | 이 드라이버의 `ETHOSU_PMU_Enable/Disable`은 `ethosu_request_power/release_power`를 불러 power 참조 수(=작업마다 soft reset 여부)를 바꾼다(CODE_VERIFIED); `Set_EVTYPER`는 enum만 받아 하드웨어 id로 지정할 수 없다; `Get_CCNTR`는 LO→HI 한 번 읽어 찢어질 수 있다 | 공식 API: 부작용이 측정 조건을 바꿈 |
| J11 | 카드의 ddr.bin은 빌드가 낸 빈 파일 대신 16 B 0 | runner는 DDR에 정적 객체가 없어 빌드가 빈 ddr.bin을 낸다. images.txt(stock과 같은 파일)가 ddr.bin을 읽으므로 MCC가 0 B 파일을 거부할 위험을 피함. 그 16 B는 모델 배치 때 덮어씀 | images.txt 수정: stock과 다른 파일이 됨 |
| J12 | 실행 중 hook 연결을 빌드 게이트로 강제(`build_driver_runner.sh`): 우리 hook이 strong(`T`)인지, `ethosu_dev_run_command_stream`이 remap hook을 부르는지, MLEK profiler 심볼이 MLEK 것인지 | 첫 빌드에서 정적 라이브러리가 `hooks.o`를 끌어오지 않아 드라이버 기본(weak)이 링크됨 — 테스트가 아니라 ELF로만 드러나는 오류. `hooks_install()`로 끌어오고 게이트로 지킴 | — |

### 2.7 Phase 1·2 중 확인한 사실 (CODE_VERIFIED, 보드 미확인)

- **stock MLEK은 작업마다 soft reset을 하지 않는다.** MLEK `ethosu_pmu_init`(부팅 시 `hal_pmu_init`)이
  `ETHOSU_PMU_Enable` → `ethosu_request_power`를 한 번 부르고 풀지 않는다. 그래서 power 참조 수가 1로 남고, 추론 때
  `ethosu_request_power`는 2가 될 뿐 첫 요청이 아니라서 soft reset을 하지 않는다. 클록·전원 Q도 계속 켜진 채다.
  soft reset은 부팅 때(`ethosu_dev_init`, 첫 power 요청)뿐이다. → `evidence/runner_gap/control_flow_diff.md`의 "작업마다
  soft reset"은 고쳐야 할 기술이다(그 문서는 고정 기록이라 정정은 덧붙인다). Driver Runner capability의
  `power_requests`(유휴 1, arm 시 2 예상)로 보드에서 확인한다.
- MLEK·TFLM은 `ethosu_address_remap`, `ethosu_semaphore_*`, `ethosu_irq_handler`를 정의하지 않는다(호출만).
- TFLM ethos-u op은 base address를 const, scratch, fast, 입력들, 출력들 순으로 최대 8개 넘긴다.

### 2.8 구현 상태 (보드 실행 없음)

| 항목 | 상태 |
| --- | --- |
| 펌웨어 | `firmware/driver_runner/use_case/pmu_runner/`: frame, workload, record, pmu_session, probe, runner(플랫폼 무관) + hooks, uart, platform.cc(MLEK/TFLM/드라이버) |
| 빌드 | 컨테이너 MLEK cmake, rc 0, 게이트 PASS, runner 소스 경고 0. boot `8d0123f3…`, bram `964ced9c…`, images.txt `af688281…`(stock과 같음) |
| 호스트 | `drwl.py`, `record_v2.py`, `driver_link.py`, `RunnerLink._decode` hook, `pack_vela_workload --format drwl`, `board/run_driver_events.py`, `board/run_driver_campaign.sh` |
| 테스트 | 시뮬레이터(코어를 호스트용으로 컴파일, `DriverLink`가 파이프로 실제 프레임 교환, board 스크립트 끝까지), 계약(C X-macro ↔ Python), record_v2, DRWL, Phase 3 판정. 변이: 코어+호스트 35개, Phase 3 판정 15개 모두 RED |
| 보드 | **미실행** — 이미지 교체 승인과 sudo 필요(지시 9.5). Phase 3 계약 `evidence/driver_p3/contract.md` 고정 |


### 2.2 모듈 구성 (펌웨어, `firmware/driver_runner/`)

```
use_case/pmu_runner/usecase.cmake   MLEK use-case 정의 (TFLM, 모델 생성 없음)
use_case/pmu_runner/src/
  MainLoop.cc        MLEK 진입점 → runner_main()
  model_tflm.cc      TFLM 실행 어댑터: Init(arena, model), 입력 복사, RunInference, 출력 포인터 (C 인터페이스)
  runner.c           상태 기계와 명령 처리 (플랫폼 무관)
  frame.c/.h         프레임 인코딩·파싱, CRC32 (플랫폼 무관, 기존 와이어 형식)
  uart.c/.h          CMSDK UART0 직접 접근 (비차단 RX)
  workload.c/.h      DRWL 해석·검사, staging → 0x70000000 배치, arena 위치 계산
  pmu_session.c/.h   PMU 소유: 설정(EVTYPER, PMCCNTR_CFG), arm(remap hook), IRQ 판독, 사후 판독, overflow
  hooks.c            드라이버 weak hook 구현: ethosu_address_remap, ethosu_irq_handler, ethosu_semaphore_take
  wait.c/.h          대기 전략: WFE(기본, 드라이버와 같은 코드) / busy / QREAD 샘플러(2B-4 재사용 지점)
  record.c/.h        측정 기록 v2 (필드 표 하나에서 직렬화)
```

호스트(`host/`): `lib/drwl.py`(형식), `lib/record_v2.py`(기록 해석 → 기존 runs.csv 열), `container/pack_vela_workload.py
--format drwl`(같은 Vela·입력 경로 재사용), `board/run_driver_events.py`(기존 `run_pmu_events.py`의 세트·반복·검증 흐름을
같은 모듈 `pmu_events_parse`로 재사용), 계약 테스트 `test_driver_runner_contract.py`.

### 2.3 RUN 수명주기와 PMU 책임

```
LOAD_MODEL(DRWL) → 검사 → tflite를 0x70000000로 복사 → TestModel.Init(arena, model) → 입력·출력 텐서 크기 = DRWL 표와 비교
SET_INSTRUMENTATION_MODE(set, codes ≤ 8) → pmu_session 설정 저장(레지스터 안 건드림)
RUN:
  DWT t0 → 입력 텐서에 IFM 복사 → (dcache 정책: MLEK과 같게 on) → DWT t_invoke
  RunInference():
     … flush → request_power(soft reset) → [MLEK begin] →
     ethosu_address_remap(-1)  ⇒ pmu_session_arm(): PMCR off → PMOVSCLR → EVTYPER[i] → PMCCNTR_CFG → counters reset
                                  → PMCNTENSET(slots|CCNT) → PMCR cnt_en → DWT t_arm   (power 유지 상태, CODE_VERIFIED 순서)
     … QBASE/BASEP/REGIONCFG → CMD run
     ethosu_semaphore_take ⇒ wait 전략 (기본 WFE)
     IRQ ⇒ ethosu_irq_handler: DWT t_irq, PMCCNTR, PMEVCNTR[0..N), PMOVSSET, STATUS, QREAD 판독 → 드라이버 기본 처리와 같은 코드
     … invalidate → [MLEK end] → release_power
  DWT t_return → 사후 판독(같은 레지스터) → 출력 텐서 vs golden 비교 → 기록 v2 → RUN_COMPLETE
```

기록 v2의 창: `npu_execution_cycles` = IRQ 진입의 PMCCNTR(arm에서 reset); `npu_execution_dwt` = t_irq − t_arm;
`host_end_to_end` = t_return − t_invoke; 이벤트 값은 IRQ 진입 판독; 사후 판독은 "IRQ 뒤에도 셌는가" 진단용.

### 2.4 Cache·메모리 (지시 2.3)

| 항목 | Driver Runner | 근거 |
| --- | --- | --- |
| D-cache | MLEK platform_init이 켬 → 그대로 | CODE_VERIFIED |
| flush / invalidate | MLEK `ethosu_cpu_cache.c` 구현(전체 clean / 전체 invalidate) 그대로 — 기본 weak는 no-op이지만 MLEK이 strong으로 제공 | CODE_VERIFIED |
| CPU가 쓴 입력 | 입력 복사 후 드라이버의 flush가 전체 clean | CODE_VERIFIED |
| CPU가 읽는 출력 | IRQ 뒤 invalidate 후에 비교 | CODE_VERIFIED |
| staging(0x9…) → 0x7… 복사 | 복사 뒤 `SCB_CleanDCache`(LOAD 시) — NPU가 읽는 모델 바이트가 메모리에 있음을 보장 | 설계 |
| 정렬 | 드라이버가 cms·base 16 B 정렬 검사; 모델 0x70000000, arena 16 B 경계 | CODE_VERIFIED |
| fast scratch | MLEK `cache_arena` (SRAM 0x31000000, 0x60000) — 드라이버가 base_addr[2]를 덮어씀 | CODE_VERIFIED |
| 주소 remap | identity (hook은 PMU arm에만 씀) | 설계 |

### 2.5 재사용 / 새로 만듦 / 쓰지 않음

| 대상 | 처리 |
| --- | --- |
| 호스트 `RunnerLink` 프레임·요청·텍스트 수집, `pmu_events_parse`(세트·검증 규칙), `pack_vela_workload`(Vela·입력·golden), 분석 스크립트(runs.csv 기반) | 재사용 |
| 기존 runner 펌웨어(`firmware/runner`, vendor 패치, 게이트) | 그대로 보존(측정 이미지 `d0cd4775`) |
| 펌웨어 프로토콜·PMU·기록 | 새 모듈(플랫폼 무관 부분과 MLEK 어댑터 분리) |
| 기존 runner의 vendor seam, PMWL knob(REGIONCFG/QCONFIG/MEM_ATTR/AXI/POWER_CTRL/TA 덮어쓰기), CFG_CAP 쓰기 | Driver Runner에는 없음 — 그 값들은 MLEK 플랫폼·드라이버가 정함 |

### 2.6 검증 계획(Phase 3 이후, 보드 전 계약으로 고정)

- 정상 추론: 7개 모델 출력 = 같은 입력의 MLEK 출력(C-a 덤프) — 먼저 kws, ad.
- Driver Baseline(이벤트 없이 PMCCNTR·event 35만) vs Driver PMU(세트 A~G) vs Stock MLEK vs 기존 runner, 같은 입력·같은 Vela.
- 계측 교란: 같은 이미지에서 이벤트 세트 유무로 출력·`NPU_ACTIVE`·DWT가 변하는지.
- 주소 동등성: TFLM이 넘긴 base address를 기록 → MLEK 빌드 map의 nn_model·arena와 비교.
- 이미지 교체·보드 측정은 승인 후(지시 9.5).
