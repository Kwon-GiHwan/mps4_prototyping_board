# remeasure/ — R1 재측정 (U85 whole-model 메모리 카운터 회수)

v1.2까지 U85 35셀 전부에서 비어 있던 SRAM/EXT 카운터 네 개를 재측정으로 회수한
작업 일체. **측정이 아니라 판독이 문제였다** — 자세한 진단은 `../SERVER_VERIFICATION.md`
V3, 회수 경위는 `../CHANGELOG.md` v1.3.

## 순서 — 계약이 데이터보다 먼저다

`REMEASURE_CONTRACT.md`는 **데이터를 얻기 전에** 동결했다 (sha256 `88d9eb65…`).
셀 목록·반복 횟수·게이트 G1–G5·판정 기준이 전부 그 안에 있다. 결과를 보고 기준을
고른 것이 아니라는 것이 이 순서로 증명된다. git 이력도 같은 순서다 —
하네스와 게이트 커밋(`5a061fb`)이 데이터 커밋(`a2ea066`)보다 앞선다.

## 파일

| 파일 | 역할 |
|---|---|
| `REMEASURE_CONTRACT.md` | **동결된 계약.** 데이터 취득 전 작성 |
| `remeasure_u85.py` | 측정 하네스. `stage1`을 **import**한다 |
| `gates.py` | G1–G5 판정. 35/35에서만 PASS |
| `test_gates.py` | **뮤테이션 테스트.** 각 게이트를 데이터에서 무력화해 FAIL 발화 확인 |
| `R1_RAW.json` | 원시 기록 — 셀별 빌드 해시, 게이트 결과, 2회 반복 전 필드 |
| `R1_MEMORY_COUNTERS.csv` | 회수된 값 (35행). 파생 표가 이걸 출처로 결합한다 |
| `R1_RESULTS.json` | 게이트 판정 결과 (기계 판독용) |
| `R1_GATE_REPORT.md` | 게이트 판정 결과 (사람 판독용) |
| `uart/` | **원시 UART 71개.** 이번엔 보존했다 |

## 왜 재구현하지 않고 import 했나

`remeasure_u85.py`는 `stage1.py`를 import한다. 빌드·해시 게이트·FVP 호출이
*같은 방식*이 아니라 **같은 코드**여야, 회수값을 기존 셀에 붙이는 것이 정당해지기
때문이다. 파서만 `pmuparse`로 교체했고, 원시 UART를 워크스페이스 밖에 보존한다.

## 결과

```
R1_GATES: PASS
  G1_artifact_reproduction        35/35   frozen anchor 해시 바이트 재현
  G2_total_cycles_match_frozen    35/35   TOTAL == frozen canonical_cycles
  G3_active_cycles_match_frozen   35/35   ACTIVE == frozen
  G4_repetition_identical         35/35   R1 == R2 전 필드
  G5_memory_counters_present      35/35   SRAM/EXT 4종 존재
```

**G1–G3이 핵심이다.** 같은 실행 파일이 같은 사이클을 냈으므로, 그 실행에서 나온
메모리 값도 그 셀의 것이다. 이 셋이 깨졌다면 계약에 따라 회수값을 붙이지 않는다.

## 재현

```sh
python3 gates.py          # R1_RAW.json -> 게이트 판정 + CSV + 리포트
python3 test_gates.py     # 뮤테이션 테스트 9건
```

측정 자체의 재현은 서버 컨테이너가 필요하다 (`remeasure_u85.py`, 35셀 × 2반복).

## 건드리지 않은 것

frozen `analysis/canonical_cells.csv`. U85 행의 `axi*_beats`는 앞으로도 비어 있다.
회수값은 이 디렉터리에 별도로 두고, 파생 표에서 **출처 컬럼과 함께** 결합한다.
