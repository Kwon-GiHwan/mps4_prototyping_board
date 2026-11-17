# Stage 6B-E2B Phase 1 — TA 변경 가능성 (보드 전, 2026-11-17)

| 항목 | 확인 | 결과 |
|---|---|---|
| RLATENCY 폭 | core-platform `timing_adapter.c`: `TA_RLATENCY_MASK 0x00000FFF`, `ta_set_rlatency`가 `val & mask`를 쓴다. 헤더·MLEK cmake 주석 "12-bit field" | 1000 < 4096, 지원 |
| 설정 경로 | driver runner는 TA를 blob이 아니라 MLEK 플랫폼 초기화로 설정한다(`npu_ta` 컴포넌트, `TA_CONFIG_FILE=ta_config_u85_sys_dram_mid`, cmake.log). `EXT_RLATENCY`는 그 파일의 CACHE 변수라 `-DEXT_RLATENCY=1000`로 바꿀 수 있다. MLEK 트리는 바꾸지 않는다(빌드 스크립트가 전후로 확인) | 가능 |
| 빌드 재현 | 현재 HEAD의 firmware·빌드 스크립트는 `70090f1`과 같다(`git diff 70090f1 HEAD` 없음). 다시 빌드한 L500의 boot `718c4562…`, bram `c80e77df…`, images.txt `af688281…`가 기록과 같다. 빌드가 만드는 ddr.bin은 빈 파일이고, 보드에서는 기존과 같이 16 B 0 파일(`374708ff…`)을 쓴다 | PASS |
| L1000 이미지 | `DRV_EXTRA_CMAKE=-DEXT_RLATENCY=1000`. boot·images.txt는 같고 bram만 다르다(`fd478e2d…`). **bram 차이 2바이트**(오프셋 637501–637502: `F4 01` → `E8 03`, 500 → 1000). ELF 디스어셈블리 차이는 데이터 1줄(0x1209ba30: `00000040 00000020 00000000 000001f4` → `…000003e8`, EXT 설정 구조체 maxr 64, maxw 32, maxrw 0, rlatency). 심볼 표 동일 | TA 상수만 다름 |
| 첫 L1000 빌드 실패 | 처음에는 `git archive HEAD`로 소스를 옮겨 커밋 전 빌드 스크립트 수정이 빠졌다. 그래서 옵션이 전달되지 않았고 L500과 같은 이미지가 나왔다. 수정본을 복사해 새 출력 디렉터리(`/work/s6be2b_img_l1000b`)로 다시 빌드했다. 첫 출력(`/work/s6be2b_img_l1000`)은 쓰지 않는다 | 기록 |
| TA 인스턴스 | `TA_EXT` 0x51102400 = MLEK mps4 `TA_EXT_BASE`(cmake.log "using TA_SRAM_BASE @ 0x51102000; TA_EXT_BASE @ 0x51102400"). runner `platform.cc`가 같은 주소를 읽는다 | 확인 |
| readback | runner가 boot마다 RUN 전에 두 TA의 11개 레지스터를 capabilities로 읽는다(`run_driver_events.py`). 판정은 L1000에서 `caps_l1000.json`(= boot 375 사본에서 `ta_ext_rlatency`만 1000)과 전체가 같고 `ta_ext_rlatency` = 1000일 때만 받아들인다 | 판정 코드에 고정 |
| 다른 TA 값 불변 | 위 caps 전체 일치 조건(SRAM 11개, EXT 10개) | 판정 코드에 고정 |
| command stream·데이터 | 두 조건이 같은 DRWL 파일을 쓴다(manifest sha256). Vela 출력은 지연 500/1000에서 바이트 동일 | 확인 |
| 복원 | 세션: deploy L500 → restore → deploy L1000 → restore → postflight. 실패하면 `sudo_session.sh`가 열린 deploy를 복원 | 세션 `--check` OK |
| 판정 코드 dry run | 기존 boot 428(REF)·429(CONV)·411(G12)에 boot 번호만 바꾼 manifest를 쓰면 VALID 3개, repro-gate PASS. L1000 키를 L500 자료에 적용하면 CONFIG_MISMATCH(image bram, RLATENCY read-back, identity capabilities) | PASS |
