# Stage 6B-E2A — Vela 5.0.0 비용 모델 정적 감사 (보드 없음, `POSTHOC_DIAGNOSTIC`)

- 계약 `evidence/stage6b/stage6be2a/contract.md`(`0e3b1fc`, 추출 전 동결). 보드 값은 모두 기존 자료다. **TA profile 1**, 이미지 `70090f1`(A·B·C1), `65cf963`(C2).
- Vela facts: 원격 컨테이너에서 17개 대상 × 27개 설정(기준 + 26개 변형)을 2회 추출했고, 두 파일 sha256이 같다(`feb5efcd…`). 원본 7개 모델은 `4c2bb90d…`.
- 재현: `python3 host/analysis/stage6be2a.py run evidence/stage6b/stage6be2a/facts <out>`. 두 번 실행해 산출물 8개가 바이트 단위로 같았다.

## 판정: **`CONFIGURATION_DISCREPANCY_IDENTIFIED`** (원인은 미해결)

| 조건 | 결과 |
|---|---|
| 무결성 I1–I3 (Vela·cms·tflite digest = 측정 기록) | 17/17 |
| I5 (보드 재계산 = 6B-B·E1-R 기록), I6 (A 오차 = 6B-R) | 16/16, 7/7 |
| M1a 연산 total = max(npu, 메모리 ac) | 40/40 |
| M1b 그래프 total = Σ 연산 total | 13/13 |
| M1c Conv `mac_cycles` 소스식 재현 | 13/13 정확히 같음 (아래 정오표) |
| M2 (F1–F4 중 하나가 B 전부 ≤ 15 %, A 중앙값 ≤ 15 %) | **불성립** |
| 설정 감사 MISMATCH_VERIFIED | **C5 SRAM burst(read·write)** |

메커니즘 판정(1순위)은 M2가 성립하지 않아 해당하지 않는다. 설정 감사에서 검증 가능한 차이가 하나 나와 2순위 판정이 됐다. **이 차이가 실행시간 오차의 원인이라는 증거는 없다.** 방향도 반대다(아래 §4).

## 1. Vela 5.0.0 비용 계산 경로 (소스 확인)

설치된 `regor` .so는 PyPI 5.0.0 cp310 wheel과 바이트 동일하고, 287개 파일이 모두 같다(`.bak` 3개만 더 있음). 소스는 같은 릴리스의 sdist다(`facts/vela_provenance.json`).

- **연산 비용** (`network_performance.cpp` EstimateFullOpPerformance): total = max(npuCycles, 메모리별 accessCycles 최대). 6B-R에서 산출값으로 본 관계가 소스와 일치한다. 범위는 **스케줄된 연산 하나**다.
- **그래프** (PerformanceResult::operator+=): total = Σ 연산 total. 연산 사이의 겹침, 그래프 고정 비용, 명령 발행 고정 비용 항은 없다.
- **npuCycles** (`ethos_u85_performance.cpp` EstimateMacOpCycles): 블록당 MAC·AO·명령 발행 한도의 균형식에 가중치 DMA·LUT 전송을 더한다.
  - MAC 블록 = max(4·ublock_c, ⌊ifmBlk_c/8⌋·ublock 수_WH)·ublock 수_C·⌈Cin/ifmBlk_c⌉.
  - Vela는 **마지막 Cin 조각도 ifm block 깊이 전체로 센다.** H1-UC는 조각마다 max(32, ⌈x,16⌉)로 센다.
  - AO 블록 = max(⌈0.0625·OFM블록 원소⌉, 10·OFM블록_c·const 지연/256)이다. const가 Dram(지연 500)이면 bias 읽기 지연 항이 대부분을 차지한다.
- **메모리** (MeasureAccessCycles, ChannelBW): 채널별로 bytes ÷ BW_ch를 구한다.
  - BW_ch = min(Bandwidth, burst·min(RB_ch/(burst/16), outstanding·ports·0.8)/latency·0.8).
  - Bandwidth = clock_scale·16·ports_used이다(`regor.cpp`가 ini를 변환할 때 계산).
  - `channel_bw.csv`: Dram IFM read는 **6.55 B/cycle**이다. 이는 read buffer 256/8 = 32 burst × 128 B ÷ 지연 500 × 0.8로 정해지는 지연 한계다. 대역폭(24)이나 outstanding(64)이 한계가 아니다. Dram write는 20.97, Sram read·write는 20.48이다.
- **바이트 추정** (EstimateMemoryTransfer): burst 효율에 따라 바이트를 부풀린다(포맷·블록 폭으로 burst 길이를 추정).

## 2. 형상별 비교 (`vela_board_table.csv`)

A군(6B-B A2 그래프)과 B군(E1-R Conv 단독)의 비교 대상은 모두 `COMPARABLE`이다. UNSTABLE 3개는 `NOT_COMPARABLE`이다.

| 군 | Vela total 오차 (NPU−Vela)/Vela | Vela가 지배 항으로 본 것 |
|---|---|---|
| A (7) | +54 ~ +102 %, 중앙값 +90 % | dram_ac (6개는 total과 1 % 안) |
| B (6) | +11 ~ +27 %, 단 o176은 **−24 %** | dram_ac (6개 모두 total = dram_ac) |
| C1 s4c2_conv_cin48 | −8 % | dram_ac |

- **MAC_ACTIVE = H1-UC**: 13/13 정확히 같다.
- Vela Conv `mac_cycles` ÷ H1-UC(진단 지표)는 A에서 1.09–2.42, B에서 0.90–1.17이다.
- Vela compute ÷ MAC_ACTIVE도 같은 이유로 예측 오차가 아니다. 서로 다른 양의 비율이다.

## 3. 메커니즘 형식 (매개변수 없음; `form_errors`)

| 형식 | A |오차| 중앙값 | B 오차 범위 | M2 |
|---|---|---|---|
| F0 Vela 그대로 | 0.90 | +0.11 ~ +0.27, −0.24 | — |
| F1 npu + max(mem) | 0.18 | −0.46 ~ −0.17 | ✗ |
| F2 max(npu, sram+dram) | 0.35 | −0.37 ~ +0.01 | ✗ (o176 −0.37) |
| F3 npu + sram + dram | **0.07** | −0.53 ~ −0.29 | ✗ (B 과대예측) |
| F4 실측 바이트 대입 | 0.79 | +0.28 ~ +0.43 | ✗ |

- F3(겹침 없음)은 A군을 7 % 안팎으로 맞춘다. 이 형식은 계약 전에 A로 찾은 것이다.
- 그러나 미리 보지 않은 B군에서는 29–53 % **과대**예측했다.
- 한 가지 겹침 가정으로 두 군을 함께 설명하는 형식은 없다.

## 4. 메모리·TA·AXI 설정 감사 (`config_audit.csv`)

| 항목 | 결과 | 근거 |
|---|---|---|
| C1 지연 SRAM 32/32, EXT 500/250 | MATCH | TA 값 = Vela 값. 단위: S0-3 c2에서 TA root clock = CPU clock이고 MCLK_ON = NPU cycles |
| C2 outstanding | MATCH | SRAM: min(TA 8/8, AXI 12/16) = 8/8. EXT: TA maxr 0 = 무한(문서 S·D: 6-bit 필드라 MLEK의 64는 0)이므로 AXI 64, write 32 |
| C3 포트 수 | MATCH | CONFIG num_axi_sram/ext = 1/1, log2로 읽어 2/2 (Vela U85-1024 표와 같은 해석) |
| C4 대역폭 | **UNKNOWN** | TA cap: SRAM 4000 word/4000 cycles, EXT 3750/5000. word 8 B(헤더)인지 16 B(MLEK 문서·cmake)인지 문서가 다르다. TA가 버스 전체를 덮는지 포트별인지도 모른다. 가능한 범위: SRAM 8–32, EXT 6–24 B/cycle. Vela: 32 / 24 |
| C5 SRAM burst | **MISMATCH_VERIFIED** | 실측 평균 burst는 read 105–256 B, write 96–256 B(A∪B 13개 전부 > 70.4 B). Vela Sram_burst_length는 64 B |
| C5 EXT read burst | MATCH | 실측 33–107 B ≤ Vela 128 B |
| C5 AXI max_beats | 기록 | SRAM·EXT 모두 필드 2(enum B256) |
| C6 배치, C7 SRAM 크기 | MATCH | 393,216 B |
| C9 TA MODE bit 0 | 해당 없음 | 동적 클럭: FPGA 메모리가 에뮬레이션 deadline을 못 맞추면 NPU 클럭을 멈춘다. NPU 사이클은 에뮬레이션된 시간이다 |

**C5의 해석 한계:**
- NPU는 SRAM에 Vela 가정(64 B)보다 긴 burst를 쓴다.
- Vela 식에서 burst가 길면 SRAM 채널 대역폭이 커지므로, 이 차이는 Vela를 더 **낙관적으로** 만드는 방향이 아니다. 실측 오차(보드가 더 느림)를 설명하지 않는다.
- 민감도에서 Sram_burst_length를 128로 바꿔도 Vela total은 사실상 그대로였다(A 중앙값 0.91).
- 따라서 "검증 가능한 설정 차이"는 맞지만, 오차의 원인 후보로서는 근거가 없다.

## 5. 원인 가설 (`hypotheses.csv`)

| 가설 | 판정 | 내용 |
|---|---|---|
| H-E2-1a 바이트량 | NOT_DISTINGUISHABLE | 실측 바이트를 대입한 F4가 오히려 더 나쁘다(중앙값 0.58 vs 0.54). 보드 총 바이트 ≤ Vela는 12/13 |
| H-E2-1b 바이트당 서비스 비용 | NOT_DISTINGUISHABLE | 계약상 정적 자료로는 판정하지 않는다. Dram_read_latency 1000이면 A 중앙값 +7 %지만 B는 −37 ~ −62 % |
| H-E2-2 실행 중첩 | NOT_DISTINGUISHABLE | F3는 A에 맞고 B에 맞지 않는다. 반증 조건(F1–F3 모두 두 군에서 과대)도 성립하지 않는다(A에서는 과소 쪽) |
| H-E2-3 고정 비용 | NOT_DISTINGUISHABLE | A: Spearman(초과분, Vela total) = 0.96으로 CONTRADICTED(초과분이 크기와 함께 커짐). B: 0.03으로 판정 불가. 소스에 고정 비용 항은 없다 |
| H-E2-4 구성·배치 | NOT_DISTINGUISHABLE (양상 차이 있음) | 오차 중앙값 A +90 %, B +17 %. 래퍼·배치·그래프 크기가 함께 바뀌어 분리할 수 없다 |

상관으로 원인을 확정하지 않았다.

## 6. Vela 단독 민감도 (`sensitivity.csv`, `POSTHOC_SENSITIVITY`, 판정 입력 아님)

- 442건 중 ESTIMATOR_ONLY_COMPARABLE 439건, COMPILE_CHANGED 3건(Dram burst 64, Dram max_reads 32, Dram ports 1에서 각 1건)이다. COMPILE_CHANGED는 보드와 비교하지 않았다.
- **A·B 모두를 크게 움직인 변수는 Dram_read_latency와 Dram_burst_length 둘이다.**
  - read_latency 탄력도는 0.34–1.0이다. ×2이면 A 중앙값은 +7 %, B는 −37 ~ −62 %가 된다.
  - burst_length ×2이면 A 중앙값은 +62 %, B는 −62 ~ −23 %가 된다. 둘 다 Dram read 채널의 지연 한계식에 들어 있다.
- 일부 Dram 변수는 A만 움직였다(탄력도 최대 −0.30). B는 그대로였다.
  - clock_scale ×0.5: A +73 %
  - max_writes ×0.5: A +68 %
  - write_latency ×2: A +68 %
  - ports_used 1: A +61 %
- max_reads, clock_scale ×1.5는 거의 무반응이다. read 채널이 RB 한계에 걸려 있기 때문이다.
- A는 SRAM 변수(clock_scale, ports, max_reads, burst 32, read_latency 64)에도 반응한다. 탄력도는 최대 −0.52이다. B는 SRAM 변수에 반응하지 않는다(탄력도 0).
- **한 변수로 두 군을 동시에 맞추는 설정은 없다.** A를 올리는 변화가 B를 과대예측으로 만든다. 최적 설정은 찾지 않았다.

## 7. C군 참고 (`reference_models.csv`, `REFERENCE_NOT_EQUIVALENT`)

driver_m7(이미지 `65cf963`, TA profile 1)의 모델 전체 오차는 ad −2 %, kws −10 %, vww4 −11 %, yolo −23 %, w2l −28 %, mobilenet −39 %, rnnoise +53 %다.
- 모델에서는 Vela가 대체로 과대예측한다. A2 독립 그래프에서는 과소예측한다.
- 이미지·workload 형식이 달라 같은 조건의 차이로 해석하지 않는다.
- Vela 출력은 Stage 6-M 기록과 7/7 같다.

## 정오표 (데이터를 본 뒤 고친 코드, 규칙 변경 아님)

M1c 첫 실행에서 재현율이 13/27 = 0.48로 나왔다. 그 결과 M1c가 실패했다.
- 원인: 범위 검사가 연산 종류를 거르지 않았다. 그래서 `perf_debug_main`에 traversal DepthFirst로 기록된 **ADD 연산 14개**(mac_cycles 없음)가 섞였다.
- 계약 §3은 "1×1 DepthFirst Conv"로 정의한다. 코드를 계약대로 고치고(`perf` operator = Conv2D), 테스트 1개와 mutation 1개를 추가했다(33 tests, 73/73 KILLED).
- Conv만 보면 13/13이 정확히 같다.
- **판정은 수정 전후 같다.** M2가 성립하지 않으므로 어느 쪽이든 2순위 판정이다.

## 산출물

`vela_board_table.csv`, `m1_mac_cycles.csv`, `config_audit.csv`, `hypotheses.csv`, `sensitivity.csv`, `channel_bw.csv`, `reference_models.csv`, `stage6be2a_summary.json`, `e2b_contract_draft.md`(후속 보드 실험 초안, 실행 미승인).
