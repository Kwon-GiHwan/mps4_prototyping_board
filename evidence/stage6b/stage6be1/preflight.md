# Stage 6B-E1 Preflight (2026-11-15, before boot 421) — **PASS**

동결 커밋은 `3a83175`(계약 `d39448c`)이다. 아래는 모두 실행해서 확인한 것이다.

| 항목 | 확인 | 결과 |
| --- | --- | --- |
| 이미지·Runner | staging digest: boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…` = `70090f1`(6B-B와 같음). 판정 코드가 모든 RUN에서 다시 확인한다 | PASS |
| TA profile 1 | 기준 capabilities(boot 375)의 TA 레지스터 = `pmwl.TA_PROFILES[1]`(6B-B preflight에서 확인). boot마다 capabilities를 대조한다 | PASS |
| 같은 산출물 | staging 44개 파일 sha256이 Mac과 보드에서 같고, AppleDouble 0개다. 7개 DRWL sha256 = manifest. 신규 6개는 두 번 독립 빌드해 같았다(`build.json` `deterministic`) | PASS |
| 메모리·정체성 | 7개 모두 n_base 5(header = manifest), REGIONCFG 0x15F, placement 0 | PASS |
| PMU·pass | `ids.txt`, `conditions.txt`가 6B-B와 같다(= Stage 4K) | PASS |
| 입력·출력 reference | golden = BUILTIN_REF(신규 6개; 최적화 커널 출력과 같음, `opt_vs_ref` 0). 기준은 Stage 4K tflite_ofm. N_MAC = H·W·Cin·Cout | PASS |
| 예측 동결 | `workloads/predictions.json`(H1-UC 정수 예측 + 경쟁 가설 8 + DPU 3)이 `3a83175`에 있다 | PASS |
| 기준 형상 | 6B-B·Stage 4K와 같은 DRWL `6eb390be…`, 같은 이미지·TA·pass. Stage 4K boot 375 수치를 직접 재현 기준으로 쓴다 | PASS |
| 판정 코드 | 보드의 `stage6bb.py`와 의존 모듈 13개 sha256 = Mac(`stage6bb.py`는 6B-B 동결본에서 바꾸지 않음) | PASS |
| 보드 dry run | `repro-gate`: boot 375 데이터 + manifest 사본(boot 375)으로 PASS. 실제 manifest(boot 421)로는 FAIL(`boot index`). 측정 전 E1 `boot-check`는 rc 1 | PASS |
| 복구 | `evidence_m6` 있음, 세션에 restore_mlek → postflight, 카드 마운트 안 됨 | PASS |
| 세션 | `~/evsweep_s6be1/session.txt` sha256 `21284a50…` = Mac, `sudo_session.sh --check` OK. boot 421–427은 쓰인 적 없음(보드 최대 420). `evsweep_s6be1_run`, `evidence_s6be1` 없음 | PASS |
| 테스트 | `sh test.sh` ALL PASS, E1 mutation 25/25 KILLED | PASS |
