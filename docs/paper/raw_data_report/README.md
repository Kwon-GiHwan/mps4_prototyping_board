# Raw data audit — working directory

**이 디렉터리는 논문 원고가 아니다.** 현재 manuscript의 섹션 순서를 따라 기존
raw/frozen evidence에 실제로 어떤 데이터가 있는지 재집계한 **감사 보고서**다.

## 원칙 (지시문 §0)

- 기존 manuscript / frozen evidence / CSV / JSON / UART log **수정 금지**
- 데이터를 보고 threshold를 새로 고르지 않음
- 누락 데이터를 0으로 간주하지 않음
- compiler estimate와 runtime observation을 같은 종류로 취급하지 않음
- cross-platform absolute cycle 비교로 architecture superiority 주장 금지
- 검증되지 않은 인과를 `caused by` / `memory-bound` / `bandwidth saturation`으로 단정 금지
- manuscript narrative가 raw data와 충돌하면 **data를 따름**
- FVP / board 재실행 없음 — 기존 evidence 집계만

## 구성

```
REPORT.md                     본문
CHANGELOG.md                  버전 이력 (수정·재계산 발생 시 기록)
provenance/INPUT_MANIFEST.csv 입력 artifact 목록과 해시
provenance/BASELINE_HASHES.txt 작업 전 frozen evidence 해시 (불변 검증용)
tables/*.csv                  생성 표
figures/*.png|svg             생성 그림
scripts/*.py                  모든 표·그림 재생성 코드
```

모든 표와 그림은 `scripts/`로 재생성 가능해야 한다.

## 재생성

```sh
python3 docs/paper/raw_data_report/scripts/build_all.py
```
