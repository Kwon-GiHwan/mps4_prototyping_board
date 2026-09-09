# Source data — 섹션별 원본 evidence

`REPORT.md`의 섹션 구성에 맞춰 **frozen evidence 원본을 그대로 복사해 둔 디렉터리**이다
(`source_data/`).

- 원본 파일은 가공·집계·컬럼 추가 없이 복사만 수행
- 모든 사본은 원본과 **SHA-256이 동일**
- 검증 결과와 원본 경로는 `source_data/MANIFEST.csv`에 기록
- 파생 표·집계 결과는 `tables/`에 별도 저장
- 여러 섹션에서 사용하는 파일은 각 섹션에 중복 배치
  - 중복 위치는 `MANIFEST.csv`의 `also_in_sections`에 기록

재생성:

```bash
python3 scripts/collect_source_data.py
```

기존 `source_data/`를 삭제한 뒤 frozen evidence에서 다시 복사한다.

## 폴더 구성

| 폴더 | REPORT 대응 | 주요 원본 데이터 |
|---|---|---|
| `3_1_methodology/` | §3.1 실험 구성 | `executability.csv` (133 cells), `canonical_cells.csv` (74 cells), `vela_matrix.csv`, `DETERMINISTIC_METRIC_VECTOR.md` |
| `3_2_inference_time/` | §3.2 실행 시간·PMU | `canonical_cells.csv`, `U85_ATTRIBUTION_UNITS.csv`, `U85_PMU_EVENT_AUTHORITY.csv` |
| `3_3_scaling/` | §3.3 MAC scaling | `canonical_cells.csv`, `executability.csv`, `scaling.csv`, `saturation.csv`, `vela_matrix.csv` |
| `3_4_limits/` | §3.4 scaling limitation 분석 | `U85_256_512_DIFFERENTIAL.csv`, `U85_GROUP_DIFFERENTIAL.csv`, `U85_P1B_CROSSMODE_GROUPS.csv` 등 |
| `4_1_estimation_accuracy/` | §4.1 Vela prediction | `vela_matrix.csv`, `canonical_cells.csv`, `vela_fvp_trend_agreement.csv` |
| `4_2_error_sources/` | §4.2 prediction error 분석 | §4.1 데이터 + `U85_256_512_DIFFERENTIAL.csv` |
| `_supporting_board/` | Board validation | MPS4 RQ3 관련 원본 3종 |
| `_supporting_platform_sensitivity/` | Platform sensitivity | X1 / X3 관련 원본 |
| `_supporting_instrumentation/` | Instrumentation validation | U65 bridge 관련 원본 2종 |

## 데이터 해석 시 주의사항

### 1. Compiler estimate와 runtime observation 구분

| 파일 | 성격 |
|---|---|
| `vela_matrix.csv` | Vela compiler estimate |
| `canonical_cells.csv` | FVP runtime observation |

두 데이터는 성격이 다르므로 같은 폴더에 있더라도 절대값을 직접 동일한 측정값처럼
비교하지 않는다.

### 2. Formal sweep과 mechanism dataset 구분

`U85_ATTRIBUTION_UNITS.csv`, `U85_256_512_DIFFERENTIAL.csv` 등 mechanism 관련
파일은 formal sweep과 다른 instrumentation binary / measurement path에서 생성된
데이터이다.

따라서:

- formal sweep 결과와 직접 병합하지 않음
- mechanism evidence는 해당 분석 범위 내에서만 사용
- 서로 다른 measurement path의 값을 동일한 표본으로 취급하지 않음

### 3. U85 whole-model memory counter — v1.3에서 재측정으로 회수

`canonical_cells.csv`의 U85 35 cells에서 `axi*_beats` 필드는 비어 있다.
**이 사본은 frozen 원본 그대로이므로 앞으로도 비어 있다** (원본 무수정 원칙).

- 실제 값 0이 아님
- U85 profiler는 `SRAM_*`, `EXT_*` 이벤트를 사용하며 **`AXI*`를 방출하지 않는다**.
  따라서 U85에서 AXI 컬럼은 손실이 아니라 `NOT_EVALUABLE`이다
- 잃어버린 것은 `SRAM_*`/`EXT_*` 값이었다. 기존 parser가 `AXI0_*`, `AXI1_*` 라벨만
  인식했고, 원시 UART까지 삭제되어 재파싱이 불가능했다
- **v1.3에서 재측정(R1)으로 35/35 회수했다.** frozen artifact 해시를 바이트 재현하고
  사이클 값이 frozen과 일치함을 확인한 뒤(G1–G3) 회수값을 붙였다

| 보려면 | 파일 |
|---|---|
| 회수된 값 | `remeasure/R1_MEMORY_COUNTERS.csv` |
| 게이트 판정 | `remeasure/R1_GATE_REPORT.md` |
| 파생 표에 결합된 형태 | `tables/3_2_whole_model_pmu.csv` (출처 컬럼 포함) |
| 원시 UART (보존) | `remeasure/uart/` |

손실 자체의 진단은 `SERVER_VERIFICATION.md` V3, 회수 경위는 `CHANGELOG.md` v1.3 참고.

## 원칙

- 원본 evidence는 수정하지 않음
- source copy 역시 내용 변경 없이 유지
- 계산·집계·재분류는 `tables/` 및 분석 스크립트에서만 수행
- 측정되지 않은 값은 0으로 대체하지 않고 missing / `NOT_EVALUABLE`로 유지
