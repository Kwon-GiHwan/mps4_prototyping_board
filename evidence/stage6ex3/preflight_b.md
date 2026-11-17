# Stage 6E-X3 Amendment B Preflight — 2026-11-18, before boot 487: **PASS**

동결 `6b292d8`. 이미지·워크로드·펌웨어는 Amendment A preflight(`dc7709c`)와 같다. 모든 항목은 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 새 G1 판정 로직 | `test_stage6ex3` 28개(허용폭 경계, R_cap, 결정적 카운터 13개의 값·RUN 변동·m7 변동, 비결정 카운터, warm-up 제외, 기준 m7 BASE 세트 구분), mutation 81/81. test.sh ALL PASS | PASS |
| 2 | m7 원시 분포 | 허용폭 사전 계산(`amendment_b.md` §1): kws 918.2–4,846(1–5.28 %), ad 1,459.5–4,370(1–2.99 %). 결정적 카운터 13개는 m7 kws·ad 모두 range 0 | 기록 |
| 3 | Flag 0/1 PMCR, PMU_MASK, KERNEL_WAIT, 스트림 동일성, 그룹 창 경계, golden | Amendment A preflight 2–7과 같은 산출물(digest 동일). 그룹 창 동작은 세션 GM gate로 판정 | PASS(재사용) |
| 4 | digest | 보드 staging `~/evsweep_x3b_img` 28개 = Mac(이미지 4, DRWL 10, manifest, ids, conditions, plan 10, session). 보드 코드 79개 = Mac. 기준 파일 3개(m7 kws·ad raw, caps) = Mac | PASS |
| 5 | 판정 경로 | 보드에서 빈 run root로 boot-check → UNMEASURED | PASS |
| 6 | 보드 상태 | 최대 host_boot_index 477(487–496 미사용). 카드 마운트 0, /dev/sdb1 없음, `evidence_m6` 있음, x3b 경로 없음(새로 만듦). 디스크 여유 2.3 GB. `sudo_session.sh --check` OK(Mac·보드) | PASS |
| 7 | 기존 결과 불변 | boot 477 원시 자료·`result_g1.md`·preflight `dc7709c` 변경 없음(git) | PASS |
