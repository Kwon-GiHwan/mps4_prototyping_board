# Stage 6B-B Preflight (2026-11-15, before boot 410) — **PASS**

계약 `contract.md`, 판정 코드와 manifest는 `0a99697`에서 동결했다. 아래는 모두 실행해서 확인한 것이다.

| # | 지시 §3 항목 | 확인 | 결과 |
| --- | --- | --- | --- |
| 1 | 검증된 Driver Runner | staging 이미지 sha256: boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…` = `70090f1`(Stage 4K·4AO-E와 같음, `~/evsweep_s4aoe2`에서 복사). 판정 코드가 모든 RUN의 이미지 digest를 다시 확인한다 | PASS |
| 2 | TA profile 1 적용 | 기준 `capabilities.json`(boot 375)의 TA 레지스터 22개 = `pmwl.TA_PROFILES[1]`(불일치 0). 측정 boot마다 판정 코드가 capabilities를 이 기준과 대조한다(펌웨어가 boot 때 읽은 값) | PASS |
| 3 | 보드 이미지·펌웨어 | 위 1과 같다. FPGA `FI101*`, NPU CONFIG macs 필드 10 = 1024 MAC(기준 capabilities) | PASS |
| 4 | SRAM/DRAM region 배치 | DRWL 11개 모두 placement 0이다. n_base는 header(3 + 입력 + 출력)와 manifest가 같다: 기준 5(REGIONCFG 0x15F), A2 6(0x55F). `stage6bb.static_checks` ok | PASS |
| 5 | 11개 binary·digest 고정 | `workloads/stage6bb_manifest.json`, `workloads.sha256`(커밋됨). staging 59개 파일 sha256이 Mac과 보드에서 같고, AppleDouble 0개 | PASS |
| 6 | PMU 이벤트·pass 호환 | `ids.txt`, `conditions.txt`가 Stage 4K와 바이트 단위로 같다. 8 카운터 × 2 pass, 두 pass 모두 35 포함 | PASS |
| 7 | 출력 reference·입력 digest | manifest에 기준 tflite_ofm sha와 A2별 golden·fixture IFM·MLEK 입력 sha256·입력 shape·dtype·quant가 있다 | PASS |
| 8 | Vela 사이클과 산출물 대응 | manifest의 Vela `vela_sha256`이 각 DRWL meta의 `vela_sha256`과 같다(Amendment B `vela` 수집 시 레코드와 일치 확인). 범위는 A2 graph `cycles_total`. static check ok | PASS |
| 9 | 복구 가능 | `~/evsweep/evidence_m6` 있음. 세션 파일에 `restore_mlek` → `postflight`가 있다. 실패 시 `sudo_session.sh`가 열린 deploy를 복원한다. 카드는 마운트되지 않았다 | PASS |

기준 형상의 의미는 다음과 같다.
- 같은 DRWL(`6eb390be…`, Stage 4K boot 375와 sha256이 같음), 같은 이미지, 같은 TA, 같은 pass로 실행한다.
- 따라서 Stage 4K 수치를 직접 재현 기준으로 쓸 수 있다.
- 보드의 boot 375 원시 데이터는 Mac evidence와 sha256이 같다.

보드 dry run(동결 코드, 보드에서 실행)은 다음과 같다.
- `repro-gate`: boot 375 데이터에 manifest boot 번호만 375로 바꾼 사본을 쓰면 PASS다(mac, dpu, output, constant counters, npu_active 모두 true).
- 실제 manifest(boot 410)에서는 같은 데이터가 FAIL(`boot index`)로 나온다. 옛 데이터를 새 측정으로 오인하지 않는다는 확인이다.
- 측정 전 `s6bb_g12`에 대한 `boot-check`는 rc 1(UNMEASURED → 중단)이다.

나머지 확인 사항은 다음과 같다.
- 판정 코드 13개 파일(host/analysis 7, host/lib 6)의 sha256이 Mac과 보드에서 같다. `sync.sh board` OK.
- 세션 파일 `~/evsweep_s6bb/session.txt` sha256 `8d029e4a…` = Mac이고, `sudo_session.sh --check` OK다.
- boot 410–420은 쓰인 적이 없다(보드·Mac 최대 409). `~/evsweep_s6bb_run`, `evidence_s6bb`는 없다.
- `sh test.sh` ALL PASS, mutation 45/45 KILLED.
