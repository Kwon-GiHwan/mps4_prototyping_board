# Stage 6B-E2E-B 계약 — A2 graph I/O 메모리 배치 × EXT 읽기 지연

지시: Stage 6B-E2E-B 공식 지시(2026-11-17). 이 계약, 판정 코드, manifest, 예상값, 실행 순서, 테스트, 세션 파일은 **보드 측정 전에** 커밋한다.
기존 데이터와 판정(Stage 4–E2E-A)은 바꾸지 않는다. 승인 상한: 5 boot / 50 RUN. Stage 6C, E3, MAC 규모 실험은 하지 않는다.

## 0. Phase 0 — 공유 identity 정정 (선행 유지보수 커밋 `6614ce8`)

- `stage4k.identity`, `stage4aoe.identity_a1`, `stage6bb.identity_of`가 기대 placement를 받는다. 기본값은 0이다. 기대값은 동결 manifest에서 온다.
- 회귀 결과(`evidence/maint/identity_placement/report.md`):
  - identity 경로 판정 9개의 출력이 바이트 단위로 같다.
  - 폴더 76개(identity 결과 155건): 같음 152, 예상된 변경 3(W0-P1 placement 항 False → True), 예상 밖 0 → REGRESSION_PASS.
  - 테스트 23개, mutation 21/21 KILLED.
- E2E-B 판정은 이 공유 경로를 그대로 쓴다. E2D의 단계별 덧씌우기(`placement_identity`)는 쓰지 않는다.

## 1. 연구 질문과 범위

RQ-E2E-B: 같은 A2 그래프에서 graph I/O를 DRAM에서 on-chip SRAM으로 옮기면 EXT 읽기 지연에 대한 NPU_ACTIVE의 민감도가 얼마나 줄어드는가? 옮긴 뒤 남은 EXT 접근은 실행시간에 어떤 영향을 주는가?

- 분리되는 것: graph I/O(입력 a·b와 출력)를 **함께** 옮긴 효과.
- 분리되지 않는 것:
  - 입력만, 출력만의 효과(B1·B2 UNAVAILABLE, E2E-A).
  - 가중치 공급 지연과 command stream 접근 지연의 구분.
  - DMA overlap, WD 공급, AO 역압력의 개별 기여.

## 2. 구성 (`workloads/`, `stage6be2eb.py workloads`로 E2D workloads에서 생성)

| ID | DRWL | graph IO | 중간 텐서 | 가중치·scale·command stream |
|---|---|---|---|---|
| REF | `s4c2_conv_cin48` `6eb390be…` | — | — | — |
| B0 | `e2d_w1p1` `928296b1…`(E2D W1-P1, E2B, 6B-B와 같은 파일), placement 0 | DDR/EXT (region 1) | fast region 2, on-chip SRAM | DDR/EXT |
| B3 | `e2eb_b3` `7b2cedd5…` = B0의 header word 7만 1 | on-chip SRAM/SRAM 포트 (region 1) | 같음 | 같음 |

**실행 구성 동일성(정적, 확인함)**:
- B0와 B3 DRWL은 길이 304,080 B로 같고, 다른 바이트는 offset 28 하나(word 7, 0 → 1)뿐이다.
- DRWL에 들어 있는 것이 모두 같다: command stream(628 B), 가중치·bias·scale, kernel 3개(ELEMENTWISE, CONV, ELEMENTWISE)와 block·ublock·traversal, 양자화·activation, 연산 순서·의존성, 입력값(6B-B fixture), golden(`b9341e6f…`).
- 동반 파일(cms, tflite_ofm, ifm, ref_ofm)도 바이트 단위로 같다.
- 바뀌는 것은 runner가 region 1 arena를 놓는 위치와, 그에 따른 REGIONCFG(B0 0x55F → B3 0x553)와 base 주소뿐이다.

## 3. SRAM 배치와 IO staging

정적 계산과 펌웨어 소스(`firmware/driver_runner/use_case/pmu_runner`):
- SRAM 창: `0x31000000–0x31400000`(4 MiB, MLEK 링커 SRAM). driver fast memory는 `0x31000000–0x31060000`이고, 그중 A2 fast scratch(region 2, 중간 텐서)는 `0x31000000–0x31024000`(147,456 B)이다.
- B3 arena(region 1) = (fast 끝을 64 KiB로 올림 `0x31070000`) + (DDR arena − model_base `0x16770`) = **`0x31076770`**. TFLM arena 길이는 2 MiB이므로 끝은 `0x31276770`으로 창 안이다. 실제 사용 141,312 B는 입력 a `+0`, b `+0x11400`, 출력 `+0`(Vela arena 재사용으로 입력 a와 같은 주소, B0와 같음)이다.
- 가중치(region 0, `0x70000420`, 90,256 B)와 command stream은 DDR의 모델 안에 있다. B0·B3 같다.
- 펌웨어 안전장치:
  - load 때 arena 전체에 주소 의존 패턴과 그 보수를 쓰고 D-cache를 비운 뒤 되읽는다. 실패하면 NACK이고 RUN이 없다.
  - load 때 출력을 poison(0x5A)으로 채운다. 첫 RUN 출력이 golden과 같으면 NPU가 실제로 썼다는 뜻이다.
  - RUN마다 측정창(probe_begin) 전에 CPU가 입력을 다시 복사한다.
  - 두 이미지 모두 MLEK `ethosu_flush_dcache`/`ethosu_invalidate_dcache`가 링크돼 있어 driver가 작업 전후 cache를 처리한다(`dcache_on` = 1이 RUN마다 기록됨).
- CPU staging과 cache 처리는 CPU 시간이다. NPU_ACTIVE(NPU가 활동한 사이클)에는 들어가지 않는다. PMCCNTR 창은 쓰지 않는다.
- 보드 판정(RUN마다, `layout`). 하나라도 거짓이면 CONFIG_MISMATCH:
  - `arena_where`: arena_base = base1 = 동결 기대 주소(B0 `0x70016770`, B3 `0x31076770`).
  - `arena_inside`: [base1, base1 + 2 MiB)가 그 메모리(SRAM 창, 또는 DDR model_base–ddr_limit) 안에 있고, region 1 크기 ≤ arena 길이.
  - `fast_inside`: region 2가 driver fast memory 안에 있다.
  - `fast_disjoint`: region 1 arena가 region 2와도, fast memory 전체와도 겹치지 않는다.
  - `weights_ddr`: region 0이 DDR 모델 안에 있다.
  - `io_in_arena`: graph 입력·출력 base(3–5)가 region 1 안에 있다.
- 주소가 할당 가능하다는 것만으로 통과시키지 않는다. layout, 출력 golden 일치(PASS_EXACT), 공유 identity(placement·REGIONCFG·REGIONCFG_MATCH)가 모두 필요하다.

## 4. 예상값과 가설 (보드 전 동결)

- B0 기준(E2D Amendment A, TA profile 1): NPU_ACTIVE L500 99,233.5(range 1,476), L1000 158,505(range 2,601), 증가 59,271.5. EXT read 27,066 beat, EXT write 7,872 beat, SRAM read 25,088, SRAM write 9,216.
- B0 재현(기술): |B0(L) − E2D(L)| ≤ max(1 % E2D, E2D range + 이번 range)이면 재현으로 기록한다. 판정 입력은 아니다.
- MAC_ACTIVE = H1-UC 20,736(B0·B3 모두).
- EXT read 정적 기대(16 B beat):
  - B0 27,066.
  - B3 = (가중치 174,752 + scale 5,760 + A2 command stream 628) / 16 = **11,321.25**. 허용폭 ±1 %(11,208.0–11,434.5).
  - 참고: E2D W0-P1에서 같은 가중치 경로의 실측은 11,304 beat였다(A0 command stream 348 B).
- EXT write: B3 = 0.
- 보존(기술, 판정 입력 아님): SRAM과 EXT read beat의 합, write beat의 합이 B0와 B3에서 같을 것으로 예상한다(read 52,154, write 17,088). W0에서는 옮겨 간 beat가 1:1이었다.
- 용어: B3의 EXT 경로는 `WEIGHT_AND_COMMAND_EXT_PATH`라고 부른다(가중치·scale + command stream). `WEIGHT_ONLY`라고 쓰지 않는다.

가설:
- **H-IO**: B3에서 EXT read가 줄고, NPU_ACTIVE와 지연 민감도도 준다. 세 가지는 따로 판정한다. 트래픽 감소가 NPU_ACTIVE 감소를 보장하지 않는다.
- **H-REMAIN**: B3에서도 지연 효과가 남을 수 있다. 그것을 가중치 공급에 전부 귀속하지 않는다. command stream과 그 밖의 EXT 접근도 함께 본다.
- **H-OVERLAP**(탐색): Vela의 연산별 max 비용 모델이 DMA·AO·WD·MAC 중첩을 표현하지 못할 수 있다. B0/B3 비교만으로는 가를 수 없다.

## 5. Vela 범위

- B0: Vela 53,052(L500) / 83,142(L1000), LE_V 30,090. 기존 오차를 그대로 보고한다.
- B3: `NO_COMPARABLE_VELA_ESTIMATE`. Shared_Sram 컴파일(Conv 3 kernel)은 다른 실행 구성이므로 쓰지 않는다. B3에 대해 Vela 오차를 계산하지 않는다.

## 6. PMU

- Pass A: 35 48 51 53* 55* 64 80 81. Pass B: 35 128 130 132 135 384 386 391. 두 pass 모두 NPU_ACTIVE(35)가 앵커다.
- *은 예약 이벤트로 탐색용이며 판정 근거로 쓰지 않는다.
- Pass C(요청 정체, AXI latency 히스토그램)는 이번 계약에 없다.
- 처리부 카운터를 더하거나 NPU_ACTIVE에서 빼서 대기 사이클을 배분하지 않는다.

## 7. 측정 (5 boot / 50 RUN, warm-up 10, 측정 40)

boot마다 pass A·B 각 5 RUN(1 + 4), `OUTPUTS=1 STOP_ON_INVALID=1`. 보드의 최대 host_boot_index는 457이다(측정 전 확인). 순서(고정):

| 순서 | boot | 조건 | 이미지 |
|---|---|---|---|
| 1 | 458 | REF | L500 (`70090f1`, bram `c80e77df…`) |
| 2 | 459 | B0 | L500 |
| 3 | 460 | B3 | L500 |
| 4 | 461 | B3 | L1000 (bram `fd478e2d…`, EXT RLATENCY만 1000) |
| 5 | 462 | B0 | L1000 |

- 이미지 교체는 한 번이다(deploy L500 → restore → deploy L1000 → restore → postflight). TA profile 1. capabilities 전체를 `caps_l500.json`/`caps_l1000.json`과 대조하고, `ta_ext_rlatency`도 별도로 대조한다.

## 8. 유효성 (E2D와 같은 상태 집합)

- 상태:
  - CONFIG_MISMATCH: workload sha256, 이미지, boot, TA readback, NPU MAC 수, 공유 identity 항, layout 항.
  - UNMEASURED.
  - INVALID_OUTPUT: PASS_EXACT가 아님.
  - INVALID_PMU: RUN 배치, 카운터 누락, overflow.
  - UNSTABLE: MAC·DPU가 RUN마다 다름, pass A 대 B NPU_ACTIVE 차이 > max(5 %, ranges), pass A range > 5 %.
  - VALID.
- REF 재현 게이트: `stage4k.reproduce` 대 boot 375. FAIL이면 세션을 멈춘다.
- 실행 구성: VALID인 B 구성의 MAC_ACTIVE ≠ 20,736이면 그 구성은 비교에서 빠진다(`mac_equals_h1uc` 거짓).
- **Measurement Validity**:
  - `VALID`: 게이트 PASS, 5개 구성 모두 VALID, MAC 일치.
  - `PARTIAL_VALID`: 게이트 PASS, CONFIG_MISMATCH·UNMEASURED 없음, 나머지 중 하나 이상이 VALID가 아님.
  - `MEASUREMENT_INVALID`: 그 밖.

## 9. 지표와 판정 (B = NPU_ACTIVE pass A 중앙값, r = range; "사용 가능" = 4개 B 구성 모두 VALID이고 MAC 일치)

- IO_PE(L) = B_B0(L) − B_B3(L). tol_PE(L) = max(0.01·B_B3(L), r_B0(L) + r_B3(L)).
- LE(B) = B(1000) − B(500). tol_LE(B) = max(0.01·B(500), r(500) + r(1000)).
- Interaction I = LE(B0) − LE(B3). tol_I = max(0.01·B_B3(500), 네 range의 합). 제거 비율(기술) = I / LE(B0).

**Graph I/O Placement**
- `IO_PLACEMENT_EFFECT_OBSERVED`: 두 지연 모두 |IO_PE| > tol_PE이고 부호가 같다.
- `IO_PLACEMENT_EFFECT_NOT_RESOLVED`: 사용 가능하지만 위 조건이 아니다.
- `NOT_IDENTIFIABLE`: 사용 가능하지 않다.

**Latency Sensitivity**
- `IO_SENSITIVITY_REDUCED`: I > tol_I.
- `IO_SENSITIVITY_NOT_REDUCED`: I ≤ tol_I(줄지 않았거나 오히려 늘었다).
- `INSUFFICIENT_EVIDENCE`: 사용 가능하지 않다.
- 한계: boot 반복이 없다.

**Residual EXT Path**(VALID이고 MAC이 일치하는 B3 구성만 사용)
- `WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED`: 두 지연 모두 B3 EXT read가 11,321.25 ±1 % 안이고 EXT write = 0.
- `EXT_PATH_UNRESOLVED`: 쓸 수 있는 B3 구성이 없거나, 하나라도 EXT write ≠ 0이거나, EXT read ≥ B0의 EXT read(VALID인 B0의 최댓값, 없으면 27,066).
- `EXT_PATH_PARTIAL`: 그 밖. 예: 한 지연만 사용 가능, 또는 EXT read가 줄었지만 ±1 % 밖. 이 경우 판정을 내리기 전에 전송 단위(beat/트랜잭션)와 주소 경로 차이를 따로 분석해 보고한다.

**Residual latency response**(H-REMAIN, 기술): |LE(B3)| > tol_LE(B3)이면 `RESIDUAL_RESPONSE_OBSERVED`, 아니면 `RESIDUAL_RESPONSE_NOT_OBSERVED`, 사용 불가이면 `NOT_EVALUABLE`. 원인은 배정하지 않는다.

**Pipeline Mechanism**: `MECHANISM_UNRESOLVED`로 고정한다. 이 설계에는 DMA 중첩, WD 공급, AO 역압력을 가르는 측정이 없으므로 `MECHANISM_SUPPORTED`에 도달할 수 없다.

**기술 보고**(판정 입력 아님):
- 처리부 활동 B0 대 B3: MAC, DPU, AO, WD, WD_STALLED, SRAM/EXT beat·트랜잭션, NPU_ACTIVE.
- read·write 합 보존.
- B0 재현.
- B0 Vela 오차와 LE(B0) 대 LE_V 30,090.

**금지 해석**:
- 실행시간이 줄었다는 것만으로 DMA overlap이나 특정 WD stall 원인이 확인됐다고 쓰지 않는다.
- WD_STALLED를 대기 총량으로 보지 않는다.
- Active/Stalled 합으로 NPU_ACTIVE를 분해하지 않는다.
- B3에 Vela 오차를 계산하지 않는다.
- 입력과 출력의 몫을 나누지 않는다.

## 10. 중단·복원

- REF 게이트 FAIL이나 boot-check rc 1(CONFIG_MISMATCH/UNMEASURED)이면 세션이 즉시 멈추고 카드를 복원한다(`sudo_session.sh`).
- 실패한 조건을 재측정하거나 다른 조건으로 대체하지 않는다. 추가 boot는 하지 않는다.
- 종료 때 RESTORE VERIFIED와 postflight를 기록한다.

## 11. 검증

- 판정 코드 `host/analysis/stage6be2eb.py`, 테스트 `host/tests/test_stage6be2eb.py`.
- mutation 전부 KILLED, `test.sh` ALL PASS.
- preflight: 보드 판정 코드와 manifest의 sha256 = Mac, staging digest = manifest, 측정 전 boot-check UNMEASURED.
- 로컬 커밋만 한다.
