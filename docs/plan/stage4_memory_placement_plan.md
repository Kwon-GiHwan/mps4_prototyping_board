# Stage 4 보완 — 대표 Conv의 IFM·OFM DRAM/SRAM 배치 비교 설계 (2026-11-11, 설계만)

Owner 지시(2026-11-11 "Stage 4 보완 — 대표 Conv의 DRAM·SRAM 배치 비교 설계"). **이번 승인 범위는 정적 조사·설계·보드 없는
검증까지다.** 펌웨어 변경 구현, 이미지 빌드, 배포, 보드 측정은 하지 않았고 이 문서를 보고한 뒤 따로 결정한다.
기본 실험(Stage 1–5)과 AD 분석의 종료 상태는 바꾸지 않는다.

**측정 조건(기존 값의 출처).** FI101 Ethos-U85 1024 MAC, **TA profile 1**(MLEK sys_dram_mid), Driver Runner 이미지
`83398c7`, Vela 5.0.0(MLEK 옵션, Dedicated_Sram, Ethos_U85_SYS_DRAM_Mid_1024, Performance), Stage 4 conv_base(boot 330).

**근거 파일.**
- `evidence/stage4_placement/container_facts.txt`: 컨테이너에서 읽기만 한 사실. 측정 이미지의 map·섹션·심볼, MLEK 링커·
  `mem_regions.h`·NPU CMake, core driver `ethosu_device_u85.c`·`ethosu_config_u85.h`, sha256 포함.
- `evidence/stage4_placement/static_facts.py` → `facts.json`: 기존 conv_base 산출물(명령 스트림, DRWL 메타데이터, boot 330의
  RUN 기록, capabilities, Stage 4 요약)에서 아래 사실을 다시 계산한다. 검사 17개가 모두 통과했다.

## 0. 판정 요약

| 질문 | 판정 |
| --- | --- |
| 3.3 필요한 변경의 범위 | **최소한의 주소·할당·영역 설정 기능 추가가 필요하다.** 현재 이미지 `83398c7`에는 arena를 SRAM에 두는 경로도, region 1을 SRAM 포트로 보내는 경로도 없다 |
| 재컴파일 필요 여부 | **불필요.** Vela payload(모델·명령 스트림·가중치)를 바이트 단위로 그대로 재사용한다. 분류: **계산 구성 유지, 메모리 접근 구성 변경** |
| IFM·OFM만 옮길 수 있는가 | **region 1 전체를 옮긴다.** 다만 이 payload의 region 1에는 IFM과 OFM만 있다(64,512 B = 9,216 + 55,296). NPU가 접근하는 다른 작업공간은 함께 옮겨지지 않는다 |
| IFM과 OFM을 따로 옮길 수 있는가 | 아니다. 둘이 같은 region 1의 base 하나를 공유한다. 따로 옮기려면 재컴파일이 필요하고 범위 밖이다 |
| 메모리 모드 | Dedicated_Sram 유지. Shared_Sram·Sram_Only로 컴파일하거나 이미지 모드를 전환하지 않는다 |

## 1. 현재 메모리·region 구조와 실제 가용 SRAM

### 1.1 conv_base의 region 사용 (명령 스트림 `evidence/stage4/registers/conv_base.regs.txt`)

| region | 명령 스트림에서의 용도 | job base (boot 330 기록, RUN 10회 모두 동일) | 크기 | NPU 포트 (REGIONCFG → MEM_ATTR) |
| --- | --- | --- | --- | --- |
| 0 | 가중치·scale 원본, DMA 소스 | `0x700003B0` (DDR, 모델 flatbuffer 안) | 0xFC0 | MEM_ATTR3 = EXT (AXI1) |
| 1 | **IFM**(오프셋 0xD800)과 **OFM**(오프셋 0x0, 두 번째 kernel은 0x10) | `0x700015C0` = TFLM arena 시작 | 0xFC00 = 64,512 | MEM_ATTR3 = EXT (AXI1) |
| 2 | 가중치·scale staging. DMA 대상, WEIGHT/SCALE region | `0x31000000` (SRAM, fast memory) | 0xFC0 = 4,032 | MEM_ATTR1 = SRAM (AXI0) |
| 3, 4 | TFLM이 넘긴 IFM·OFM 텐서 포인터. 명령 스트림은 사용하지 않음 | `0x7000EDC0`, `0x700015C0` | 0x2400, 0xD800 | MEM_ATTR1 |
| QBASE | 명령 스트림 | 모델 안 (DDR) | 520 B | QCONFIG 3 = EXT |

- kernel은 2개다(CONV, OFM 깊이 16 + 80으로 분할). 두 kernel이 각각 IFM 전체를 읽는다.
- DMA는 region 0 → region 2만 있다(1,024 B + 3,008 B). region 1과 관련된 DMA는 없다.
- MEM_ATTR 값: 0 = 0, 1 = 0, 2 = 4, 3 = 4. `capabilities.json`에서 읽었고 드라이버 기본값과 같다(0·1 = SRAM 포트, 2·3 = EXT 포트).
- region 매핑의 출처:
  - MLEK `source/hal/source/components/npu/CMakeLists.txt`의 Dedicated_Sram 설정: `NPU_QCONFIG=3`, `NPU_REGIONCFG_0=3`,
    `NPU_REGIONCFG_1=3`, region 2–7 = 1.
  - 측정 이미지의 `ethosu_config_select`(weak, 드라이버 것)를 디스어셈블한 결과: index 2–7 → 1, 그 외 → 3.
- 이 job의 REGIONCFG(base 5개)는 계산값으로 **0x15F**다. 기존 이미지는 RUN마다 REGIONCFG를 읽지 않았다. capabilities의
  `regioncfg 0`은 job 전에 읽은 값이다.

### 1.2 같은 region에 함께 있는 것

- region 1(TFLM arena의 앞 64,512 B)에는 IFM과 OFM만 있다. Vela `arena_size` 64,512 = OFM 55,296(0x0–0xD7FF) + IFM
  9,216(0xD800–0xFBFF)이고 남는 바이트가 없다.
- TFLM arena(2 MiB, `ACTIVATION_BUF_SZ`)의 나머지는 TFLM의 CPU 전용 자료(텐서 구조체, 계획 정보 등)다. TFLM 로그에 따르면
  사용량은 64,980 B다.
- NPU가 접근하는 base는 region 0·1·2뿐이다. region 3·4는 base로 넘어가지만 명령 스트림이 참조하지 않는다.

### 1.3 fast scratch(가중치 staging)

- 드라이버의 fast memory는 `cache_arena` 하나다: `0x31000000`, 0x60000 = 384 KiB. MLEK `ethosu_npu_init`의 정적 버퍼이고,
  링커 `.sram` 섹션에 이것만 있다.
- conv_base가 쓰는 부분은 앞 4,032 B다. 이 workload의 가중치를 double buffer로 staging한다.
- 수명: 이미지 수명 전체. 드라이버가 job마다 region 2의 base로 넘긴다.

### 1.4 SRAM 전체와 빈 영역 (측정 이미지 map)

| 범위 | 내용 |
| --- | --- |
| `0x31000000–0x3105FFFF` (384 KiB) | `cache_arena` = fast memory(region 2) |
| `0x31060000–0x311FFFFF` (1.625 MiB) | ISRAM0의 나머지. **링커가 어떤 섹션도 두지 않음** |
| `0x31200000–0x313FFFFF` (2 MiB) | ISRAM1. **링커가 어떤 섹션도 두지 않음** |

- 링커 `MEMORY`: `SRAM 0x31000000, LENGTH 0x00400000`.
- `mem_regions.h`: ISRAM0 = 0x31000000(2 MiB), ISRAM1 = 0x31200000(2 MiB), secure alias. non-secure alias는 0x21000000이다.
- 측정 이미지의 섹션과 심볼 중 SRAM 범위에 있는 것은 `cache_arena`뿐이다(`nm`, `objdump -h`).
- 펌웨어의 다른 메모리:
  - 코드·데이터·.bss·heap: BRAM 0x12000000.
  - stack: DTCM 0x30000000.
  - 모델·arena: DDR 0x70000000.
  - UART staging: DDR 0x90000000.
- 결론: 빈 SRAM 0x31060000–0x313FFFFF(3,801,088 B)는 현재 펌웨어의 어떤 데이터와도 겹치지 않는다(정적 근거).
- **보드에서 확인하지 않은 것.**
  - FI101에 그 주소의 SRAM이 실제로 있고 CPU가 접근할 수 있는지.
  - ISRAM1까지 접근할 수 있는지.
  - NPU가 SRAM 포트로 0x31060000 이후 주소에 접근할 수 있는지.
  - 이 셋은 §7의 사전 검증 P2로 확인한다. NPU가 SRAM 포트로 `0x31000000`에 접근한다는 것만 기존 데이터로 확인되어 있다
    (region 2, Stage 4 PASS_EXACT).

### 1.5 CPU 주소와 NPU 주소, 캐시

- 주소 대응:
  - 드라이버의 `ethosu_address_remap`은 runner hook으로 덮어쓰여 있고 identity다. NPU base는 CPU 주소와 같다.
  - region 2(0x31000000, secure alias)와 region 0/1(0x70000000, secure alias)이 이 대응으로 이미 동작했다.
  - B는 같은 SRAM secure alias를 쓴다.
- 캐시:
  - MLEK `ethosu_cpu_cache.c`는 base 주소를 보지 않는다. job 전에 D-cache 전체를 clean하고(`SCB_CleanDCache`), job 후에
    전체를 invalidate한다(`SCB_InvalidateDCache`). 그래서 A와 B는 같은 코드, 같은 동작으로 캐시를 처리한다.
  - MLEK 소스에는 MPU 설정이 없다(grep 결과 0건). CPU 측 메모리 속성은 아키텍처 기본 메모리 맵을 따른다.
    0x3xxxxxxx와 0x7xxxxxxx가 둘 다 write-back cacheable이라는 것은 아키텍처 문서에 근거한 판단이고 보드에서 확인하지 않았다.
  - 이 차이는 CPU 접근에만 해당하며 NPU 계측창 밖이다.
- 계측창:
  - PMU는 QBASE remap hook에서 arm된다. 드라이버 순서는 soft reset, power, flush 다음이고 REGIONCFG·CMD 바로 앞이다.
  - PMU snapshot은 완료 IRQ 진입 시점이다.
  - CPU의 IFM 복사(`run()`의 memcpy), 캐시 clean·invalidate, 출력 비교와 조회는 모두 이 창 밖이다.

## 2. IFM·OFM만 옮길 수 있는가

- **region 1 base 하나를 SRAM으로 옮긴다.** 함께 이동하는 NPU 접근 데이터는 IFM(9,216 B)과 OFM(55,296 B)뿐이다.
  가중치 원본(region 0), staging(region 2), 명령 스트림은 이동하지 않는다.
- 구현상 TFLM arena 전체(2 MiB)를 SRAM에 둔다.
  - region 1 base는 TFLM이 scratch 텐서 주소(arena 시작)로 정하므로, arena 시작 위치가 곧 region 1 위치다.
  - 함께 옮겨지는 나머지는 TFLM의 CPU 전용 자료이고 NPU는 접근하지 않는다.
  - 보고서에는 "region 1(IFM·OFM)과 TFLM arena(CPU 전용 자료 포함)를 SRAM으로 옮긴 비교"라고 쓴다.
- IFM과 OFM은 같은 base를 쓰므로 둘 중 하나만 옮길 수 없다. 결과는 **입력 읽기와 출력 쓰기의 개별 기여로 나누지 않는다.**

## 3. 기존 payload 재사용과 계산 구성

- 재사용하는 payload:
  - DRWL 안의 Vela tflite 바이트 그대로(`vela_sha256 fadf33d7…`): 명령 스트림 `596fe964…`(520 B), 가중치 4,032 B.
  - 입력(seed 1, `7dc7f308…`)과 CPU 기준 출력(`05deb078…`)도 그대로다.
- 명령 스트림은 region 번호와 오프셋만 담는다. 메모리 종류는 런타임의 base 주소와 REGIONCFG가 정한다. 따라서 같은 바이트의
  명령 스트림이 B에서 SRAM 주소로 실행된다.
- kernel 수·순서, block(OFM 6×12×96, IFM 6×12×16), ublock 2×2×32, PartKernel traversal, 채널 분할, 가중치 인코딩과 DMA,
  stride는 모두 명령 스트림 안에 있으므로 동일하다.
- 해석 한계:
  - Vela는 region 1을 DRAM이라고 보고 스케줄을 골랐다(`ifm_memory/ofm_memory Dram`, 추정값 `dram_ac 24999`).
  - 그래서 B는 "SRAM을 전제로 Vela가 최적화한 구성"이 아니라 **DRAM 전제로 만든 같은 구성을 SRAM 경로에서 실행한 것**이다.
  - Vela가 B 조건에서 다른 스케줄을 골랐을지는 이 비교로 답하지 않는다(재컴파일은 범위 밖).

## 4. 필요한 Runner·펌웨어 변경과 복원 방법 (목록만, 구현하지 않음)

MLEK 트리와 core driver는 수정하지 않는다. MLEK의 `inference_runner`도 건드리지 않는다. 모든 변경은
`firmware/driver_runner`와 `host/` 안에서 한다.

| # | 변경 | 내용 | 기본값(A)이 기존과 같은 이유 |
| --- | --- | --- | --- |
| F1 | DRWL 헤더 word 7 `placement` | 0 = 기존(DDR arena), 1 = SRAM arena. 다른 값은 load에서 거부. `workload.h`/`workload.c`, `host/lib/drwl.py`, 계약 테스트 | A blob은 Stage 4 blob(`2681c566…`)과 바이트가 같다(word 7 = 0). B blob은 word 7 하나(오프셋 28–31)만 다르다 |
| F2 | SRAM arena 배치 | `place_and_load()`: placement 1이면 arena = (fast memory 끝, 런타임에 `ethosu_drv.fast_memory + fast_memory_size`로 구함) + (DDR arena − model_base). conv_base에서는 `0x310615C0`(하위 16 bit `0x15C0`이 A와 같음). 끝 `0x312615C0` ≤ `0x31400000`이 아니면 `LOAD_NO_ROOM`. arena 길이는 A와 같은 2 MiB | placement 0이면 기존 `drwl_arena_after()` 그대로 |
| F3 | region 1 포트 선택 | `hooks.c`에 strong `ethosu_config_select()`를 둔다. MLEK Dedicated_Sram 값(QCONFIG 3, region 0·1 = 3, 2–7 = 1)을 그대로 반환하고, placement 1일 때만 index 1 → **0**(MEM_ATTR0 = SRAM 포트, MLEK Shared_Sram이 region 1에 쓰는 값). 표는 `placement.c`의 순수 함수로 두어 host 시뮬레이터에서 시험한다 | 반환값이 드라이버 기본값(디스어셈블로 확인)과 같다. 보드에서는 F4로 RUN마다 다시 읽는다 |
| F4 | 배치 되읽기 | IRQ 진입 시 REGIONCFG(0x3C)와 QCONFIG(0x1C)를 읽는다. record schema 3 → 4에서 끝에 `regioncfg_irq`, `qconfig_irq`, `placement`를 추가한다. `host/lib/record_v2.py`와 계약 테스트도 같이 바꾼다 | 기존 필드의 순서와 의미는 바뀌지 않는다 |
| F5 | 적재 시 메모리 검사 | LOAD_MODEL_END 때 **두 조건 모두**: arena 전체에 패턴 쓰기·읽기 검사(실패 시 `LOAD_MEM_CHECK`), 모델 init 뒤 OFM 텐서를 `0x5A`로 채우고 캐시 clean. 결과는 load 상태와 capabilities로 보고한다 | RUN 경로(`run()`)에는 아무것도 추가하지 않는다 |
| F6 | 빌드 gate | `build_driver_runner.sh`에 추가: (a) SRAM 범위의 심볼은 `cache_arena`(0x60000) 하나뿐, (b) `ethosu_config_select`가 runner의 strong 정의(T), (c) 기존 gate | — |
| F7 | host | `pack`에 `--placement sram`(word 7만 바꿈, 바꾸기 전후 sha256 기록), 분석 `host/analysis/stage4p.py`(§6–8 규칙, Stage 4 지표 함수 재사용), 테스트와 mutation | — |

- **보드 없이 할 검증(구현 승인 뒤).**
  - host 시뮬레이터(`firmware/driver_runner/tests/host_sim.c`) 확장:
    - word 7 거부(2, 0xFFFFFFFF).
    - SRAM arena 계산과 범위 밖 거부.
    - `ethosu_config_select` 표: A = 원래 표, B = index 1만 0.
    - REGIONCFG 계산 A 0x15F, B 0x153.
    - schema 4 record 왕복.
  - `test_drwl.py`·`test_record_v2.py`·계약 테스트 갱신.
  - `stage4p.py` 규칙 테스트와 mutation(각 규칙을 무력화했을 때 RED 확인, sha256으로 복원).
  - `sh test.sh` 전체 실행.
- **복원.**
  - 새 이미지는 새 커밋에서 빌드하고 배포 때 새 evidence root를 쓴다.
  - 측정 뒤 `restore.sh ~/evsweep/evidence_m6` → `postflight.sh`(기존 절차).
  - placement 0이 기본이므로, 이후 다른 측정에 새 이미지를 쓰더라도 기존 동작이 유지된다(A 재현으로 확인).
  - 저장소 변경은 별도 커밋으로 둔다. 되돌리려면 revert한다. 기존 이미지 `83398c7`과 그 데이터는 그대로 둔다.

## 5. 두 조건의 비교표

| 항목 | A (DDR, 기준) | B (SRAM) | 상태 |
| --- | --- | --- | --- |
| 입력·가중치·Bias·양자화·Activation, CPU 기준 출력 | Stage 4 conv_base | 동일(같은 DRWL 바이트, word 7만 다름) | 동일 |
| Vela 산출물: kernel 2개(CONV), block 6×12×96 / 6×12×16, ublock 2×2×32, PartKernel, 채널 분할 16 + 80 | 명령 스트림 `596fe964…` | 같은 바이트 | 동일 |
| 텐서 형식·stride(NHWC, IFM stride Y 0x180 / X 0x10, OFM Y 0x900 / X 0x60) | 명령 스트림 | 같은 바이트 | 동일 |
| 가중치 인코딩과 DMA(region 0 → 2, 1,024 + 3,008 B) | DDR → SRAM staging | 동일 | 동일 |
| region 0(가중치 원본)·QBASE | `0x700003B0` 부근, EXT 포트 | 동일 | 동일 |
| region 2(staging) | `0x31000000`, SRAM 포트 | 동일 | 동일 |
| **region 1(IFM·OFM)** | `0x700015C0`, EXT 포트(MEM_ATTR3), TA_EXT | **`0x310615C0`, SRAM 포트(MEM_ATTR0), TA_SRAM** | **의도한 변경** |
| region 1 주소 특성 | DDR4 block 0. 하위 16 bit `0x15C0`, 64 B 정렬 | ISRAM0. 하위 16 bit `0x15C0`, 64 B 정렬. 접근 범위 끝 `0x310711C0` < ISRAM1 | 정렬은 맞춤, 메모리 종류만 다름 |
| REGIONCFG(job, base 5개) | 0x15F | 0x153 | 의도한 변경(region 1 필드만) |
| TFLM arena의 CPU 전용 자료(2 MiB 중 나머지) | DDR | SRAM(일부는 ISRAM1) | 함께 이동. NPU는 접근하지 않음 |
| TA 설정 | profile 1(TA_SRAM rlat 32, maxr 8, bwcap 4000 / TA_EXT rlat 500, wlat 250, bwcap 3750) | 같은 레지스터 값 | 동일. 단 region 1 트래픽이 **어느 TA를 지나는지**가 바뀜(§5.1) |
| AXI limit | AXI_SRAM 0x20F0B / AXI_EXT 0x21F3F | 같은 값 | 동일. region 1에 적용되는 쪽이 바뀜 |
| CPU 대기(WAIT_WFE), D-cache 켜짐, 캐시 처리(전체 clean/invalidate) | MLEK 그대로 | 동일 | 동일 |
| PMU pass A·B 이벤트, RUN 수 | Stage 4 `ids.txt`, 1 + 4 | 동일 | 동일 |
| 펌웨어 이미지 | **새 이미지**(F1–F6) | 같은 새 이미지 | 동일(기존 이미지 값과는 직접 비교하지 않음) |

### 5.1 함께 바뀌는 것 (분리할 수 없음)

- 이 플랫폼에서 "region 1을 SRAM에 둔다"는 것은 다음 세 가지가 함께 바뀌는 것이다.
  - 물리 메모리가 DDR에서 ISRAM으로 바뀐다.
  - NPU AXI 포트가 EXT에서 SRAM으로 바뀐다.
  - 적용되는 timing adapter가 TA_EXT(SYS_DRAM_Mid 흉내, 지연 500/250)에서 TA_SRAM(지연 32)으로 바뀐다.
- 그러므로 B는 MLEK이 SRAM arena에 쓰는 경로(Shared_Sram 이미지의 region 1 설정)를 Dedicated_Sram payload에 적용한 것이고,
  결과는 **"profile 1에서 DRAM 경로와 SRAM 경로의 비교"**다.
- 순수한 물리 메모리 지연의 차이로 해석하지 않는다. TA가 FI101의 지연을 덮어쓴다는 것이 이미 확인되어 있다(`evidence/ta_ab/`).
- B에서는 IFM·OFM 트래픽과 가중치 staging(region 2)이 같은 SRAM 포트와 같은 TA_SRAM을 함께 쓴다. 이 공유도 B 구성의 일부다.
- 채택하지 않은 대안: "SRAM 주소인데 EXT 포트를 쓰는 구성".
  - EXT 포트가 ISRAM에 닿는지 확인된 근거가 없다.
  - 그렇게 하면 트래픽이 TA_EXT를 지나므로 사실상 TA 효과만 남는다.
  - 세 번째 조건이 되므로 이번 범위 밖이다.

## 6. 출력·계측·배치 검증

**배치 검증(주소·설정 기반, 판정 조건).** 조건별 모든 RUN의 record에서 확인한다.

| 항목 | A | B |
| --- | --- | --- |
| `arena_base` = `base1` | `0x700015C0` | `0x310615C0` |
| `base_size1` | 0xFC00 | 0xFC00 |
| `base0`, `base2`, `base_size0`, `base_size2`, `n_base`, `model_base`, `model_len`, `arena_len` | Stage 4 값 | A와 같음 |
| `regioncfg_irq` / `qconfig_irq` | 0x15F / 3 | 0x153 / 3 |
| `placement` / 적재 시 메모리 검사 | 0 / 통과 | 1 / 통과 |
| capabilities MEM_ATTR0–3, AXI_SRAM/EXT, TA 22개 레지스터 | Stage 4와 같음 | A와 같음 |

**트래픽(보조 증거, 단독으로 배치를 입증하지 않음).**
- A의 기존 값(pass B 중앙값, TA profile 1, 이미지 `83398c7`): SRAM rd beat 2,016, SRAM wr 252, EXT rd 1,437, EXT wr 3,456.
  EXT wr 3,456 × 16 B = OFM 55,296 B로 정확히 같다.
- IFM·OFM이 region 1을 따라 이동했다면 사전 계산상 B는 다음과 같아야 한다.
  - EXT wr: −3,456(≈ 0).
  - EXT rd: −1,152(IFM 576 beat × kernel 2).
  - SRAM rd: +1,152.
  - SRAM wr: +3,456.
- 판정: 방향이 모두 맞으면 `TRAFFIC_CONSISTENT`, 아니면 `TRAFFIC_INCONSISTENT`.
  - 주소 설정이 B인데 EXT wr가 줄지 않는 등 **주소 증거와 트래픽이 모순되면 성능 해석을 중단한다.**
  - SRAM beat가 생겼다는 사실만으로 배치를 판정하지 않는다. A에서도 staging 때문에 SRAM 트래픽이 있다.

**출력.**
- Stage 4 규칙(CPU 기준 + 최대 1 LSB, `INVALID` 조건 포함)을 그대로 쓴다.
- 두 조건 모두 `PASS_EXACT`여야 하고, A와 B의 출력 CRC가 같아야 한다.
- F5로 OFM을 오염시켜 두었으므로, B의 정확한 출력은 NPU가 SRAM 주소에 실제로 쓴 결과다. 이전 RUN이나 다른 메모리의
  값으로는 통과할 수 없다.

**계측.**
- Stage 4 pass A(35, 48, 51, 53, 55, 64, 80, 81)와 pass B(35, 128, 130, 132, 135, 384, 386, 391)를 그대로 쓴다.
- 새 이벤트, QREAD, PMU Mask, IRQ 추적은 추가하지 않는다. record의 validity 조건도 Stage 4와 같다.

## 7. 비교 측정안(최대 20 RUN)과 별도 사전 검증 — 계약 초안 (동결 전)

**측정.**
- 새 이미지 하나, boot 2개: boot 1 = A(word 7 = 0), boot 2 = B(word 7 = 1).
- boot마다 pass A 5 RUN + pass B 5 RUN(각 warm-up 1 + 측정 4), `wfe 0 0 off 1,2`, `OUTPUTS=1`.
- 합계 **20 RUN**, 추가 반복은 없다. driver_r5의 "5 RUN 추가" trigger는 정하지 않는다.
- 순서는 A → B로 고정한다. 순서를 바꾼 반복은 하지 않으며, 순서 효과는 통제하지 않았다고 보고한다.

**별도 사전 검증(20 RUN과 구분).**

| # | 내용 | 비용 | 보드 |
| --- | --- | --- | --- |
| P0 | F1–F7 구현, host 시뮬레이터·`test.sh`·mutation 전부 GREEN/RED, 빌드 gate, A blob = Stage 4 blob 바이트 동일 | 구현과 컨테이너 빌드(약 10분) | 아니오 |
| P1 | **A 재현**: 새 이미지의 A를 Stage 4 conv_base(boot 330)와 비교. MAC_ACTIVE 2,304와 MAC_DPU 1,152가 같고(Stage 4 range 0), NPU_ACTIVE 차이 ≤ max(1 %, RUN range)(Stage 4: 21,207, range 367), 출력 `PASS_EXACT` | A 측정 RUN을 그대로 쓰고 RUN을 추가하지 않음 | 예(측정에 포함) |
| P2 | **SRAM 접근 확인**: B boot의 LOAD_MODEL_END에서 F5 메모리 검사가 통과하고, 배치 되읽기(§6 표)가 일치. 실패하거나 CPU fault로 boot가 멈추면 중단 | load 1회(RUN 아님) | 예(측정에 포함) |
| — | 배포·복원 세션 1회 | 약 5분 | 예 |

예상 보드 시간: boot 2개 × (reboot + 70 KB 업로드 + 10 RUN + 출력 55 KB 조회) ≈ 6–10분 + 배포·복원 ≈ 5분.

- P1이 실패하면 새 이미지가 기준을 바꾼 것이다. B를 해석하지 않고 원인부터 보고한다.
- 기존 이미지의 Stage 4 값과 새 이미지의 B를 직접 비교하지 않는다.

## 8. 판정 규칙, 해석 범위, 중단 조건

**유효성 gate(조건별).** 아래가 모두 맞아야 비교에 들어간다.
- Stage 4 Gate C: 출력 `PASS_EXACT`/`PASS_TOLERANCE`, RUN 유효, pass별 측정 4회.
- §6 배치 검증 전부.
- A와 B의 출력 CRC가 같음.
- P1 통과.

**지표.**
- 4회 측정의 중앙값과 RUN range를 쓴다.
- NPU_ACTIVE, MAC_ACTIVE, MAC_DPU_ACTIVE.
- 유효 MAC 884,736 / MAC_ACTIVE(Stage 4 A: 384/cycle).
- MAC_ACTIVE / NPU_ACTIVE.
- AO, WD, WD_STALLED / NPU_ACTIVE.
- pass B의 beat 7종.

**규칙.**
- 실행 비용:
  - pass마다 tol = max(A 중앙값의 1 %, 두 조건 중 큰 RUN range)를 정하고, |B − A| ≤ tol이면 그 pass는 차이 없음이다.
  - 두 pass가 모두 tol 밖이고 부호가 같으면 `B_LOWER` 또는 `B_HIGHER`다.
  - 그 밖의 경우(한 pass라도 tol 안, 또는 부호가 반대)는 `UNRESOLVED`다. Stage 4·5와 같은 규칙이다.
- 계산 활동: |ΔMAC_ACTIVE| ≤ max(두 RUN range)이고 |ΔMAC_DPU_ACTIVE|도 같은 조건이면 `COMPUTE_SAME`, 아니면 `COMPUTE_CHANGED`.
- 보조 지표(AO, WD, WD_STALLED, beat)는 같은 tol 규칙으로 "변화 / 미판정"만 기록하고 원인을 배정하지 않는다.
- 규칙과 허용폭은 측정 전에 동결하고, 결과를 본 뒤 완화하지 않는다.

| 결과 | 해석 범위 |
| --- | --- |
| `COMPUTE_SAME` + `B_LOWER`/`B_HIGHER` | 같은 계산 구성에서 계산 활동은 유지되고, region 1(IFM·OFM)의 메모리 경로(물리 메모리·포트·TA)를 바꾸면 전체 비용이 달라졌다. 그 차이를 DRAM 지연 하나의 효과로 확정하지 않는다 |
| `COMPUTE_CHANGED` | 같은 명령 스트림인데 계산 활동이 바뀐 것이다. 실행·계측 조건(되읽은 레지스터, record, 이미지)을 확인하고 무엇이 함께 바뀌었는지 보고한다. 메모리 위치 효과로 해석하지 않는다 |
| `UNRESOLVED` | 이번 조건에서는 차이를 판정하지 못했다. 메모리 경로의 영향이 없다는 뜻은 아니다 |
| (계산 스케줄 변경) | 이 설계에서는 명령 스트림이 바이트 단위로 같아서 생기지 않는다. 만약 다르다면 payload 동일성이 깨진 것이므로 중단한다 |
| 출력·배치·A 재현·트래픽 모순 중 하나라도 실패 | 성능을 해석하지 않는다. 원시 데이터를 보존하고 보고한다. 재측정하지 않는다 |

**해석 금지.**
- NPU_ACTIVE − MAC_ACTIVE를 모두 메모리 대기로 배정하지 않는다.
- IFM 읽기와 OFM 쓰기의 몫을 나누지 않는다.
- Vela가 SRAM 전제로 골랐을 스케줄과 비교하지 않는다.
- 결과를 7개 모델의 성능 원인으로 일반화하지 않는다. 원본 모델 안의 대응 연산이 SRAM을 썼다는 사실과는 "조건이
  비슷하다(`CONSISTENT_WITH`)" 수준으로만 연결한다.

**중단 조건.**
- P0 실패: 테스트, gate, A blob 동일성 중 하나라도 실패하면 중단한다.
- P1 실패.
- P2 실패: 메모리 검사 실패, fault, 배치 되읽기 불일치.
- boot가 RUN 전에 실패: 데이터를 보존하고 재실행하지 않는다.
- 위 어느 경우에도 다른 주소, 다른 arena 크기, 다른 포트로 바꿔 다시 시도하지 않는다. 바꾸려면 계약 Amendment와 승인이 필요하다.

**범위 밖(하지 않음).**
- conv_base 이외의 연산, 다른 채널 수.
- 메모리 모드 비교, Shared_Sram·Sram_Only 재컴파일.
- 주소 sweep, SRAM 예산 sweep.
- 가중치나 staging 위치 변경.
- 새 PMU 이벤트, QREAD, PMU Mask, IRQ 추적.

## 9. 이번 단계에서 실제로 한 것

- 정적 조사:
  - 저장소: Driver Runner 소스, Stage 4 산출물·원시 기록·요약.
  - 컨테이너(읽기만): 측정 이미지의 map·ELF, MLEK 링커·HAL·NPU CMake, core driver 소스.
  - 보드와 보드 host 파일은 건드리지 않았다(컨테이너는 보드 host의 docker 안에 있으며 읽기만 했다).
- 보드 없는 검증:
  - `static_facts.py`의 검사 17개가 모두 통과했다.
  - 잘못된 입력 4종(OFM region 변경, arena_size 변경, RUN 하나의 base1 변경, fast memory 크기 변경)에서는 각각 해당 검사가
    FAIL을 냈다(rc 1).
  - 이 스크립트는 판정 gate가 아니라 사실 재계산이다. 그래서 mutation 시험 대상에서 빼고, 잘못된 입력 시험만 했다.
- 하지 않은 것: F1–F7 구현, 이미지 빌드, 배포, 보드 측정, 계약 동결.
