# Stage 6E-X3 계약 Amendment C — 그룹 창 NPU_ACTIVE 안정성 기준 (boot 497–504 전에 동결; X3 마지막 실행)

- **지시**: `docs/plan/stage6ex3_amendment_c_chatgpt.txt`(2026-11-18).
- **동결 시점**: boot 489(kws B2 UNSTABLE)를 본 뒤 설계한 전향적 수정이다. boot 489는 실패 기록으로만 남기고 이 기준으로 다시 판정하지 않는다.
- **바꾸지 않는 것**: contract.md, Amendment B(G1, 결정적 카운터 gate, 판정 항목), 펌웨어 f0baf8c, 이미지·워크로드 digest, TA profile 1, EXT RLATENCY 500, placement 0, 가설 H-S·H-P·H-K·H-A·H-O·H-V와 기준값.

## 1. 바뀐 것: 그룹 창(B2, B3, B4)의 pass A NPU_ACTIVE 안정성만

- **변경 전**: range ≤ 5 % × 중앙값.
- **변경 후**: range ≤ GS_limit = max(5 % × 중앙값, cap_model). range = 측정 RUN max − min이다.
- **cap**: kws **2,423**, ad **2,596** 사이클.
  - m7 세트별 NPU_ACTIVE range의 최댓값이다(Amendment B R_cap과 같은 값).
  - 출처: `evidence/driver_m7/raw/wfe/<model>/raw_runs.json`, sha256 kws `0217993436f8…`, ad `34374320e8f2…`.
  - 테스트 `test_group_cap_from_m7`가 원시 자료에서 다시 계산해 확인한다.
- **그대로 두는 안정성 규칙**:
  - B0·B1은 5 %다.
  - 그룹 창의 MAC·DPU는 RUN 사이에 같아야 한다.
  - pass A 대 B·C의 NPU_ACTIVE 차이는 max(5 %, range 합)이다.
  - cap은 보드 결과를 보고 조정하지 않는다.
- **해석 한계**:
  - 모델 전체에서 관측된 절대 변동을 그룹 창 허용폭으로 쓰는 경험적 기준이다. 그룹 창에서 같은 변동 메커니즘이 생긴다는 것은 입증되지 않았다.
  - GS PASS는 그룹 NPU_ACTIVE가 고정밀이라는 뜻이 아니다.
  - 그룹마다 중앙값, 최소·최대, 절대·상대 range, GS_limit, 상대 허용폭을 보고한다(`window_npu`).

## 2. 기존 유효 측정 재사용

- boot 487(kws B0: VALID, G1 PASS)과 488(kws B1: VALID, GS PASS)은 Amendment B run root(`raw_b/`, 보드 `~/evsweep_x3b_run`)에서 그대로 읽는다(root "b").
- 나머지 8개는 boot 497–504(root "c")다.
- 판정 코드는 키별로 root를 정한다(`KEY_ROOT`). 직렬 boot의 출력 CRC는 root b의 kws B0 / root c의 ad B0와 비교한다.
- 487·488은 Amendment C 판정 코드로 다시 계산해도 VALID / G1 PASS다(테스트 `test_real_boots_487_488`). boot 489 자료는 kws B2(497)로 쓰이지 않는다(boot 번호 불일치).

## 3. 따로 판정하는 네 항목 (지시 §5; 기존 Group Attribution 정의는 그대로)

| 항목 | 판정 |
|---|---|
| **PMU_MASK Functionality** | kws GM M2(각 그룹 창 0 < NPU < 0.95 × B1)가 성립하면 FUNCTIONAL, 아니면 NOT_FUNCTIONAL, 자료가 없으면 INSUFFICIENT_EVIDENCE. Amendment B의 "M2와 M3"에서 M2만으로 바꾸고, M3은 아래 항목으로 분리한다 |
| **Group Partition Consistency** | 모델별 M3(NPU_ACTIVE, MAC_ACTIVE: \|Σ그룹 − B1\| ≤ max(1 %, range 합))이 성립하면 CONSISTENT, 아니면 INCONSISTENT, 자료가 없으면 INSUFFICIENT_EVIDENCE |
| **Independent Reference Agreement** | kws H-K G_0(26,090 ±1 %)과 G_V(11,700 ±5 %)가 모두 SUPPORTED이면 AGREES, 하나라도 REFUTED이면 DISAGREES, 자료가 없으면 INSUFFICIENT_EVIDENCE |
| **Temporal Attribution Validity** | Independent AGREES이고 두 모델 모두 MAC_ACTIVE 그룹 합 = B1 MAC_ACTIVE(정확히 같음; MAC은 결정적)이면 VALIDATED_FOR_KERNEL_UNITS, 아니면 NOT_VALIDATED, 자료가 없으면 INSUFFICIENT_EVIDENCE. 커널 단위(MAC·DPU·AO·WD)에 한정하며, mem2mem DMA가 낸 AXI 계수는 대상이 아니다 |

## 4. 측정 변동과 판별 (지시 §1)

- **H-V 그룹 분류**:
  - 그룹 NPU_ACTIVE의 측정 range 안에 분류 경계(0.9 × Vela 또는 1.1 × Vela)가 들어오면(range > 0이고 \|NPU − 경계\| ≤ range) INSUFFICIENT_EVIDENCE다.
  - 하나라도 INSUFFICIENT이면 Vela Fidelity는 INSUFFICIENT_EVIDENCE다.
- **H-O**는 이미 range 합을 허용폭에 쓴다. H-K·H-A·H-S는 결정적 MAC 기준이라 그대로다.

## 5. 실행 (마지막 X3 실행; 추가 Amendment·재측정 없음)

| boot | 497 | 498 | 499 | 500 | 501 | 502 | 503 | 504 |
|---|---|---|---|---|---|---|---|---|
| 키 | kws B2 | kws B3 | kws B4 | ad B0 | ad B1 | ad B2 | ad B3 | ad B4 |

- 3 pass × 5 RUN이며, 8 boot / 120 RUN이다. X3 누적은 12 boot / 180 RUN이다.
- staging `~/evsweep_x3c_img`, run root `~/evsweep_x3c_run`, evidence root `~/evsweep/evidence_x3c`.
- **gate(실패 시 중단·복원)**:
  - 각 boot 뒤 boot-check: B0는 CONFIG·출력 실패 시, 직렬·그룹 boot는 VALID가 아니면 중단한다.
  - kws B4 뒤 gate-gm(kws, B1은 root b): 실패하면 ad로 가지 않는다.
  - ad B0 뒤 gate-g1(Amendment B 기준).
- 판정 코드 `stage6ex3.py`, 테스트 34개, mutation 98/98.
