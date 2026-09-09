# Source data — 원본 그대로, 섹션별 사본

`REPORT.md`의 섹션 순서대로 **원본 frozen evidence를 복사만** 해둔 곳이다.
가공·집계·컬럼 추가 없음. 파생 표는 `../tables/`에 따로 있다.

- 모든 사본은 원본과 **SHA-256 동일**하며 `MANIFEST.csv`가 그 검증 결과를 담는다.
- 여러 섹션이 쓰는 파일은 **각 섹션에 중복 복사**해서 폴더 하나만 봐도 되게 했다.
  중복 위치는 `MANIFEST.csv`의 `also_in_sections` 컬럼에 기록된다.
- 재생성: `python3 ../scripts/collect_source_data.py` (기존 폴더를 지우고 다시 복사)

## 폴더 구성

| 폴더 | REPORT 대응 | 핵심 파일 |
|---|---|---|
| `3_1_methodology/` | 3.1 실험 매트릭스 | `executability.csv`(133셀), `canonical_cells.csv`(74셀), `vela_matrix.csv`, `DETERMINISTIC_METRIC_VECTOR.md` |
| `3_2_inference_time/` | 3.2 시간의 소재 | `canonical_cells.csv`, `U85_ATTRIBUTION_UNITS.csv`(per-unit SRAM/EXT), `U85_PMU_EVENT_AUTHORITY.csv` |
| `3_3_scaling/` | 3.3 스케일링 | `canonical_cells.csv`, `executability.csv`, `scaling.csv`, `saturation.csv`, `vela_matrix.csv` |
| `3_4_limits/` | 3.4 제약 가설 | `U85_256_512_DIFFERENTIAL.csv`, `U85_GROUP_DIFFERENTIAL.csv`, `U85_P1B_CROSSMODE_GROUPS.csv` 외 |
| `4_1_estimation_accuracy/` | 4.1 Vela 정확도 | `vela_matrix.csv`(추정), `canonical_cells.csv`(관측), `vela_fvp_trend_agreement.csv` |
| `4_2_error_sources/` | 4.2 오차의 소재 | 위 + `U85_256_512_DIFFERENTIAL.csv` |
| `_supporting_board/` | Appendix / 가용성 | 보드 RQ3 3종 |
| `_supporting_platform_sensitivity/` | 가용성 | X1/X3 |
| `_supporting_instrumentation/` | 가용성 | U65 bridge 2종 |

## 주의

- `vela_matrix.csv`는 **compiler estimate**, `canonical_cells.csv`는 **runtime
  observation**이다. 같은 폴더에 있어도 종류가 다르며 절대 비교는 frozen semantics가
  거부한다.
- `U85_ATTRIBUTION_UNITS.csv` 등 mechanism 파일은 formal sweep과 **다른 바이너리**를
  계측한 것이다. `canonical_cells.csv`와 병합하지 말 것.
- `canonical_cells.csv`의 U85 35셀은 `axi*_beats`가 비어 있다. **0이 아니다.**
  U85는 AXI 이름을 방출하지 않으며(`SRAM_*`/`EXT_*` 사용), 잃어버린 것은 그 SRAM/EXT
  값이었다. v1.3에서 재측정으로 회수했다 — `../remeasure/R1_MEMORY_COUNTERS.csv`.
  **이 폴더의 `canonical_cells.csv` 사본은 frozen 원본 그대로이므로 여전히 공란이다**
  (원본 무수정 원칙). 회수값은 `../tables/3_2_whole_model_pmu.csv`에서 출처 컬럼과
  함께 결합된다
  (`../SERVER_VERIFICATION.md` V3).
