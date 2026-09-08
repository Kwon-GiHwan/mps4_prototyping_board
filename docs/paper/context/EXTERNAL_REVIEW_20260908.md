# 외부 리뷰 — 스윕 설계·계측·지표 (2026-09-08)

**성격:** 외부 검토자가 제출한 방법론 리뷰. 이 저장소의 frozen evidence,
공개 Vela/Arm 자료, 공개 MLEK 소스(Arm 저작권 표시된 Alif 공개 저장소)를 근거로 작성.
검토자는 서버의 `stage1.py`, 실제 `CMakeCache.txt`, 생성 헤더, 원시 UART를 직접
열람하지 않았음 — 따라서 공개 저장소 값이 서버 고정 커밋과 일치하는지는 별도 대조 필요.

**이 파일은 리뷰 원문 보존용이다.** 검증 결과는 `EXTERNAL_REVIEW_VERIFICATION.md`.

---

## 1. 전체 판정표

| 항목 | 판정 | 핵심 이유 |
|---|---|---|
| Vela → MLEK 빌드 → FVP 실행 | 적절 | 도구의 일반적 사용 흐름과 일치 |
| 각 플랫폼 내부에서 MAC별 재컴파일 | 적절 | MAC별 최적화까지 포함하는 배포 구성 평가에 맞음 |
| 모델·Vela·생성 코드·ELF 해시 검사 | 적절 | 반복 간 동일 실행물 확인 가능 |
| TA 꺼진 플랫폼을 주 분석에서 분리 | 적절 | 서로 다른 메모리 타이밍 조건을 섞지 않음 |
| 현재 U85 결과를 **순수 MAC scaling**으로 해석 | **부적절** | `system_config`와 TA 기본값이 함께 달라질 수 있음 |
| 현재 PMU 항목으로 AXI 대역폭 포화 확정 | **불충분** | 트래픽·사이클만으로 대역폭/지연/의존성 대기 분리 불가 |
| `TOTAL = ACTIVE + IDLE`를 독립 계측 검증으로 사용 | **재확인 필요** | 공개 profiler에서 IDLE은 차감으로 계산 |
| warm-up 및 saturation 정의 | **수정 필요** | 프로세스 재시작 여부와 임계값의 수학적 의미 구분 |

## 2. U85에서는 MAC 외의 조건도 바뀜

### 2.1 현재 스윕이 실제로 바꾸는 것

| U85 MAC | Vela `system_config` | 메모리 모드 |
|---:|---|---|
| 128 | `Ethos_U85_SYS_DRAM_Low` | `Dedicated_Sram` |
| 256 | `Ethos_U85_SYS_DRAM_Low` | `Dedicated_Sram` |
| 512 | `Ethos_U85_SYS_DRAM_Mid_512` | `Dedicated_Sram` |
| 1024 | `Ethos_U85_SYS_DRAM_Mid_1024` | `Dedicated_Sram` |
| 2048 | `Ethos_U85_SYS_DRAM_High_2048` | `Dedicated_Sram` |

256→512에서 **MAC 증가와 시스템 프로파일 변경을 동시 수행**. 조합 자체가 틀린 건
아니고 Arm MLIA 기본 프로파일도 같은 방식. 다만 답하는 질문이 다름:

- 현재 광역 스윕: "각 MAC에 대응하는 시스템 프로파일에서 관측 비용은 어떻게 달라지는가?"
- 통제 스윕이 답해야 할 것: "동일한 메모리 서비스 조건에서 MAC 구성만 바꾸면?"

### 2.2 `Low → Mid`는 이름만 바뀌는 게 아님

공개 `default_vela.ini` 값 (서버 파일로 확정한 것 아님):

| Vela 설정 | `DRAM_Low` | `DRAM_Mid_512` |
|---|---:|---:|
| `core_clock` | 500 MHz | 1 GHz |
| `Sram_read_latency` | 16 cycles | 32 cycles |
| `Sram_write_latency` | 16 cycles | 32 cycles |
| `Dram_clock_scale` | 0.46875 | 0.75 |
| `Dram_max_reads` | 24 | 64 |
| `Dram_max_writes` | 12 | 32 |

사이클로 정규화해도 교란이 사라지지 않음 — 메모리 지연의 사이클 단위와 컴파일러
스케줄 선택까지 달라지므로.

### 2.3 Vela만 고정하면 부족

Vela INI는 **컴파일러가 사용하는 시스템 설명**, MLEK TA 설정은 **실행 중 적용할
메모리 서비스 조건**. 공개 MLEK 문서는 U85 TA 기본 파일을 이렇게 선택:

```
128 / 256 MAC  -> ta_config_u85_sys_dram_low.cmake
512 / 1024 MAC -> ta_config_u85_sys_dram_mid.cmake
2048 MAC       -> ta_config_u85_sys_dram_high.cmake
```

따라서 **`TA=ON`은 "동일한 메모리 조건"을 뜻하지 않음.** 공개 TA 파일에서 Low와 Mid는
SRAM 지연, 외부 메모리 지연, outstanding request 제한, bandwidth cap이 다름.

문서의 `dual binding`이 아래 둘을 모두 통제했는지 확인 필요:
- 컴파일러 측: Vela `system_config`, `memory_mode`
- 실행 측: TA 실제 적용값, FVP 관련 시스템 설정

## 3. Vela 옵션 검토

기본 형태는 맞음. 확인·보완할 점:

| 옵션 | 확인할 점 |
|---|---|
| `--accelerator-config` | FVP MAC 및 드라이버 대상 구성과 일치해야 함 |
| `--config default_vela.ini` | 경로뿐 아니라 **파일 해시와 내용** 보존 |
| `--system-config` | 통제 스윕에서는 같은 조건으로 고정 |
| `--memory-mode` | MLEK 메모리 모드와 실제 배치도 확인 |
| `--optimise Performance` | 모든 비교 셀에서 동일 유지 |
| 입력 `.tflite` | 동일 workload 입력 모델 해시는 MAC 간 동일해야 함 |

MAC별 Vela 재실행은 **맞음**. 단, 측정 효과의 정확한 명명은
"MAC 구성 변경 + 그 구성에 맞춘 컴파일러 재최적화를 포함한 효과"이며,
"연산기 수만의 물리적 효과"라고 부르면 안 됨.

메모리 모드 주의 — 공개 기본 정의:

| 모드 | 상수·가중치 | 일반 arena | 빠른 cache 영역 |
|---|---|---|---|
| `Sram_Only` | AXI0 | AXI0 | AXI0 |
| `Shared_Sram` | AXI1 | AXI0 | AXI0 |
| `Dedicated_Sram` | AXI1 | AXI1 | AXI0 |

`Dedicated_Sram`은 "모든 데이터를 전용 SRAM에"가 **아님**. 현재 U85 프로파일이
`SYS_DRAM_*`이므로 "SRAM/Flash 대역폭 실험"보다 "SRAM 및 외부 메모리 서비스 조건
분석"이 정확.

## 4. CMake 옵션 검토

| 옵션 | 판정 및 주의점 |
|---|---|
| `CMAKE_TOOLCHAIN_FILE` | 적절. GCC 버전과 컴파일·링크 옵션도 보존 |
| `TARGET_PLATFORM` / `TARGET_SUBSYSTEM` | 적절. 실제 FVP와 대응해야 함 |
| `ETHOS_U_NPU_ID` | 적절 |
| `ETHOS_U_NPU_CONFIG_ID` | 접두어는 맞음. **단순 표시용으로 취급하면 안 됨** |
| `ETHOS_U_NPU_MEMORY_MODE` | Vela 모드와 일치 필요 |
| `ETHOS_U_NPU_ENABLED=ON` | **CPU fallback 0개 보장 아님** |
| `ACTIVATION_BUF_SZ=0x00200000` | arena 크기. 물리 SRAM 용량과 별개 |

### 4.1 `CONFIG_ID`는 소스 기준 확인 필요
공개 CMake 소스에서 `CONFIG_ID`에서 MAC 수를 추출해 `ETHOSU_TARGET_NPU_CONFIG`를
구성하는 코드가 확인됨. 세 설정이 모두 맞아야 함:
```
Vela accelerator-config = ethos-u85-512
MLEK CONFIG_ID          = Z512
FVP num_macs            = 512
```

### 4.2 `ACTIVATION_BUF_SZ` ≠ NPU cache 크기
공개 MLEK에 별도 `ETHOS_U_NPU_CACHE_SIZE`, 공개 기본값 393,216 bytes.
`wav2letter` SRAM overflow도 **링커 map에서 어떤 객체·버퍼가 넘쳤는지** 확인 필요.
링크 실패만으로 "가중치가 SRAM보다 커서 실행 불가"라고 단정하지 말 것.

### 4.3 추가 기록 권고
```
TA_CONFIG_FILE
ETHOS_U_NPU_CACHE_SIZE
CMAKE_BUILD_TYPE 및 실제 최적화 옵션
FPGA/FVP 빌드 분기
CPU_PROFILE_ENABLED
실제 드라이버 target configuration
```
`TA_CONFIG_FILE`은 파일명뿐 아니라 생성된 `timing_adapter_settings.h`와 최종 적용값까지 보존.

## 5. FVP 실행 명령 검토

명령 형태 타당. 파라미터 경로는 FVP 바이너리별 확인 권고:
```sh
FVP_Corstone_SSE-320 --version
FVP_Corstone_SSE-320 --list-params > fvp-parameters.txt
grep -E 'num_macs|uart0|telnetterminal0|visualisation' fvp-parameters.txt
```
FVP 실행 파일 SHA-256도 기록 권고.
**주의:** `--list-params`로 펌웨어가 부팅 후 TA 레지스터에 쓴 값까지 확인되지 않음.

## 6. PMU 검증의 두 가지

### 6.1 `TOTAL == ACTIVE + IDLE`는 독립 증거가 아닐 수 있음
공개 `ethosu_profiler.c`:
```c
idle = total_ccnt - active_counter;
```
같은 구현이면 항등식은 **세 독립 카운터의 일치가 아님**. 출력·파싱의 산술 일관성
검사로는 유용하나 측정 경계·카운터 의미를 검증하지 못함.

구분해야 할 것:
- **합계 일치**: 출력 및 파싱의 산술 일관성 확인
- **측정 경계 검증**: reset·enable·disable·read 위치와 동작 확인

측정값을 `T_NPU` 대신 "드라이버 추론 호출에 걸친 PMU 카운터 측정 구간"으로 제한한 것은 적절.

### 6.2 U85 메모리 이벤트를 AXI0/AXI1 이름으로만 파싱하면 안 됨
결정론 검사 필드는 `axi0_rd_beats`, `axi0_wr_beats`, `axi1_rd_beats`.
공개 U85 profiler는 `SRAM_RD`, `SRAM_WR`, `EXT_RD`, `EXT_WR` 출력.
**이 이름 차이로 U85 메모리 필드가 유실되었을 가능성.**

> **`None == None == None`도 결정론 검사를 통과할 수 있음.**

equality 검사 전에 **해당 세대에서 필수인 필드가 실제 숫자로 수집되었는지** 확인하는
검사 필요. 카운터 overflow 경고도 실패·제외 기준에 포함 권고.
기존 동결 결과를 수정된 파서 결과로 덮어쓰지 말고, 원시 UART 재파싱인지 새 캠페인인지 구분.

## 7. 반복 방법

### 7.1 별도 FVP 실행을 버린 것은 모델 warm-up이 아닐 수 있음
```
FVP 프로세스 A: 추론 1회 → 종료 → 폐기
FVP 프로세스 B: 추론 1회 → M1
...
```
A의 캐시·NPU 상태는 B로 이어지지 않음. 정확한 표현:
> "예비 실행 1회 후, 독립적인 FVP 시작에서 첫 추론을 3회 측정했다."

같은 프로세스에서 첫 추론만 버린 경우에만 warm-up으로 설명 가능.

### 7.2 입력 데이터 정책 누락
공개 stock runner에는 입력을 `std::rand()`로 채우는 경로와 메모리에서 읽는 경로가 있음.
stock이라는 이유로 입력이 모두 0이라 가정하면 안 됨. 최소 기록 항목:
```
입력 생성 방식 및 seed
전체 입력 tensor의 해시
RNNoise 상태 입력의 초기화 방식
출력 검증 방식
각 셀의 CPU fallback 여부
```

### 7.3 세 번 일치 = 재현 가능. 정확성 입증은 아님
불일치의 의미는 우선 "사전 정의한 결정론 조건 미충족". 조사 없이 하네스 결함으로
확정할 필요 없음. FVP 결과가 세 번 같아도 실제 하드웨어 타이밍과 일치한다는 뜻 아님.

## 8. saturation과 reversal — 반드시 고칠 점

정의:
```
E_inc = (C_prev / C_next) / (M_next / M_prev)
```
`incremental < 0.50`을 처음 만족하는 구성을 saturation으로 정의.

**MAC 2배 구간에서는 이것이 정확히 "사이클 증가" 조건:**
```
E_inc < 0.5  <=>  C_prev/C_next < 1  <=>  C_next > C_prev
```

| MAC 2배 결과 | Speedup | E_inc |
|---|---:|---:|
| 사이클 절반 | 2.0 | 1.0 |
| 변화 없음 | 1.0 | 0.5 |
| 사이클 증가 | <1 | <0.5 |

즉 기존 `saturation_point`는 포화점보다 **첫 성능 역전 지점**에 가까움.

권고: 사전 정의는 그대로 보고하되 "본 연구의 saturation 기준은 인접 2배 전이에서
사이클 증가를 검출하는 운영적 정의"라고 명시. 추가 분석에서 `reversal`, `plateau`,
`diminishing returns` 분리. **스케일링 포화와 AXI 대역폭 포화는 같은 개념이 아님.**

### 21 ladder의 분모 구분
TA ON 조합 11개 × 7 workload = 77 후보. SSE-300/U55 ASR 3셀 제외 → 74.
ASR/U55 그룹에는 한 점만 남으므로 **21개 그룹과 실제 전이 평가 가능 ladder 수를 구분** 필요.
함께 보고 권고:
```
전체 workload-platform 그룹 수
2개 이상 유효 MAC 점을 가진 그룹 수
유효한 인접 전이 수
실행 불가로 평가하지 못한 전이 수
```

## 9. 스윕 분할 제안

### 단계 A — 기존 광역 스윕 유지
"지원되는 구성 조합에서 어떤 workload와 전이가 낮은 효율 또는 역전을 보이는가?"
이 단계에서는 병목을 확정하지 않음.

### 단계 B — 이상점 통제: MAC × 시스템 프로파일
| 실행 | MAC | Vela 시스템 조건 | 실행 메모리 조건 |
|---|---:|---|---|
| A | 256 | Low | Low 고정 |
| B | 512 | Low | Low 고정 |
| C | 256 | Mid | Mid 고정 |
| D | 512 | Mid | Mid 고정 |

**A↔B, C↔D**가 같은 외부 메모리 조건 아래 MAC 비교. **A↔D만 비교하면 섞임.**
이미 수행한 dual-binding이 이 통제를 구현했다면, 추가 실행보다 그 설정표와 결과를
본문에 연결하는 것이 우선.

### 단계 C — 원인별 표적 실험
| 가설 | 통제할 조건 | 바꿔볼 변수·측정 |
|---|---|---|
| 메모리 대역폭 제약 | MAC, 지연, 요청 동시성, 실행 스트림 | 대역폭 완화 시 사이클 감소하는가 |
| 메모리 지연·요청 동시성 제약 | MAC, 대역폭, 실행 스트림 | read latency / outstanding request 민감도 |
| DWConv 낮은 확장성 | 메모리 조건, 비교 가능 tensor shape | 연산별 MAC scaling과 tiling 변화 |
| 작은 feature map 병렬성 부족 | 연산 유형, 채널·메모리 조건 | spatial shape 및 tile 수에 따른 scaling |
| 작은 연산량과 고정 비용 | 메모리·launch 조건 | 연산량 증가 시 고정 비용 비중 감소하는가 |
| SRAM 용량·weight streaming | MAC, 대역폭·지연 | cache/버퍼 용량 변경 시 스케줄·트래픽·사이클 변화 |
| 비단조 scaling | 앞 단계 통제 구성 | launch/group별 cycle 증가 분포 |

두 실험을 구별할 것:
- **실행 스트림 고정 + 메모리 서비스만 변경**: 해당 실행의 메모리 민감도 분석
- **새 메모리 조건에 맞춰 Vela도 재컴파일**: 메모리 조건 + 컴파일러 적응 포함 배포 성능 분석

## 10. 서버에서 우선 확인할 명령 (덮어쓰지 않는 확인용)

```bash
export KIT=/opt/arm/ml-embedded-evaluation-kit
export BUILD=/실제/보존된/셀/build-a1

git -C "$KIT" rev-parse HEAD
git -C "$KIT" status --short
git -C "$KIT" submodule status --recursive
vela --version
arm-none-eabi-gcc --version
cmake --version

sha256sum "$KIT/scripts/vela/default_vela.ini"

grep -E '^(TARGET_PLATFORM|TARGET_SUBSYSTEM|ETHOS_U_NPU_|ETHOSU_TARGET_NPU_CONFIG|TA_CONFIG_FILE|SRAM_|EXT_|inference_runner_|CMAKE_BUILD_TYPE)[^=]*=' "$BUILD/CMakeCache.txt"

find "$BUILD" -type f -name 'timing_adapter_settings.h' -print

grep -RnsE 'ETHOS_U_NPU_CONFIG_ID|TA_CONFIG_FILE|ETHOSU_TARGET_NPU_CONFIG' "$KIT/scripts" "$KIT/source"

grep -RnsE 'npu_derived_counters|npu_total_ccnt|NPU IDLE|Get_CCNTR' "$KIT/source"
```

새 통제 빌드에는 `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` 권고.
`SOURCE_DATE_EPOCH=1776763519` = 2026-04-21 09:25:19 UTC, 문서와 일치.

## 최종 정리

"광역 스윕 → 이상점 발견 → 통제 비교 → 연산별 분석" 순서는 맞음. 다만 광역 스윕
다음에 바로 병목 설명으로 넘어가기 전에 **MAC과 함께 바뀐 Vela·TA 조건을 분리하는
단계가 반드시 필요**.

우선 작업 세 가지:
1. U85의 실제 `TA_CONFIG_FILE`·생성 헤더와 Vela INI를 대조하고, 기존 dual-binding이
   두 경로를 모두 통제했는지 확인
2. 서버 profiler의 IDLE 계산 방식과 U85 이벤트 파서 확인
3. warm-up, saturation, 유효 ladder 정의를 실제 실행 구조에 맞게 수정

현재 자료는 **기본 구성의 특성화와 이상점 탐지에는 사용 가능하지만, 그 자체로 AXI
대역폭 포화나 네 가지 원인을 입증하지는 않음.**

### 참고 출처
- Alif 공개 MLEK `docs/sections/timing_adapters.md`
- PyPI `mlia`, `ethos-u-vela 5.0.0`
- Arm Developer: MLEK 블로그, Arm Learn FVP 실행
- CMake 공식 문서, GCC 환경변수 문서
- Alif 공개 MLEK `inference_runner/src/UseCaseHandler.cc`
