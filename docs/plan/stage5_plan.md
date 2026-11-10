# Stage 5 설계 — 지원되는 메모리 배치·컴파일 조건 비교 (2026-11-11, 설계만, 보드 측정 없음)

Owner 지시(2026-11-11): 같은 워크로드에서 지원되는 메모리 배치와 컴파일 조건을 바꿨을 때 실행 비용·MAC 활동·전송량이
어떻게 달라지는지 확인한다.

이 문서는 설계 검토이며 계약이 아니다. 보드 측정은 Stage별 계약을 동결하고 owner 승인을 받은 뒤에만 한다.
모든 보드 수치는 **TA profile 1** 기준이다. 지원 여부가 확인되지 않은 모드는 가능하다고 가정하지 않는다.

## 1. 실제로 가능한 비교 — 근거 조사 결과

| 항목 | 현재 상태 (근거) | Stage 5에서의 지위 |
| --- | --- | --- |
| 메모리 모드 (Dedicated_Sram / Shared_Sram / Sram_Only) | **이미지 빌드 설정이다.** MLEK `source/hal/source/components/npu/CMakeLists.txt`가 `ETHOS_U_NPU_MEMORY_MODE`로 region→AXI 매핑과 cache arena를 정한다. 현재 이미지 `83398c7`은 Dedicated_Sram(QCONFIG=3, region 0·1 → AXI1/EXT, region 2–7 → AXI0/SRAM; `ethosu_config_select` 기계어로 확인). Shared_Sram은 region 1(arena)을 SRAM 포트로 보내고 arena가 SRAM에 있다고 가정하지만, 러너는 arena를 DDR(0x70000000 + 모델 길이)에 둔다. Sram_Only는 모델까지 SRAM에 둔다. | **Dedicated_Sram만 지원.** 다른 모드로 컴파일한 모델을 현재 이미지에서 실행하면 그 모드를 측정한 것이 아니므로 하지 않는다. 다른 모드는 이미지 재빌드와 러너의 arena·모델 배치 변경(펌웨어 변경), SRAM 용량 검증이 필요하다 → **승인 전 범위 밖** (`NOT_SUPPORTED_WITHOUT_IMAGE_CHANGE`). |
| NPU fast cache (region 2) | SRAM 0x31000000, 0x60000 = 384 KiB, 이미지에 고정(`ETHOS_U_NPU_CACHE_SIZE`; capabilities `fast_base`/`fast_size`). | Vela `--arena-cache-size` ≤ 384 KiB로 **사용량을 줄이는 것만** 가능. 384 KiB보다 크게 요구하는 컴파일은 이미지가 제공하지 못한다 → 쓰지 않음. 768 KiB 컴파일은 조사한 6개 워크로드에서 384 KiB와 같은 산출물이었다. |
| region→AXI 포트 재배치 | `ethosu_config_select`는 core driver의 weak hook이다. 러너는 이를 덮어쓰지 않으며, 기존 runner의 REGIONCFG knob은 driver runner에 없다. | 펌웨어 기능 추가가 필요하다 → **범위 밖** (제안만). |
| arena·IO 텐서 위치(DDR 안) | 러너가 arena를 모델 바로 뒤(16 B 올림)에 둔다(`drwl_arena_after`, Stage 4 기록 8/8로 확인). | 런타임 배치는 바꾸지 않는다. Vela의 텐서 할당(`--tensor-allocator`, `--cpu-tensor-alignment`)은 arena 안 오프셋을 바꾸지만, 정렬 효과가 Stage 4C의 쓰기 규칙과 얽히므로 **이번 최소안에서 제외**한다. |
| Vela 최적화 전략 | `--optimise Size`(arena cache 미사용) / `Performance`(기준). Vela 5.0.0 `--help`로 확인. | **지원** (컴파일 조건). |
| 시스템 설정 | 기준 `Ethos_U85_SYS_DRAM_Mid_1024`(TA profile 1의 SYS_DRAM_Mid와 짝). ini에 Low / Mid_512 / High_2048도 있다. | 보드 조건과 맞지 않는 비용 모델이므로 **제외**한다. |
| TA 상태 | 측정 조건(CLAUDE.md). | **변경하지 않음** (profile 1 고정). |

### 컴파일만 해 본 사전 조사 (2026-11-11, 계약 전 참고값; 계약에서 다시 생성·고정)

Vela 5.0.0, Dedicated_Sram, Mid_1024. 기준 = `--optimise Performance`, cache 384 KiB(ini 기본).

| 워크로드 | Size | cache 64 KiB | cache 0 | cache 768 KiB |
| --- | --- | --- | --- | --- |
| Stage 4 conv_base (1×1, Cin 16) | 같음 | 같음 | **다름** | 같음 |
| Stage 4C-2 conv Cin 64 | **다름** | 같음 | **다름** | 같음 |
| Stage 4 dw_base (3×3, 144) | 같음 | 같음 | **다름** | 같음 |
| Stage 4 fc_base | 같음 | 같음 | 같음 | 같음 |
| kws_micronet_m (SRAM 89 KiB) | **다름** | **다름** (59 KiB) | **다름** | 같음 |
| ad_medium_int8 (SRAM 244 KiB) | **다름** (301 KiB) | **다름** (60 KiB) | **다름** | 같음 |

"같음"은 Vela 출력 tflite의 sha256이 같다는 뜻이다. 산출물이 같은 변형은 보드에서 잴 이유가 없다(`COMPILE_IDENTICAL`).

## 2. 고정 조건

- FI101/MPS4, Ethos-U85 1024 MAC, **TA profile 1**, 공식 Driver Runner 이미지 `83398c7`(재빌드 없음)
- 이미지 메모리 모드 Dedicated_Sram, fast cache 384 KiB @ 0x31000000, arena DDR
- Vela 5.0.0, `ethos-u85-1024`, `Ethos_U85_SYS_DRAM_Mid_1024`, `--memory-mode Dedicated_Sram`
- 워크로드의 입력·가중치·양자화(Stage 4 연산 = 기존 생성 규칙과 seed, MLEK 모델 = MLEK 입력 + MLEK FI101 golden, amendment 2)
- WAIT_WFE, 캐시·초기화 절차, Pass A(Stage 1 set A)·Pass B(Stage 3 set B), 구성·Pass마다 warm-up 1 + 측정 4

## 3. 바꾸는 조건 — 한 번에 한 축

| 축 | 수준 | 성격 |
| --- | --- | --- |
| **P (배치 축)**: `--arena-cache-size` | 384 KiB(기준) / 64 KiB / 0 | 어떤 텐서·가중치 버퍼가 SRAM fast cache에 놓이는지를 컴파일러가 바꾼다 |
| **S (전략 축)**: `--optimise` | Performance(기준) / Size | 스케줄 전략 |

- P와 S를 같은 구성에서 함께 바꾸지 않는다(예: Size + 64 KiB는 없음). S는 P를 마친 뒤에 한다.
- 축을 바꾸면 컴파일 결과도 바뀔 수 있다. 그래서 각 변형을 산출물로 먼저 분류한다(측정 전, 고정).

| 분류 | 조건 (`stage4c1.kernels` 디코더 + Vela debug DB) | 보고 방식 |
| --- | --- | --- |
| `COMPILE_IDENTICAL` | Vela 출력 sha256이 기준과 같음 | 보드 측정 안 함 |
| `PLACEMENT_ONLY` | kernel 수·종류, OFM/IFM block, ublock, traversal, 채널 분할, kernel 순서가 같고 region·오프셋·fast cache 사용량·DMA만 다름 | 배치의 효과로 보고 |
| `PLACEMENT_AND_SCHEDULE` | 위 항목 중 하나라도 다름 | **구성 전체의 효과**로만 보고(배치 효과로 분리하지 않음) |

## 4. 최소 실험표 (제안; 계약 전 사전 조사 기준)

선정 규칙(고정):
- Stage 4·4C 워크로드 중 P 축에서 산출물이 달라지는 것을 쓴다.
- MLEK 모델은 업로드 시간이 짧고 P·S 모두에서 산출물이 달라지는 kws·ad를 쓴다. 기존 m7 DRWL, MLEK 입력과 golden이 있다.
- 나머지 MLEK 모델(mobilenet, vww4, yolo, rnnoise, wav2letter)은 **5-0 컴파일 조사에만** 넣고 보드에서 제외한다. 이유: 대상 실험이고 업로드 시간이 크다(wav2letter ≈ 33분). 계약에 명시한다.
- fc_base는 모든 변형에서 산출물이 같아 제외한다.

| 단계 | 워크로드 | 구성 | 구성 수 | RUN |
| --- | --- | --- | ---: | ---: |
| 5-0 | Stage 4 연산 + 7개 MLEK 모델 | 컴파일만: 기준 / cache 64 KiB / cache 0 / Size, 분류표 작성 | — | 0 |
| 5-1 (P 축) | kws, ad | 기준, cache 64 KiB, cache 0 | 6 | 60 |
| 5-1 (P 축) | dw_base, conv_base | 기준, cache 0 | 4 | 40 |
| 5-2 (S 축, 5-1 이후 별도 승인) | kws, ad, conv Cin 64 | Size (기준은 5-1 값과 같은 세션에서 재측정) | 3 + 3 | 60 |

5-1은 10 구성, 100 RUN, 4~10 부팅(구성마다 한 부팅)이다. 5-0의 실제 분류에 따라 `COMPILE_IDENTICAL` 구성은 표에서 빠진다.

## 5. 측정과 판정

| 항목 | 규칙 |
| --- | --- |
| 출력 | Stage 4 연산: CPU 기준 PASS_EXACT / PASS_TOLERANCE(≤ 1 LSB) / FAIL / INVALID. MLEK 모델: MLEK FI101 golden과 바이트 일치(amendment 2). 변형마다 기준 구성의 NPU 출력과 같은지 별도로 기록(컴파일이 수치를 바꿨는지) |
| RUN 유효성 | `record_v2.validity`, 출력 CRC가 모든 RUN에서 같음, 카운터 초기화(PMCR at arm)·IRQ 1회 |
| 실행 가능성 | fast cache·arena 요구량이 이미지 제공량 안인지 산출물로 확인. 런타임 실패는 `NOT_EXECUTABLE`(원인 기록, 우회하지 않음) |
| 기준 재현 | 각 워크로드 기준 구성이 기존 측정(Stage 4 / 4C-2 / m7)의 출력 해시와 결정적 카운터(MAC_ACTIVE, MAC_DPU_ACTIVE, 결정적 beat)를 재현해야 함. 아니면 그 워크로드의 비교를 해석하지 않고 차이를 먼저 보고 |
| 실행 비용 | NPU_ACTIVE, Stage 4 pair rule(tol = max(1 %, RUN 범위)), Pass A 주·Pass B 확인, 방향이 다르면 `UNRESOLVED` |
| 계산 활동 | MAC_ACTIVE, MAC_DPU_ACTIVE: 결정적이면 정확한 값 비교(같음/다름), 비결정적이면 pair rule |
| 전송량 | SRAM / EXT 읽기·쓰기 beat와 transaction: pair rule로 변화 여부, SRAM↔EXT 이동은 기술. 새 전송 모델은 만들지 않음 |
| 보조 | AO·WD 활동·정체, Vela 예상(필드·범위 명시, 오차율로 해석하지 않음) |
| 해석 한계 | `PLACEMENT_AND_SCHEDULE`은 구성 전체 효과로만 보고. NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않음. 원본 모델의 원인을 확정하지 않음 |

## 6. 중단 조건

- 5-0에서 모든 P 변형이 `COMPILE_IDENTICAL`인 워크로드는 보드에서 제외한다(구성을 대체하지 않음).
- 기준 재현 실패: 해당 워크로드 해석을 중단하고 보고한다.
- 런타임 실패(`NOT_EXECUTABLE`), 출력 FAIL/INVALID: 해당 구성을 비교에서 빼고 원시 데이터를 보존한다. 재실행·우회하지 않는다.
- 이미지·펌웨어 변경이 필요해지면 진행하지 않고 사유만 보고한다.
- 5-2는 5-1 결과 보고 후 별도 승인 없이는 시작하지 않는다.

## 7. 완료 후 종합 방법 (Stage 1·2A·3·4·5)

1. **지표별 근거 표:** 각 지표(NPU_ACTIVE, MAC_ACTIVE·DPU, AO·WD, SRAM/EXT 전송, 정체)마다 Stage별 결과를 출처, TA 상태, 실행 환경(legacy runner / driver runner), 판정 수준(`REVALIDATED`, `CONDITION_SPECIFIC`, `OBSERVED`, `POST_HOC_DESCRIPTIVE`, `UNRESOLVED`)과 함께 한 줄로 모은다.
2. **모델 현상 ↔ 통제 실험 연결:** Stage 1·3의 7개 모델 현상(rnnoise 낮은 MAC 활동, kws 낮은 효율, yolo·vww4 AO/정체, mobilenet 혼합, ad·w2l 높은 활동)마다 Stage 4·5에서 관측한 통제 결과를 `OBSERVED` / `CONSISTENT_WITH` / `NOT_SUPPORTED` / `UNRESOLVED`로 붙인다. Stage 2B H1/H2는 계속 무효이며 근거로 쓰지 않는다.
3. **설명된 것과 남은 것을 분리:**
   - 계산부(MAC/DPU, ublock·채널 올림, 스케줄 전환)
   - 전송(쓰기 beat 규칙 A, 입력 읽기)
   - 배치·전략(Stage 5)
   - 전체 실행시간(대부분 미분해)
4. **중요 미해결 현상만 추가 검증 후보로 올린다:** 각 후보마다 질문 하나, 필요한 최소 구성, 지원 여부(이미지·펌웨어 변경 필요 여부)를 붙인다. 자동 실행하지 않는다.

## 8. 승인이 필요한 결정

1. 5-1 범위(위 10 구성·100 RUN, kws·ad·dw_base·conv_base). 5-0 결과로 줄어들 수 있다.
2. MLEK 모델 5개를 보드에서 빼는 것(5-0 컴파일 조사에는 포함).
3. Shared_Sram·Sram_Only·region 포트 재배치를 Stage 5에서 다루지 않는 것. 다룬다면 이미지·펌웨어 변경 계획을 따로 세운다.
