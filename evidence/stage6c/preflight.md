# Stage 6C Preflight (2026-11-18, before boot 468) — **PASS**

동결 `81145da`. 모든 항목을 실제로 실행해서 확인했다.

| # | 항목 | 확인 | 결과 |
|---|---|---|---|
| 1 | 계약·판정·manifest·순서·세션 동결 | `81145da`(테스트 18개, mutation 41/41, test.sh ALL PASS) | PASS |
| 2 | 컴파일 무결성 | 6C-0 컨테이너 컴파일 2회 동일(`f77884ec…`), 정오표 수정 반영(F2 c16 per-channel zero point). 대표 5개 MAPPING_SAME, 통제 3개 대표와 같은 매핑. 원본 MLEK 텐서·양자화 사용(`stage6c0_models.source_op`) | PASS |
| 3 | 출력 reference | 8개 모두 BUILTIN_REF golden = CPU 최적화 커널 출력. DRWL에 IFM·golden 포함 | PASS |
| 4 | identity 기대값 | `expected_identity.json`: Vela custom op에서 도출한 n_base 5, placement 0(8개)과 REF(E2E-D와 같음) | PASS |
| 5 | F2 Vela 4배 변화 | 컴파일 사실: DRAM 항 140,000 → 35,000, npu 22,974 → 15,303, MAC 14,184 → 14,544. 변화는 DRAM 접근 비용 항이다. MAC 비용 변화로 해석하지 않는다(계약 §1) | 기록 |
| 6 | 이미지 | staging boot/bram/ddr/images.txt = E2E-D 새 L500 이미지(`14077be`, bram `ec0e8c3b…`) = manifest | PASS |
| 7 | digest | staging·workloads·판정 코드(host/analysis·lib) 151개 sha256 = Mac | PASS |
| 8 | PMU | ids 3줄(A·B·C), conditions `1,2,3`. Pass C 8개 모두 FI101 VERIFIED이고 driver_m7에서 driver runner로 유효 측정된 이력이 있다 | PASS |
| 9 | 판정 경로 | 보드에서 E2E-D boot 463 REF(같은 이미지)를 Stage 6C 판정으로 확인했다(boot 번호만 바꾼 임시 manifest). 사유는 "3 pass 배치" 하나뿐이다(2 pass 자료이므로 기대된 결과). identity·이미지·TA·capabilities는 통과 | PASS |
| 10 | 측정 전 상태 | 보드 최대 host_boot_index 467(468–476 미사용). boot-check s6c_f1_rep rc 1(UNMEASURED) | PASS |
| 11 | 업로드 크기 | F4 DRWL 10.1 MB < 이전에 올린 wav2letter DRWL 14.5 MB(driver_m7). RUN_TIMEOUT 600 s | PASS |
| 12 | 복원 | `evidence_m6` 있음, 카드 마운트 0, run·evidence root 없음, `sudo_session.sh --check` OK(Mac·보드). 보드 디스크 여유 2.3 GB | PASS |
