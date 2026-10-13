# 74셀 정식 FVP 스윕 (Stage 1/2/3, 2026-08-25) — 방법·명령어·설정

**범위 경고 — 반드시 먼저 읽을 것.**

이 문서는 **74셀 정식 FVP 성능 스윕 한 캠페인**의 방법입니다. 이 프로젝트의
다른 측정 캠페인에 그대로 적용되지 **않습니다**. 각 캠페인은 날짜도 하네스도
다르며, 어느 것이 이 절차를 공유하는지는 §8에 검증 상태로 명시했습니다.

**출처:** frozen evidence에서 재구성. 기억이 아니라 아래 파일들에서 직접 추출.

- `docs/paper/evidence/stage1-formal-20260825/stage1.py` — 실제 실행 하네스
- `docs/paper/evidence/vela-matrix-20260824/vela_matrix.csv` — 기록된 Vela 인자 전문
- `docs/paper/evidence/executability-20260825/FORMAL_PRESWEEP_ANCHOR.json` — 셀별 앵커 해시
- `docs/paper/evidence/stage1-formal-20260825/DETERMINISTIC_METRIC_VECTOR.md` — 결정론 계약

---

## 1. 실행 환경

| 항목 | 값 |
|---|---|
| 호스트 | 원격 x86_64, 컨테이너 내부 (`ssh gihwan` → `docker exec benchmark-runner`) |
| MLEK | `/opt/arm/ml-embedded-evaluation-kit` (`KIT`) |
| 작업 루트 | `/tmp/xq` (`ROOT`), 셀마다 `rm -rf` 후 재생성 |
| Vela | 5.0.0 |
| 크로스컴파일러 | `arm-none-eabi-gcc` |
| `SOURCE_DATE_EPOCH` | **1776763519** (고정) |
| 기대 빌드 스탬프 | `Apr 21 2026 @ 09:25:19` |
| Activation buffer (arena) | `0x00200000` (2 MiB) |
| 실행 타임아웃 | 3600 s |
| 디스크 여유 게이트 | 1 GiB (`FREE_GATE`) |

`SOURCE_DATE_EPOCH` 고정이 필수인 이유: 펌웨어가 `__DATE__`/`__TIME__`을 바이너리에
박아 넣어서, 고정하지 않으면 모든 빌드가 유일해지고 바이트 재현이 불가능해집니다.

## 2. 셀 하나를 도는 절차

```
① Vela 컴파일  →  ② cmake configure  →  ③ cmake build
      ↓
④ 재현 게이트 (5개 해시/설정 검사, 하나라도 실패하면 스테이지 전체 중단)
      ↓
⑤ FVP 실행 → UART 로그 파싱 → PMU 카운터 수집
```

### ① Vela

```sh
vela --accelerator-config <ACC_CFG> \
     --config /opt/arm/ml-embedded-evaluation-kit/scripts/vela/default_vela.ini \
     --system-config <SYS_CFG> \
     --memory-mode <MEM_MODE> \
     --optimise Performance \
     --output-dir <WS>/vela \
     /opt/arm/ml-embedded-evaluation-kit/resources_downloaded/<MODEL_PATH>
```

실제 기록된 예 (rnnoise / SSE-320 / U85-512):

```sh
vela --accelerator-config ethos-u85-512 \
     --config /opt/arm/ml-embedded-evaluation-kit/scripts/vela/default_vela.ini \
     --system-config Ethos_U85_SYS_DRAM_Mid_512 \
     --memory-mode Dedicated_Sram \
     --optimise Performance \
     --output-dir /tmp/vela_matrix/rnnoise_INT8__SSE-320__ethos-u85-512 \
     /opt/arm/ml-embedded-evaluation-kit/resources_downloaded/noise_reduction/rnnoise_INT8.tflite
```

`vela_core_clock`은 1,000,000,000.0 (1 GHz)로 기록됩니다.

### ② / ③ 빌드

```sh
cmake -B <WS>/build-a1 -S $KIT \
  -DCMAKE_TOOLCHAIN_FILE=$KIT/scripts/cmake/toolchains/bare-metal-gcc.cmake \
  -DTARGET_PLATFORM=<mps3|mps4> \
  -DTARGET_SUBSYSTEM=<sse-300|sse-310|sse-315|sse-320> \
  -DETHOS_U_NPU_ID=<U55|U65|U85> \
  -DETHOS_U_NPU_CONFIG_ID=<H|Y|Z><MAC> \
  -DETHOS_U_NPU_MEMORY_MODE=<MEM_MODE> \
  -DETHOS_U_NPU_ENABLED=ON \
  -DUSE_CASE_BUILD=inference_runner \
  -Dinference_runner_ACTIVATION_BUF_SZ=0x00200000 \
  -Dinference_runner_MODEL_PATH=<WS>/vela/<model>_vela.tflite

cmake --build <WS>/build-a1 -j $(nproc)
```

산출물: `<WS>/build-a1/bin/mlek_inference_runner.axf`

`ETHOS_U_NPU_CONFIG_ID` 접두어는 NPU별로 `u55→H`, `u65→Y`, `u85→Z` (예: `H256`, `Y512`, `Z2048`).

### ④ 재현 게이트 — 5개 전부 통과해야 실행

| 검사 | 내용 |
|---|---|
| `vela_sha_matches_anchor` | Vela 산출물 SHA-256이 앵커와 일치 |
| `cc_body_sha_matches_anchor` | 생성된 `*_vela.tflite.cc`의 **정규화된 본문** 해시 일치 |
| `axf_sha_matches_anchor` | 링크된 ELF SHA-256 일치 |
| `timing_adapter_on` | `CMakeCache.txt`에 `ETHOS_U_NPU_TIMING_ADAPTER_ENABLED:BOOL=ON` |
| `embedded_stamp_matches_epoch` | ELF에 박힌 `Build date:`가 기대 스탬프와 일치 |

생성 `.cc`는 **raw 해시가 아니라 canonical body 해시**로 비교합니다 — 생성기가 벽시계
주석을 넣기 때문에 raw는 재현 불가이고, 그 주석은 바이너리에 도달하지 않습니다.
`ccident.body_sha256()`이 정규화를 수행하며, 실패 시 `CanonicalizationError`로 중단.

**게이트 실패는 재시도 없이 스테이지 전체를 중단합니다.** top-up 없음, 재량 재시도 없음.

### ⑤ FVP 실행

```sh
<FVP_BINARY> -a <AXF> \
  -C <MAC_PARAM>=<MAC> \
  -C <BOARD>.visualisation.disable-visualisation=1 \
  -C <BOARD>.telnetterminal0.start_telnet=0 \
  -C <BOARD>.uart0.out_file=<UART_LOG> \
  -C <BOARD>.uart0.unbuffered_output=1
```

보드/파라미터 매핑:

| target_platform | BOARD | MAC_PARAM |
|---|---|---|
| `mps4` | `mps4_board` | `mps4_board.subsystem.ethosu.num_macs` |
| `mps3` (그 외) | `mps3_board` | `ethosu.num_macs` |

FVP 바이너리: `FVP_Corstone_SSE-300_Ethos-U55`, `FVP_Corstone_SSE-300_Ethos-U65`,
`FVP_Corstone_SSE-310`, `FVP_Corstone_SSE-310_Ethos-U65`, `FVP_Corstone_SSE-315`,
`FVP_Corstone_SSE-320`.

Fast Models 버전은 플랫폼마다 다릅니다 — 11.22.35 / 11.24.13 / 11.27.25 / 11.31.28.
이것이 절대 cross-generation 비교를 거부하는 근거 중 하나입니다.

**성공/실패 판정** (UART 로그 폴링):

- 성공: `Inference completed.` 출현 **그리고** `Total number of inferences: 1`
- `count != 1` → `FAILURE_COUNT_MISMATCH`
- 치명 문자열 발견 시 즉시 `FAILURE_FATAL_BEFORE_COMPLETION`:
  `Failed to resize buffer`, `tensor allocation failed`, `Failed to initialise model`,
  `Arm Ethos-U NPU initialisation failed`, `Failed to allocate tensors`

프로세스는 `start_new_session=True`로 띄워 pgid를 잡고, 종료 후 잔존 FVP를
`ps -eo pid=,comm=,args=`로 검사해 남아 있으면 하드 스톱입니다.

## 3. 설정 매트릭스 (전 19개 설정)

| platform | npu | MAC | system_config | memory_mode | TA |
|---|---|---|---|---|---|
| SSE-300 | u55 | 32/64/128/256 | `Ethos_U55_High_End_Embedded` | `Shared_Sram` | ON |
| SSE-300 | u65 | 256/512 | `Ethos_U65_High_End` | `Dedicated_Sram` | ON |
| SSE-310 | u55 | 32/64/128/256 | `Ethos_U55_High_End_Embedded` | `Shared_Sram` | **OFF** |
| SSE-310 | u65 | 256/512 | `Ethos_U65_High_End` | `Dedicated_Sram` | **OFF** |
| SSE-315 | u65 | 256/512 | `Ethos_U65_High_End` | `Dedicated_Sram` | **OFF** |
| SSE-320 | u85 | 128 | `Ethos_U85_SYS_DRAM_Low` | `Dedicated_Sram` | ON |
| SSE-320 | u85 | 256 | `Ethos_U85_SYS_DRAM_Low` | `Dedicated_Sram` | ON |
| SSE-320 | u85 | 512 | `Ethos_U85_SYS_DRAM_Mid_512` | `Dedicated_Sram` | ON |
| SSE-320 | u85 | 1024 | `Ethos_U85_SYS_DRAM_Mid_1024` | `Dedicated_Sram` | ON |
| SSE-320 | u85 | 2048 | `Ethos_U85_SYS_DRAM_High_2048` | `Dedicated_Sram` | ON |

**U85는 MAC마다 system_config가 바뀝니다.** 256→512 전이가 `SYS_DRAM_Low`→
`SYS_DRAM_Mid_512` 불연속을 함께 넘습니다 — 메커니즘 스터디가 dual binding으로
따로 통제한 지점입니다.

## 4. 워크로드 소스 경로

```
ad_medium_int8              resources_downloaded/ad/ad_medium_int8.tflite
kws_micronet_m              resources_downloaded/kws/kws_micronet_m.tflite
mobilenet_v2_1.0_224_INT8   resources_downloaded/img_class/mobilenet_v2_1.0_224_INT8.tflite
rnnoise_INT8                resources_downloaded/noise_reduction/rnnoise_INT8.tflite
vww4_128_128_INT8           resources_downloaded/vww/vww4_128_128_INT8.tflite
wav2letter_pruned_int8      resources_downloaded/asr/wav2letter_pruned_int8.tflite
yolo-fastest_192_face_v4    resources_downloaded/object_detection/yolo-fastest_192_face_v4.tflite
```

## 5. 반복과 결정론

- 셀당 warm-up 1회(버림) + **정식 3회** (M1, M2, M3) = 74 × 3 = **222 samples**
- 세 반복은 **정확히 같아야 합니다.** 평균·중앙값·재실행·다수결 없음
- 불일치 = `DETERMINISM_FAILURE` → Stage 2 중단, Stage 3 금지
- equality-bearing 필드 **19개** (`DETERMINISTIC_METRIC_VECTOR.md`에 사전 고정):

```
measurement.status / inference_count_line
measurement.npu_total_cycles / npu_active_cycles / npu_idle_cycles
measurement.axi0_rd_beats / axi0_wr_beats / axi1_rd_beats
artifact_identity.model_sha256 / vela_sha256 / generated_cc_body_sha256 / axf_sha256
config_identity.platform / npu / mac_config / fvp
config_identity.timing_adapter_cache / embedded_build_stamp / source_date_epoch
```

비교 대상 **아님** (구성상 변동): `wall_clock_s`, `owned_pgid`, `elapsed_s`,
`uart_tail`, 파일 경로/타임스탬프. `survivors_after_cleanup`은 동등성에서 제외되지만
**비어 있어야 하는 하드 스톱** 조건입니다.

qualification 값은 M1/M2/M3의 **구성원이 아니며**, 불일치하는 반복을 이기는 제3의
의견으로 쓸 수 없습니다.

## 6. 수집되는 수치

`canonical_cycles = npu_active_cycles + npu_idle_cycles` (74/74 셀에서 항등 성립).
AXI beat 3종(axi0 rd/wr, axi1 rd)도 함께 기록됩니다.

**측정 경계 주의:** 이 값은 NPU PMU 카운터이지만, 카운터가 언제 reset/enable/read
되는지는 stock MLEK 러너의 배치가 정하며 이 스윕에서 독립 검증되지 않았습니다.
정확한 명명은 `T_NPU`가 아니라 *PMU cycle-counter window over the driver's inference
call* 입니다. 보드 쪽 대응 개념과 계약은 `docs/paper/MEASUREMENT_SEMANTICS.md` 참조.

## 7. 스테이지 구성

| 스테이지 | 내용 | 증거 |
|---|---|---|
| pre-sweep qualification | 2026-08-24 | `evidence/pre-sweep-qualification-20260824/` |
| vela matrix | 전 셀 Vela 컴파일 + 해시 | `evidence/vela-matrix-20260824/` |
| executability | 133셀 감사, 6셀 실행불가 확정 | `evidence/executability-20260825/` |
| Stage 1 (M1) | 74셀 1회차 | `evidence/stage1-formal-20260825/` |
| Stage 2 (M2) | 2회차, M1==M2 검사 | `evidence/stage2-formal-20260825/` |
| Stage 3 (M3) | 3회차 | `evidence/stage3-formal-20260825/` |

각 스테이지는 `*_EVIDENCE_FROZEN.json` + `.sha256` + 원시 로그 tarball로 동결됩니다.

**세 스테이지가 같은 절차를 쓴다는 것은 검증했습니다:**

```
build()      1859d709ac02f7c5   ← stage1/2/3 바이트 동일
run_once()   FVP 호출부 동일; stage2/3 은 뒤에 결정론 비교 함수가 추가될 뿐
```

## 8. 이 문서가 **적용되지 않는** 캠페인 — 검증 상태

위 절차는 `stage1.py`에서 직접 읽은 것이고 Stage 2/3까지만 동일함이 확인됐습니다.
아래는 **각각 다른 날짜·다른 하네스**이며, 이 절차를 공유하는지 확인되지 않았습니다.

| 캠페인 | 날짜 | 규모 | 하네스 위치 | 대조 여부 |
|---|---|---|---|---|
| pre-sweep qualification | 2026-08-24 | — | `evidence/pre-sweep-qualification-20260824/` | **미확인** |
| FVP qualification | 2026-08-24 | — | `evidence/fvp-qualification-20260824/` | **미확인** |
| vela matrix | 2026-08-24 | 전 셀 | `evidence/vela-matrix-20260824/` | 기록된 인자 컬럼만 확인 |
| executability audit | 2026-08-25 | 133셀 | `evidence/executability-20260825/` | **미확인** |
| **X1 플랫폼 민감도** | **2026-09-04** | **92셀 / 276샘플** | **저장소에 없음** (아래) | **미확인** |
| U85 메커니즘 P0/P1 | 2026-08-21~26 | 18셀+ | post-compilation 계측 경로 | **다른 경로임이 확실** |
| 보드 RQ3 | 2026-08-25~26 | 21샘플 | MPS4 FPGA (FVP 아님) | **다른 경로임이 확실** |

### X1은 취득 스크립트가 이 저장소에 없습니다

`X1_EVIDENCE_FROZEN.md`가 증거 위치를 이렇게 기록합니다:

```
evidence  gihwan:/home/gihwan/mps4/X1_PLATFORM_SENSITIVITY_20260904T002134Z
          (634 files, EVIDENCE.sha256; per-cell UART logs, build identities,
           result vectors, acquisition script and plan)
```

acquisition script가 원격 호스트 디렉터리 안에만 있습니다. X1(09-04)은 정식
스윕(08-25)보다 **열흘 뒤**이고, 그 사이 하네스가 동일했다는 근거는 없습니다.
정황상 유사합니다 — 39/39 Vela artifact가 X0 해시를 재현했고 `CMakeCache.txt`에서
TA 상태를 건별 확인했다는 서술이 stage1 게이트와 같은 계열입니다. **그러나 정황이지
대조가 아닙니다.**

### 메커니즘·보드는 명백히 다른 경로

- **U85 메커니즘**: default regor 경로에 **post-compilation `NPU_OP_IRQ` 삽입**.
  stock 러너가 아니라 계측된 커맨드 스트림을 실행합니다. 매뉴스크립트 §3.4가
  세 컴파일/계측 경로를 분리하는 이유가 이것입니다.
- **보드 RQ3**: FVP가 아니라 MPS4 FPGA. `3 boots × 1 stock inference`이며, 원래
  등록된 `3 boots × 10 runs`는 stock 러너가 부팅당 1회만 추론하므로 실행 불가로
  판명되어 supersession 처리됐습니다.

### 이 갭을 닫으려면

X1 취득 스크립트를 원격에서 가져와 `stage1.py`와 대조해야 합니다. 해당
디렉터리는 X1 증거로 동결되어 있으므로 **읽기 전용 접근**이어야 합니다.
