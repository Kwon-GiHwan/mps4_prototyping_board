# Stage 6E-X3 Preflight (amendment A) — 2026-11-18, before boot 477

이전 정적 preflight `e8f75d3`의 결과는 FAIL이었다(mask_en 미설정). 이 문서는 amendment A 수정 뒤의 preflight이며 결과는 **PASS**다. 모든 항목은 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 동결 | 계약·판정·워크로드·세션 `1d6e715`. test.sh ALL PASS, mutation 70/70(판정·스트림 편집), 14/14(펌웨어) | PASS |
| 2 | 펌웨어 수정 | `f0baf8c`. host sim: flag 0 → PMCR 0x2001 → 0x2007(mask_en 0), flag 1 → 0x200F(다른 비트 보존), flag 1 다음 flag 0 load → mask_en 0(누출 없음), 반복 RUN 유지, 알 수 없는 비트 → load 0x108. record schema 5(pmu_flags, pmcr_after_arm), schema 3·4 파싱 유지 | PASS |
| 3 | 이미지 | 컨테이너 빌드 2회 동일: boot `3b4af743`, bram `9b1844a3`, images.txt `af688281`(14077be와 같음). ddr.bin은 빌드 결과 0 B → 기존과 같은 16 B 0(`374708ff`) 사용. ELF 심볼 차이(`image/symdiff_vs_14077be.txt`)는 의도한 변경뿐이다: drwl_parse, ethosu_address_remap, pmu_session_arm, pmu_session_set_mask_en·mask_en(신규), record_serialise, runner_poll, out.3(+8 B), wl(+4 B). 빌드 gate(driver hook, SRAM 배치) OK | PASS |
| 4 | KERNEL_WAIT | 인코딩: Vela 원본 yolo 스트림의 KERNEL_WAIT n=1 = `0x00010012` → n=0 `0x00000012`. 의미(TRM 102685, 2B-3 인용): "Wait for n or fewer kernel operations to be remaining before starting the next command"; mem2mem DMA는 기다리지 않음 → 계약 §1 한계로 기록 | PASS(정적) |
| 5 | PMU_MASK | PMCR.mask_en은 DRWL pmu_flags로 켜진다(2). 실제 계수 제어는 정적으로 증명할 수 없어 세션 안 GM gate(M2·M3·M4)로 판정하며, 실패하면 ad 전에 멈춘다. 경계 위치는 독립값(6C F5 26,090)으로 확인한다 | 세션 gate |
| 6 | 워크로드 | B0 = m7 DRWL 바이트 그대로(kws `c77bf2b7`, ad `9d8b45ad`). B1–B4: 삽입 단어를 빼면 원래 스트림과 동일(8/8). 컨테이너 tflite 독립 확인 10/10: 단일 ethos-u op, 다른 버퍼·텐서·연산 I/O 동일, 원래 범위에서 바뀐 바이트는 Buffer.data 오프셋 2바이트. IFM·golden·placement 동일. 그룹이 겹치지 않고 모두 덮음 | PASS |
| 7 | Vela 근거 | `vela --verbose-performance` 같은 옵션. 명령 스트림 = m7(`21564a54`, `093dcda9`). per-layer Op Cycles 합 = cycles_total(kws 102,248, ad 148,328) | PASS |
| 8 | digest | 보드 staging 28개(이미지 4, DRWL 10, manifest, ids, conditions, plan 10, session) = Mac. 보드 코드 79개(host/analysis·lib·board) = Mac. m7 기준 raw 2개, caps 기준(6C boot 468, 14077be TA profile 1) = Mac | PASS |
| 9 | 판정 경로 | 보드(Python 3.12)에서 빈 run root로 boot-check → UNMEASURED rc 1, gate-g1 → FAIL. 세션 중단 경로 동작 | PASS |
| 10 | 보드 상태 | 보드 runs.csv 전체 최대 host_boot_index 476(477–486 미사용). 카드 마운트 0, /dev/sdb1 없음(USB off), `evidence_m6` 있음, x3 경로 없음. 디스크 여유 2.3 GB. `sudo_session.sh --check` OK(Mac·보드) | PASS |
| 11 | G1 기준값 | m7 pass A(65cf963, TA profile 1) 중앙값: kws NPU 91,824.5(±1 % = ±918), MAC 56,450, DPU 49,495; ad NPU 145,949.5(±1 % = ±1,459), MAC 93,672, DPU 93,672 | 기록 |
