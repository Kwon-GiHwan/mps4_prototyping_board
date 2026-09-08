# 변경 이력

수정·재계산이 발생하면 새 버전을 추가한다. 이전 기술은 지우지 않는다.

## v1.0 — 2026-09-09

최초 생성. 기존 frozen evidence 무수정 집계. 표 15 · 그림 15(PNG+SVG) · provenance 4.
검증 10/10 통과.

### 작업 중 발생한 재계산 (v1.0 내부)

| # | 사항 | 조치 | 근거 |
|---|---|---|---|
| R1 | 3.3 점 데이터 출처를 `analysis/scaling.csv` → `analysis/canonical_cells.csv`로 변경 | 재계산 | `scaling.csv`가 측정된 셀 `SSE-300/u55/wav2letter@256`을 사다리 baseline 결측을 이유로 점 행에서 누락. 측정 데이터를 버리지 않기 위함 |
| R2 | `scaling.csv`가 점 행(73)과 전이 행(56) 혼합 파일임을 확인 | 파서 분리 | `mac` 컬럼에 `32->64` 형태가 섞여 있음 |

두 조치 모두 **기존 파일을 수정하지 않았고**, 재계산 결과는 frozen 집계와 일치한다
(53 evaluable transition, legacy `<0.50` 규칙 2건 = manuscript의 `WEAK_OR_SATURATED | 2`).

### 검사기 결함 정정 (v1.0 내부, 데이터 아님)

| # | 검사 | 결함 | 조치 |
|---|---|---|---|
| C1 | #1 evidence 불변 | `.omc/state/...` 플러그인 세션 파일을 evidence로 오인 | 검사 범위에서 `/.omc/` 제외. **실제 evidence는 무수정 확인** |
| C2 | #1 evidence 불변 | baseline은 상대경로, 검사는 절대경로 → 전량 불일치로 오판 | repo 루트 기준 경로 정규화 |
| C3 | #9 figure 추적 | 파일명이 동적 생성이라 소스에 리터럴 부재 | 파일명 대신 SVG에 삽입된 `source: tables/*.csv` 스탬프로 검증 |
| C4 | #9 figure 추적 | 태그 제거 정규식이 스탬프(주석 내부)를 함께 삭제 | 원문에서 검색 |

C1은 결과적으로 **frozen evidence가 실제로 무수정임을 확인**한 것이다.
