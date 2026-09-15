# amendments/ — 2026-09-14 미확인 항목 평가

REPORT.md 부록 A·B의 미확인 항목을 계획서
`docs/superpowers/plans/2026-09-14-unresolved-items-evaluation-plan.md`(계약 먼저, 값 나중)에 따라
평가한 기록이다. 동결 evidence는 수정하지 않았고, REPORT 본문도 고치지 않았다. 이 디렉터리의 문서가
amendment이며, 논문에 반영할 때는 각 문서의 "제안 판정"과 매니저 승인 문구를 그대로 옮긴다.

| 문서 | 항목 | 상태 | 핵심 |
|---|---|---|---|
| `A5_effective_bandwidth.md` | 요인 1·2, 실효 대역폭 vs TA 명목 예산 | POST_HOC_DESCRIPTIVE | U55 RNNoise Flash 경로 명목 예산 근접(사전 정량 예측은 X4에서 NOT_MET); U85 평균 기준 지속 포화 근거 없음 |
| `A6_model_structure.md` | 요인 4·5, 133셀 verbose 재컴파일(SHA 133/133 동일) | POST_HOC_DESCRIPTIVE | H4 순서 관계 없음(요인 4 판정 유지); H5 SMALL_FM_CONCENTRATED, 공간 크기(H×W)로 보면 모델 간 일관 |
| `A7_input_tensor_seed.md` | 방법론, 입력 생성 | 확인 | 소스상 결정론(std::rand, srand 없음); 입력 동일성 실측은 NOT_TESTED |
| `A8_x4_timing_adapter_sweep.md` | 요인 2·7, TA 변주(캠페인 A–E, 111회) | 실행 결과, 게이트 전부 통과 | 같은 절대 지연에서 512 산출물 < 256 산출물; 역전은 TA 프로파일 변경과 동반; 1024→2048은 별도; U55 cap×지연 상호 의존 |
| `A9_s4_closure.md`, `s4_stall/` | U85 stall 이벤트 원시 수집 | **NOT_EVALUABLE, 종결** (qualification 1·2 실패: ACTIVE −12; 매니저 결정 (a)) | 첫 셀 qualification 실패로 캠페인 중단, 나머지 5셀 미실행, 원시값은 보존만 |
| `A10_revised_hypotheses.md` | 기각된 가설 1·4를 대체하는 후속 가설 H1′–H3′ (매니저 검토 반영 정정본) | 미검증 가설 (다음 계약 후보) | H1′ RNNoise 지연 민감도(실측 C(0)·ΔC, k = 실효 지연 민감도) · H2′-a 외부 대역폭 제약 / H2′-b 가중치 귀속 분리 · H3′ 블록 매핑 특성(ublock 면적 4→4) |
| `manager_log.md` | 매니저(ChatGPT 창) 교환 전문 | 기록 | 8회 교환 |
| `h13/` | **H13 검증 캠페인** (GO `docs/superpowers/plans/2026-09-14-h1-h3-verification-GO.md`, 계획서 `...-plan.md` A1–A7) — H1-A/B/C, H2-A, SRAM cap, H3 합성 51모델, H2-B-X, 진단 | S1–S5 완료, 131셀 게이트 전부 통과 | 결과 `h13/H13_RESULTS.md` §8 요인표. 분석기 `h13_analyze.py`(+unittest·mutation), 하니스 `h13_sweep.py`, 원시 `results.jsonl`·`uart/`·`verify/`·`vela/` |
| `h3r/` | **H3-R 보강 실험** (GO `docs/superpowers/plans/2026-09-15-h3r-verification-GO.md`, 계획서 `...-plan.md` **A8**) — H3의 두 통제 문제(형상별 양자화 · relaxed의 MAC 간 MAXR/MAXW 차이)를 제거하고 면적 36 형상 효과를 재측정. 27 파생모델 × 256/512 × base·equalized(+DW bridge) = 126 arm | 완료, 126 arm 게이트 전부 통과·거부 0건 | 결과 `h3r/H3R_RESULTS.md`. **두 통제 문제는 실재했으나 결과를 바꾸지 않았다** — base 54셀이 H3와 TOTAL·ACTIVE 모두 일치, DW의 bridge↔equalized는 7개 카운터 18/18 동일. 판정기 `h3r_analyze.py`(+fixture 28·돌연변이 23 RED), G1′ `check_g1prime.py`, 하니스 `h3r_sweep.py` |
| `manager_review_20260914_v7_directive.md` | A10 초판·발표 v7 구성에 대한 매니저 지시 전문 + 대조 체크리스트 C1–C15 | 기록 (발표·A10 작성 시 대조 기준) | H1′ 회귀계수, H2′ 귀속, H3′ ublock 면적 정정 지시; 20장 판정 문구; 21·22·후속가설 장 구성 |
| `ta_parameters.csv`, `vela_verbose/`, `x4/`, `s4_stall/` | 원시 증거·하니스·분석기·게이트 검사 | | 각 분석기는 unittest + 돌연변이 검사 |

재현: 각 문서 끝의 "재현" 절. 서버 증거 회수는 `x4/collect.sh`, `s4_stall/collect.sh`, `h3r/collect.sh`.
`h13/`에는 별도 README가 없고 이 표가 색인이다. H3-R은 `h13/`을 읽기만 하며, `h3r/h3r_analyze.py`의 보존 게이트가 h13 evidence 4개 파일의 sha256 불변을 검사한다.
