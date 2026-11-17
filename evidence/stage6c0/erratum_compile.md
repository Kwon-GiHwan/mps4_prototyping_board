# 정오표 — 컴파일 검증 스크립트 (2026-11-18, 동결 74aa09d 뒤)

- 현상: `s6c_f2_c16`(DW C 8 → 16)에서 TFLite가 모델을 거부했다("8 zero_point values and 16 scale values").
- 원인: `stage6c0_models.variant`가 per-channel scale만 16개로 늘리고 zero point는 그대로 두었다. 도구 결함이다.
- 조치: scale과 zero point를 함께 늘리고(`_ext_q`, `_dup_q`) 8개 형상을 두 번 다시 컴파일했다.
- 영향: 선정 규칙(`stage6c0.py`), 기준, 대표·통제 형상 정의는 바뀌지 않는다. 다른 7개 형상의 사실은 수정 전과 같아야 하며, 비교로 확인한다.

# 정오표 2 — 통합 로더 (2026-11-18, 결과 작성 중)

- 현상: 통합표에 Stage 4WD 행이 없었다.
- 원인: 로더가 `wd_inventory.csv`에서 `stage == "stage4wd"` 행을 찾았지만, 이 파일은 4WD 이전 단계의 39개 실행 목록이라 4WD 자신의 행이 없다. 4WD 보드 값(boot 402–409)은 `results/fi101_stage4wd/summary.json` configs에 있다.
- 조치: 4WD 로더를 `summary.json` configs(pass A·B 중앙값)로 바꿨다. 선정·분류 규칙과 상수는 바뀌지 않는다. 테스트에 4WD 행 존재를 추가했다.
