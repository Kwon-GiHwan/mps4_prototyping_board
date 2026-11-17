# Stage 6B-E2B Preflight (2026-11-17, before boot 435) — **PASS**

동결 커밋 `f9b2344`. 아래 항목은 모두 실제로 실행해서 확인했다.

| 항목 | 확인 | 결과 |
|---|---|---|
| 이미지 L500 | `~/evsweep_s6be2b_l500`: boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…` = `70090f1` 기록(E1-R staging 사본) | PASS |
| 이미지 L1000 | `~/evsweep_s6be2b_l1000`: bram `fd478e2d…`(나머지 3개 L500과 같음) = Mac `image_l1000/image.sha256` = manifest. L500과의 차이는 TA EXT RLATENCY 상수 2바이트(`phase1_ta.md`) | PASS |
| TA 설정·readback | 12-bit 필드에 1000. 판정 코드가 boot마다 RUN 전 capabilities 전체를 조건별 기대값과 대조(`caps_l500.json` = boot 375 사본, `caps_l1000.json` = 같고 `ta_ext_rlatency` 1000) | PASS |
| 워크로드 | DRWL 3개 sha256: Mac = 보드 staging = manifest. 같은 워크로드는 두 이미지 staging에서 같은 파일 | PASS |
| Vela 대응 | predictions.json = E2A facts(기준 대 `Dram_read_latency_1000`), Vela 출력 sha256 동일, cms sha256 = 측정 DRWL 기록 | PASS |
| PMU·pass | `ids.txt`·`conditions.txt` = E1-R와 같은 Stage 4 pass A·B(`wfe 0 0 off 1,2`) | PASS |
| 입력·출력 reference | REF: Stage 4K tflite_ofm. G12·CONV: `ref_ofm.bin`(6B-B·E1-R 그대로) | PASS |
| 판정 코드 | 보드 `~/evsweep/host/analysis/stage6be2b.py` sha256 `d2edcae9…` = Mac. 의존 모듈 5개(stage6bb, stage4k, stage4aoe, stage4, stage4ao) sha256 = Mac. `sync.sh board` OK | PASS |
| 사전 테스트 | `sh test.sh` ALL PASS. test_stage6be2b 15 tests, mutation 31/31 KILLED | PASS |
| dry run | Mac: 기존 boot 428·429·411 자료 VALID 3개, repro-gate PASS, L1000 키를 L500 자료에 적용하면 CONFIG_MISMATCH. 보드: 측정 전 boot-check UNMEASURED(rc 1), 기존 E1-R run root에 repro-gate는 boot index로만 FAIL | PASS |
| 기준 형상 재현 | REF는 boot 375 사본(`~/evsweep_s6be1r/ref/wfe`) 대비 `stage4k.reproduce` | 준비됨 |
| boot 번호 | 보드 원시 자료 최대 host_boot_index 434. run root·evidence root 4개 모두 없음 | PASS |
| 복원 | `~/evsweep/evidence_m6` 있음. 세션 = deploy → restore → deploy → restore → postflight. 카드 마운트 0 | PASS |
| 세션 | `~/evsweep_s6be2b_l500/session.txt` sha256 `085f10d2…` = Mac, `sudo_session.sh --check` SESSION OK | PASS |
| 디스크 | 보드 host 여유 2.5 GB(95 % 사용). 이 세션 원시 자료는 수 MB | 주의, 진행 가능 |
