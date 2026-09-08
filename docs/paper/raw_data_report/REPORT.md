# Raw Data Audit for Current Manuscript Structure

**v1.1 · 2026-09-09.** (v1.0에서 서버 검증 결과 반영 — `CHANGELOG.md` 참조.
V1/V2/V3가 `NOT_VERIFIED` → `VERIFIED`로 바뀌었고, 그로 인해 무효화된 해석을
"검증으로 무효화된 해석" 절에 명시했다. 근거는 `SERVER_VERIFICATION.md`.) 기존 frozen evidence를 manuscript 섹션 순서로 재집계한 감사
보고서. **논문 원고가 아니다.** 모든 수치는 `tables/`의 CSV에서 재생성되며, 모든
CSV는 `scripts/`로 재생성 가능하다. 기존 evidence는 read-only.

재생성: `python3 scripts/build_manifest.py && python3 scripts/build_tables.py && python3 scripts/build_figures.py`

Provenance: `provenance/INPUT_MANIFEST.csv` (971 artifact), `provenance/TOOL_VERSIONS.csv`,
`provenance/BASELINE_HASHES.txt` (541 파일 불변 검증용).

---

## 3 Performance Characterization

### 3.1 Methodology

**Table 3.1-A** `tables/3_1_platform_matrix.csv` — 19개 설정. MAC 옆에
`system_config`·`memory_mode`·TA를 함께 둔다. U85는 MAC마다 `system_config`가 바뀐다.

| platform | npu | MAC | system_config | memory_mode | TA | formal cells |
|---|---|---:|---|---|---|---:|
| SSE-300 | u55 | 32/64/128/256 | `Ethos_U55_High_End_Embedded` | Shared_Sram | ON | 25 |
| SSE-300 | u65 | 256/512 | `Ethos_U65_High_End` | Dedicated_Sram | ON | 14 |
| SSE-310 | u55 | 32/64/128/256 | `Ethos_U55_High_End_Embedded` | Shared_Sram | OFF | 0 |
| SSE-310 | u65 | 256/512 | `Ethos_U65_High_End` | Dedicated_Sram | OFF | 0 |
| SSE-315 | u65 | 256/512 | `Ethos_U65_High_End` | Dedicated_Sram | OFF | 0 |
| SSE-320 | u85 | 128 | `Ethos_U85_SYS_DRAM_Low` | Dedicated_Sram | ON | 7 |
| SSE-320 | u85 | 256 | `Ethos_U85_SYS_DRAM_Low` | Dedicated_Sram | ON | 7 |
| SSE-320 | u85 | 512 | `Ethos_U85_SYS_DRAM_Mid_512` | Dedicated_Sram | ON | 7 |
| SSE-320 | u85 | 1024 | `Ethos_U85_SYS_DRAM_Mid_1024` | Dedicated_Sram | ON | 7 |
| SSE-320 | u85 | 2048 | `Ethos_U85_SYS_DRAM_High_2048` | Dedicated_Sram | ON | 7 |

`ta_config_file` **VERIFIED** (`SERVER_VERIFICATION.md` V1, MLEK `b2c0bb2`):

| npu | MAC | TA_CONFIG_FILE | 파라미터 집합 |
|---|---|---|---|
| u55 | 전체 | `ta_config_u55_high_end` | `u55_high_end` |
| u65 | 전체 | `ta_config_u65_high_end` | `u65_high_end` |
| u85 | 128, 256 | `ta_config_u85_sys_dram_low` | `u85_low` |
| u85 | 512, 1024 | `ta_config_u85_sys_dram_mid` | `u85_mid_high` |
| u85 | 2048 | `ta_config_u85_sys_dram_high` | `u85_mid_high` (mid와 **바이트 동일**) |

`low → mid` 차이: SRAM latency 16→32, `EXT_MAXR` 24→64, `EXT_MAXW` 12→32,
EXT latency 250→500, `EXT_BWCAP` 2344→3750.

**Table 3.1-B** `tables/3_1_workload_matrix.csv` — 133행. workload × 설정별로
model SHA, Vela artifact SHA, npu/cpu operator 수, encoded weight, SRAM/DRAM 사용량.
구성별로 값이 다르므로 대표값으로 합치지 않았다. shape·total MAC·operator type·
DWConv 수·launch 수는 로컬 evidence에 없어 `NOT_COLLECTED`.

**Table 3.1-C** `tables/3_1_measurement_availability.csv` — 계측 가용성.

| platform/npu | TOTAL | ACTIVE | IDLE | AXI0/1 | SRAM/EXT | per-layer |
|---|---|---|---|---|---|---|
| SSE-300 / u55 | AVAILABLE | AVAILABLE | AVAILABLE_DERIVED | AVAILABLE | NOT_EVALUABLE | NOT_COLLECTED |
| SSE-300 / u65 | AVAILABLE | AVAILABLE | AVAILABLE_DERIVED | AVAILABLE | NOT_EVALUABLE | NOT_COLLECTED |
| SSE-310/315 | NOT_COLLECTED | — | — | NOT_COLLECTED | NOT_EVALUABLE | NOT_COLLECTED |
| SSE-320 / u85 | AVAILABLE | AVAILABLE | AVAILABLE_DERIVED | **PARSER_LOSS** | AVAILABLE_PARTIAL | AVAILABLE |

`IDLE`이 `AVAILABLE_DERIVED`인 것은 **VERIFIED**다 (`SERVER_VERIFICATION.md` V2).
`ethosu_profiler.c:187-189`가 `npu_total_ccnt - npu_evt_counters[0]`로 계산하고
`:131`에서 `"NPU IDLE"`로 명명한다. 따라서 `TOTAL = ACTIVE + IDLE` 74/74는
**산술 항등식이며 독립 카운터 일치의 증거가 아니다.**
측정 창도 확정됐다 — `inference_begin`(Disable→Enable) ~ `inference_end`(Disable),
즉 드라이버의 추론 호출 구간이지 "첫 NPU 명령 ~ 마지막 NPU 사이클"이 아니다.

**Observed from data:** 19개 설정 중 TA-ON 11개만 formal sweep에 들어갔다. U85는 MAC
5단계에서 `system_config`가 4종으로 바뀐다. U85 whole-model 메모리 필드는 35/35 셀
전부 비어 있고, 같은 이벤트군이 mechanism dataset에는 존재한다.
**Not established from current data:** 컴파일러 버전; 모델 shape·DWConv 수.
(TA_CONFIG_FILE과 MLEK git commit은 v1.1에서 VERIFIED로 이동.)
**Data/provenance used:** `analysis/executability.csv`, `analysis/canonical_cells.csv`,
`evidence/vela-matrix-20260824/vela_matrix.csv`, `MAIN_EXPERIMENT_MATRIX.md`(FVP 버전).

---

### 3.2 Where Does Inference Time Go?

**Table 3.2-1** `tables/3_2_whole_model_pmu.csv` — 74 formal cell의 long-form PMU.
architecture별 event 의미가 다르므로 `memory_event_family` 컬럼으로 구분하고 통합하지 않았다.

**Table 3.2-2** `tables/3_2_memory_traffic.csv` — beat가 존재하는 구성만 traffic
composition 계산. U85 35행은 `NOT_EVALUABLE`.

**Table 3.2-3** `tables/3_2_per_layer_pmu.csv` — 656행. U85 mechanism dataset의
per-unit `ccnt`/`evt_sram_rd`/`evt_sram_wr`/`evt_ext_rd`/`evt_ext_wr`.
**formal sweep과 다른 바이너리이므로 3_2_whole_model_pmu.csv와 병합 금지.**

**Figure 3.2-A** (u55/u65 각각) — AXI0 대 AXI1 beat 비중. AXI1_WR는 미수집이므로
수집된 부분집합에 대한 비중이다. U85는 whole-model beat가 없어 그림 없음.
**Figure 3.2-B** — ACTIVE/TOTAL 비율. **ACTIVE는 compute utilization이 아니고
compute-bound를 뜻하지도 않는다.**

Effective bandwidth: beat 정의, beat당 바이트, 클럭, peak bytes/cycle, TA 설정,
counter semantics 중 **어느 것도 로컬 provenance로 확인되지 않아 계산하지 않았다** →
`NOT_EVALUABLE`.

**Observed from data:** U55/U65는 AXI1(read)이 트래픽 대부분을 차지한다. ACTIVE/TOTAL은
전 셀에서 0.976–0.9999 구간이다.
**Not established from current data:** effective bandwidth; U85 whole-model 메모리
구성; stall 원인; ACTIVE가 실제 연산 활용도라는 해석.
**Data/provenance used:** `analysis/canonical_cells.csv`, `mechanism/U85_ATTRIBUTION_UNITS.csv`.

---

### 3.3 How Does Performance Scale?

**Table 3.3-1** `tables/3_3_cycles_by_mac.csv` — 77행(TA-ON 그리드 전체, 실행불가 6셀 포함).
점 출처는 `canonical_cells.csv`이며 `analysis/scaling.csv`가 아니다 — 후자는
`SSE-300/u55/wav2letter@256`(측정된 셀)을 사다리 baseline 결측을 이유로 누락한다.

**Table 3.3-2** `tables/3_3_scaling_transitions.csv` — 56 전이 전수.
`legacy_saturation_rule` 컬럼에 기존 `<0.50` 규칙을 보존했다.
**2배 MAC 구간에서 `incremental_efficiency < 0.5`는 `cycles 증가`와 동치이므로,
이 규칙은 포화 검출기가 아니라 역전 검출기다.**

**Table 3.3-3** `tables/3_3_ladder_summary.csv` — 사다리 21개별 요약.

전수 스캔 결과 (`provenance/TRANSITION_STATS.json`):

```
transition rows            56
  IMPROVED                 50
  PLATEAU                   1
  REVERSED                  2
  NOT_AVAILABLE             3
  evaluable                53
ladders total              21
  with >=2 executable pts  20
  containing a reversal     1
  containing a plateau      1
legacy <0.50 rule fired     2
```

역전·평탄 전이 전체:

| platform/npu | workload | 전이 | cycles | delta | E_inc | system_config 변화 |
|---|---|---|---|---:|---:|---|
| 전이 | cycles | delta | E_inc | system_config | TA 파일 | **TA 파라미터** |
|---|---|---:|---:|---|---|---|
| 128→256 | 36,086 → 36,086 | **0** | 0.5000 | 불변 | 불변 | **불변** |
| 256→512 | 36,086 → 55,086 | **+19,000** | 0.3275 | 변경 | 변경 | **변경** |
| 512→1024 | 55,086 → 49,086 | −6,000 | 0.5611 | 변경 | 불변 | **불변** |
| 1024→2048 | 49,086 → 54,086 | **+5,000** | 0.4538 | 변경 | 변경(이름만) | **불변** |

TA 파라미터가 실제로 바뀌는 전이는 **256→512 하나뿐**이다 (`mid`와 `high`는 바이트 동일).

**Figure 3.3-A/B/C** raw cycles (u55/u65/u85 별도) · **3.3-D/E/F** 사다리 자체
baseline으로 정규화 · **3.3-G** 전이별 incremental efficiency 히트맵 ·
**3.3-H** rnnoise/U85 전체 사다리 + MAC·system_config·memory_mode 주석.

**Observed from data:** 53개 평가 가능 전이 중 역전 2건, 평탄 1건. 모두 같은 사다리
(rnnoise/U85). 역전을 포함한 사다리는 21개 중 1개. 유효 MAC 점이 2개 이상인 사다리는 20개.
`system_config`가 바뀌지 않은 유일한 U85 전이(128→256)에서 개선이 정확히 0이다.
**Not established from current data:** 역전의 원인; `system_config`·TA 변경과 사이클
변화의 관계(표본 4개, controlled intervention 없음).
**두 역전을 하나의 원인으로 묶을 근거는 없다** — 256→512는 TA 파라미터가 바뀌고
1024→2048은 바뀌지 않는다.
**Data/provenance used:** `analysis/canonical_cells.csv`, `analysis/executability.csv`,
`evidence/vela-matrix-20260824/vela_matrix.csv`.

---

### 3.4 What Limits Performance Scaling?

**Table 3.4-A** `tables/3_4_mechanism_evidence_matrix.csv` — 가설 7종의 근거 수준.
`CAUSAL` 상태값은 사용하지 않는다.

| mechanism | evidence status |
|---|---|
| SRAM bandwidth pressure | `NOT_EVALUABLE` |
| External-memory service latency | `NOT_EVALUABLE` |
| Weight streaming / on-chip capacity | `STRUCTURAL_CONTEXT` |
| DWConv / output-channel mismatch | `NOT_ESTABLISHED` |
| Small feature map / tile parallelism | `CONSISTENT_WITH` |
| Low compute volume / cost floor | `ASSOCIATED_WITH` |
| Ublock geometry mismatch | `ASSOCIATED_WITH` |

**Table 3.4-B** `tables/3_4_u85_256_512_combined.csv` — 251행. 같은 표에서 MAC·
ublock(before/after)·`system_config`(before/after)·TA·cycle·방향을 함께 본다.

7개 가설 모두 **controlled intervention 없음**. 대역폭·지연을 독립적으로 바꾼 실험이
존재하지 않으므로 어떤 것도 원인으로 확정되지 않는다. link-time SRAM overflow는
runtime weight-streaming bottleneck과 별개 상태로 기록했다.

**Observed from data:** ublock 변화는 rnnoise 256→512에서 방향 부류와 무관하게
광범위하게 동반된다. 평탄 전이가 1건 존재한다.
**Not established from current data:** 7개 가설 중 어느 것도 원인으로 확정되지 않음.
effective bandwidth 미산출. DWConv 수·feature map shape 미수집.
**Data/provenance used:** `mechanism/U85_256_512_DIFFERENTIAL.csv`,
`mechanism/U85_ATTRIBUTION_UNITS.csv`, `mechanism/U85_PMU_EVENT_AUTHORITY.csv`.

---

## 4 Performance Estimation

### 4.1 How Accurate Is Ethos-U Compiler Performance Estimate?

**Table 4.1-1** `tables/4_1_vela_fvp_pairs.csv` — 148행. 어떤 Vela metric을 어떤 FVP
metric과 짝지었는지 명시하고, `semantic_compatibility`에 **`REFUSED_ABSOLUTE`** 를 기록.

| Vela metric | FVP metric | 상태 |
|---|---|---|
| `vela_cycles_total` | `npu_total_cycles` | `REFUSED_ABSOLUTE` |
| `vela_cycles_npu` | `npu_active_cycles` | `REFUSED_ABSOLUTE` (Vela의 npu-cycle은 ACTIVE 이벤트로 정의되지 않음) |

**Table 4.1-2** `tables/4_1_accuracy_metrics.csv` — 설정 11개.

```
A. Legacy manuscript calculation        MAPE 1.47 % – 35.40 %   → LEGACY_ONLY
B. Currently admissible                 ranking only (Spearman)
```

Spearman rho는 11개 설정 중 10개에서 `1.0`, 1개에서 `0.964286`.
**절대오차는 frozen semantics가 거부하므로 이 보고서의 어떤 결론에도 사용하지 않는다.**

**Figure 4.1-A** estimate vs observation 산점도 (LEGACY_ONLY 표기) ·
**Figure 4.1-B** 설정별 ranking rho.

**Observed from data:** workload ranking은 거의 모든 설정에서 보존된다.
**Not established from current data:** 절대 정확도; Vela의 계통 편향.
**Data/provenance used:** `evidence/vela-matrix-20260824/vela_matrix.csv`,
`analysis/canonical_cells.csv`.

---

### 4.2 Where Do Estimation Errors Come From?

**Table 4.2-A/B** `tables/4_2_transition_prediction.csv` — 53 전이 전체.
**rnnoise/U85의 역전 2건이 모두 포함되어 있다.**

| direction match | 전이 수 |
|---|---:|
| 일치 | 50 |
| 불일치 | 3 |

불일치 3건은 전부 rnnoise/U85 사다리다:

| 전이 | FVP 관측 | Vela 예측 |
|---|---|---|
| 128→256 | PLATEAU | IMPROVED |
| 256→512 | **REVERSED** | IMPROVED |
| 512→1024 | IMPROVED | **REVERSED** |
| 1024→2048 | **REVERSED** | **REVERSED** (일치) |

Vela도 역전을 2건 예측했으나 **위치가 다르다** — 첫 역전은 놓치고, 개선 구간에서
역전을 예측했으며, 두 번째 역전은 맞혔다.

**Table 4.2-C** `tables/4_2_error_associations.csv` — 53행. `analysis_type` 컬럼에
`ASSOCIATION_ONLY - not a causal decomposition` 고정.

**Figure 4.2-B** 방향 일치 분포 · **Figure 4.2-C** rnnoise/U85 전체 사다리의
예측 곡선과 관측 곡선(두 값은 종류가 다르므로 절대 비교하지 않음).

**Observed from data:** 53개 중 50개 전이에서 방향이 일치한다. 불일치는 한 사다리에 몰려 있다.
**Not established from current data:** 오차의 원인; DWConv·feature-map 연관(미수집).
**Data/provenance used:** `tables/4_1_vela_fvp_pairs.csv`, `tables/3_3_scaling_transitions.csv`.

---

## Manuscript/Data Discrepancies

수정안이 아니라 불일치 사실만 기록한다. 수치는 전부 위 CSV에서 재계산했다.

| # | manuscript 서술 | raw data |
|---|---|---|
| D1 | "One boundary is non-monotonic" (abstract) | 사이클 증가 전이 **2건** (256→512, 1024→2048). 둘 다 같은 사다리 |
| D2 | "The **single** observed saturation point" (§4.1) | `saturation_point` 정의상 첫 지점만 보고하므로 정의에는 부합. 그러나 `WEAK_OR_SATURATED = 2`가 무엇인지 본문에 설명 없음 |
| D3 | 128→256 전이 | **개선 0** (36,086 → 36,086). 본문에 언급 없음. `system_config`가 바뀌지 않은 유일한 U85 전이 |
| D4 | "AXI beat 3종도 함께 기록" | U85 35/35 셀에서 `axi*_beats` = 비어 있음. U85 stock profiler는 SRAM/EXT를 노출(`VERIFIED_AVAILABLE`)하므로 파서 손실로 보인다 |
| D5 | 결정론 19개 필드 동등성 | U85에서 메모리 3개 필드가 `None == None == None`으로 vacuous 통과 |
| D6 | "21 ladders" | 사다리 21개 중 **유효 MAC 점 2개 이상은 20개**. 전이 수와 사다리 수는 별개 |
| D7 | `TOTAL = ACTIVE + IDLE` 74/74 | 산술 항등이며 독립 카운터 일치의 증거가 아님 |
| D8 | "Vela predicted improvement for ... this one" (§7.1) | 256→512에 대해서는 참. 전체 사다리에서는 4개 중 3개 방향 불일치 |
| D9 | `analysis/scaling.csv` | 측정된 `SSE-300/u55/wav2letter@256` 점이 누락되어 있음 |

---

## Appendix A. Data Availability Matrix

`tables/3_1_measurement_availability.csv` 참조. 요약:

| 분석 항목 | 상태 | 안전한 해석 | 위험한 해석 |
|---|---|---|---|
| whole-model scaling | AVAILABLE | 사다리 내 사이클 비교 | 세대 간 절대 비교 |
| memory traffic (U55/U65) | AVAILABLE_PARTIAL | 포트 비중(수집분) | 절대 대역폭 |
| memory traffic (U85) | **PARSER_LOSS** | 없음 | 0으로 간주 |
| stall cycles | NOT_COLLECTED / SEMANTICS_UNVERIFIED | 없음 | stall 기반 원인 귀속 |
| effective bandwidth | **NOT_EVALUABLE** | 없음 | bandwidth saturation 주장 |
| per-layer cycles (U85) | AVAILABLE | 그룹 단위 비용 분포 | formal sweep과 병합 |
| per-layer memory (U85) | AVAILABLE | 그룹 단위 트래픽 | whole-model 대체 |
| DWConv behavior | NOT_COLLECTED | 없음 | DWConv 원인 주장 |
| feature-map behavior | NOT_COLLECTED | 없음 | PE utilization 주장 |
| ublock transition | AVAILABLE | 동반 발생 기술 | 원인 귀속 |
| Vela absolute accuracy | LEGACY_ONLY | 없음 | 정확도 주장 |
| Vela ranking | AVAILABLE | 순위 보존 | 크기 예측 |
| board correspondence | AVAILABLE (1 cell) | 순위·상대 형태 | 절대 타이밍 일치 |

## Appendix B. Unresolved / Not-Evaluable Items

**v1.1에서 해소된 항목** (`SERVER_VERIFICATION.md`):

| 항목 | v1.0 | v1.1 |
|---|---|---|
| TA_CONFIG_FILE의 MAC별 변화 | NOT_VERIFIED_LOCALLY | **VERIFIED** — MAC별로 달라지며 파라미터는 256→512에서만 변경 |
| profiler의 IDLE 계산 방식 | NOT_VERIFIED_LOCALLY | **VERIFIED** — `TOTAL − ACTIVE` 소프트웨어 파생 |
| U85 메모리 필드 손실 원인 | 파서 손실로 추정 | **VERIFIED** — `PARSER_LOSS_BUT_RAW_UART_NOT_RETAINED` |
| PMU 카운터 reset/enable/read 위치 | NOT_VERIFIED | **VERIFIED** — `inference_begin`/`inference_end` enable-disable 창 |
| MLEK git commit | NOT_VERIFIED_LOCALLY | **VERIFIED** — `b2c0bb2884698b7328f65c41b7c8c51ca9bec386` |

**남은 미해소 항목**

| 항목 | 상태 | 해소 조건 |
|---|---|---|
| 입력 tensor 생성 방식·seed | NOT_COLLECTED | 서버 runner 소스 |
| counter overflow 경고 | NOT_COLLECTED | `counter_overflow()`가 `warn()`을 내지만 파서가 수집하지 않음 |
| effective bandwidth | NOT_EVALUABLE | beat 정의·클럭·TA 설정 확인 |
| gcc 버전 | NOT_VERIFIED_LOCALLY | 서버 |
| 모델 shape·total MAC·DWConv 수 | NOT_COLLECTED | Vela verbose 출력 재수집 |

## 검증으로 무효화된 해석 (v1.1)

`SERVER_VERIFICATION.md`가 확정한 사실로 인해 **더 이상 성립하지 않는 읽기**들이다.
어떤 것도 새 인과 주장을 만들지 않는다.

| # | v1.0까지 가능했던 해석 | v1.1 이후 |
|---|---|---|
| I1 | "TA=ON 구성은 동일한 memory-service 조건" | **무효.** U85에서 TA 파라미터는 256→512에서 바뀐다 |
| I2 | 256→512 역전을 **MAC 증가만의 효과**로 읽기 | **무효.** MAC·`system_config`·TA 파라미터가 동시에 바뀐다 |
| I3 | 두 역전(256→512, 1024→2048)을 **같은 원인**으로 묶기 | **무효.** 후자는 TA 파라미터가 불변이다 |
| I4 | `TOTAL = ACTIVE + IDLE` 74/74를 **계측 일관성 검증**으로 인용 | **무효.** 산술 항등식이다 |
| I5 | 측정 구간을 `T_NPU`(첫 명령~마지막 사이클)로 명명 | **무효.** 드라이버 추론 호출 구간이다 |
| I6 | U85 메모리 공란을 "미수집"으로 처리하거나 재파싱으로 복구 가능하다고 보기 | **무효.** 파서 손실이며 원시 UART 미보존 → 재측정 필요 |

**여전히 성립하는 것:** 128→256이 개선 0이고 그 구간은 `system_config`·TA가 모두
불변이라는 관찰. 다만 표본 4개에 controlled intervention이 없으므로 인과가 아니다.

## Appendix C. Generated Tables and Figures

표 15종 · 그림 15종(PNG+SVG) · provenance 4종. 목록은
`provenance/TABLE_COUNTS.json`, 검증 결과는 `provenance/VERIFICATION.json`.
