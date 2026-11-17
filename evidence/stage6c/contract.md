# Stage 6C 계약 — 연산군 F1–F5의 Unit/AXI/Vela 동시 계측 (보드)

지시: ChatGPT "Stage 6C 공식 지시"(2026-11-18, 사본 `docs/plan/stage6c_directive_chatgpt.txt`). 6C-0 결과 `da60114`, 규칙 동결 `74aa09d`, 컴파일 정오표 `93d4fbc`.
이 계약, 판정 코드 `host/analysis/stage6c.py`, manifest, 실행 순서, 테스트, 세션 파일은 **보드 측정 전에** 커밋한다.
기존 결과는 바꾸지 않는다. 승인 범위: 9 boot / 135 RUN(측정 108, warm-up 27), Pass A·B·C, **TA profile 1**, runner 이미지 `14077be`(L500 bram `ec0e8c3b…`), placement 0, PMCLUT 미사용. TA 지연 변형, SRAM 배치, PMCAXI_CHAN, 추가 형상은 없다.

## 1. 구성 (`workloads/s6c_manifest.json`; 6C-0 컴파일 사실 `f77884ec…`)

| boot | 키 | 원본 | 형상 | N_MAC(TFLite) | Vela op cycles | DRWL |
|---|---|---|---|---|---|---|
| 468 | REF | Stage 4K | s4c2_conv_cin48 | 2,654,208 | — | `6eb390be…` |
| 469 | s6c_f1_rep | yolo op9 | 96²×4→24, 1×1 PK | 884,736 | 56,249 | `a1b054c4…` |
| 470 | s6c_f1_cin16 | 통제 Cin 16 | 96²×16→24 | 3,538,944 | 56,249 | `5a00c052…` |
| 471 | s6c_f2_rep | yolo op3 | 96²×8 DW 3×3 | 663,552 | 140,000 | `61466c04…` |
| 472 | s6c_f2_c16 | 통제 C 16 | 96²×16 DW 3×3 | 1,327,104 | 35,000 | `23cbc089…` |
| 473 | s6c_f3_rep | rnnoise op46 | FC 114→288 | 32,832 | 7,929 | `2c952744…` |
| 474 | s6c_f3_cin16 | 통제 Cin 128 | FC 128→288 | 36,864 | 7,929 | `8e48d7f1…` |
| 475 | s6c_f4_rep | wav2letter op17 | 1×148×250→2000, 1×32 PK | 2,368,000,000 | 4,716,796 | `9289007c…` |
| 476 | s6c_f5_rep | kws op0 | 49×10×1→140, 10×4 PK | 2,744,000 | 23,501 | `26351394…` |

- **매핑과 출력 기준**:
  - 대표 형상은 원본 MLEK 텐서·양자화로 다시 만들었다. traversal·block·ublock은 모델 안 연산과 같다(MAPPING_SAME, 6C-0).
  - 통제 형상은 대표와 같은 매핑이다.
  - golden = BUILTIN_REF이며, CPU 최적화 커널과 같다.
  - n_base 5, placement 0(Vela custom op에서 도출).
- **F5의 N_MAC**: Vela mac_count는 1,372,000이고 TFLite는 2,744,000이다. 비율은 TFLite 기준으로 계산한다.
- **통제할 수 없는 조건**: 단독 연산의 graph IO는 DDR(Dram→Dram)이다. 모델 안은 대부분 SRAM이다. 단독 NPU_ACTIVE를 모델 안 연산의 시간으로 귀속하지 않는다.
- **F2 Vela 4배 변화**: 컴파일 사실에서 Vela DRAM 항이 140,000 → 35,000으로 바뀌었고, npu 항은 22,974 → 15,303, MAC 항은 14,184 → 14,544다. 즉 변화는 DRAM 접근 비용 항에서 나온다. MAC 처리 비용 변화로 해석하지 않는다.

## 2. PMU (8 카운터, 모든 pass에 NPU_ACTIVE, 측정창·구성·입력 동일)

| set | 이벤트 |
|---|---|
| 1 (A) | 35 48 51 53* 55* 64 80 81 |
| 2 (B) | 35 128 130 132 135 384 386 391 |
| 3 (C) | 35 131 142 387 640 642 656 658 |

- C의 8개는 모두 FI101 VERIFIED이고, driver_m7에서 driver runner로 측정된 적이 있다.
- 387은 ARVALID/ARREADY 핸드셰이크 정체다. 서비스 대기시간이 아니다.
- *은 Reserved 이벤트로 탐색용이다.
- boot당 3 set × 5 RUN(1 + 4) = 15 RUN.

## 3. 유효성 (형상별 Measurement)

- 상태:
  - CONFIG_MISMATCH: workload, 이미지, boot, TA readback, NPU MAC 수, 공유 identity 항.
  - UNMEASURED.
  - INVALID_OUTPUT: PASS_EXACT가 아님.
  - INVALID_PMU: 3 set × 5 RUN 배치, 카운터 누락·잘못된 pass, overflow, cycle window.
  - UNSTABLE: MAC·DPU가 RUN마다 다름, A 대 B, A 대 C NPU_ACTIVE 차이 > max(5 %, ranges), A range > 5 %.
  - VALID.
- Measurement 판정: VALID ← VALID. PARTIAL_VALID ← UNSTABLE, INVALID_PMU. MEASUREMENT_INVALID ← 그 밖.
- 전체: REF 게이트(`stage4k.reproduce` 대 boot 375) FAIL이나 CONFIG_MISMATCH·UNMEASURED가 있으면 MEASUREMENT_INVALID. 전부 VALID면 VALID. 그 밖은 PARTIAL_VALID.

## 4. 판정 (형상별, 측정 전 동결; 6C-0 가설의 적용 범위를 명확히 한 것이며 수치 기준은 6C-0 그대로)

**Compute Characterization**
- F1·F2·F3 쌍(채널 16 올림 가설): 대표와 통제가 모두 VALID일 때, |MAC_통제 − MAC_대표| ≤ 1 % × MAC_대표이면 PREDICTION_SUPPORTED, 아니면 PREDICTION_REFUTED. 쌍의 두 형상에 같은 판정을 준다.
- F4: 384 ≤ N_MAC/MAC_ACTIVE ≤ 1024이면 SUPPORTED, 아니면 REFUTED.
- F5: 사전 수치 예측이 없으므로 INSUFFICIENT_EVIDENCE(기술만).
- 유효하지 않으면 INSUFFICIENT_EVIDENCE.

**Pipeline / Memory**
- F1–F3 쌍: |ΔNPU| > max(1 % × NPU_대표, range 합)이면 CONTROLLED_EFFECT_OBSERVED, 아니면 ASSOCIATION_ONLY.
- F4·F5(통제 없음): ASSOCIATION_ONLY. 형상 민감도의 인과 판정 대상이 아니다.
- 유효하지 않으면 MECHANISM_UNRESOLVED.
- 연산군 사이 비교(F1·F2 대 F3·F4의 NPU/MAC)는 관측 비교다: min(F1,F2) > max(F3,F4)이면 SUPPORTED, max(F1,F2) < min(F3,F4)이면 REFUTED, 그 밖은 INSUFFICIENT. 단일 Unit 병목의 인과 근거로 쓰지 않는다.
- 전체 Mechanism은 MECHANISM_UNRESOLVED로 고정한다.

**Vela Fidelity**(board NPU_ACTIVE ÷ Vela op cycles, 단일 연산이므로 total)
- < 0.9 OVERESTIMATION, > 1.1 UNDERESTIMATION, 그 사이 ESTIMATE_AGREEMENT. 유효하지 않으면 INSUFFICIENT_EVIDENCE.
- 가설:
  - H-VELA F1·F2(4개 형상): OVER 예측. 하나라도 UNDER면 REFUTED, 판정된 모두가 OVER면 SUPPORTED, 그 밖은 INSUFFICIENT.
  - H-VELA F3: board/Vela > 1.0 예측. 하나라도 < 0.9면 REFUTED, 모두 > 1.0이면 SUPPORTED, 그 밖은 INSUFFICIENT.
- 통제 쌍에서 보드 비 NPU_통제/NPU_대표와 Vela 비 op_통제/op_대표를 나란히 기술한다(F2 Vela 0.25).

**금지 해석**:
- Unit 카운터를 합산해 NPU_ACTIVE를 분해하지 않는다.
- 387·131을 서비스 대기시간으로 보지 않는다.
- 포트 바이트를 물리 이용률로 부르지 않는다.
- 단독 연산 시간을 모델 연산 시간으로 귀속하지 않는다.
- 결과를 본 뒤 임계값을 바꾸지 않는다.

## 5. 실행 (이미지 교체 없음)

- 순서 고정: boot 468 REF → 469 F1 rep → 470 F1 ctl → 471 F2 rep → 472 F2 ctl → 473 F3 rep → 474 F3 ctl → 475 F4 → 476 F5.
- deploy L500(새 이미지) → boot마다 campaign + boot-check(REF는 repro-gate) → restore → postflight.
- 중단: REF 게이트 FAIL, boot-check rc 1(CONFIG_MISMATCH/UNMEASURED)이면 멈추고 복원한다. 재측정·대체·추가 boot는 없다.

## 6. 검증

- 테스트 `test_stage6c`, mutation 전부 KILLED, `test.sh` ALL PASS.
- preflight(보드 digest, 판정 코드, boot 번호, 세션 점검), 원시 자료 sha256, 판정 2회 바이트 동일.
- 로컬 커밋만 한다.
