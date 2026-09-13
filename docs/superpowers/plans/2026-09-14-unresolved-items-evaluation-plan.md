# 미확인 항목 평가 계획 (2026-09-14)

**상태: 계획. 이 문서는 어떤 실행도 승인하지 않는다.** 새 FVP 실행이 필요한 단계는
매니저 GO가 있어야 시작한다 (`docs/FUTURE_EXPERIMENT_PLAN.md` §0, 기동 규약).
동결 evidence는 수정하지 않는다. 결과는 새 evidence 디렉터리에 쌓고 REPORT는
amendment로만 갱신한다.

출발점: `docs/paper/raw_data_report/REPORT.md` 부록 A(데이터 가용성)·부록 B(미해소),
§3.4 7개 가설 판정. 이 문서는 그 표의 미확인 항목마다 "무엇을 하면 판정으로 올라가는가"를
적는다.

## 0. 공통 규칙

1. **계약 먼저.** 각 단계는 실행 전에 가설·지표·닫힌 결과 집합·판정 규칙을 이 문서의
   해당 절에 확정하고 커밋한다. 이미 데이터가 존재하는 항목(1, 2, 3단계)은 계산 전에
   계약을 커밋하되 결과에는 `POST_HOC_DESCRIPTIVE`를 붙인다. 동결 당시 등록되지 않은
   지표이기 때문이다.
2. **한 번에 하나만 바꾼다.** MAC·산출물·TA·프로파일 중 변주하는 축을 절마다 하나로
   명시한다. 두 개가 같이 바뀌는 비교는 이 계획에 넣지 않는다.
3. **산출물 고정은 SHA-256으로 증명한다.** "같은 Vela 산출물"이라는 말은
   `vela_sha256`이 같다는 뜻이며, 재컴파일한 경우 해시가 같아야 같은 산출물이다.
4. **stock 러너 무변경.** `inference_runner`를 패치해 지표를 얻지 않는다. PMU 슬롯
   변경은 core-driver 패치(V15·U85 mechanism과 같은 경로)로만 한다. 이 경계는 4단계
   계약에서 다시 확인한다.
5. **게이트는 돌연변이 검사.** 새로 만드는 판정 코드(포화 판정, 민감도 판정)는 검사를
   무력화한 뒤 RED를 확인한다. 실패하지 못하는 검사는 만들지 않는다.
6. **결과 어휘는 닫힌 집합.** 각 절의 결과 집합 밖의 문장은 쓰지 않는다.

## 1. 실효 대역폭 산출 (요인 1 · 새 측정 없음)

**판정 대상**: "SRAM/EXT 포트가 포화했는가"를 기존 beat 수로 계산할 수 있는가.

**현재 막힌 이유**: beat당 바이트·클럭·TA 대역폭 상한을 확인하지 않아 계산 불가
(REPORT 부록 B `effective bandwidth: NOT_EVALUABLE`).

**이번에 확인한 입력** (2026-09-14, 서버 read-only, `scripts/cmake/timing_adapter/`).
Shared_Sram·Dedicated_Sram 분기(`else` 블록)의 값이며, Sram_Only일 때만 EXT가 SRAM 값을
상속한다.

| TA config | word 폭 | SRAM: MAXR/MAXW · R/W 지연 · PULSE on/off · BWCAP | EXT: MAXR/MAXW · R/W 지연 · PULSE on/off · BWCAP |
|---|---|---|---|
| u55_high_end | 64-bit (8 B) | 8/8 · 32/32 · 3999/1 · 4000 | 2/0 · 64/0 · 320/80 · 50 |
| u65_high_end | 128-bit (16 B) | 16/16 · 32/32 · 3999/1 · 4000 | 24/12 · 500/250 · 4000/1000 · 1172 |
| u85_sys_dram_low | 128-bit (16 B) | 8/8 · 16/16 · 3999/1 · 4000 | 24/12 · 250/125 · 4000/1000 · 2344 |
| u85_sys_dram_mid | 128-bit (16 B) | 8/8 · 32/32 · 3999/1 · 4000 | 64/32 · 500/250 · 4000/1000 · 3750 |
| u85_sys_dram_high | 128-bit (16 B) | 8/8 · 32/32 · 3999/1 · 4000 | 64/32 · 500/250 · 4000/1000 · 3750 |

TA 대역폭 상한 = `BWCAP × word 폭 / (PULSE_ON + PULSE_OFF)` bytes/cycle. 계산하면
Vela ini 주석의 레퍼런스 대역폭과 일치한다:

| | TA 상한 | 클럭 | 환산 | Vela ini 주석 |
|---|---|---|---|---|
| U55 EXT | 50×8/400 = 1.0 B/cyc | 500 MHz | 0.5 GB/s | "Flash (0.5 GB/s)" |
| U65 EXT | 1172×16/5000 = 3.75 B/cyc | 1 GHz | 3.75 GB/s | "DRAM (3.75 GB/s)" |
| U85 low EXT | 2344×16/5000 = 7.5 B/cyc | 500 MHz | 3.75 GB/s | "DRAMx1 (3.75 GB/s)" |
| U85 mid/high EXT | 3750×16/5000 = 12 B/cyc | 1 GHz | 12 GB/s | "DRAM (12 GB/s)" |
| SRAM (전부) | 4000×w/4000 = 1 word/cyc/포트 | | | "SRAM 4/16/32/64 GB/s" (포트 수 × 폭 × 클럭) |

즉 **TA 설정과 Vela ini는 같은 레퍼런스 시스템을 표현하며, 대역폭은 일치한다.** 앞서
"기대이지 확인은 아님"이라 했던 부분이 대역폭에 한해 확인됐다. 지연은 U85 low에서만
다르다: Vela ini `Dram_read_latency=500/write 250`, TA low `250/125`. 128·256 MAC 셀은
Vela가 가정한 것보다 2배 짧은 외부 지연에서 실행됐다. 나머지 프로파일은 지연도 일치한다.
이 표는 부록 A3에 나란히 붙일 내용이다.

**절차**

1. 위 표를 `tables/ta_parameters.csv`로 고정하고 SHA를 기록한다 (완료 항목이므로
   재확인만).
2. 계약 커밋: 지표 = `effective_bytes_per_cycle = Σ(beat × bytes_per_beat) / npu_total_cycles`,
   상한 = `ports × bytes_per_beat × (BWCAP / (PULSE_ON+PULSE_OFF))`. 결과 집합:
   `SATURATION_RULED_OUT`(≤ 상한의 50%) / `NEAR_LIMIT`(50–90%) / `AT_LIMIT`(>90%) /
   `NOT_EVALUABLE`(입력 누락). 판정은 포트별·셀별.
3. `canonical_cells.csv`(U55/U65, TA ON 39셀)와 `R1_MEMORY_COUNTERS.csv`(U85 35셀)에
   적용. U55/U65는 AXI1 write가 없으므로 AXI1 판정은 `LOWER_BOUND_ONLY`.
4. 게이트 검사: BWCAP을 0으로 바꾼 돌연변이에서 `NOT_EVALUABLE`이 나와야 한다.

**산출물**: `docs/paper/raw_data_report/amendments/A5_effective_bandwidth.md` + CSV.
**한계**: TA 모델의 대역폭 상한 대비 사용률이지 실제 메모리의 포화가 아니다. 결과가
`SATURATION_RULED_OUT`이면 요인 1의 대역폭 부분은 "TA 조건에서 배제"로 올라가고,
`AT_LIMIT`이면 4·5단계로 넘긴다.

## 2. 모델 구조 재수집: DWConv 수·연산 유형·shape·total MAC (요인 4·5 · 새 측정 없음)

**판정 대상**: Depthwise 비중과 확장 효율의 관계, feature map 크기와 그룹 사이클의 관계.

**현재 막힌 이유**: 동결 evidence에 연산 종류·shape가 없음 (`NOT_COLLECTED`).

**절차**

1. 계약 커밋. 지표: 모델별 `dwconv_op_count`, `dwconv_mac_share`(DWConv MAC / 전체 MAC),
   층별 `ofm_hwc`. 가설 4의 결과 집합: `DW_SHARE_ORDER_MATCHES`(DW 비중 순위 = 효율 등급
   역순, Spearman ≤ −0.7) / `NO_ORDER_RELATION` / `NOT_EVALUABLE`. 가설 5: U85 그룹별
   `ofm_size`와 256→512 Δcycle의 방향 일치율, 결과 집합 `SMALL_FM_CONCENTRATED`
   (증가 그룹의 ofm 중앙값이 감소 그룹의 1/2 이하) / `NOT_CONCENTRATED` / `NOT_EVALUABLE`.
2. 133개 구성의 `vela_args`(vela_matrix.csv)를 그대로 재실행하되
   `--verbose-performance --verbose-operators`를 추가한다. 출력 산출물의 SHA-256이
   동결 `vela_sha256`과 같아야 하며, 다르면 그 구성은 `ARTIFACT_MISMATCH`로 제외한다
   (verbose 옵션은 산출물을 바꾸지 않아야 하나 확인 전까지 가정하지 않는다).
3. per-layer CSV에서 연산 종류·MAC·shape를 파싱한다. 파서는 fixture 3개(DW 있는 모델,
   없는 모델, CPU fallback 모델 dnn_s)로 검사하고, 연산 종류 열을 비우는 돌연변이에서
   RED를 확인한다.
4. 가설 4는 TA ON 20개 계열, 가설 5는 U85 256→512 그룹 데이터(`U85_ATTRIBUTION_UNITS.csv`)와
   결합한다.

**승인**: 컴파일만이므로 GO 불필요. 컨테이너 CPU 시간 133회 × 수 초.
**산출물**: `amendments/A6_model_structure.md`, `tables/model_structure.csv`,
가설 4·5 판정 갱신(POST_HOC 표시).

## 3. 입력 텐서 생성 방식·seed 확인 (방법론 · 새 측정 없음)

**이번에 확인한 사실** (서버 read-only,
`source/app/use_case/inference_runner/src/UseCaseHandler.cc:37-61`): 입력은
`std::rand() & 0xFF`로 채운다. `DYNAMIC_IFM_BASE`가 정의되면 메모리에서 복사한다.
MLEK `source/` 전체에 `srand` 호출이 없다(grep 0건). 따라서 seed는 libc 기본값이며 매
부팅 같은 입력이다. `/work/selftest/build*` 캐시에는 `DYNAMIC_IFM_BASE`가 없으나,
캠페인 빌드 디렉터리는 아직 확인하지 않았다.

**절차**

1. 캠페인 빌드의 `CMakeCache.txt`(cells.json의 build 경로)에서 `DYNAMIC_IFM_BASE`
   미정의를 확인한다.
2. 결과 집합: `DETERMINISTIC_DEFAULT_SEED` / `SEEDED_FROM_X` / `DYNAMIC_IFM` /
   `NOT_ESTABLISHED`. 1이 확인되면 `DETERMINISTIC_DEFAULT_SEED`로 REPORT 부록 B 행을
   갱신한다.

M1=M2=M3 동등성(3회 반복 일치)이 이미 74/74였으므로 이 확인은 원인 설명이지 결과 변경이
아니다.

## 4. stall 카운터 수집 (요인 1·2 · 새 FVP 실행 · GO 필요)

**판정 대상**: NPU가 메모리를 기다린 사이클이 Total의 몇 %인가.

**현재 막힌 이유**: stock 프로파일러 슬롯이 고정(U55/U65 4개, U85 4개 사용 중 8개 가용)
이고 stall 이벤트가 없음. 이벤트 의미도 헤더에 없어 `SEMANTICS_UNVERIFIED`.

**설계 결정(계약 전에 확정할 것)**

- 슬롯 변경 위치: core-driver 초기화 패치 vs HAL `ethosu_profiler.c`. 후자는 MLEK
  앱 프레임워크라 "stock 러너 무변경" 경계에 걸린다. **core-driver 패치로 한다**
  (U85 mechanism의 드라이버 패치 v2와 같은 계층).
- U85는 8슬롯이므로 기존 5개(ACTIVE, SRAM R/W, EXT R/W)를 유지하고 3개를 추가할 수
  있다: `MAC_STALLED_BY_W`, `MAC_STALLED_BY_IB`, `AO_STALLED_BY_OB`. U55/U65는 4슬롯이라
  기존 beat 카운터를 빼야 하므로 **U85만** 한다.
- 이벤트 의미는 Arm Ethos-U85 TRM PMU 표에서 확인해 `U85_PMU_EVENT_AUTHORITY.csv`의
  `semantics_status`를 갱신한 뒤에만 해석한다. TRM 없이 해석하지 않는다.

**절차**

1. 계약 커밋. 지표: `stall_share = Σstall / npu_total_cycles`. 결과 집합:
   `MEMORY_WAIT_DOMINANT`(≥ 30%) / `MEMORY_WAIT_PRESENT`(5–30%) /
   `MEMORY_WAIT_NEGLIGIBLE`(< 5%) / `NOT_EVALUABLE`. 경계값은 실행 전에 고정한다.
2. 대상: U85 RNNoise·KWS·Wav2Letter × MAC 256·512 (역전 구간) = 6셀 × 3회. 산출물은
   동결 `vela_sha256`과 동일해야 한다.
3. 드라이버 패치는 stock 결과(ACTIVE·beat 5종)를 그대로 재현해야 한다. 기존 R1 값과
   비교해 일치하지 않으면 패치 결함으로 보고 중단한다.
4. 슬롯이 비어 있는 상태로 실행하는 돌연변이에서 파서가 `NOT_EVALUABLE`을 내는지 확인.

**승인**: 매니저 GO. FVP만 사용, 보드 불필요.
**산출물**: `evidence/u85-stall-<date>/`, 가설 1·2 판정 갱신.

## 5. TA 메모리 서비스 민감도 (요인 2 · Stage X4 · 새 FVP 실행 · GO 필요)

**판정 대상**: 외부 메모리 지연이 사이클을 움직이는가. 특히 U85 RNNoise 256→512 역전이
TA 조건에 따라 달라지는가.

**변주 축 하나**: TA `EXT_RLATENCY`(및 `EXT_WLATENCY`)만. Vela 산출물·MAC·SRAM TA는 고정.
TA는 펌웨어가 부팅 시 레지스터에 쓰므로 펌웨어 재빌드가 필요하지만 Vela 산출물은
그대로다(SHA로 증명).

**절차**

1. 계약 커밋. 수준: EXT 지연 {16(기본), 64, 250, 500, 1000}. 지표: 셀별 Total cycles,
   256→512 방향. 결과 집합 (FUTURE_EXPERIMENT_PLAN X4 그대로):
   `MEMORY_SERVICE_SENSITIVE`(어느 수준에서든 방향이 바뀌거나 Total이 기본 대비 ±10% 이상)
   / `ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE` / `NOT_EVALUABLE`.
2. 대상: U85 RNNoise·Wav2Letter(외부 경로 비중 최고) × MAC 256·512 × 5수준 × 3회 = 60회.
3. 대역폭 축은 별도 계약(`EXT_BWCAP` 변주)으로 두 번째 캠페인에서 한다. 같은 캠페인에
   섞지 않는다.
4. 게이트: 지연 0과 기본을 같은 값으로 돌리는 돌연변이에서 판정기가 `NOT_EVALUABLE`
   또는 RED를 내야 한다.

**승인**: 매니저 GO. Stage X4는 계획서에서 "optional"이므로 GO 요청 시 4단계 결과를
근거로 필요성을 설명한다. 4단계에서 `MEMORY_WAIT_NEGLIGIBLE`이 나오면 5단계는
우선순위를 낮춘다.

## 6. 분리되지 않은 요인 3·6·7 — 계획하지 않는 이유

| 요인 | 이유 | 대신 하는 것 |
|---|---|---|
| 3 가중치 저장 위치 | memory mode를 바꾸면 산출물이 바뀌므로 "같은 프로그램, 다른 위치"가 원리적으로 불가능 | 서술을 "저장 위치 = 다른 컴파일"로 고정. 18장 3모드 비교로 충분 |
| 6 연산 외 고정 비용 | 연산 크기를 독립 변주하려면 합성 모델이 필요 | 2단계의 per-op MAC과 그룹 Δcycle로 "MAC 수 대비 사이클 하한" 산점도만 POST_HOC로 그린다 |
| 7 Ublock 형상 | Vela에 블록 구성 고정 옵션이 있는지 미확인 | `vela --help`와 regor 옵션에서 `block_config` 강제 여부를 먼저 확인. 있으면 별도 계약 |

## 7. 계획하지 않는 항목

- **U65 AXI1 write**: 4슬롯 한계. 부록 A4의 U85 추정으로 대체하고 미확인으로 남긴다.
- **Vela 절대 정확도**: `REFUSED_ABSOLUTE`는 설계 결정이다. 작업이 아니다.
- **세대 간 절대 비교 (X5)**: 논문이 그 층을 열기로 하기 전에는 하지 않는다.
- **보드 대응 셀 추가**: 보드 접근은 단계별 승인이며 V15 보드 작업은 미승인 상태.

## 8. 순서와 게이트

```
1 실효 대역폭 (문서·계산)  ─┐
2 모델 구조 재수집 (컴파일)  ├─ GO 불필요, 병렬 가능, 전부 POST_HOC 표시
3 입력 seed 확인 (읽기)     ─┘
        │  1이 AT_LIMIT 이거나 2가 NO_ORDER_RELATION이면 4의 필요성 근거가 된다
        ▼
4 stall 카운터 (U85, 드라이버 패치, FVP)  ── GO 요청 #1
        │  MEMORY_WAIT_NEGLIGIBLE이면 5는 보류
        ▼
5 TA 지연 변주 (U85, 펌웨어 재빌드, FVP)  ── GO 요청 #2
```

각 단계 종료 시 보고 형식:

```
검증 수준: [구문 | 단위 | 통합 | E2E]
실제 실행한 것:
실행하지 않은 것:
결과 (닫힌 집합의 값):
```

## 9. 진행 기록

**2026-09-14 — 1·2·3단계 완료 (GO 불필요 단계). 4·5단계는 GO 대기.**

| 단계 | 계약 커밋 | 결과 | 산출물 |
|---|---|---|---|
| 1 실효 대역폭 | `4631acc` | U55 RNNoise EXT 4/4 `AT_LIMIT` (전송 시간 ≈ 측정 사이클), U85 RNNoise EXT `RULED_OUT`, U65 EXT `LOWER_BOUND_ONLY` 14/14, `NOT_EVALUABLE` 0 | `amendments/A5_effective_bandwidth.md`, `.csv`, `ta_parameters.csv` |
| 2 모델 구조 | `50c61e3` | 133/133 산출물 SHA 동일. H4 `NO_ORDER_RELATION` (rho −0.075, n=20). H5 `SMALL_FM_CONCENTRATED` (REGRESS OFM 중앙값 8,064 vs IMPROVE 18,432) | `amendments/A6_model_structure.md`, `a6_*.csv`, `vela_verbose/` |
| 3 입력 seed | (계획서 §3) | `DETERMINISTIC_DEFAULT_SEED` — `std::rand` 경로, `srand` 없음, UART 71개에 DYNAMIC_IFM 줄 없음 | `amendments/A7_input_tensor_seed.md` |

**2026-09-14 — 5단계(X4) 완료.** 캠페인 A–E 111회, 게이트 전부 통과, `amendments/A8_x4_timing_adapter_sweep.md`.
핵심: 같은 절대 EXT 지연에서 RNNoise 512 산출물이 256 산출물보다 항상 적은 사이클(0/250/500/1000);
동결 +19,000 역전은 low→mid TA 프로파일 변경과 함께 나타나고 512 산출물을 지연 250으로 되돌리면
사라짐. 전체 프로파일 교차(C)는 지연만 바꾼 값과 동일. 1024→2048 역전은 지연을 바꿔도 유지(D).
U55 RNNoise: cap 완화 −27% 후 지연이 지배(B·E), A5 사전 예측 NOT_MET → 전송-시간 모델 철회.

계약과 다르게 한 것: 1단계 결과 집합에 `LOWER_BOUND_ONLY`를 계산 전에 추가했다(U65 EXT).
2단계 H4의 "효율 등급"을 "계열의 인접 전이 효율 평균"으로 계산 전에 구체화했다.

4단계 GO 요청 근거: 1단계에서 U55 RNNoise가 Flash 대역폭 상한에 있었으므로 stall
카운터는 U55에서 가장 유익하나 U55는 4슬롯이라 beat 카운터를 빼야 한다. 계약 시
"U85만"을 "U85 8슬롯 + U55는 beat 대신 stall 슬롯으로 별도 실행"으로 넓힐지 결정 필요.
5단계 GO 요청 근거: U55 RNNoise의 Flash 대역폭 의존은 `EXT_BWCAP`만 바꾼 1건 실험으로
직접 검증된다 (계획 §5의 두 번째 캠페인을 첫 번째로 당길 것을 제안).

**2026-09-14 — GO 기록.** 유저(매니저 역할)가 "현재 단계 기록해 놓고 나머지 단계 전부
진행"으로 4·5단계 실행을 승인했다. 승인 사실만 기록한다. 실행 순서는 §9의 제안대로
5단계(TA 변주, 패치 없음)를 먼저, 4단계(드라이버 패치 + stall 카운터)를 다음에 한다.
두 단계 모두 실행 전에 §10·§11의 구체 계약을 커밋한다.

## 10. 5단계 구체 계약 — TA 메모리 서비스 변주 (X4)

**실행 전 커밋. 값 계산 전 확정.**

**변주 축 하나.** Vela 산출물·MAC·SRAM TA·플랫폼·펌웨어 소스는 고정. 바꾸는 것은 MLEK
cmake 캐시 변수 `EXT_RLATENCY`/`EXT_WLATENCY`(캠페인 A) 또는 `EXT_BWCAP`(캠페인 B)뿐이다.
`ta_config_*.cmake`의 `set(… CACHE STRING)`은 명령행 `-D`로 미리 채워진 캐시를 덮지 않으므로
`-DEXT_RLATENCY=<v>`가 유효하다. 각 빌드에서 생성된 `timing_adapter_settings.h`의 값을
읽어 기록하고, 값이 요청과 다르면 그 arm은 `NOT_EVALUABLE`이다.

**캠페인 A — U85 EXT 지연.** 셀 4개: RNNoise·Wav2Letter × 256·512 MAC (SSE-320,
Dedicated_Sram, 동결 산출물). 수준: 읽기 지연 L ∈ {0, ½·base, base, 2·base, 4·base},
쓰기 지연 = L/2 (기본값 비율 2:1 유지). base = 250 (SYS_DRAM_Low, 256 MAC) / 500 (Mid, 512 MAC).
반복 3회. 총 60회 실행, 20 빌드.

**캠페인 B — U55 EXT 대역폭 상한.** 셀 1개: RNNoise 256 MAC (SSE-300, Shared_Sram).
`EXT_BWCAP` ∈ {50 (base), 25, 100, 200, 0 (무제한)}. 반복 3회. 15회 실행, 5 빌드.
**사전 예측 (A5에서):** Flash 대역폭에 묶여 있다면 BWCAP 25에서 Total ≥ 1.8×base,
BWCAP 100에서 ≤ 0.6×base. 어긋나면 A5의 해석을 철회한다.

**게이트 (arm마다):**
- G1 Vela 산출물 SHA = 동결 `formal_vela_sha256`. 생성 `.cc` body SHA = 앵커.
- G2 base arm의 Total·Active·beat 전부가 동결값(canonical / R1)과 정확히 같다. 아니면
  캠페인 전체 `NOT_EVALUABLE` (하니스가 캠페인을 재현하지 못한 것).
- G3 3회 반복이 벡터 단위로 완전 동일. 아니면 그 arm `NOT_EVALUABLE`.
- G4 UART 원문 보존 (D4 교훈). 파서 결과는 UART에서 재생성 가능해야 한다.

**결과 집합 (셀 단위):**
- 캠페인 A: `MEMORY_SERVICE_SENSITIVE` — 어느 수준에서든 Total이 base 대비 ±10% 이상
  움직이거나, 256→512 방향(Δ 부호)이 base와 달라짐 / `ROBUST_TO_TESTED_MEMORY_SERVICE_RANGE`
  / `NOT_EVALUABLE`.
- 캠페인 B: `BANDWIDTH_SENSITIVE` — 어느 수준에서든 ±10% 이상 / `BANDWIDTH_INSENSITIVE` /
  `NOT_EVALUABLE`. 사전 예측 적중 여부는 별도 열 `A5_PREDICTION`: `MET` / `NOT_MET`.

**해석 경계:** 민감하다는 것은 "TA 조건이 사이클을 바꾼다"이지 원인 귀속이 아니다. 둔감하다는
것은 "시험한 범위에서"다. 하드웨어 기하나 스케줄러 인과는 주장하지 않는다 (X4 원문).

**하니스:** `docs/paper/raw_data_report/amendments/x4/x4_ta_sweep.py` (stage1의 build·run을
재사용, cmake 명령에 -D만 추가). 산출: `/tmp/x4/results.jsonl`, `/tmp/x4/uart/*.txt` →
리포 `amendments/x4/`.

### 10b. 매니저 검토(2026-09-14, manager_log.md 첫 회신) 후 추가한 캠페인 — 실행 전 커밋

매니저 지적: (i) 같은 지연 설정 ≠ 같은 메모리 조건 — 지연 외 TA 파라미터(요청 동시성, BWCAP,
SRAM 지연)도 low/mid에서 다르므로 **공통 TA 프로파일 전체**를 두 MAC에 적용한 비교가 필요.
(ii) 두 번째 역전(1024→2048)은 별도. (iii) U55 BWCAP 변주는 "완화했을 때 개선되는가"가 핵심이며
대역폭·지연 공동 제약을 가르려면 2×2가 필요. 이에 따라 X4 하니스에 세 캠페인을 추가한다.
산출물은 전부 동결 그대로(SHA 게이트 동일).

**캠페인 C — 전체 TA 프로파일 교차.** RNNoise 256 산출물을 **mid 프로파일 전체**(SRAM 지연 32,
EXT MAXR/MAXW 64/32, 지연 500/250, BWCAP 3750)로, RNNoise 512 산출물을 **low 프로파일 전체**
(SRAM 16, EXT 24/12, 250/125, 2344)로 실행. 각 3회. 결과는 판정이 아니라 2×2 서술표
(산출물 × TA 프로파일)로 남기고, "공통 실행 메모리 조건에서의 MAC 구성+컴파일 결과 차이"
문장의 근거로만 쓴다. 매니저 문구대로 "동일 메모리 조건에서 MAC만 늘렸더니"로 쓰지 않는다.

**캠페인 D — 두 번째 역전.** RNNoise 1024·2048 (둘 다 base EXT 지연 500) × 지연
{500(base), 0, 250, 1000} × 3회. 결과 집합은 캠페인 A와 같다(`MEMORY_SERVICE_SENSITIVE` /
`ROBUST_…` / `NOT_EVALUABLE`), 방향 반전 검사는 1024↔2048 쌍에 적용.

**캠페인 E — U55 RNNoise 2×2.** EXT {BWCAP 50, 200} × {지연 64(base), 16}. (50,64)와
(200,64)는 캠페인 B에 이미 있으므로 (50,16)·(200,16) 2 arm × 3회만 추가. 판정은 서술표
(대역폭 완화 효과 / 지연 완화 효과 / 둘 다). BWCAP=0은 "quota 무제한"이지 TA 비활성이
아니므로 결과 해석에서 그렇게 쓴다.

**A5·A6·A7 표현 수정(매니저 지적, 값 변경 없음):** U55 AT_LIMIT → "TA의 명목 대역폭 예산에
근접" (물리 Flash 포화 아님); U85 RULED_OUT → "전체 추론 평균에서 지속적 집계 포화의 근거
없음" (구간 집중·포트 집중은 배제 못 함); U55 AXI1 write도 "측정하지 않음"으로 명시; A6 H5의
OFM 크기는 N×H×W×C 원소 수임을 명시하고 H×W와 C를 분리한 표·YOLO 제외 결과 추가; H4는
계열 20개가 독립 모델 20개가 아님을 명시; A7은 "소스상 결정론"과 "입력 동일성 실측"을 구분.

## 11. 4단계 구체 계약 — U85 stall 카운터

**정정(매니저 검토, 서버 재확인 2026-09-14):** stock U85 프로파일러는 이벤트 슬롯 **5개**
(0–4 = NPU_ACTIVE, SRAM_RD, SRAM_WR, EXT_RD, EXT_WR)를 쓴다. 빈 슬롯은 5·6·7 셋뿐이다.
처음 계약의 "4–7에 4개"는 EXT_WR 슬롯을 덮어썼을 것이므로 폐기하고 두 패스로 나눈다.
자동 시작은 취소했다(런처 kill).

| 패스 | 슬롯 5 | 슬롯 6 | 슬롯 7 |
|---|---|---|---|
| A | MAC_ACTIVE | MAC_STALLED_BY_W | MAC_STALLED_BY_IB |
| B | MAC_ACTIVE | AO_STALLED_BY_OB | NPU_IDLE |

MAC_ACTIVE를 두 패스에 모두 넣어 패스 간 재현(정확 일치)을 게이트 G5로 추가한다. NPU_IDLE
이벤트는 HAL이 소프트웨어로 계산하는 IDLE(=TOTAL−ACTIVE, REPORT I4)과 대조하는 보조값이다.
측정 창: 추가 카운터는 HAL의 begin 훅 **이전**에 설정·enable하고, end 훅 **이후**에 읽는다.
HAL은 자기 마스크(CCNT+CNT1–5)만 enable/disable하므로 추가 카운터는 NPU가 다시 실행되기
전까지 값을 유지한다. 부팅당 추론 1회이므로 누적 문제는 없다. 이 사실은 결과 문서에 적는다.
stall_share는 패스 A의 (W+IB)와 패스 B의 OB를 합산하되 겹칠 수 있으므로 상한으로만 쓴다.

**정정 2 (매니저 2차 회신, manager_log.md):** (a) 추가 카운터는 읽기 직전에 **명시적으로 disable**
한다. S4 측정 창(HAL begin 이전 enable ~ HAL end 이후 disable)은 stock TOTAL 창보다 넓으며
S4 고유 창으로 기록하고 TOTAL과 같은 창으로 취급하지 않는다. 초기화는 HAL init의
`EVCNTR_ALL_Reset` 1회(카운터 0에서 시작)이고, overflow 상태 워드(`PMU_Get_CNTR_OVS`)를 출력해
비트 5–7이 0임을 게이트 G6으로 요구한다. (b) 이벤트 의미가 미확인인 동안 **stall 이벤트를
합산하지 않는다.** 결과 집합은 `RAW_PRESERVED` / `NOT_EVALUABLE`뿐이고, 이벤트별 원시 카운트와
TOTAL 대비 비율은 서술값으로만 남긴다. `MEMORY_WAIT_*` 판정은 폐기. (c) `derived_idle =
TOTAL − ACTIVE`(HAL 파생)와 `NPU_IDLE` 이벤트를 구분해 기록하며 동등성은 검증 대상이다.
(d) MAC_ACTIVE 패스 간 일치(G5)는 재현성 검사이지 측정 창 동일성의 증명이 아니다.
(e) 최소 qualification = 패치 빌드에서 stock 카운터 6종이 R1과 정확히 같음(G2). 이것이 통과해야
S4 값을 보존한다. (f) 논문 처리: 본문 근거로 쓰지 않고 부록에 `SEMANTICS_UNVERIFIED` 원시값과
수집 방법(이벤트 이름·ID·슬롯·마스크·창·도구 버전·UART)만 공개한다.

**캠페인 D 해석 정정(매니저):** 1024와 2048은 TA 파라미터 값이 같아도 SRAM 포트 수(2 vs 4)와
컴파일 결과가 다르므로 "지연 외 조건이 같다"고 쓰지 않는다. 논문 문장: "1024→2048 전이에서는
TA 프로파일의 수치 변경 없이 두 구성의 외부 메모리 지연 민감도를 비교했다. 다만 SRAM 포트 수와
컴파일 결과가 달라, 구성 간 차이를 MAC 수만의 효과로 해석하지 않는다."

**정정 3 (매니저 3차 회신 — S4 보류 사유 반영):** (g) 이벤트값/TOTAL 비율은 창이 다르고 의미도
미확인이므로 **출력하지 않는다**. 이벤트별 원시 카운트만 보존. (h) **clean/A/B 출력 동일성 검사(G7)**:
패치 없는 clean 빌드를 같은 셀에서 먼저 3회 실행하고, A·B 실행의 UART에서 `NPU S4 ` 줄만 제거한
나머지가 clean UART와 바이트 동일해야 한다. stock 러너는 출력 텐서를 인쇄하지 않으므로 이 검사는
"UART에 나타나는 모든 값(카운터·로그)"의 동일성이며, 출력 텐서 값 자체의 동일성은 아니다 — 이
한계는 결과에 적는다. 순서: clean → A → B, 각 셀 3회.

**정정 4 / GO (매니저 4차 회신):** S4의 목적은 "의미론 미확인 PMU 이벤트의 탐색적 원시값 수집"이다.
G7의 이름은 `UART_NON_S4_EQ`(`NPU S4 ` 줄을 제외한 UART의 clean/A/B 동일성)이며 출력 텐서 동일성
검사로 해석하지 않는다. 별도 검증 상태 `output_tensor_equivalence = NOT_TESTED`,
`event_semantics = SEMANTICS_UNVERIFIED`를 모든 결과에 붙인다. 이전에 요구된 기능 동등성 조건은 이번
원시값 수집의 필수 게이트에서 분리한다. 실행 순서: 첫 셀(RNNoise 256)에서 clean→A→B 게이트를 확인한
뒤 나머지 셀. 실패 시 원시 UART를 보존하고 중단하며, 결과를 본 뒤 게이트를 완화하지 않는다. 부록
제목은 "의미론 및 출력 동등성 미검증 이벤트의 원시 관측". MAC_ACTIVE를 MAC 이용률로, stall 카운트를
X4 원인의 입증으로 연결하지 않는다. 출력 덤프(DYNAMIC_OFM)는 이번 착수의 필수 조건이 아니며, 하려면
별도 qualification으로 분리한다. **이 조건으로 매니저 GO (manager_log.md 5번째 교환).**

### 11 (원안)

**실행 전 커밋. 5단계 결과를 본 뒤에 커밋해도 되지만, 이 절의 임계값은 지금 고정한다.**

**패치 범위.** core-driver `src/ethosu_driver.c`만, stock 파일 digest
`56b2fecb…963f`에서 출발. `handle_command_stream()`에서 `ethosu_inference_begin()` 호출
직후에 이벤트 카운터 4–7의 EVTYPER를 {MAC_ACTIVE, MAC_STALLED_BY_W, MAC_STALLED_BY_IB,
AO_STALLED_BY_OB}로 설정하고 CNT5–8을 enable, `ethosu_inference_end()` 호출 직후에
네 값을 읽어 `printf("NPU X4STALL %s: %u cycles\n", …)`로 낸다. HAL 프로파일러가 쓰는
CCNT·CNT1–4는 건드리지 않는다. inference_runner·HAL 무변경. 패치 적용·복원은 digest로
증명한다.

**셀:** U85 RNNoise·KWS·Wav2Letter × 256·512 = 6셀 × 3회. 동결 산출물.

**게이트:** G1 산출물 SHA 동일. G2 stock 카운터(Total·Active·SRAM/EXT beat)가 R1 값과 정확히
같다 — 패치가 측정을 흔들었으면 중단. G3 3회 동일. G4 UART 보존.

**지표·결과 집합 (셀 단위):** `stall_share = (MAC_STALLED_BY_W + MAC_STALLED_BY_IB +
AO_STALLED_BY_OB) / Total` (겹침 가능성 있음 → 상한으로 해석).
`MEMORY_WAIT_DOMINANT` ≥ 0.30 / `MEMORY_WAIT_PRESENT` 0.05–0.30 / `MEMORY_WAIT_NEGLIGIBLE`
< 0.05 / `NOT_EVALUABLE`. 보조: `mac_active_share = MAC_ACTIVE / Total`.

**의미론:** 이벤트 의미는 헤더 이름뿐이다. Arm U85 TRM에서 확인을 시도하고, 확인되지
않으면 모든 결과에 `SEMANTICS_UNVERIFIED`를 붙인다. 그 상태에서는 "대기"라는 단어 대신
"헤더가 stall이라 부르는 이벤트"로 쓴다.

## 12. 매니저(ChatGPT 창) 대화 규약 — 2026-09-14 유저 지정

유저가 Chrome의 ChatGPT 대화("논문 요약과 개선 가이드")를 임시 매니저로 지정했다.
GO·판정·누락 검토는 이 창에 묻고, 답변을 받은 뒤에 다음 단계로 간다.

**보내고 받는 방법** — `docs/paper/raw_data_report/amendments/manager_bridge.py`

```sh
python3 docs/paper/raw_data_report/amendments/manager_bridge.py status          # 탭·생성 중 여부·메시지 수
python3 docs/paper/raw_data_report/amendments/manager_bridge.py ask "<질문>"    # 보내고 완전히 렌더링될 때까지 대기
python3 docs/paper/raw_data_report/amendments/manager_bridge.py last            # 마지막 답변 다시 읽기
```

- AppleScript → Chrome "execute javascript"로 **front window의 active tab**에 쓴다. 질문이
  걸려 있는 동안 그 탭이 앞에 있어야 한다. 탭이 바뀌었으면 `status`의 url이
  `chatgpt.com/c/6a966f7b-…`인지 먼저 확인한다.
- **기다리는 규칙**: 보낸 뒤 2초마다 폴링. (a) assistant 메시지 수가 늘고, (b) stop 버튼이
  없고, (c) 마지막 답변 텍스트가 3회 연속 같을 때만 완료로 본다. 답변 생성에 시간이 걸리므로
  중간 텍스트를 답으로 쓰지 않는다. 600초 초과면 실패로 기록하고 다시 묻는다.
- **질문 형식**: 첫 줄에 무엇을 묻는지(GO 요청 / 판정 검토 / 누락 검토), 이어서 근거
  수치와 닫힌 결과 집합, 마지막에 "선택지 중 하나로 답해 주세요" 또는 "빠진 것을
  지적해 주세요". 한 질문에 한 결정.
- **기록**: 모든 교환은 `amendments/manager_log.md`에 질문·답변·소요 시간과 함께 남긴다.
  매니저 답변은 판단 참고이고, 계약·실행·커밋의 책임은 이 세션에 있다. 답변이 동결 계약과
  충돌하면 그대로 따르지 않고 충돌을 매니저에게 되묻는다.
- 자격 증명·개인 정보는 보내지 않는다. 서버 경로·해시·수치는 보내도 된다.

## 부록: 2026-09-14 서버 확인 기록 (read-only)

- `scripts/cmake/timing_adapter/`: `ta_config_u55_high_end`, `u65_high_end`,
  `u85_sys_dram_{low,mid,high}.cmake`. SRAM·EXT 값은 1절 표 참조. `EXT_* = SRAM_*`
  상속은 `ETHOS_U_NPU_MEMORY_MODE STREQUAL Sram_Only` 분기에서만 일어난다 (53–71행);
  본 실험 모드에서는 `else` 분기(71–89행)의 값이 적용된다. mid와 high는 값이 같다
  (REPORT v1.1의 "바이트 동일"과 일치).
- `source/hal/source/components/npu/ethosu_profiler.c:73-132`: U55/U65 슬롯 =
  ACTIVE, AXI0_RD, AXI0_WR, AXI1_RD. U85 = ACTIVE, SRAM_RD, SRAM_WR, EXT_RD (+ EXT_WR는
  R1 재측정에서 추가 수집).
- `pmu_ethosu.h:36-38`: `ETHOSU_PMU_NCOUNTERS` U85 8, U55/U65 4.
- `inference_runner/src/UseCaseHandler.cc:37-61`: 입력은 `std::rand() & 0xFF`,
  `DYNAMIC_IFM_BASE` 정의 시 메모리 복사.
- Vela 5.0.0 `--verbose-performance`, `--verbose-weights`, `--verbose-schedule`,
  `--verbose-cycle-estimate` 사용 가능. `--verbose-operators`는 DEPRECATED.
