# Arm Ethos-U NPU 구성 특성화 — 아키텍처부터 MPS4 FPGA 측정까지

발표용 내용 정리 (md 초안, 2026-09-09). 9부 구성. 슬라이드로 옮길 때의 장수 제안과
그래프 후보를 각 부 머리에 적었다.

표기 규칙
- **[벤더]** Arm 공식 문서 인용 — Ethos-U 시리즈 브리프(2024), Ethos-U85 Technical
  Overview (102684_0000_03, 2025-01), Corstone-320 Reference Package Technical
  Overview (109761_0100_02, 2025-07), arm.com 제품 페이지.
- **[측정]** 이 프로젝트의 frozen 증거 (`docs/paper/`, 브랜치
  `paper/sigmetrics2027-submission`).
- **[확인 필요]** 발표자가 직접 채우거나 확인해야 하는 항목.
- 결론 어휘는 논문 계약을 따른다: `ASSOCIATED_WITH` / `CONSISTENT_WITH` /
  `NOT_SEPARATED` / `NOT_EVALUABLE`. "faster/slower", "latency", "T_npu"는 쓰지 않는다.

---

## 1. Ethos-U 아키텍처 개관 — CPU · 메모리 · NPU (슬라이드 2~3장)

### 1.1 Ethos-U 제품군 한눈에 [벤더]

| | Ethos-U55 | Ethos-U65 | Ethos-U85 |
|---|---|---|---|
| 성능 (1 GHz) | 64 ~ 512 GOP/s | 512 GOP/s ~ 1 TOP/s | 256 GOP/s ~ 4 TOP/s |
| MACs (8×8) / cycle | 32, 64, 128, 256 | 256, 512 | 128, 256, 512, 1024, 2048 |
| 내부 SRAM | 18 ~ 50 KB | 55 ~ 104 KB | 29 ~ 267 KB |
| 시스템 인터페이스 | 64-bit AXI ×2 | 128-bit AXI ×2 | 128-bit AMBA 5 AXI 최대 6개 |
| 외부 메모리 | SRAM, Flash | SRAM, DRAM, Flash | SRAM, DRAM, Flash |
| 권장 호스트 | Cortex-M55/M7/M4/M33 | Cortex-M55/M7 | Cortex-M85/M55/M7, Cortex-A520/A510/A57/A55/A53/A35 |
| OS | bare-metal, RTOS | bare-metal, RTOS, Linux | bare-metal, RTOS, Linux |

- U85는 3세대. 벤더 주장: "U55/U65 대비 20% 에너지 효율 개선", "transformer 네이티브
  지원, TOSA 준수", 2048-MAC 구성이 128-MAC의 약 7배 면적 (xpu.pub 기사).
- 벤더가 제시하는 용도: 객체 분류/검출, 얼굴·포즈, 세그멘테이션, 초해상도, 음성
  인식·합성, 노이즈 캔슬링, NLP. 시장: 소비자, 의료, 드론, 로보틱스, AR/VR, STB/DTV,
  스마트 카메라·홈, 모바일.
- **주의**: 이 슬라이드의 TOPS는 벤더 이론치(1 GHz 기준 MAC 수 × 2)다. 이 프로젝트는
  절대 성능이나 TOPS를 측정하지 않았고, 세대 간 절대 사이클 비교를 금지한다.

### 1.2 CPU · 메모리 · NPU의 역할 분담 [벤더 + 측정]

```
[Cortex-M CPU]  TFLite Micro 런타임 + Ethos-U 드라이버 실행
      │         NPU가 못 도는 연산은 CMSIS-NN으로 CPU에서 (fallback)
      │  APB (레지스터) / IRQ (완료 통지)
      ▼
[Ethos-U NPU]   command stream을 순차 실행하는 기계
      │         8-bit / 16-bit 정수 양자화 네트워크 (TOSA base-inference, TFLite int)
      │         내부: Central Control · DMA · MAC unit · Weight Decoder · Activation Output
      ├─ AXI_SRAM ──▶ 온칩 SRAM   (activation/arena, 빠름)
      └─ AXI_EXT  ──▶ DRAM / Flash (weights, 느림·대역폭 제한)
```

- **CPU (Cortex-M85, Corstone-320)**: Armv8.1-M, Helium(MVE) 벡터 확장, FPU/DSP,
  캐시, TCM. 이 프로젝트에서 CPU는 추론을 "발행하고 완료를 관측"한다. 7개
  워크로드 모두 CPU fallback 연산 0개 [측정].
- **메모리**: NPU는 두 종류의 AXI 매니저를 가진다 — `AXI_SRAM`(온칩 SRAM 대상),
  `AXI_EXT`(DRAM/Flash 대상). Vela의 memory-mode가 상수(가중치)·arena(activation)·
  cache를 어느 포트에 둘지 정한다 (§2.4). 온칩 SRAM 용량이 arena를 못 담으면
  컴파일은 돼도 링크가 실패한다 (§7.4 executability).
- **NPU 데이터 타입**: INT8 activation/weight, 누산기 32/64-bit, AO unit이 8/16-bit
  OFM으로 스케일. 가중치는 압축 스트림(SWD 무손실, FWD 8/4/2-bit 테이블). 2:4
  sparsity 지원(사용 안 함). 우리 워크로드는 전부 INT8 TFLite [측정].

### 1.3 Corstone-320 (SSE-320) 구성 [벤더]

- Cortex-M85 (또는 M55) + 선택형 Ethos-U85/U65/U55 + CoreLink DMA-350(선택) +
  Mali-C55 ISP(확장 버스 예제 통합).
- 메모리: 휘발성 메모리 뱅크 4개(보통 SRAM), DRAM 2개에 대한 2-way striping 지원.
- 인터커넥트: CoreLink NIC-450 라이브러리(NIC-400 계층 인터커넥트, QoS-400,
  ADB-400 도메인 브리지), SIE-200/300 보안 IP, MPC/MSC/EAM.
- 보안: TrustZone for Armv8-M, LCM/KMU/SAM, CoreSight SoC-600M + SDC-600.
- 제공 형태: Fast Models FVP(`FVP_Corstone_SSE-320`) + MPS4 FPGA (FI101 이미지).
  **MPS4 FPGA는 U85 1024 MAC 고정** [측정: `CFG__NPU0_NUM_MACS 0x400`].

---

## 2. 상세 아키텍처 — 버스, NPU 내부, 명령 스트림 (슬라이드 3장)

### 2.1 U85의 AXI 포트는 MAC 구성에 따라 늘어난다 [벤더, U85 TO Table 2-2]

| MAC/cycle | SRAM 포트 (128-bit) | EXT 포트 (128-bit) |
|---:|---:|---:|
| 128 | 2 | 1 |
| 256 | 2 | 1 |
| 512 | 2 | 1 |
| 1024 | 2 | 2 |
| 2048 | 4 | 2 |

- 40-bit 주소. `CFGSRAMHASH0/1`, `CFGEXTHASH0` 핀으로 포트 간 striping(최소 64 B
  경계). 1024에서 EXT 포트가 2개로, 2048에서 SRAM 포트가 4개로 늘어난다.
- 우리가 본 U85 PMU 이벤트 목록도 이 구조를 그대로 반영: `SRAM0_*`~`SRAM3_*`,
  `EXT0_*`, `EXT1_*` 각 13종 + 집계 `SRAM_*`/`EXT_*` [측정: core-driver 25.11 헤더,
  170 이벤트].
- **U55/U65의 AXI0/AXI1**: 포트 2개. Vela system-config가 `axi0_port=Sram`,
  `axi1_port=OffChipFlash`(U55) / `Dram`(U65)로 모델링. MLEK 타이밍 어댑터는
  TA0=SRAM 경로, TA1=EXT 경로에 붙는다 [측정: `default_vela.ini`,
  `ta_config_*.cmake`].

### 2.2 NPU 내부 블록과 DMA 채널 [벤더, U85 TO §2.3~2.6]

```
Command stream ─▶ Central Control (CC) ─▶ 각 unit에 작업 분배
DMA controller  ─ command 채널 (cms 읽기, 보통 SRAM)
                ─ IFM 채널  (Input Buffer로, 블록마다 1회)
                ─ IFMS 채널 (elementwise 입력·MATMUL을 AO/WD로)
                ─ weight / fast-weight 채널 (압축 가중치 → WD, read buffer로 버스 지연 은닉)
                ─ OFM 채널  (Output Buffer → SRAM 또는 EXT, 출력 블록마다 1회)
Weight Decoder  ─ SWD 무손실 압축, 64 bit/cycle; 고 MAC 구성은 num_wd개 병렬
                ─ FWD 256 bit/cycle, conv 전용(depthwise 불가), 1×1 conv/FC에 유리
                ─ MATMUL용 tensor core (IFM 재포맷)
MAC unit        ─ IFM unit + Dot Product Units(DPU, 구성 가능한 개수) + Activation Input unit
                ─ conv / depthwise / vector product / pooling(MAX·MIN·AVG·REDUCE_SUM)
Activation Out  ─ Accumulator Buffer → per-channel bias·scale·shift → LUT → Chaining Buffer → Output Buffer
                ─ elementwise 연산, Resize, transpose/reverse 융합, 연산 chaining(메모리 왕복 없이)
```

- 피처맵 포맷 NHWC / NHCWB16 네이티브, NCHW는 내부 transpose.
- **왜 중요한가**: "출력 블록마다 OFM 채널 1회", "블록마다 IFM 1회" — 블록/ublock
  기하가 DMA 트랜잭션 수를 결정한다. §7의 mechanism study에서 `UBLOCK_CHANGED`가
  256→512 전환의 배경률 95%인 이유가 여기 있다.

### 2.3 명령 스트림 — NPU가 실제로 실행하는 것 [측정: `ethosu85_interface.h` 기계 추출]

- Vela 출력 tflite는 `ethos-u` 커스텀 op 하나이며 입력 텐서가
  `ethos_u_command_stream / read_only(가중치·scale) / scratch / scratch_fast / input`.
- 스트림은 32-bit 워드: `opcode[9:0]`, `control[15:14]`(cmd0/cmd1), `param[31:16]`.
  `NPU_SET_*`(레지스터 설정: base 주소, kernel, block 크기, pad…) 수십 개 뒤에
  `NPU_OP_CONV / DEPTHWISE / POOL / ELEMENTWISE …`(launch) 하나, 가중치 prefetch는
  `NPU_OP_DMA_START / DMA_WAIT`, 끝은 `NPU_OP_STOP`. 예: kws @512는 352 commands,
  launch 15개.
- 18개 후보 스트림 전부 `NPU_OP_BRANCH` 0개 — 후처리 삽입이 안전한 이유 (§4 부록).

### 2.4 Vela가 결정하는 메모리 배치와 시스템 가정 [측정: `default_vela.ini`]

| memory-mode | const(가중치) | arena(activation) | cache |
|---|---|---|---|
| Sram_Only | Axi0 | Axi0 | Axi0 |
| Shared_Sram | Axi1 | Axi0 | Axi0 |
| Dedicated_Sram | Axi1 | Axi1 | Axi0 (arena_cache 384 KB) |

| system-config (U85) | 사용 MAC | core_clock | SRAM ports_used / latency | DRAM clock_scale / ports / max R,W / burst / latency R,W |
|---|---|---|---|---|
| `SYS_DRAM_Low` | 128, 256 | 500 MHz | 2 / 16 | 0.469 / 1 / 24,12 / 128 / 500,250 |
| `SYS_DRAM_Mid_512` | 512 | 1 GHz | 2 / 32 | 0.75 / 1 / 64,32 / 128 / 500,250 |
| `SYS_DRAM_Mid_1024` | 1024 | 1 GHz | 2 / 32 | 0.75 / 2 / 64,32 / 128 / 500,250 |
| `SYS_DRAM_High_2048` | 2048 | 1 GHz | 4 / 32 | 0.75 / 2 / 64,32 / 128 / 500,250 |

- U55: `Ethos_U55_High_End_Embedded` (500 MHz, axi1=OffChipFlash clock_scale 0.125);
  U65: `Ethos_U65_High_End` (1 GHz, axi1=Dram 0.234).
- **경계 조건**: U85 사다리에서 256→512는 MAC만이 아니라 system-config(클럭
  가정·DRAM 파라미터)도 바뀌는 경계다. §7.5에서 dual binding으로 처리.

---

## 3. 제조사 시뮬레이터와 측정 지표·옵션 (슬라이드 3장)

### 3.1 무엇이 제공되나 [측정: 컨테이너에서 확인]

| 플랫폼 (FVP) | NPU | Fast Models | 비고 |
|---|---|---|---|
| `FVP_Corstone_SSE-300_Ethos-U55/U65` | U55, U65 | 11.22.35 | TA ON |
| `FVP_Corstone_SSE-310(_Ethos-U65)` | U55, U65 | 11.24.13 | MLEK이 TA 강제 OFF |
| `FVP_Corstone_SSE-315` (AVH) | U65 | 11.31.28 | TA OFF, `--fast` 모드 금지 |
| `FVP_Corstone_SSE-320` | U85 | 11.27.25 | TA ON, 보드와 같은 서브시스템 |
| MPS4 FPGA (FI101) | U85 @1024 고정 | — | 물리 검증 1 cell |

- 툴체인: Vela 5.0.0(regor 백엔드), MLEK `26.03-8-gb2c0bb2`, core-driver 25.11,
  arm-none-eabi-gcc 15.2.1, CMake 4.3.2.
- **Fast Models 버전이 플랫폼마다 다르다** → 세대 간 절대 사이클 비교 금지의 한
  근거. 같은 컨테이너의 AVH 번들에 4종 모두 11.31.28로 존재했으나 사용하지 않았다
  (§8 A1).

### 3.2 측정 지표 — 세 종류의 숫자 [측정: MEASUREMENT_SEMANTICS]

| 종류 | 출처 | 정체 | 대표 필드 |
|---|---|---|---|
| compiler estimate | Vela summary CSV | 성능 모델 예측 | `cycles_total / cycles_npu / cycles_sram_access / cycles_dram_access`, `inference_time`(= cycles ÷ 가정 클럭), `sram/dram_memory_used`, `total_npu_encoded_weights` |
| simulated observation | FVP + stock MLEK `inference_runner` | cycle-model 관측 | `NPU TOTAL`(48-bit CCNT), `NPU ACTIVE`, `NPU IDLE`(= TOTAL − ACTIVE, 파생값), 메모리 beat 카운터 |
| physical observation | MPS4 보드 | 소프트웨어 가시 관측 | `software_visible_completion_observation_cycles`(= NPU TOTAL) + 같은 U85 이벤트 |

- PMU 하드웨어: 48-bit cycle counter + 이벤트 카운터 8개. stock 프로파일러가 쓰는
  슬롯은 U55/U65 4개(`NPU_ACTIVE, AXI0_RD, AXI0_WR, AXI1_RD` — `AXI1_WR` 미수집),
  U85 5개(`NPU_ACTIVE, SRAM_RD, SRAM_WR, EXT_RD, EXT_WR`).
- U85 이벤트 공간 170종: WD 36, SRAM0~3/EXT0~1 각 13, 집계 SRAM/EXT 각 13, AO 7,
  AXI latency 7, MAC 6, ECC 6, NPU_ACTIVE/IDLE, CC_STALLED_ON_BLOCKDEP. 세대 간
  공유 이름 22개 중 18개는 ordinal이 다르다 → 번호 비교 금지. stall 계열은 TRM
  의미론 부재로 `SEMANTICS_UNVERIFIED`, 한 번도 수집하지 않음.
- 파생 지표(결과 전 동결): speedup, cumulative/incremental efficiency,
  saturation(incremental < 0.50), STRONG ≥0.75 / PARTIAL / WEAK, Spearman rho,
  normalized cost(= cost / geomean).

### 3.3 측정 옵션 — 실제로 무엇을 어디서 조정하나 [측정: FVP_METHOD_REVIEW]

**FVP 런타임 `-C` 파라미터** (SSE-320은 1,870개 노출, 우리는 5개만 설정)

```
mps4_board.subsystem.ethosu.num_macs=<128..2048>    (default 256)
mps4_board.visualisation.disable-visualisation=1
mps4_board.telnetterminal0.start_telnet=0
mps4_board.uart0.out_file=<path>
mps4_board.uart0.unbuffered_output=1
```

- `ethosu.*`는 3개뿐: `num_macs`, `diagnostics`(0~4), `extra_args`(Arm 지원 지시
  시에만). FVP 자체의 메모리 지연 파라미터(`ddr/sram.read_latency` 등)는 **전부
  기본값 0** — 메모리 타이밍은 FVP가 아니라 타이밍 어댑터가 만든다. CPU 캐시는
  존재하되 상태 모델링 OFF.

**타이밍 어댑터(TA)** — 펌웨어 빌드 타임, MLEK cmake가 `ETHOS_U_NPU_CONFIG_ID`(=MAC)로
자동 선택. FVP `-C`로는 조정 불가(재빌드 필요). 레지스터 필드: `MAXR/MAXW/MAXRW`(pending
수), `RLATENCY/WLATENCY`(cycles), `PULSE_ON/OFF`·`BWCAP`(대역폭 캡), `MODE`(동적 클럭,
재정렬, 주파수 스케일), `PERFCTRL/PERFCNT`, `HISTBIN/HISTCNT`.

| TA 파일 | SRAM: MAXR/W · lat R/W · BWCAP | EXT: MAXR/W · lat R/W · pulse on/off · BWCAP |
|---|---|---|
| `u55_high_end` | 8/8 · 32/32 · 4000 (64-bit words) | 2/0 · 64/0 · 320/80 · 50 |
| `u85_sys_dram_low` (128, 256) | 8/8 · 16/16 · 4000 (128-bit words) | 24/12 · 250/125 · 4000/1000 · 2344 |
| `u85_sys_dram_mid` (512, 1024) | 8/8 · 32/32 · 4000 (128-bit words) | 64/32 · 500/250 · 4000/1000 · 3750 |
| `u85_sys_dram_high` (2048) | mid와 바이트 동일 | |

- **U85 사다리에서 TA는 정확히 한 번, 256→512에서 바뀐다.** `TA=ON`이 전 MAC 동일
  조건을 뜻하지 않는다. SSE-310/315는 TA 소스 파일 자체가 컴파일되지 않는다
  (sse-300: 401 소스 중 TA 2개, sse-310: 399/0).

**Vela 옵션**: `--accelerator-config`(11개 이산 값), `--system-config`,
`--memory-mode`, `--optimise {Size,Performance}`, `--tensor-allocator`,
`--max-block-dependency`, `--arena-cache-size`, `--verbose-schedule /
--verbose-performance / --verbose-cycle-estimate / --verbose-allocation`.

---

## 4. 실험 환경 구성 — Vela 컴파일에서 실행까지 (슬라이드 2장 + 부록 2장)

### 4.1 파이프라인 [측정: `SWEEP_METHOD_AND_COMMANDS.md`]

```
TFLite INT8 (MLEK resources_downloaded)
  │ vela --accelerator-config ethos-u85-512 --system-config Ethos_U85_SYS_DRAM_Mid_512
  │      --memory-mode Dedicated_Sram --optimise Performance --config default_vela.ini
  ▼
*_vela.tflite  (ethos-u 커스텀 op + command stream + 가중치)  ── SHA-256 기록
  │ cmake -DTARGET_PLATFORM=mps4 -DTARGET_SUBSYSTEM=sse-320 -DETHOS_U_NPU_ID=U85
  │       -DETHOS_U_NPU_CONFIG_ID=Z512 -DETHOS_U_NPU_MEMORY_MODE=Dedicated_Sram
  │       -DUSE_CASE_BUILD=inference_runner -Dinference_runner_ACTIVATION_BUF_SZ=0x200000
  │       -Dinference_runner_MODEL_PATH=<vela.tflite>      SOURCE_DATE_EPOCH=1776763519
  ▼
mlek_inference_runner.axf  (모델은 .cc 배열로 내장, TA 설정 포함)  ── .cc body SHA, AXF SHA
  │ FVP_Corstone_SSE-320 -a <axf> -C ...num_macs=512 -C uart0.out_file=…
  ▼
UART 프로파일 블록  →  pmuparse.py (이벤트 이름 discovery)  →  cells.json
```

- 재현 게이트 5개(모델 SHA, Vela artifact SHA, .cc body SHA, AXF SHA, build
  stamp)가 전부 통과해야 실행. `__DATE__/__TIME__`이 펌웨어에 박히므로
  `SOURCE_DATE_EPOCH`(MLEK 커밋 시각)을 고정하지 않으면 AXF가 초 단위로 달라진다.
- 반복: warm-up 1회 폐기 후 fresh FVP 프로세스 3회, 전 필드 exact equality
  (`M1==M2==M3`, 74/74). 불일치는 하네스 결함으로 hard stop. 평균·median 금지.
- 보드: 같은 소스의 **FPGA 전용 빌드**(`-DFPGA_PLATFORM_SSE_320=ON`, Z1024). FVP
  바이너리는 FPGA에서 돌지 않는다 → "같은 바이너리를 양쪽에서" 표현 금지.

### 4.2 부록 A — layer-wise 측정을 위해 추가한 것 [측정: `docs/paper/mechanism/`]

**문제**: 이전 U55/U65 방법은 Vela의 Python code generator를 패치해 op마다
`NPU_OP_IRQ`를 넣었다. Vela 5.0.0의 U85(그리고 기본 경로 전체)는 C++ `regor`
백엔드라 그 삽입 지점을 우회한다 → `PROFILING_PATH_NOT_QUALIFIED`.

**해법: 컴파일 결과물 후처리** (`insert_irq.py`, 502줄)

1. 벤더 헤더 `ethosu85_interface.h`에서 opcode 표를 기계 추출(바이트 패턴 추론 금지).
2. tflite의 `ethos-u` 커스텀 op payload를 파싱: `COP1` FOURCC → driver action →
   `COMMAND_STREAM`(24-bit 길이, words) → cms.
3. 모든 non-DMA launch(`CONV/DEPTHWISE/POOL/ELEMENTWISE…`) 직후에
   `NPU_OP_IRQ(param = 1-based launch 순번)` 워드 삽입.
4. 정확히 네 곳만 바뀐다: cms 바이트, `COMMAND_STREAM` 길이 필드, cms 텐서 shape,
   flatbuffer 컨테이너(`force_align 16` 유지). 가중치·scratch·입력·양자화 파라미터
   무변경 — 독립 비교기가 "다른 버퍼 = cms 하나, 다른 텐서 = cms 하나"를 검증하고,
   IRQ 워드를 빼면 원본 명령 리스트와 동일함을 확인.
5. 드라이버 패치 v2: IRQ 핸들러에서 `STATUS.cmd_end_reached==0`이면 CCNT + 이벤트
   5슬롯 snapshot → reset → clear 후 세마포어 없이 리턴, `==1`이면 stock 완료 경로.
   결과는 추론 종료 후 `PLPROF,<idx>,<ccnt>,<active>,<sram_rd>,<sram_wr>,<ext_rd>,<ext_wr>`로
   printf. 빌드마다 적용→revert, 백업과 바이트 동일 확인.
6. 연산 identity: IRQ param = launch 순번 ↔ Vela `--verbose-schedule`의 op(depth
   slice 포함). kws: schedule op 13개 → launch 15개(op0×2, op8×2) → 레코드 14 + tail.
7. U85 interrupt-history mask로 작은 연산들이 한 서비스 창에 합쳐져도 창의 정확한
   멤버를 복원 → 연산 그룹 단위로 손실 없이 귀속(개별 연산은 `NOT_SEPARATED`).

### 4.3 부록 B — 개조가 연산 결과와 사이클에 영향을 주지 않는 근거 [측정: P0-C0/P0-C]

| 검사 | 결과 |
|---|---|
| 정적 | `NPU_OP_IRQ`는 U85 ISA의 정규 명령(opcode 1). 레지스터 상태·데이터 경로 불변. 스트림 내 주소는 다른 텐서를 가리키는 base pointer라 cms 길이 변화에 무관. branch 0개(18/18 스트림) |
| 왕복 | parse→serialize 무수정 round trip 18/18 바이트 동일 |
| 출력 | 출력 CRC32 `0xCEE9B7FE` — clean / IRQ 1개 / 전체 삽입 ×3 전부 동일 (kws @512) |
| 합 정합 | Σ(14 records) + tail = 114,420 vs clean 114,068 → **+352 cycles = 경계당 ≈23.5, 전체 +0.309%** |
| 드라이버만 패치 (IRQ 없음) | +2 cycles |
| 결정론 | fresh FVP 3회 PLPROF 벡터·CRC·TOTAL 바이트 동일 |
| 매칭 | schedule에서 예측한 launch 순서와 실측 IRQ 순서 정확히 일치 |
| 격리 | `clear_irq_history` 디바이스 패치는 불필요 — 초기 실패는 flatbuffer 정렬 결함이 원인 |

- 정확히 말하면 "영향 0"이 아니라 "일정한 경계 skid만 추가, 연산은 비트 동일".
  skid는 NPU 정지 → CPU가 카운터 6개 읽고 리셋·clear할 때까지의 시간이고 결정론적.
- IRQ 시점에 파이프라인이 완전히 멈추는지는 `NOT_SEPARATED`. 분석에는 영향 없음.
- U65에서 두 계측 방법(컴파일러 내부 vs 후처리)을 같은 프로그램에 적용한 bridge:
  스트림 바이트 동일, CYCLE/ACTIVE 세그먼트 exact, AXI beat만 ≤8 차이(무계측
  재컨테이너화 대조군에서도 같은 변동) → 전체 벡터 기준 `NOT_EQUIVALENT`, cycle
  도메인은 `ESTABLISHED`.

---

## 5. 측정 모델 후보 — MLEK, 그리고 MLPerf Tiny와의 관계 (슬라이드 1~2장)

### 5.1 채택한 워크로드 [측정]

| 모델 | 태스크 | Vela cycles_total @U85-256 | 구조 특성 |
|---|---|---:|---|
| rnnoise_INT8 | 노이즈 억제 | 37,836 | 작은 FC/GRU 계열, 저연산 elementwise 다수 |
| kws_micronet_m | 키워드 스포팅 | 217,565 | 작은 CNN (MicroNet) |
| ad_medium_int8 | 이상 탐지 | 452,112 | Conv2D 기반 |
| vww4_128_128_INT8 | Visual Wake Words | 477,109 | MobileNet 계열, depthwise 비중 큼 |
| yolo-fastest_192_face_v4 | 객체 탐지 | 1,300,857 | 다중 해상도 CNN |
| mobilenet_v2_1.0_224_INT8 | 이미지 분류 | 4,896,641 | Conv + depthwise 혼합, 큼 |
| wav2letter_pruned_int8 | 음성 인식 | 17,718,837 | 가중치·연산 최대 |
| (별도 트랙) dnn_s_quantized | 범용 DNN | 24,452 | CPU 연산 9.5% → 스케일링 분석 제외 |

- 동적 범위 **468×**. 7종 모두 NPU 배치 100%.

### 5.2 왜 MLEK 모델인가 [측정 + 판단]

1. 측정 계약이 "stock MLEK `inference_runner` 무수정"이다. MLEK `resources_downloaded`가
   제공하는 모델은 Vela 컴파일·러너 통합·양자화(INT8)가 이미 검증돼 있어 러너를
   건드리지 않고 19개 (platform, MAC) 빌드를 만들 수 있다.
2. TinyML 대표 태스크(KWS, VWW, AD, 이미지 분류, 객체 탐지, ASR, NR)를 한 러너
   계약 안에서 덮는다.
3. 스케일링·saturation 질문에 필요한 468× 동적 범위를 준다.

### 5.3 MLPerf Tiny는 어떻게 다루었나 [벤더/문헌 + 확인 필요]

- MLPerf Tiny(v1.x) 공식 모델: KWS **DS-CNN**(52.5 KB), VWW **MobileNetV1 96×96**
  (325 KB), 이미지 분류 **ResNet-8**(CIFAR-10, 96 KB), 이상 탐지 **FC-AutoEncoder**
  (ToyADMOS, 270 KB), v1.3부터 streaming wake word.
- 논문 원고의 위치: "우리 워크로드는 MLPerf Tiny 계보에서 가져온 것(MicroNet KWS
  등)이며, MLPerf Tiny는 시스템 수준 전체 추론 latency·accuracy·energy를 보고하는
  반면 이 연구는 한 구성 전환을 연산 단위로 분해한다."
- 즉 **MLPerf Tiny 스위트 자체를 실행한 기록은 frozen 증거에 없다.** MLEK의 KWS/VWW/
  AD/IC 모델은 같은 태스크의 Arm 최적화 변형(MicroNet, vww4, ad_medium, MobileNetV2)
  이다. **[확인 필요]** 발표에서 "MLPerf를 했다"고 말하려면 별도 실행 증거가
  필요하다. 없다면 "MLPerf Tiny 태스크 계보를 MLEK 구현으로 측정"으로 표현.
- MLPerf Tiny를 그대로 쓰지 않은 이유(판단): 공식 reference 모델은 TFLM 러너
  기준이고 Vela/Ethos-U 배치가 보장되지 않아 stock 러너 계약과 충돌하며, MLPerf
  Tiny의 산출물(latency/energy)은 이 프로젝트의 금지 어휘·비교 규칙과 맞지 않는다.

---

## 6. 측정 Sweep 설계 — 옵션 조합과 실험 가짓수 (슬라이드 2장, 매트릭스 표)

### 6.1 옵션 축 [측정: MAIN_EXPERIMENT_MATRIX, X0]

| 축 | 값 | 어떻게 정했나 |
|---|---|---|
| Corstone 서브시스템 | SSE-300, 310, 315, 320 | 컨테이너에 설치된 FVP 전부 |
| NPU × MAC | U55 {32,64,128,256} · U65 {256,512} · U85 {128,256,512,1024,2048} | Vela enum ∩ FVP init 수용 (양쪽 일치할 때만) |
| memory-mode | U55 Shared_Sram · U65/U85 Dedicated_Sram (MLEK 기본) | mechanism study에서 U85 3종 전부 (Sram_Only/Shared/Dedicated) |
| system-config | NPU/MAC별 MLEK 기본 (U85는 MAC마다 다름) | mechanism study에서 dual binding |
| 타이밍 어댑터 | 300/320 ON, 310/315 OFF | MLEK 강제, 변경 불가 |
| 워크로드 | 7 (+dnn_s 별도) | §5 |

### 6.2 실험 가짓수 [측정]

```
capability universe        19 configs × 7 workloads = 133 cells  (전부 Vela 컴파일 성공)
  ├ TA OFF (310/315)         56 cells → 실행성·진단 증거만, 성능 데이터 아님
  ├ 실행 불가                 6 cells (wav2letter × U55 × Shared_Sram × MAC 32/64/128, SRAM overflow)
  └ formal TA-ON 실행 가능    74 cells × 3 fresh runs = 222 samples   (M1==M2==M3 74/74)

platform sensitivity (X1)   92 cells (U55 4 MAC × 2 platform, U65 2 MAC × 3 platform) × 3 = 276 samples
board (RQ3)                 1 cell (U85 @1024) × 7 workloads × 3 fresh boots = 21 samples
mechanism (RQ4)             6 workloads × 3 artifacts (256@Low 공유, 512@Mid_512, 512@Low) = 18 cells,
                            clean + profiled 각 3회; memory-mode 3종 교차 profiling 12 cells
U65 bridge                  2 cells × 2 방법 × 3회
```

- Vela memory-mode 지원 감사: U55 `Dedicated_Sram`은 `NOT_SUPPORTED`(ConfigOptionError),
  U85 Flash system-config 없음 → `NOT_SUPPORTED`. 모든 memory-mode 조합은 **서로 다른
  artifact**를 만든다.

---

## 7. 결과 — 문제가 드러난 지표 모음 (슬라이드 5~6장, 그래프 위주)

그래프 후보 (전부 frozen CSV에서 생성된 SVG가 이미 있음):
`figures/fig1_mac_scaling.svg`(플랫폼별 cumulative efficiency),
`raw_data_report/figures/3_3_H_rnnoise_u85_ladder.svg`, `4_2_C_rnnoise_predicted_vs_observed.svg`,
`3_2_B_active_over_total.svg`, `3_2_A_traffic_share_u55/u65.svg`,
`fig3_board_relative_cost.svg`, `fig4_u85_group_delta.svg`, `fig5_u85_memory_robustness.svg`,
`fig2_platform_sensitivity.svg`. 새로 그릴 후보: Vela DRAM 비중 heatmap(§7.6), U85
TOTAL 사다리 7선.

### 7.1 MAC 스케일링은 워크로드 의존적이고 대체로 sub-linear (RQ2)

| incremental class (53 transitions, 21 ladders) | count |
|---|---:|
| STRONG (≥ 0.75) | 28 |
| PARTIAL (0.50–0.75) | 23 |
| WEAK_OR_SATURATED (< 0.50) | 2 |
| NOT_AVAILABLE | 3 |

saturation: 19/21 NONE_OBSERVED, **1건 관측 — SSE-320/U85/rnnoise @512**, 1건
NOT_AVAILABLE(wav2letter/U55 baseline 실행 불가). → 그래프: fig1.

### 7.2 컴파일러 추정 vs 시뮬레이션 — 모양은 맞추고 크기는 못 맞춘다

- saturation 분류 일치 19/20, normalized speedup 순위(rho=1.0) 19/20,
  per-step class 일치는 4/4 … 0/1로 불균일.
- **Vela는 rnnoise 256→512도 개선으로 예측** — 유일한 역전을 못 잡았다.
  → 그래프: 4_2_C.

### 7.3 순위는 이식되는 양, 절대값은 아니다 (RQ1, RQ3)

- 55개 구성 쌍 workload ranking: rho=1.0 31/55, min 0.9429, median 1.0.
- 보드(U85@1024, 21 samples): **rho = 1.0, inversion 0**, 도메인별 geomean 정규화
  상대 비용 모양 일치 (rnnoise 0.152/0.162 … wav2letter 12.75/12.14). 절대 비교·
  오차·비율은 계산하지 않음. → 그래프: fig3.
- 보드 raw triplet 예: rnnoise 55,151 / 55,149 / 54,672 → median 55,149.

### 7.4 컴파일 ≠ 배포 — executability

- 133 컴파일 성공 / 6 실행 불가, 전부 wav2letter × U55 × Shared_Sram × MAC 32/64/128,
  링커 SRAM overflow. 시스템 메모리 맵 한계(NPU 마이크로아키텍처 한계 아님).

### 7.5 유일한 비단조 경계: U85 256→512, rnnoise (RQ4)

| workload | @256 | @512 | @1024 |
|---|---:|---:|---:|
| **rnnoise_INT8** | **36,086** | **55,086** | 49,086 |
| kws_micronet_m | 199,068 | 114,068 | 90,068 |
| ad_medium_int8 | 377,068 | 235,068 | 141,068 |
| vww4_128_128_INT8 | 287,068 | 259,068 | 230,068 |
| yolo-fastest_192_face_v4 | 812,074 | 587,074 | 439,074 |
| mobilenet_v2 | 2,874,068 | 1,914,068 | 1,406,068 |
| wav2letter | 15,147,068 | 7,654,068 | 4,115,068 |

(dnn_s 별도 트랙도 역전: 22,068 → 29,068)

연산 그룹 분해 결과 (dual binding: rnnoise/dnn_s는 512@Low와 512@Mid_512 artifact가
**바이트 동일** → system-config 선택은 이 두 워크로드에서 변수가 아님):

- **분산되어 있다, 국소적이지 않다**: 10개 그룹이 각 +1,000 ~ +4,030 regress, 1개 그룹
  −1,000. 합 +19,060 vs 전체 모델 +19,000(60 cycles = 경계 잔차). 최대 기여 그룹도
  전체의 약 1/5. regress 그룹은 Add/Mul/Sub/Pack 클러스터, 작은 FC, Concat/Quantize —
  큰 행렬 연산이 아니라 저연산 연산들. → 그래프: fig4.
- **ublock 변화는 판별력이 없다**: `UBLOCK_CHANGED`가 regress 41/43, improve 63/65,
  unchanged 14/16 — 모든 방향에서 ~95% 배경률. `BLOCK_CONFIG_CHANGED`는 오히려
  improve(92%)에서 regress(63%)보다 흔함. "ublock이 원인"은 기각.
- 개선된 워크로드 안에도 국소 regress 있음: vww4 19 ops +31,015 vs −56,000,
  yolo 21 ops +40,985 vs −140,000.
- rnnoise 44 ops 중 개별 분리 가능 3개, 나머지는 14-group 공통 분할로 귀속.

### 7.6 메모리 구성에 대한 강건성 — 방향 불변, 크기 가변

| workload | Sram_Only | Shared_Sram | Dedicated_Sram |
|---|---:|---:|---:|
| rnnoise | **+3,000** | **+15,000** | **+19,000** |
| dnn_s | **+2,000** | **+6,000** | **+7,000** |
| vww4 | −83,000 | −32,000 | −28,000 |
| yolo | −288,000 | −244,000 | −225,000 |

- 어느 모드도 역전을 없애거나 만들지 않는다. rnnoise 12 profiled cells에서 29 그룹
  중 27이 방향 일치, 방향 flip 0. 반복 클러스터가 단조 증가 (+1k→+4k→+7k 등).
  → 그래프: fig5.
- vww4는 33 그룹 중 11이 메모리 구성에 방향 민감 — 33-op cascade 그룹이
  −35,000 → −2,120 → **+7,015**로 개선에서 regress로 넘어감.
- 모든 모드가 다른 artifact이므로 memory-system 효과와 컴파일러 프로그램 변화는
  `NOT_SEPARATED`. "bandwidth 실험"이 아니라 "configuration 실험".

Vela 추정의 DRAM access 비중(cycles_dram_access / cycles_total, U85) — compiler
estimate, 발표용 산출:

| workload | 128 | 256 | 512 | 1024 | 2048 |
|---|---:|---:|---:|---:|---:|
| rnnoise | 0.94 | 0.95 | 0.86 | 0.88 | 0.93 |
| kws | 0.44 | 0.51 | 0.80 | 0.82 | 0.85 |
| ad_medium | 0.49 | 0.49 | 0.76 | 0.83 | 0.94 |
| vww4 | 0.64 | 0.69 | 0.81 | 0.82 | 0.83 |
| yolo | 0.71 | 0.71 | 0.78 | 0.81 | 0.83 |
| mobilenet_v2 | 0.77 | 0.87 | 0.89 | 0.95 | 0.95 |
| wav2letter | 0.54 | 0.59 | 0.67 | 0.57 | 0.48 |

→ memory-system 계열과 `CONSISTENT_WITH`까지만. "memory-bound가 원인"은 금지.

### 7.7 측정 방법론에서 드러난 문제 (재사용 가능한 교훈)

1. **타이밍 어댑터가 측정 대상을 바꾼다**: 같은 Vela artifact(바이트 동일)가
   SSE-300/U55@32 112,059 vs SSE-310/U55@32 27,059 (~4×). TA·서브시스템·FM 버전이
   함께 바뀌므로 `NOT_SEPARATED`, 성능 비교가 아니라 경고.
2. **플랫폼 민감도(X1, 92 cells)**: ranking·direction·saturation·normalized 순서는
   전 쌍 보존. 불일치는 threshold 라벨 8건뿐, 전부 TA_ON PARTIAL → TA_OFF STRONG
   (0.64–0.75 vs 0.77–0.86, 0.75 컷 교차). TA_OFF끼리(310↔315)는 14/14 셀 사이클
   완전 동일 (FM 11.24.13 vs 11.31.28인데도). → 그래프: fig2.
3. **컴파일러 백엔드 변경이 계측 대상을 바꾼다**: regor 기본 경로 vs legacy core.
4. **빌드 타임스탬프**가 재현성을 깨고, **executability 분류**는 스윕 전에 해야
   한다 (399 예상 → 222 실제).
5. **ACTIVE ≥ 0.98은 busy이지 compute-bound가 아니다** — stall 카운터 없이는
   병목 지정 불가 (`NOT ESTABLISHED`).

---

## 8. 미흡한 점과 개선 여지 (슬라이드 2장)

### 8.1 측정에서 놓친 것 [측정: FVP_METHOD_REVIEW, LIMITATIONS]

| # | 항목 | 영향 | 조치 |
|---|---|---|---|
| F1 | Fast Models 버전이 플랫폼마다 다름 (11.22 / 11.24 / 11.27 / 11.31) — AVH 번들에 4종 모두 11.31.28이 있었는데 안 씀 | 플랫폼 비교에 시뮬레이터 버전 교락 | **A1**: 단일 버전 재측정 (펌웨어 수정 불필요, 관리자 판단 대기) |
| F2 | 파서가 `AXI0/1_*`만 인식 → U85 35셀 whole-model 메모리 카운터 유실, 원시 UART 미보존 | U85 formal에 SRAM/EXT beats 없음 | **A2**: R1 재측정 35셀 × 2회 진행 중 (12/35, 게이트 G1–G5 사전 등록) |
| F3 | U55/U65 stock 슬롯에 `AXI1_WR` 없음 → port1 read-only 비율 | U85와 port share 비교 불가 | A3: 러너 수정 필요 → 계약 충돌로 보류 |
| F4 | TA가 MAC에 따라 조용히 바뀜 (U85 256→512) | `TA=ON` ≠ 동일 조건 | 사실로 기록, X4에서 격리 가능 |
| F8 | counter overflow 경고를 파서가 수집 안 함 (IDLE 32-bit) | 발생 여부 미확인 | R1 UART로 사후 확인 |
| F9 | IDLE = TOTAL − ACTIVE 파생값 | `TOTAL==ACTIVE+IDLE`는 항등식, 독립 검증 아님 | 표현 수정 |

### 8.2 설계상 분리하지 못한 것 [측정: LIMITATIONS §9]

- TA_ON 상태에서 플랫폼을 바꾼 대조쌍이 없다 (CLASS A 결과의 TA_ON 이전은
  `NOT_EVALUABLE`).
- 같은 플랫폼의 U65↔U85 대조쌍이 없다 → U85 세대 비교는 구조 지표에만 의존.
- stall 계열 PMU를 한 번도 수집하지 않아 stall 기반 인과 귀속 `NOT_EVALUABLE`.
- memory-mode는 bandwidth 개입이 아니라 구성 개입 — 하드웨어 기하 vs 컴파일러
  스케줄링 인과 미분리.
- 보드는 1024 한 구성 → 물리 스케일링 검증 불가, FVP/FPGA 빌드가 다르므로 절대
  편차 미보고.
- 작은 연산은 IRQ 서비스 창에 합쳐져 개별 연산 원인 `NOT_EVALUABLE`(rnnoise 3/44).

### 8.3 개선 후보 (승인 대기, 우선순위 순)

1. **A1 단일 Fast Models 재측정** — 비용 최소, 결론 강도 최대.
2. **X4 TA memory-service sensitivity** — artifact 고정, SSE-320에서 latency/BWCAP만
   변주해 U85 256→512 역전이 `MEMORY_SERVICE_SENSITIVE`인지
   `ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE`인지.
3. **X2 같은 Corstone, 다른 NPU** (SSE-300 U55@256 vs U65@256, TA ON).
4. stall 이벤트 의미론 확보(U85 TRM) 후 슬롯 확장 — 러너 계약과의 충돌을 관리자
   승인으로 해소해야 함.
5. **X5 FM 버전 통일 + TA 캘리브레이션** — 절대 비교를 목표로 할 때만.

---

## 9. 현재 진행: MPS4 FPGA 지원 기반 측정 모듈 (슬라이드 1~2장)

### 9.1 지금까지 보드에서 확보된 것 [측정]

| 계층 | 상태 |
|---|---|
| 하드웨어 bring-up (SODIMM 접촉 불량 규명), GCC golden baseline | 완료 |
| 커스텀 러너 (프레임 프로토콜, 측정 경계, stale-output 차단, PMU seam) | 보드 인수 16/16 + 15/15, V13~V15로 관측 경계 특성화 완료 |
| stock MLEK FPGA 빌드 + MCC 배포/복원 하네스 (capture-before-reset, postflight 순서 가드) | QUALIFIED, RQ3 21 samples 수집 |
| 보드에서 U85 SRAM/EXT beats 수집 | 가능 (qualification에서 확인) |
| per-layer IRQ 계측 | **FVP에서 QUALIFIED, 보드 미실행** |

### 9.2 만들고 있는 모듈 [확인 필요 — 발표자가 현재 구현 범위를 채울 것]

목표: FVP에서 자격 검증된 per-layer 계측 경로를 MPS4 FPGA(Corstone-320 / U85@1024)로
옮겨, 같은 연산 그룹 분해를 실보드에서 얻는다.

```
insert_irq.py (동일)  →  FPGA 전용 MLEK 빌드 (FPGA_PLATFORM_SSE_320=ON, Z1024)
                       + 드라이버 v2 패치 (IRQ 핸들러 snapshot/reset, PLPROF printf)
                    →  SD 카드 배포 (boot.bin / bram.bin / ddr.bin, 해시 4/4)
                    →  listener 확인 → REBOOT → UART0 캡처 → PLPROF 파싱
                    →  postflight: REBOOT → USB_OFF → /dev/sdb* 부재 → 원본 복원
```

보드에서 새로 자격 검증해야 하는 것:
- IRQ 경계 skid: FVP의 23.5 cycles는 실 CPU에서 다르다 → clean vs profiled 전체
  모델 차이를 서술적으로 재측정 (임계값 신설 금지).
- 결정론: fresh boot 3회에서 PLPROF 벡터가 exact인지, 아니면 floor+excursion
  구조인지 (V15에서 본 관측 경계 특성이 per-layer에도 나타날 수 있음).
- power-lifecycle: 벤더 terminal release가 PMU bank를 지우는 문제는 중간 IRQ
  snapshot에는 해당 없지만 tail 레코드에는 해당 → 확인.
- 1024 MAC 고정이므로 256→512 경계 자체는 보드에서 재현 불가. 보드가 답할 수 있는
  질문은 "FVP에서 본 연산 그룹별 비용 분포가 1024에서 물리적으로도 같은 순서인가".

**[확인 필요]** 현재 구현 진척(빌드 완료 여부, 드라이버 패치 적용 여부, 첫 보드 실행
결과), 승인 상태(보드 접근은 단계별 승인), 그리고 이 모듈이 위 흐름과 다른 설계인지.

---

## 슬라이드 구성 제안 (총 22~24장)

| 부 | 장수 | 핵심 시각물 |
|---|---:|---|
| 표지 | 1 | |
| 1 아키텍처 개관 | 2 | 제품군 표, CPU-Mem-NPU 도식 |
| 2 상세 아키텍처 | 3 | AXI 포트 표, NPU 블록/DMA 채널 도식, 명령 스트림 예 |
| 3 시뮬레이터·지표·옵션 | 3 | FVP 표, 세 종류 숫자 표, TA 파라미터 표 |
| 4 실험 환경 (+부록 2) | 2+2 | 파이프라인 도식, 삽입 전후 스트림, 검증 표 |
| 5 모델 후보 | 1 | 워크로드 표 + MLPerf Tiny 대조 |
| 6 Sweep 설계 | 2 | 옵션 축 표, 가짓수 트리 |
| 7 결과 | 5 | fig1, 4_2_C, fig3, fig4, fig5 (+ DRAM 비중 heatmap) |
| 8 미흡·개선 | 2 | F/A 표, 개선 후보 |
| 9 FPGA 모듈 | 1 | 보드 파이프라인 도식 + 자격 항목 |

---

## 출처

- Arm, *Ethos-U Processor Series Product Brief* (2024): armkeil.blob.core.windows.net/developer/Files/pdf/arm-ethos-u-processor-series-brief-v2.pdf
- Arm, *Ethos-U85 NPU Technical Overview*, 102684_0000_03_en (2025-01): documentation-service.arm.com/static/67b5b9e6fdbd9d54ee93e7d0
- Arm, *Corstone-320 Reference Package Technical Overview*, 109761_0100_02_en (2025-07): documentation-service.arm.com/static/68da2fa4bd7cab51328bfa30
- Arm, Ethos-U85 제품 페이지: arm.com/products/silicon-ip-cpu/ethos/ethos-u85 · Corstone-320: arm.com/products/silicon-ip-subsystems/corstone-320
- xpu.pub, "Arm Ethos-U85 NPU Raises Edge AI Performance and Efficiency" (2024-04-25)
- MLPerf Tiny: arxiv.org/abs/2106.07597, mlcommons.org/2026/07/mlperf-tiny-v1-4-results/
- 프로젝트: `docs/paper/MANUSCRIPT.md`, `MEASUREMENT_SEMANTICS.md`, `MAIN_EXPERIMENT_MATRIX.md`,
  `PMU_EVENT_COMPATIBILITY.md`, `raw_data_report/FVP_METHOD_REVIEW.md`, `platform_sensitivity/X1_RESULTS.md`,
  `mechanism/*.md`, `context/SWEEP_METHOD_AND_COMMANDS.md`, `docs/FUTURE_EXPERIMENT_PLAN.md`;
  컨테이너 `default_vela.ini`, `scripts/cmake/timing_adapter/*.cmake`, `ethosu85_interface.h`.
