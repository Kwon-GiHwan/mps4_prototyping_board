# Stage 6B-E2E-A Track A — `stage4k.identity` placement 고정 항의 과거 영향 감사

계약 `evidence/stage6b/stage6be2ea/contract.md`(`603ed72`). 보드 없음. 산출물: `raw_scan.csv`(원시 파일 359개의 placement 값, 실험 묶음 35개), `trackA_summary.json`.

## 판정: **`NO_HISTORICAL_IMPACT`**

## 1. 호출 지점 (실제 코드 경로)

| 경로 | 실험 |
|---|---|
| `stage4k.config_result` → `identity` | Stage 4K |
| `stage4ao` → `K.identity` | Stage 4AO |
| `stage4aoe.identity_a1` → `K.identity` | Stage 4AO-E(원래, A1) |
| `stage4wd` → `stage4aoe.config_result` → `identity_a1` | Stage 4WD |
| `stage6bb.identity_of` → `K.identity`(REF) / `identity_a1` | 6B-B, E1, E1-R, E2B, E2D(원래) |
| `stage6be2d.placement_identity`(Amendment A)가 placement 항 대체 | E2D 정정 세션 |
| 쓰지 않음 | Stage 4 placement(`stage4p` 자체 placement 검사), Stage 4/4C/5, 그 밖 |

문서에 모듈 이름이 나오는 것과 실제 호출은 구분했다. 위 표는 import·호출 줄 기준이다.

## 2. 실험별 분류 (원시 RUN 기록의 placement 값 전수)

| 실험 | identity 경로 | 기록 placement | 분류 |
|---|---|---|---|
| Stage 4K, 4AO, 4AO-E, 4WD | 예 | {0} | UNAFFECTED |
| 6B-B, E1, E1-R, E2B | 예 | {0} | UNAFFECTED |
| **E2D 원래 세션(boot 440–442)** | 예 | {0, 1} | **JUDGE_FALSE_REJECTION**. 재판정과 재측정 모두 끝남 |
| E2D 정정 세션(449–457) | 정정 판정 | {0, 1} | UNAFFECTED |
| Stage 4 placement(boot 367–368) | 아니오(`stage4p`) | {0, 1} | UNAFFECTED |
| 그 밖 24개 묶음(stage1, 2a, 4, 4c*, 5, 5_2, driver_m7 등) | 아니오 | 필드 없음 또는 0 | UNAFFECTED |

- `stage4k.identity`를 거치는 실험 중 placement 1 기록이 있는 것은 E2D 원래 세션 하나뿐이다.
- Stage 4 placement의 SRAM 배치(boot 368)는 자체 판정을 써서 이 결함과 무관하다.

## 3. 재판정 (별도 산출물, 원래 판정 유지)

E2D boot 440–442를 정정 판정 코드(Amendment A `347712c`, `placement_identity`)로 다시 판정했다.
- 결과: REF VALID, W0-P0 VALID, W0-P1 VALID, 기준 게이트 PASS.
- 원래 판정 MEASUREMENT_INVALID는 그대로 둔다.
- 빠진 boot 443–448은 Amendment A 세션(449–457)으로 계약 전체를 다시 측정했다. 그래서 추가 재측정이 필요한 과거 실험은 **없다**.

## 4. 과거 결론에 대한 영향

없다. 결함은 거부(더 엄격) 방향으로만 작동하므로, 잘못 통과된 기록이 생길 수 없다. 거부된 것은 E2D 원래 세션뿐이다.

## 5. 공유 모듈 (A4)

- `stage4k.identity`는 바꾸지 않았다. 현재 동작을 고정하는 특성 테스트를 추가했다(`test_stage6be2ea.SharedIdentityCharacterisation`: boot 441 placement 0 → 참, boot 442 placement 1 → 거짓).
- 변경안: `shared_module_change_proposal.md`(미적용).
