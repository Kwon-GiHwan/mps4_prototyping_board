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
