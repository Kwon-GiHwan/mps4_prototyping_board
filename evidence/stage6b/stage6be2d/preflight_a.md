# Stage 6B-E2D Amendment A Preflight (2026-11-17, before boot 449) — **PASS**

동결 `347712c`. 원래 preflight(`preflight.md`) 항목 1–12를 다시 확인했고, 아래는 새로 확인하거나 바뀐 것이다.

| 항목 | 확인 | 결과 |
|---|---|---|
| boot 번호 | 보드 원시 자료의 최대 host_boot_index는 442다. 449–457은 쓰인 적이 없다. 새 run root·evidence root는 없다 | PASS |
| 이미지·DRWL | `~/evsweep_s6be2d_a_l500`·`_l1000`의 이미지 4개와 DRWL 5개(4개) sha256 = 원래 동결값 = manifest | PASS |
| 판정 코드 | 보드 `stage6be2d.py` `c8cadc3d…` = Mac. manifest `e2d_manifest_a.json` `a54736c3…` = Mac. 공유 모듈은 바뀌지 않았다(원래 preflight와 같은 sha256) | PASS |
| placement identity | 보드에서 정정 판정 코드로 원래 boot 440–442를 다시 판정했다(boot 번호만 바꾼 임시 manifest): REF·W0-P0·W0-P1 VALID, repro-gate PASS. Mac 회귀 테스트로 기대 placement 대 관측이 다르면 CONFIG_MISMATCH, REGIONCFG를 조작하면 CONFIG_MISMATCH임을 확인했다 | PASS |
| 측정 전 상태 | boot-check W0-P1-L500 = UNMEASURED(rc 1) | PASS |
| 세션 | `~/evsweep_s6be2d_a_l500/session.txt` `77500713…` = Mac, `--check` OK, 카드 마운트 0, `evidence_m6` 있음 | PASS |
| 테스트 | `test.sh` ALL PASS(공유 모듈 테스트 포함), E2D 15 tests, mutation 35/35 | PASS |
