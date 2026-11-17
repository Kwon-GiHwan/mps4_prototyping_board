# 공유 identity 정정 — 기대 placement를 인자로 (유지보수, 2026-11-17)

지시: Stage 6B-E2E-B Phase 0(1.1 공유 모듈 정정 승인). 변경안: `results/fi101_stage6b/stage6be2ea/trackA/shared_module_change_proposal.md`.
기준 코드: `e53b618`(변경 전). 기존 원시 결과와 공식 판정 파일은 바꾸지 않았다.

## 변경

| 모듈 | 변경 |
|---|---|
| `stage4k.identity` | `expected_placement: int = 0` 인자 추가. `placement` 항 = 모든 RUN의 placement == 기대값. `regioncfg` 항 = n_base 5에서 그 placement의 값(0: 0x15F, 1: 0x153, 그 밖: 거짓) |
| `stage4aoe.identity_a1` | `expected_placement: int = 0`을 받아 K에 넘긴다. 기존 `drwl_placement`(RUN = DRWL header)와 `expected_agree`(manifest = header)는 그대로이므로 RUN = 기대값 = header가 함께 묶인다 |
| `stage6bb.identity_of` | 동결 manifest 항목의 `placement`를 넘긴다. 필드가 없으면(E2D 이전 manifest) 0 |

- 기대값은 manifest에서만 온다. RUN 기록에서 만들지 않는다(mutation `BB: from RUN`이 테스트로 잡힌다).
- 기본값 0이므로 인자 없이 부르는 과거 호출은 결과가 같다.
- E2D 원래 manifest(`e2d_manifest.json`, placement 필드 없음)로 boot 442를 판정하면 지금도 `placement` 항만 거짓이다. 즉 원래 판정(MEASUREMENT_INVALID)은 그대로 재현된다.

## 회귀 1 — 판정 단위 (`judges.sh`)

identity 경로의 판정 9개(4K, 4AO, 4AO-E A1, 4WD, 6B-B, E1, E1-R, E2B, E2D Amendment A)를 변경 전 코드(`e53b618` worktree)와 변경 후 코드로 같은 원시 자료에 실행했다.

- 변경 전 코드의 출력 11개 파일(summary 10, table 1)이 커밋된 결과와 바이트 단위로 같다. 인자가 원래와 같다는 확인이다.
- 변경 후 코드의 출력이 변경 전과 바이트 단위로 같다(`diff -r` 차이 없음). 따라서 커밋된 결과와도 같다.
- 4AO-E 원래 세션(boot 387, REGIONCFG 0x55F로 중단)은 summary가 없다. 아래 함수 단위 회귀에 포함된다.

## 회귀 2 — 함수 단위 (`regression.py`, `compare.py`)

- 대상: identity 경로 실험 9개의 `conds/*/wfe` 폴더 **76개 전부**.
  - 폴더마다 `K.identity`(기본값), `identity_a1`(그 workload의 A1 manifest에 config가 있을 때), `identity_of`(동결 manifest 항목 중 config와 boot가 맞는 것)를 계산했다.
  - E2D 원래 세션(440–442)은 Amendment A manifest의 같은 config·지연 항목으로도 계산했다(정정 기대값).
  - 결과 155건.
- 그 밖의 원시 자료:
  - reproduction reference 폴더(`ref/wfe`) 5개는 identity로 판정되지 않으므로 수만 센다.
  - 나머지 저장소 원시 파일(Track A 359개 중 identity 경로 밖)은 이 함수를 부르지 않으므로 바뀔 수 없다.
- 결과(`compare.json`): **REGRESSION_PASS**.
  - 같음 152건.
  - 예상된 변경 3건. 모두 SRAM 기대(manifest placement 1) + SRAM 관측(RUN placement 1)인 W0-P1이며, `identity_of`의 `placement` 항만 False → True로 바뀌었다(다른 항·필드 불변).
  - 예상 밖 차이 0건, 오류 0건.

| 폴더 | manifest 항목 | ok 전 → 후 |
|---|---|---|
| E2D 원래 세션 boot 442 `e2d_w0p1` | `e2d_manifest_a.json:W0-P1-L500` (재판정) | False → **True** |
| E2D-A boot 451 `e2d_w0p1` | `W0-P1-L500` | False → True |
| E2D-A boot 456 `e2d_w0p1` | `W0-P1-L1000` | False → True |

E2D-A 두 boot는 이미 E2D 계층의 `placement_identity`로 VALID였다. 이제 공유 경로만으로도 통과한다. E2D summary는 바뀌지 않는다(회귀 1).

## 테스트와 mutation

- `host/tests/test_identity_placement.py` 23개.
  - DRAM/DRAM PASS, SRAM/SRAM PASS, DRAM 기대/SRAM 관측 FAIL, SRAM 기대/DRAM 관측 FAIL
  - RUN 하나만 다름 FAIL, 모르는 placement FAIL, REGIONCFG 불일치 FAIL
  - workload digest 불일치 FAIL(`stage6bb.environment`)
  - 기본값 하위 호환(K, A1)
  - manifest 기반(boot 442 재판정 PASS, 원래 manifest는 placement 항만 FAIL, reference 종류)
  - 모든 호출 경로 회귀(`before.json` 대비 REGRESSION_PASS, 76/152/3/0)
  - `compare.py` 판정 자체(다른 항 뒤집힘, K 기본 경로 뒤집힘, 방향 반대, 다른 필드 동반, 폴더 집합 → 모두 FAIL)
- `mutate.py`: **21/21 KILLED**, 복원 sha256 확인, after restore GREEN(`mutation.txt`).
- `sh test.sh`: ALL PASS.

## 파일

`regression.py`, `compare.py`, `judges.sh`, `before.json`(변경 전 코드), `after.json`(변경 후 코드), `compare.json`, `mutate.py`, `mutation.txt`.
