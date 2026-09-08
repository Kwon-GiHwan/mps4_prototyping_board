# 지시문 — Raw data audit report (2026-09-09)

**목적:** 논문 수정이나 새 초안 작성이 아니다. 현재 manuscript의 섹션 순서를 그대로
사용해 기존 raw/frozen evidence에 실제로 어떤 데이터가 존재하는지 재집계하고 표·그래프로
정리한 **별도 보고용 Markdown 문서**를 만든다. 최종 산출물은 원고가 아니라
**raw-data audit / analysis report**.

논문의 기존 문장이나 conclusion에 데이터를 맞추지 말고, raw evidence에서 확인되는
사실을 기준으로 작성한다.

## §0 원칙 — 절대 하지 말 것
- manuscript 수정 금지 / frozen evidence·CSV·JSON·UART log 수정·덮어쓰기 금지
- 데이터를 보고 threshold를 새로 선택하지 말 것
- 누락 데이터를 0으로 간주하지 말 것
- compiler estimate와 runtime observation을 같은 종류로 취급하지 말 것
- cross-platform absolute cycle 비교로 architecture superiority 주장 금지
- 검증 안 된 인과를 caused by / memory-bound / bandwidth saturation 으로 단정 금지
- narrative가 raw data와 충돌하면 narrative를 따라가지 말 것
- FVP·board 재실행 금지. 기존 evidence 집계가 목적
- 기존 자료 read-only. 새 파일은 별도 디렉터리에만

## §1 Provenance 우선
`docs/paper/`, `evidence/`, `analysis/`, `mechanism/`를 inventory.
구분할 종류: Vela compiler output / Vela summary CSV / verbose-performance /
verbose-schedule / FVP whole-model PMU / per-layer·IRQ profiling PMU / board PMU /
model metadata / executability / configuration metadata / raw UART / derived frozen.
`provenance/INPUT_MANIFEST.csv` 생성 (artifact_type, path, sha256, source_stage,
platform, npu, mac, workload, memory_mode, system_config, timing_adapter,
measurement_type, notes). Git commit, MLEK/Vela/FVP version은 별도 표.

## §2 보고서 구조 (manuscript와 동일 순서 유지)
```
# Raw Data Audit for Current Manuscript Structure
## 3 Performance Characterization
### 3.1 Methodology
### 3.2 Where Does Inference Time Go?
### 3.3 How Does Performance Scale?
### 3.4 What Limits Performance Scaling?
## 4 Performance Estimation
### 4.1 How Accurate Is Ethos-U Compiler Performance Estimate?
### 4.2 Where Do Estimation Errors Come From?
## Appendix A. Data Availability Matrix
## Appendix B. Unresolved / Not-Evaluable Items
## Appendix C. Generated Tables and Figures
```
prose보다 표·그래프·계산식·provenance 우선. 각 subsection 끝에 반드시:
```
Observed from data:
Not established from current data:
Data/provenance used:
```

## §3.1 Methodology
- Table 3.1-A 플랫폼/구성 매트릭스: platform, Corstone/SSE, NPU, MAC, FVP binary,
  Fast Models version, system_config, memory_mode, timing_adapter_enabled,
  TA_CONFIG_FILE, workload_count, executability_count, formal_sample_count.
  **U85는 MAC(128/256/512/1024/2048)마다 system_config·TA·memory mode를 옆에 명시.
  MAC만 달라졌다고 가정하지 않는다.**
- Table 3.1-B workload 매트릭스: workload, task, model file, model SHA, input/output
  shape, dtype, total MACs, weight size, Vela SRAM usage, file size, operator types,
  DWConv count, Vela pass/launch count, executability notes.
  구성별로 값이 다르면 대표값 하나로 합치지 말고 configuration dependency 명시.
- Table 3.1-C 계측 가용성: platform별 TOTAL/ACTIVE/IDLE/AXI0_RD/AXI0_WR/AXI1_RD/
  SRAM_RD/SRAM_WR/EXT_RD/EXT_WR/stall/per-layer cycles/ublock schedule.
  vocabulary: AVAILABLE / AVAILABLE_PARTIAL / NOT_EVALUABLE / NOT_COLLECTED /
  PARSER_LOSS / SEMANTICS_UNVERIFIED. **0으로 대체 금지.
  U85 memory field가 frozen formal data에서 실제 손실되었는지 재확인.**

## §3.2 Where Does Inference Time Go?
- 3.2.1 whole-model PMU long-form CSV `tables/3_2_whole_model_pmu.csv`
  (platform, npu, mac, workload, total/active/idle_cycles, memory_event_family,
  rd_beats_0, wr_beats_0, rd_beats_1, wr_beats_1, source, status).
  architecture마다 event 의미가 다르면 AXI 이름으로 억지 통합 금지.
- 3.2.2 traffic composition — beat가 유효한 구성에서만. U55/U65 AXI와 U85 SRAM/EXT를
  같은 hardware path로 가정 금지.
- Figure 3.2-A workload × memory-traffic share (semantics 다르면 figure 분리)
- Figure 3.2-B ACTIVE/TOTAL ratio. **ACTIVE ≠ compute utilization ≠ compute-bound** 명시
- Figure 3.2-C per-layer가 있으면 representative workload. whole-model formal과
  per-layer mechanism을 같은 dataset처럼 병합 금지
- effective bandwidth는 beat definition / bytes per beat / clock / peak bytes-per-cycle /
  TA·system config / counter semantics 가 모두 provenance로 확인될 때만 계산.
  하나라도 불명확하면 NOT_EVALUABLE. traffic 많다는 것만으로 bandwidth saturation 금지

## §3.3 How Does Performance Scale?
- 3.3.1 `tables/3_3_cycles_by_mac.csv` (platform, npu, workload, mac, cycles,
  system_config, memory_mode, TA_config, executability, source)
- 3.3.2 `tables/3_3_scaling_transitions.csv`:
  speedup=C_base/C_current; cumulative_efficiency=speedup/(MAC_cur/MAC_base);
  adjacent_speedup=C_prev/C_next; incremental_efficiency=adjacent_speedup/(MAC_next/MAC_prev).
  컬럼에 cycle_delta, cycle_delta_pct, system_config_prev/next, system_config_changed,
  memory_mode_changed, TA_config_changed, transition_status
  (IMPROVED / PLATEAU / REVERSED / NOT_AVAILABLE), legacy_saturation_rule.
  **기존 <0.50 규칙은 삭제하지 말고 별도 컬럼으로 재현하되, 2× MAC 전이에서는 사실상
  reversal detector임을 주석으로 명시.**
- **전체 53 transition 전수 검사.** RNNoise/U85 ladder 128→256→512→1024→2048 빠짐없이
  출력. 알려진 결과 hard-code 금지, raw에서 재계산.
  자동 검사: reversed / plateau / improved / unavailable transition 수,
  reversal 포함 ladder 수. **transition 수와 ladder 수를 별도로 보고.**
- Figure 3.3-A/B/C architecture별 scaling curve (x=MAC, y=raw cycles, series=workload,
  U55/U65/U85 별도 figure)
- Figure 3.3-D/E/F normalized cycle 또는 speedup
- Figure 3.3-G adjacent incremental efficiency heatmap/grouped
- Figure 3.3-H RNNoise/U85 전체 ladder + MAC·system_config·TA_config·memory_mode annotation.
  **256→512만 잘라서 보여주지 말 것**

## §3.4 What Limits Performance Scaling?
원인 확정 section이 아니라 **현재 evidence가 각 가설을 얼마나 지원하는지** 정리.
후보 7: SRAM bandwidth pressure / External-memory service latency / Weight streaming /
DWConv mismatch / Small feature map / Low compute volume·floor / Ublock geometry mismatch.
Table 3.4-A 열: structural / whole-model / per-layer / memory-counter / compiler-schedule
evidence, controlled intervention, representative workload, evidence status, notes.
status vocabulary: DIRECTLY_OBSERVED / ASSOCIATED_WITH / STRUCTURAL_CONTEXT /
CONSISTENT_WITH / NOT_EVALUABLE / NOT_ESTABLISHED. **CAUSAL 사용 금지.**
- link SRAM overflow와 runtime weight streaming bottleneck은 별개 status
- DWConv 존재만으로 원인 주장 금지
- H×W/MAC 비율을 measured PE utilization으로 부르지 말 것
- plateau 존재와 compute volume이 원인이라는 해석을 구분
- ublock과 reversal 동시 발생 ≠ ublock이 원인. U85 256→512는 MAC/ublock/system_config/
  TA/cycle/per-group 분포를 같은 표에

## §4 Performance Estimation
Vela estimate ↔ FVP observation absolute 비교가 frozen contract상 금지면 기존 metric을
자동 정당화하지 말 것. 다음을 분리 보고:
```
A. Legacy manuscript calculation
B. Currently admissible analysis under frozen measurement semantics
```
- 4.1.1 `tables/4_1_vela_fvp_pairs.csv` — 어떤 Vela metric을 어떤 FVP metric과
  비교하는지 명시 (cycles_total? cycles_npu? TOTAL? ACTIVE?). paper에 값이 있다고
  자동 선택 금지. 컬럼에 pairing_status, semantic_compatibility
- 4.1.2 accuracy metrics — contract 허용 시에만. ranking metric과 absolute error를 분리.
  absolute 비교가 불허면 LEGACY_ONLY 표기 후 main conclusion에 사용 금지
- Figure 4.1-A scatter / 4.1-B ranking / 4.1-C MAC별 error
- 4.2 Table A error by configuration / Table B transition prediction
  (**RNNoise/U85 두 reversal 모두 포함, 첫 것만 출력 금지**) / Table C error associations
  (association이지 causal decomposition 아님)
- Figure 4.2-A error vs MAC / 4.2-B direction match / 4.2-C RNNoise 전체 ladder

## §5 Appendix A — claim/data availability matrix
행: whole-model scaling, memory traffic, stall cycles, effective bandwidth,
per-layer cycles, per-layer memory traffic, DWConv behavior, feature-map behavior,
ublock transition, Vela absolute accuracy, Vela ranking, board correspondence.
열: required_data, available_data, missing_data, source, status,
safe_interpretation, unsafe_interpretation.

## §6 Manuscript/Data Discrepancies
**수정안이 아니라 불일치 사실만** 기록. 숫자는 raw에서 재계산, hard-code 금지.

## §7 산출물
REPORT.md / provenance/INPUT_MANIFEST.csv / tables 13종 / figures / scripts.
figure는 가능하면 PNG + PDF 또는 SVG. 모든 표·그림은 script로 재생성 가능.

## §8 최종 자동 검증 10항목
1 frozen evidence hash 전후 동일  2 raw transition 수 == report transition 수
3 valid adjacent MAC pair 누락 없음  4 reversal/plateau 자동 검출
5 None/missing을 0으로 변환한 곳 없음  6 estimate vs observed가 source 컬럼으로 구분
7 cross-platform absolute cycle 비교가 conclusion에 없음
8 mechanism table에 causal language 없음  9 모든 figure의 입력 CSV 추적 가능
10 REPORT의 모든 숫자가 생성 CSV에서 재현

## §9 종료 보고 (이것만 요약)
1 REPORT 경로  2 CSV/figure 수  3 raw data 주요 discrepancy
4 NOT_EVALUABLE 항목  5 manuscript 수정 전 반드시 확인할 데이터 문제

## 사용자 추가 지시
- 로컬에 지시문 기록 후 참조하며 진행
- 결과물은 md 파일
- **논문처럼 긴 설명 금지.** 어떤 데이터에 대한 표인지 간략한 설명만
- §9까지 허가 없이 전부 진행
- 재측정하거나 수정할 부분이 생기면 **새 버전을 달아 history 파악 가능하게 기록**
