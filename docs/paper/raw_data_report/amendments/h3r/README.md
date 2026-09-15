# h3r/ — H3-R 보강 실험 (2026-09-15)

H3의 두 통제 문제(형상별 양자화 · relaxed의 MAC 간 MAXR/MAXW 차이)를 제거하고 면적 36의 형상 효과를 다시 측정한
별도 캠페인이다. 기존 `h13/`·`x4/`·frozen evidence는 읽기만 했고 수정하지 않았다(보존 게이트 `RULE_H3R_PRESERVATION`).

- 계약(측정 전 고정): `docs/superpowers/plans/2026-09-14-h1-h3-verification-plan.md` **A8**
- 매니저 GO: `docs/superpowers/plans/2026-09-15-h3r-verification-GO.md` · 실행 지시서: `…-h3r-agent-brief.md`
- **결과 보고서: `H3R_RESULTS.md`**

## 코드 (재생성 순서)

| 파일 | 하는 일 |
|---|---|
| `gen_h3r_models.py` | 기준 6×6 INT8 모델의 flatbuffer에서 IFM/OFM `shape`만 바꿔 27모델 파생 → `models/`, `derived_models.json` |
| `check_g1prime.py` | G1′ 필드 단위 비교(+규칙별 fixture 9개) → `h3r_manifest.json`, `model_manifest.csv` |
| `func_check.py` | TF 인터프리터 로드·실행·출력 크기 확인 → `func_check.json` |
| `make_cells.py` | 126 arm 셀 정의와 요청/적용 TA 행렬 → `h3r_cells.json`, `ta_matrix.csv` |
| `h3r_sweep.py` | 서버(`/tmp/h3r/`) 하니스. H13 하니스 사본 + CMakeCache 판독 + 헤더·출력 게이트로 즉시 중단 |
| `collect.sh` | 서버 증거 회수 후 분석·표 생성 |
| `h3r_analyze.py` | **판정기**(계약). 게이트 7종, TOTAL·ACTIVE 병렬 판정 → `h3r_results.json` |
| `test_h3r_analyze.py` | 게이트·판정 fixture (28 테스트) |
| `mutation_check.py` | 판정기 돌연변이 검사 → `mutation_log.md` |
| `h3r_tables.py` | 서술 표 생성(Q1–Q5, 게이트 요약, H3 재계산) |
| `h3r_plots.py` | 그림 재생성 → `plots/` |

```sh
~/.venvs/h3r-tf/bin/python gen_h3r_models.py && ~/.venvs/h3r-tf/bin/python check_g1prime.py \
  && ~/.venvs/h3r-tf/bin/python func_check.py && /usr/bin/python3 make_cells.py
# 서버 배치 후: python3 h3r_sweep.py qual  →  python3 h3r_sweep.py all
sh collect.sh && ~/.venvs/h3r-tf/bin/python h3r_plots.py
python3 -m unittest docs.paper.raw_data_report.amendments.h3r.test_h3r_analyze   # 저장소 루트에서
python3 docs/paper/raw_data_report/amendments/h3r/mutation_check.py
~/.venvs/h3r-tf/bin/python check_g1prime.py test
```

## 증거

`results.jsonl`(arm×반복 레코드), `uart/`(원시 UART), `verify/`(검증 빌드 출력 덤프), `vela/`(`--verbose-schedule`
·`--verbose-performance` 덤프와 per-layer CSV), `run_*.log`, `driver_masks.txt`(TA 드라이버 마스크 발췌와 sha256),
`base_models/`(기준 6×6 모델 사본), `models/`(파생 27모델).

`results_qual_precachefix.jsonl`은 CMakeCache 판독을 기록하기 전에 돌린 첫 qualification 실행이다. 값은 최종 실행과
같지만 실효 설정 열이 비어 있어 결과에 쓰지 않고 기록으로만 남긴다.

## 표

`runs_all.csv`, `h3r_models_conditions_metrics.csv`(요청·헤더·적용 TA 16값 포함), `h3r_judgements_total_vs_active.csv`,
`h3r_spread_medians.csv`, `h3_vs_h3r_base.csv`(Q1), `base_vs_equalized.csv`(Q2), `dw_bridge_vs_equalized.csv`(Q3),
`legacy_judgements_area36.csv`(Q4 기준선), `h3r_blocks.csv`(Q5), `gate_summary.csv`.
