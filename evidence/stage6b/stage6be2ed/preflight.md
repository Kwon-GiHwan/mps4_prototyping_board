# Stage 6B-E2E-D Preflight (2026-11-18, before boot 463) — **PASS**

동결 `9e02818`(펌웨어·공유 모듈 `14077be`). 모든 항목을 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 계약·manifest·판정 사전 동결 | `9e02818`에 계약, 판정, manifest, plan, session, 테스트 37개, mutation 58/58이 있다 | PASS |
| 2 | B3/B3w 정체성 | B3 `7b2cedd5…` = E2E-B B3. B3w `51ff7a4a…` = B3에서 offset 28만 1→2. 동반 파일 동일, golden `b9341e6f…` | PASS |
| 3 | Weight/Scale 원본·사본 | region 0 = 모델 offset 0x420의 flatbuffer 벡터 90,256 B(sha256 `c2fe2704…`, WEIGHT·SCALE만 사용). 사본은 펌웨어가 만든 뒤 바이트 비교하고, 다르면 remap하지 않는다(probe 테스트 `prep_corrupt`). 보드 사본의 바이트 일치는 출력 PASS_EXACT, EXT read 감소, REGIONCFG 0x550과 REGIONCFG_MATCH 플래그로 확인한다 | PASS(정적) / 보드에서 확인 |
| 4 | QBASE/command 경로 | remap은 index 0만 한다(계약 테스트). QCONFIG는 3으로 identity가 RUN마다 검사한다. command stream은 region 0 밖(offset 0x164f0) | PASS |
| 5 | base remap | 펌웨어가 BASEP0에 쓴 주소를 base0로 기록한다. 판정 `weights_where` = `0x31280420`(manifest) | PASS(정적) |
| 6 | SRAM 안전성 | 사본 `0x31280420–0x312964B0` < `0x31400000`. arena `0x31076770–0x31276770`, fast memory `0x31000000–0x31060000`과 겹치지 않음. 펌웨어는 창 밖이면 사본을 만들지 않는다(probe `wdst_2`) | PASS |
| 7 | 이미지 | 새 L500 두 번 빌드 동일. L1000은 RLATENCY 2바이트만 다름. 기존 이미지 대비 심볼 차이는 placement/remap 코드뿐. 빌드 게이트 OK. staging 8개 = manifest | PASS |
| 8 | 출력 reference·PMU | golden, ids·conditions = E2E-B | PASS |
| 9 | 안정성 기준 | 기존 5 %, pass A 대 B(`stage6bb.stability`) | PASS |
| 10 | TA readback | 판정은 capabilities 전체 = `caps_l500/l1000.json`, `ta_ext_rlatency`를 별도로 대조한다. build_id·schema가 같으므로 새 이미지에서도 같아야 한다. 첫 boot-check에서 확인한다 | 보드에서 확인 |
| 11 | B3 재현 기준 | 보드 dry run(E2E-B boot 458/460/461, boot 번호·이미지만 바꾼 임시 manifest): repro-gate PASS, B3-L500·B3-L1000 VALID, b3-gate PASS | PASS |
| 12 | 판정 코드 | 보드 `host/{analysis,lib}` 68개와 staging·workloads 49개, 합 117개 sha256 = Mac | PASS |
| 13 | 측정 전 상태 | boot 번호: 보드 최대 host_boot_index 462. boot-check B3w-L500 rc 1(UNMEASURED) | PASS |
| 14 | 복원 | `evidence_m6` 있음, 카드 마운트 0, run·evidence root 없음, `sudo_session.sh --check` OK(Mac·보드). 보드 디스크 여유 2.4 GB | PASS |
| 15 | 테스트 | `test.sh` ALL PASS | PASS |

새 이미지에서 처음 확인되는 것은 boot 463의 capabilities와 boot 465의 remap 동작이다. 어긋나면 그 boot-check(CONFIG_MISMATCH)나 b3-gate가 세션을 멈춘다.
