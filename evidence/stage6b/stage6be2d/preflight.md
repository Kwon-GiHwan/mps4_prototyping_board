# Stage 6B-E2D Preflight (2026-11-17, before boot 440) — **PASS**

동결 `3ca60a7`. 모든 항목을 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 두 이미지의 TA 차이 | L500 = `70090f1`(boot `718c4562…`, bram `c80e77df…`). L1000 = bram `fd478e2d…`. 차이는 EXT RLATENCY 상수 2바이트(E2B `phase1_ta.md`). 보드 staging digest = manifest | PASS |
| 2 | L500 기존 결과 재현 가능성 | W1-P1 DRWL = E2B boot 436/438의 DRWL(`928296b1…`). 판정 dry run에서 E2B 원시 자료 VALID(99,866 / 158,707.5, MAC 20,736) | PASS |
| 3·4 | TA readback·나머지 TA 불변 | boot마다 RUN 전 capabilities 전체 = `caps_l500.json`/`caps_l1000.json`(E2B와 같은 파일). `ta_ext_rlatency`도 별도로 대조 | 판정 코드에 고정 |
| 5 | 입력·출력 | 4개 workload: golden = BUILTIN_REF 출력 `b9341e6f…`, 최적화 커널과 차이 0. W0 IFM = A2 Conv 입력(CPU), A0 출력 = A2 conv_out | PASS |
| 6 | DRWL·binary digest | 컨테이너 2회 빌드 바이너리 동일. Mac = 보드 staging = manifest(DRWL 5개) | PASS |
| 7 | 메모리 영역·buffer 충돌 | arena: W0 141,312, W1-P0 215,040, W1-P1 141,312(≤ 2 MiB TFLM arena). fast: W1-P1 147,456(≤ driver fast 0x60000 = 393,216), 나머지 0. W1-P0의 그래프 IO(a 73,728–144,384, b 144,384–215,040, ofm 0–70,656)는 서로 겹치지 않는다. W0-P1의 SRAM arena(fast 뒤 64 KiB 정렬 + 모델 오프셋, 2 MiB)는 0x31400000 아래에 들어간다(Stage 4 placement와 같은 계산). 펌웨어가 load 때 패턴·보수 되읽기를 하고, 실패하면 NACK이며 RUN이 없다 | PASS |
| 8 | W1-P0/P1 실행 구성 | kernel 3개(ELEMENTWISE, CONV, ELEMENTWISE) 순서 같음, DMA 0. 세 kernel 모두 레지스터 차이는 ADDRESS뿐(base·region) | PASS |
| 9 | W0-P0/P1 | command stream 바이트 동일, DRWL header word 7만 다름 | PASS |
| 10 | PMU pass·판정 | ids/conditions = E2B. 판정 코드 sha256(stage6be2d `72529661…`, 의존 6개) Mac = 보드. 측정 전 boot-check UNMEASURED. test.sh ALL PASS, mutation 30/30 | PASS |
| 11 | 기준 형상·측정창 | REF는 boot 375 사본 대비 `stage4k.reproduce`(E2B boot 435 PASS) | 준비됨 |
| 12 | 복원 | `evidence_m6` 있음, 세션 = deploy → restore → deploy → restore → postflight, 카드 마운트 0, run root·evidence root 없음, `sudo_session.sh --check` OK(session `d8edc748…` = Mac) | PASS |
| — | boot 번호 | 보드 최대 host_boot_index 439(E2B). 440–448은 쓰인 적 없음 | PASS |
| — | 디스크 | 보드 host 여유 2.5 GB | 주의, 진행 가능 |
