# Stage 6E-X3 계약 — 직렬화(KERNEL_WAIT n=0) + 그룹 PMU_MASK, kws·ad (보드)

- **근거 문서**:
  - 지시: `docs/plan/stage6ex3_directive_chatgpt.txt`, Amendment A `docs/plan/stage6ex3_amendment_a_chatgpt.txt`.
  - 설계: 6E-0 `16f8127`, 정오표 `evidence/stage6e0/erratum_mask_en.md`, `erratum_vela_terms.md`.
- **동결 시점**: 이 계약, 판정 코드 `host/analysis/stage6ex3.py`, 워크로드·manifest, 세션 파일은 보드 측정 전에 커밋한다. 결과를 본 뒤 기준을 바꾸지 않는다.
- **승인 범위**:
  - kws·ad, 10 boot(477–486), 150 RUN(측정 120, warm-up 30), Pass A·B·C.
  - **TA profile 1**, EXT RLATENCY 500, placement 0.
  - 펌웨어 `f0baf8c`(14077be + PMCR.mask_en 플래그) 이미지 bram `9b1844a3…`, boot `3b4af743…`, ddr 16 B 0(`374708ff…`), images.txt `af688281…`.
  - 추가 모델·boot·TA·계측 방식은 없다.

## 1. 실행 구성 (`workloads/x3_manifest.json`)

| boot | 키 | 내용 | pmu_flags |
|---|---|---|---|
| 477 | x3_kws_B0 | m7 DRWL 그대로(`c77bf2b7…`) | 0 |
| 478 | x3_kws_B1 | 직렬 스트림, 모든 창 ON | 1 |
| 479 | x3_kws_B2 | 직렬, G_V 창만 ON(stream 연산 3, 5, 7 = TFLite 2, 4, 6) | 1 |
| 480 | x3_kws_B3 | 직렬, G_0 창만 ON(stream 0, 1 = TFLite 0) | 1 |
| 481 | x3_kws_B4 | 직렬, G_R 창만 ON(나머지 9개) | 1 |
| 482 | x3_ad_B0 | m7 DRWL 그대로(`9d8b45ad…`) | 0 |
| 483 | x3_ad_B1 | 직렬, 모든 창 ON | 1 |
| 484 | x3_ad_B2 | 직렬, G_V(stream 3, 5, 7, 9 = TFLite 2, 4, 6, 8) | 1 |
| 485 | x3_ad_B3 | 직렬, G_0(stream 0, 1) | 1 |
| 486 | x3_ad_B4 | 직렬, G_R(나머지 8개) | 1 |

**직렬 스트림** (`host/lib/cms.serial_mask`):
- 경계마다 KERNEL_WAIT n=0(`0x00000012`)과 PMU_MASK(bit)를 넣는다. 경계는 시작과 각 커널 연산 명령 바로 뒤이며, 마지막 커널 뒤에는 KERNEL_WAIT(0)과 PMU_MASK(0)을 넣는다.
- 그래서 창 i = 연산 i의 설정과 실행이고, 다음 KERNEL_WAIT(0)이 연산 i의 완료 뒤에 창을 닫는다.
- B1–B4는 같은 스트림이며 PMU_MASK enable 비트만 다르다.

**정적 확인** (preflight에서 기록):
- 삽입한 단어를 빼면 원래 스트림과 바이트 동일하다(8/8).
- 모델은 COP1 버퍼만 끝에 다시 붙였고, 원래 범위에서 바뀐 것은 Buffer.data 오프셋 2바이트뿐이다. 다른 버퍼·텐서·연산 I/O는 동일하다(컨테이너 tflite 독립 확인 10/10).
- IFM·golden·placement는 m7과 같다.

**그룹**:
- G_0 = TFLite op0(Cin 1 첫 Conv; stream 연산 2개).
- G_V = 6D EXACT_VALIDATED(DF1x1 h1uc 검증 연산).
- G_R = 나머지. 세 그룹은 겹치지 않고 모든 커널 연산을 덮는다.

**한계(사전 기록)**:
- KERNEL_WAIT는 mem2mem DMA를 기다리지 않는다. 그래서 DMA가 낸 AXI 계수(pass B·C의 전송·요청)는 창 경계를 넘을 수 있다.
- 그룹별 AXI 값은 "창 값"으로만 기술하고 귀속 판정에 쓰지 않는다. MAC·DPU·AO·WD(커널 단위 처리부)만 귀속 판정에 쓴다.

## 2. PMU (8 카운터, 모든 pass에 NPU_ACTIVE)

| set | 이벤트 |
|---|---|
| 1 (A) | 35 48 51 53* 55* 64 80 81 |
| 2 (B) | 35 128 130 132 135 384 386 391 |
| 3 (C) | 35 131 142 387 640 642 656 658 |

boot당 3 set × 5 RUN(1 warm-up + 4 측정). 값은 측정 RUN 중앙값, range = max − min.

## 3. RUN·boot 유효성 (`config_result`)

| 상태 | 조건 |
|---|---|
| UNMEASURED | 원시 자료가 없음 |
| CONFIG_MISMATCH | 다음 중 하나가 어긋남: workload sha256 = manifest, 이미지 4개 digest, boot 번호, condition wfe, capabilities(TA 레지스터 `ta_*` = Stage 6C 14077be TA profile 1 값, EXT RLATENCY 500, NPU 1024 MAC, schema 5, record_fields 92), 모든 RUN 기록(schema 5, placement 0, model_len = DRWL, `pmu_flags` = manifest, `pmcr_after_arm`의 bit 3 = `pmu_flags`, irq_count 1) |
| INVALID_OUTPUT | 출력 판정 실패: RUN마다 DRWL golden(= m7 golden)과 같음(OUTPUT_MATCH, ofm_mismatch 0), 모든 RUN의 output CRC가 하나, 그리고 B1–B4는 그 CRC = 이번 B0의 CRC(원본과 같은 출력). m7 원시 자료에는 output CRC가 없다 |
| INVALID_PMU | `record_v2.validity` 실패, 3 set × 5 RUN 배치 위반, 카운터 누락·잘못된 pass, overflow |
| UNSTABLE | MAC_ACTIVE·DPU가 측정 RUN 사이에 다름, NPU_ACTIVE A 대 B 또는 A 대 C 차이 > max(5 %, range 합), pass A range > 5 % |
| VALID | 그 밖 |

## 4. 세션 중 gate (실패하면 즉시 중단·복원; 재측정·추가 boot 없음)

**G1 — 원본 재현** (kws B0 직후, ad B0 직후에도 같은 규칙):
- B0이 VALID여야 한다.
- 모든 RUN에서 pmu_flags 0, mask_en(bit 3) 0.
- NPU_ACTIVE(pass A 중앙값)가 m7 pass A 중앙값과 ±1 % 안.
- pass A·B·C의 나머지 이벤트는 |B0 − m7| ≤ max(1 % × m7, range_m7 + range_B0). m7 값은 같은 이벤트의 m7 측정 RUN이다(이벤트별 m7 set; 65cf963 이미지, TA profile 1).
- 출력 = DRWL golden(= m7 golden, OUTPUT_MATCH).

**GS — 직렬 boot** (B1–B4 각각 직후): VALID(출력 = 원본 CRC 포함), pmu_flags 1, mask_en 1.

**GM — 마스크 동작** (kws B4 직후, ad 진행 전):
- M2: 각 그룹 boot(B2, B3, B4)가 0 < NPU_ACTIVE(B_k) < 0.95 × NPU_ACTIVE(B1)이다(ON 창은 세고, OFF 창은 뺀다).
- M3 (H-P): NPU_ACTIVE와 MAC_ACTIVE 각각에서 |Σ_k E(B_k) − E(B1)| ≤ max(1 % × E(B1), range 합)이다.
- M4: MAC_ACTIVE(B3) = 26,090 ±1 %이다(6C F5 단독 독립값; 창 경계가 의도한 명령 위치와 일치함을 확인).
- M2·M3·M4가 모두 맞아야 통과한다. 실패하면 ad boot를 하지 않는다.
- ad에는 M2·M3만 적용하며, 판정은 §6에서 한다(세션 중단 조건은 아님).

## 5. 가설 (6E-0 기준 유지; 측정 RUN 중앙값, pass A)

| 가설 | 규칙 |
|---|---|
| H-S | 모델별로 \|MAC(B1) − MAC(B0)\| ≤ 1 % × MAC(B0)이면 SUPPORTED, 아니면 REFUTED(직렬화가 MAC_ACTIVE를 바꿈) |
| H-P | 모델별로 M3이 성립하면 HOLDS, 아니면 FAILS. DPU·AO·WD도 같은 식으로 기술한다 |
| H-K (kws) | G_0: \|MAC(B3) − 26,090\| ≤ 1 %. G_V: \|MAC(B2) − 11,700\| ≤ 5 %(h1uc). 각각 SUPPORTED/REFUTED |
| H-A (ad) | MAC(B2) ∈ 60,480 ± 5 %이면 H-A1(잔차는 검증 밖 연산) SUPPORTED. > 1.05 × 60,480이면 H-A2(검증 연산의 문맥 비용) SUPPORTED. < 0.95 × 60,480이면 NEITHER. 그룹 측정이 유효하지 않으면 INSUFFICIENT_EVIDENCE |
| H-O | Serialization_Delta = NPU(B1) − NPU(B0). \|Δ\| > max(1 % × NPU(B0), range_B0 + range_B1)이면 SCHEDULE_EFFECT_OBSERVED, 아니면 NO_SIGNIFICANT_EFFECT. 장벽·명령 처리 비용을 배제하지 못하므로 순수 중첩 이득으로 단정하지 않는다 |
| H-V | 그룹 g의 Vela 비용은 TFLite 연산의 per-layer Op Cycles 합이다(`evidence/stage6ex3/vela`, 스트림 = m7). ratio_g = NPU(B_k) ÷ Vela_g이고, < 0.9 OVER, > 1.1 UNDER, 그 사이 AGREE. NPU·SRAM·DRAM 항 합과 연산별 지배 항은 기술만 한다. 원본 대 직렬 전체는 NPU(B0)/cycles_total과 NPU(B1)/cycles_total로 비교한다 |

## 6. 최종 판정

| 항목 | 판정 |
|---|---|
| **Measurement** | VALID: 10 boot 모두 VALID이고 G1·GS·GM 통과. PARTIAL_VALID: 모든 gate를 통과했고 UNSTABLE·INVALID_PMU가 있음. MEASUREMENT_INVALID: gate 실패, CONFIG_MISMATCH, UNMEASURED, INVALID_OUTPUT |
| **Group Attribution** | VALIDATED: kws GM 통과, kws H-K G_V SUPPORTED, ad M2·M3 성립. PARTIALLY_VALIDATED: kws GM은 통과했지만 나머지 일부가 실패. INVALID: kws GM 실패이거나 그룹 boot 무효 |
| **Compute Explanation** | RESIDUAL_REDUCED: 귀속이 VALIDATED 또는 PARTIALLY이고 H-A1 SUPPORTED(ad 잔차가 측정된 G_0 + G_R에 있음). RESIDUAL_UNCHANGED: 귀속은 유효하지만 H-A2 또는 NEITHER. INSUFFICIENT_EVIDENCE: 귀속 INVALID |
| **Serialization** | SCHEDULE_EFFECT_OBSERVED: 어느 모델이든 B0·B1 VALID이고 H-O 유의. NO_SIGNIFICANT_EFFECT: 두 모델 모두 유효하고 유의하지 않음. INSUFFICIENT_EVIDENCE: 그 밖 |
| **Vela Fidelity** | GROUP_FIDELITY_IMPROVED: 귀속이 유효하고, 두 모델 모두 \|ln(NPU(B1)/total)\| < \|ln(NPU(B0)/total)\|이며, 모든 그룹 ratio가 AGREE. GROUP_DISCREPANCY_REMAINS: 귀속은 유효하지만 위가 아님. INSUFFICIENT_EVIDENCE: 귀속 INVALID |

**해석 제한**:
- 그룹 값은 "직렬 실행에서 완료 경계로 나눈 비용"이다. 원본 모델의 연산별 실행시간이라고 쓰지 않는다.
- 합계 일치는 필요조건일 뿐이다.
- Vela가 직렬 실행을 정확히 예측한다고 가정하지 않는다.
- 6D/6E-0의 board/Vela(NPU 항 합 기준)와 이번 total 기준은 다른 값이며, 나란히 놓을 때 기준을 표시한다.

## 7. 검증

- 테스트 `test_stage6ex3`(판정), `test_cms_serial`(삽입·복원·COP1 교체), 펌웨어 변경 테스트(sim·contract·drwl·record) — mutation 전부 KILLED.
- `test.sh` ALL PASS.
- preflight(보드 digest, 판정 코드, boot 번호, 세션 점검, 컨테이너 독립 모델 확인), 원시 자료 sha256, 판정 2회 바이트 동일.
- 로컬 커밋만 한다.
