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
| `manager_log.md` | 매니저(ChatGPT 창) 교환 전문 | 기록 | 7회 교환 |
| `ta_parameters.csv`, `vela_verbose/`, `x4/`, `s4_stall/` | 원시 증거·하니스·분석기·게이트 검사 | | 각 분석기는 unittest + 돌연변이 검사 |

재현: 각 문서 끝의 "재현" 절. 서버 증거 회수는 `x4/collect.sh`, `s4_stall/collect.sh`.
