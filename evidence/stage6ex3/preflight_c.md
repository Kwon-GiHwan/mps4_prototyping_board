# Stage 6E-X3 Amendment C Preflight — 2026-11-18, before boot 497: **PASS**

동결 `9081e77`. 펌웨어·이미지·워크로드는 이전 preflight와 같다. 모든 항목은 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 판정 수정 범위 | 그룹 창 GS 기준(cap kws 2,423 / ad 2,596, m7 원시 자료에서 다시 계산해 일치, sha 확인), 지시 §5의 네 판정 항목, H-V 잡음 판별. B0·B1 안정성, pass B·C 안정성, G1(Amendment B), 가설 기준값은 변경 없음(테스트 34개로 확인) | PASS |
| 2 | mutation | 98/98 KILLED(새 규칙 경계, root 경로, 잡음 판별, 네 판정 포함). test.sh ALL PASS | PASS |
| 3 | 재사용 boot | 보드 `~/evsweep_x3b_run` 원시 자료 = `evidence/stage6ex3/raw_b.sha256`(일치). 보드에서 새 판정 코드로: kws B0 VALID + G1 PASS, kws B1 VALID | PASS |
| 4 | digest | staging `~/evsweep_x3c_img` 26개(이미지 4, DRWL 10, manifest, ids, conditions, plan 8, session) = Mac. 코드 79개 = Mac. 기준 파일 3개 = Mac | PASS |
| 5 | 판정 경로 | boot-check kws B2(root c 비어 있음) → UNMEASURED rc 1 | PASS |
| 6 | 보드 상태 | 최대 host_boot_index 489(497–504 미사용), 카드 마운트 0, /dev/sdb1 없음, `evidence_m6` 있음, x3c 경로 새로 만듦, 디스크 2.3 GB, `sudo_session.sh --check` OK(Mac·보드) | PASS |
| 7 | 기존 결과 불변 | boot 477·487–489 원시 자료와 판정 문서 변경 없음(git) | PASS |
