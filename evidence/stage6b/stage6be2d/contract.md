# Stage 6B-E2D 계약 — G12 Conv 메모리 배치 × EXT 읽기 지연

지시: Stage 6B-E2D 공식 지시(2026-11-17). 이 계약, workload manifest, Vela 예상값, 판정 코드, 실행 순서, 세션 파일은 **보드 측정 전에** 커밋한다.
기존 판정(H1-UC PROSPECTIVE_SUPPORT, 6-M, E2A, E2B, E2C)은 바꾸지 않는다. Wrapper 단독 효과는 판정 대상이 아니다.

## 0. 정정 (E2C 보고서 문구, 판정 영향 없음)

E2C README §3은 "A2를 6B-B 입력(a, b)으로 실행"이라고 썼지만, 실제 입력은 Revision A의 시드 입력(`/work/s6b_ra_compile/s6b_g12_f_ctx_self.ifm.bin`)이었다.
- 6B-B·E2B가 측정한 입력은 Amendment B fixture(`s6bb_g12.ifm.bin`, `33658e2f…`)다.
- CPU 동등성(A0(Conv 입력) = A2 conv_out)은 입력과 무관하게 성립하므로 E2C 판정은 그대로다.
- E2D workload는 6B-B fixture로 만들었다. 그 결과 W1-P1이 E2B에서 측정한 DRWL과 바이트 단위로 같다.

## 1. 구성 (workloads/, 컨테이너 2회 빌드 결과 바이너리 동일)

| ID | DRWL | 그래프 | Conv IFM/OFM | Vela | Vela L500 → L1000 |
|---|---|---|---|---|---|
| W0-P0 | `e2d_w0p0` `ab2d487f…` | Conv 단독(A0) | DDR/EXT (NHWC) | `64c350eb…` | 107,812 → 215,624 |
| W0-P1 | `e2d_w0p1` `0137db73…` (W0-P0의 header word 7만 1) | Conv 단독 | on-chip SRAM/SRAM 포트(runner placement) | **NO_COMPARABLE_VELA_ESTIMATE** | — |
| W1-P0 | `e2d_w1p0` `b291c5ad…` | ADD→Conv→ADD(A2, `--arena-cache-size=0`) | DDR/EXT (NHCWB16) | `eb299685…` | 100,310 → 200,622 |
| W1-P1 | `e2d_w1p1` `928296b1…` (= E2B·6B-B DRWL) | A2 | SRAM 캐시/SRAM 포트 (NHCWB16) | `95cf070b…` | 53,052 → 83,142 |
| REF | `s4c2_conv_cin48` `6eb390be…` | Stage 4K 기준 | — | — | — |

- 입력: W1 = 6B-B fixture a|b. W0 = A2 첫 ADD 뒤 Conv 입력(CPU, `5ea9be64…`).
- 출력 reference(BUILTIN_REF): 네 구성 모두 `b9341e6f…`. A2 최종 출력은 Conv 출력과 같다(ADD(x, x), scale 2배).
- 이 일치는 이 입력에서 성립한 사실일 뿐이다. W0와 W1 출력이 같아야 한다는 조건으로 쓰지 않는다.
- A2 Conv 중간 출력은 보드에서 직접 관측하지 않는다: `INTERNAL_CONV_NOT_OBSERVED`.
- H1-UC 예상 MAC_ACTIVE는 네 구성 모두 20,736이다.

## 2. 비교 가능성 (Phase 1, 보드 전 → preflight에 기록)

- W1-P0 대 W1-P1: kernel 3개(ELEMENTWISE, CONV, ELEMENTWISE), 순서, DMA(0개)가 같다. 세 kernel 모두 레지스터 차이가 ADDRESS(base·region)뿐이다. 따라서 `COMPILE_CHANGED_CONFOUNDED`가 아니다. 두 ADD의 메모리 경로도 함께 바뀐다(복합 배치 변수).
- W0-P0 대 W0-P1: command stream이 같고 DRWL header word 7만 다르다. 실제 재배치(arena = base1 SRAM 주소, REGIONCFG)는 RUN마다 펌웨어 기록과 판정 코드(identity의 placement·REGIONCFG)로 확인한다.

## 3. 측정 (승인 상한 9 boot / 90 RUN, warm-up 18, 측정 72)

- boot마다 pass A·B 각 5 RUN(1 + 4), `OUTPUTS=1 STOP_ON_INVALID=1`. PMU: 기존 Stage 4 pass(A: 35 48 51 53* 55* 64 80 81, B: 35 128 130 132 135 384 386 391)이고, 두 pass 모두 NPU_ACTIVE(35)를 앵커로 쓴다. *는 예약 이벤트로 탐색용이다. outstanding·세부 stall 전용 공개 이벤트는 쓰지 않는다(공개 TRM 지원 확인 안 됨).
- 순서(고정):

| 순서 | boot | 조건 | 이미지 |
|---|---|---|---|
| 1 | 440 | REF | L500 (`70090f1`) |
| 2 | 441 | W0-P0 | L500 |
| 3 | 442 | W0-P1 | L500 |
| 4 | 443 | W1-P0 | L500 |
| 5 | 444 | W1-P1 | L500 |
| 6 | 445 | W1-P1 | L1000 (bram `fd478e2d…`, EXT RLATENCY만 1000) |
| 7 | 446 | W1-P0 | L1000 |
| 8 | 447 | W0-P1 | L1000 |
| 9 | 448 | W0-P0 | L1000 |

- 이미지 교체는 한 번이다(deploy L500 → restore → deploy L1000 → restore → postflight).
- 한계: 조건마다 boot가 하나다. 시간 drift는 REF로 시작 때만 확인한다. 역순 배치로도 drift를 완전히 통제하지 못한다.

## 4. 유효성

E2B 판정 함수를 그대로 쓰고, 조건별로 다음만 manifest에서 읽는다: 이미지 digest, `ta_ext_rlatency` readback, capabilities 기대값, placement·n_base·REGIONCFG.
- 상태: CONFIG_MISMATCH / UNMEASURED / INVALID_OUTPUT / INVALID_PMU / UNSTABLE(MAC·DPU가 RUN마다 다름, pass A 대 B, **NPU_ACTIVE pass A range > 5 %**) / VALID.
- REF 재현 게이트: `stage4k.reproduce` 대 boot 375. FAIL이면 세션을 멈춘다.
- 실행 구성 확인: VALID 구성의 MAC_ACTIVE가 H1-UC 20,736과 다르면 `EXECUTION_MISMATCH`이고 그 구성은 비교에서 뺀다.

**Measurement Validity**
- `VALID`: 게이트 PASS이고 8개 구성 모두 VALID이며 MAC 일치.
- `PARTIAL_VALID`: 게이트 PASS이고 CONFIG_MISMATCH·UNMEASURED는 없지만 나머지 중 하나 이상이 VALID가 아님.
- `MEASUREMENT_INVALID`: 그 밖.

## 5. 지표와 판정 (B = NPU_ACTIVE pass A 중앙값, r = range)

- Placement_Effect(L) = B_P0(L) − B_P1(L). 허용폭 tol_PE(L) = max(0.01·B_P1(L), r_P0(L) + r_P1(L)).
- Latency_Effect(P) = B_P(1000) − B_P(500). tol_LE(P) = max(0.01·B_P(500), r_P(500) + r_P(1000)).
- Interaction = LE(P0) − LE(P1). tol_I = max(0.01·B_P1(500), 네 range의 합).

**Placement Effect (W1 주 판정; W0는 같은 규칙으로 보조 보고)**
- `PLACEMENT_EFFECT_OBSERVED`: 두 지연 모두 |PE| > tol_PE이고 부호가 같음.
- `PLACEMENT_EFFECT_NOT_RESOLVED`: 그 밖(한쪽 또는 양쪽이 tol 안, 또는 부호 다름).
- `NOT_IDENTIFIABLE`: W1 4구성 중 하나라도 VALID·MAC 일치가 아님.

**Vela Fidelity (W1만, 배치 반응)** — Vela PE_V(500) = 47,258, PE_V(1000) = 117,480, Interaction_V = 70,222(동결)
- L마다: |PE_B − PE_V| ≤ 0.15·|PE_V| + tol_PE이면 일치.
- `PLACEMENT_RESPONSE_CONSISTENT`: 두 L 모두 일치.
- `PLACEMENT_RESPONSE_DISCREPANCY`: 평가 가능한 L 중 하나라도 불일치.
- `FIDELITY_PARTIAL`: 한 L만 평가 가능하고 그 L이 일치.
- `NOT_COMPARABLE`: 평가 가능한 L이 없음.
- 보고만: LE(P) 대 Vela LE_V(P0) 100,312 / LE_V(P1) 30,090(밴드 0.15·|V| + tol_LE), Interaction 대 70,222(밴드 0.15·70,222 + tol_I), 구성별 절대·상대 오차.

**Mechanism**: 이 설계에는 DMA 중첩과 AO/WD 역압력을 직접 가르는 측정이 없다. 그래서 `MECHANISM_UNRESOLVED`로 고정하고, `MECHANISM_SUPPORTED`는 이 계약에서 도달할 수 없다.

금지 해석: B/V 비가 1에 가까워졌다는 이유로 overlap 원인 확정, WD_STALLED 변화를 메모리 대기 총량으로 보기, NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 보기, W0와 W1 차이를 래퍼 효과로 보기, 유닛 Active/Stalled 합으로 NPU_ACTIVE 분해.

## 6. 중단·복원

- 세션 단계가 실패하면(REF 게이트 FAIL, boot-check rc 1 = CONFIG_MISMATCH/UNMEASURED) 즉시 멈추고 카드를 복원한다.
- 실패한 조건을 재측정하거나 대체하지 않는다. 추가 boot는 하지 않는다.
- 종료 때 RESTORE VERIFIED와 postflight를 기록한다.

## 7. 검증

판정 코드 `host/analysis/stage6be2d.py`, 테스트, mutation 전부 KILLED, `test.sh` ALL PASS, 보드 판정 코드 sha256 = Mac. 로컬 커밋만 한다.
