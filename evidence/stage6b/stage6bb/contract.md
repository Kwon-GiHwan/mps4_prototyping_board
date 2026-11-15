# Stage 6B-B — Model-informed MAC Characterization & Vela Fidelity: 보드 계약 (동결, boot 410 전)

- 근거: "Stage 6B-B 공식 지시"(조건부 보드 승인). 기본 계약은 `../revision_a/amendment_b/amendment_b_board_contract.md`(`22a89cf`)이다.
  이 문서는 실측 전에 그 계약을 아래처럼 보완·정정한 것이다. 동결 뒤에는 바꾸지 않는다.
- 판정 코드는 `host/analysis/stage6bb.py`, 테스트는 `host/tests/test_stage6bb.py`다.
  - 테스트 41개는 Stage 4K boot 375와 4AO-E boot 395 원시 데이터의 복사본에 오류를 주입해 검사한다.
  - mutation 기록은 `mutate.py`·`mutation.txt`에 있다.
- 실험 manifest는 `workloads/stage6bb_manifest.json`, 정체성 manifest는 `workloads/expected_identity.json`이다.

## 0. 기본 계약 대비 변경 (실측 전, 근거 포함)

| 항목 | 기본 계약 | 이 계약 | 근거 |
| --- | --- | --- | --- |
| 대표 형상 입력 | Revision A seed 입력 | **MLEK 모델 내부 Conv 입력**(Amendment B fixture DRWL) | 지시 §1. 각 fixture DRWL은 `vela_sha256`·`cms_sha256`이 Revision A A2 컴파일과 같고 IFM·golden만 다르다(Amendment B V7) |
| MAC_ACTIVE ≠ MAC_DPU_ACTIVE | 그 구성의 MAC 지표를 쓰지 않음 | **삭제**. DPU/MAC는 지표로 보고 | Stage 4K boot 369(1×1 Cin 16)에서 MAC 2,304와 DPU 1,152가 유효 측정이었다. 둘이 다르다는 것은 오류의 증거가 아니다. 이 조항은 계약 작성자(Claude)의 잘못이었다 |
| 대표 형상 실패 시 | 세션 중단 | 출력·PMU·안정성 실패는 그 형상만 기록하고 계속. 환경 불일치·무측정은 중단 | 지시 §4.3("해당 형상을 INVALID로 기록하고 … 진행"). 환경 불일치는 다음 boot도 신뢰할 수 없다 |
| 상태 이름 | 범주 4개 | 지시 §2.2의 7개 상태 | 지시 |

## 1. 대상과 순서 (11 boot, 110 RUN 상한)

boot 번호는 410–420이다. 보드와 Mac의 기록에서 가장 큰 번호는 409다.

| boot | config | 무엇 | DRWL sha256 (앞 16) |
|---:|---|---|---|
| 410 | `s4c2_conv_cin48` | Stage 4K 기준(boot 375와 같은 DRWL, 같은 이미지) | `6eb390be2874088b` |
| 411–420 | `s6bb_g12, g25, g40, g53, g11, g56, g52, g57, g09, g28` | A2 대표 형상(선정 순서 그대로), MLEK 입력 fixture | manifest |

- 형상별로 다음 정보를 manifest에 기록했다.
  - 원본 모델과 op, 입력 shape·dtype·scale·zero point.
  - MLEK 입력 sha256, fixture IFM sha256, golden sha256.
  - N_MAC, block·ublock·traversal·메모리, spatial block 수, Vela `cycles_total`.
- 실패한 형상을 다른 형상(G23·G41 포함)으로 대체하지 않는다. 추가 RUN으로 보충하지 않는다.
- 조건은 다음과 같다.
  - Driver Runner 이미지 `70090f1`(boot `718c4562…`, bram `c80e77df…`, ddr `374708ff…`, images.txt `af688281…`).
  - TA profile 1, placement 0(DDR/EXT).
  - `wfe 0 0 off 1,2`, `OUTPUTS=1`, `STOP_ON_INVALID=1`.
  - pass A = 35 48 51 53 55 64 80 81, pass B = 35 128 130 132 135 384 386 391.
  - pass마다 warm-up 1 + 측정 4 RUN.

## 2. 판정 (`stage6bb.config_result`)

상태는 아래 순서로 처음 해당하는 것을 고른다. INVALID인 형상은 0으로 바꾸거나 정상 측정치에 넣지 않는다.

| 상태 | 조건 |
| --- | --- |
| `UNMEASURED` | 원시 데이터(`raw_runs.json`, `runs.csv`)가 없다 |
| `CONFIG_MISMATCH` | 다음 중 하나라도 어긋난다(모든 RUN 기준). ① workload sha256 = manifest ② 이미지 digest 4개 ③ FPGA `FI101*` ④ boot 번호 = manifest ⑤ condition `wfe` ⑥ NPU CONFIG macs 필드 = log2(1024) ⑦ 정체성: 기준은 `stage4k.identity`(REGIONCFG 0x15F), A2는 `stage4aoe.identity_a1`(n_base 6, REGIONCFG 0x55F, QCONFIG 3, placement 0, REGIONCFG_MATCH). 두 정체성 검사 모두 `capabilities.json`이 기준(boot 375)과 같음을 포함한다(TA 22개 레지스터 = TA profile 1, AXI, NPU config). RUN 수는 ⑦에서 빼고 PMU 항목에서 본다 |
| `INVALID_OUTPUT` | 보드 출력 불일치. 기준은 Stage 4K 규칙(tflite_ofm 대비 PASS_EXACT)이다. A2는 `output.bin` = golden(fixture 입력에서 얻은 BUILTIN_REF 출력)이어야 하고, 모든 RUN의 `output_match` = 1, mismatch 0이어야 한다. RUN마다 출력 CRC가 하나여야 하고 출력 길이도 맞아야 한다 |
| `INVALID_PMU` | 다음 중 하나라도 있다. RUN 배치 ≠ 2 pass × (warm-up 1 + 측정 4). 측정 RUN 무효(`record_v2.validity`: completed, invoke_ok, one_arm, one_irq, no_overflow, REGIONCFG_MATCH, job_result, codes_echo, run_rc). 측정 RUN에 그 pass의 카운터가 빠졌거나 다른 이벤트가 섞였다. `event_overflow`. `cycle_valid` ≠ 1(측정창). MAC_ACTIVE < N_MAC/1024(물리적으로 불가능) |
| `UNSTABLE` | 측정 RUN 4회의 MAC_ACTIVE가 서로 다르거나 MAC_DPU_ACTIVE가 서로 다르다. 또는 NPU_ACTIVE의 pass A와 B 차이 > max(5 % × A, range A + range B)(Stage 4AO-E 규칙). 또는 pass A의 NPU_ACTIVE range > 중앙값의 5 % |
| `VALID` | 위에 해당하지 않음 |
| `NOT_COMPARABLE` | Vela fidelity 비교에만 쓴다(§4) |

- A2에서 보드로 관측하는 것은 최종 ADD 출력뿐이다. Conv 중간 출력은 관측하지 않으므로 모든 A2 결과에
  `INTERNAL_CONV_NOT_OBSERVED`를 단다. 출력 PASS는 "A2 그래프 최종 출력이 golden과 같다"는 뜻으로만 쓴다.
- CPU reference 검증만으로 보드 출력 PASS를 선언하지 않는다. 출력 판정은 보드의 `output.bin`과 RUN별 `output_match`로 한다.

## 3. Gate와 중단

| Gate | 내용 | 실패 시 |
| --- | --- | --- |
| Preflight | 지시 §3의 9개 항목(`preflight.md`) | FAIL 또는 UNRESOLVED면 boot하지 않는다 |
| boot 410 `repro-gate` | 기준 config가 VALID이고, boot 375와 같은 DRWL이며, `stage4k.reproduce`를 통과(측정 RUN마다 MAC·DPU가 같고 boot 375와 같음, 출력 sha256 같음, 상수 카운터 같음, NPU_ACTIVE 중앙값 차이 ≤ max(1 %, 두 range)) | rc 1 → 세션 중단·복원. 411–420은 `UNMEASURED` |
| boot 411–420 `boot-check` | 상태 계산 | `CONFIG_MISMATCH`·`UNMEASURED` → rc 1 → 세션 중단·복원. 나머지 상태는 기록하고 다음 boot로 간다 |

## 4. 지표와 분석 (데이터 전에 고정)

- 형상마다 다음 지표를 계산한다. 값은 모두 pass A 측정 RUN의 중앙값이고, N_MAC은 원본 Conv의 H·W·Cin·Cout이다(ADD의 MAC은 넣지 않는다).
  - MAC_ACTIVE/NPU_ACTIVE
  - N_MAC/MAC_ACTIVE
  - N_MAC/(1024·MAC_ACTIVE)
  - MAC_DPU_ACTIVE/MAC_ACTIVE
  - N_MAC/(1024·NPU_ACTIVE)
- 보조로 다음을 기록한다. 원인은 배정하지 않는다.
  - AO_ACTIVE, WD_ACTIVE, WD_STALLED
  - pass B의 SRAM/EXT beat·transaction
  - 53, 55(TRM 목록 밖이므로 보고만)
- Stage 4K의 640·768과는 기술적으로만 비교한다(가장 가까운 값, 비율). 정답으로 쓰지 않고, 다르다고 해서 오류로 처리하지도 않는다.
  - 비교값 하나를 데이터 전에 고정한다: `c16_rate_768` = 768 · Cin / (⌈Cin/16⌉·16).
    - Stage 4K 1×1 DepthFirst 관측을 한 식으로 쓴 것이다: Cin 40 → 640(MAC_ACTIVE가 Cin 48과 같음), Cin 48·64 → 768.
    - 판정도 기대값도 아니다. 비율 `rate_over_c16_768`만 보고한다.
    - Stage 4K 1×1 PartKernel(Cin 16·32)의 384와 DPU/MAC 0.5도 함께 적는다.
- 분석 변수는 manifest의 Cin, Cout, OFM shape, OFM block/ublock, traversal, Cin·Cout mod 16, spatial block 수, IFM/OFM 메모리다.
  형상이 10개뿐이므로 경향은 기술 통계(정렬·그룹 비교)로만 말하고 인과를 주장하지 않는다.
- **Vela fidelity**(`stage6bb.fidelity`):
  - 계산 조건은 네 가지다.
    - A2 대표 형상이다.
    - 상태가 VALID다.
    - manifest의 Vela `cycles_total`이 있다.
    - 그 Vela 산출물의 sha256 = 측정한 DRWL의 `vela_sha256`이고, 범위가 "A2 graph"다.
  - 조건이 맞으면 Error(%) = (NPU_ACTIVE − Vela) / Vela × 100을 계산한다. 양수는 Vela가 과소예측했다는 뜻이다. |Error|도 함께 보고한다.
  - 조건 표시: Vela `Ethos_U85_SYS_DRAM_Mid_1024` @1 GHz와 보드 TA profile 1은 둘 다 NPU 사이클 단위다. 메모리 모델이 같다는 것은 증명하지 않았다.
  - 조건이 하나라도 안 맞으면 `NOT_COMPARABLE`(숫자 없음)이다. 기준 형상은 A2가 아니므로 fidelity 분석에서 뺀다.
  - Vela의 Conv 단위 추정은 보조로만 쓴다. PMU를 연산별로 귀속했다고 해석하지 않는다.
- 최종 판정은 두 축이며 합치지 않는다.
  - Characterization:
    - `CHARACTERIZATION_VALID`: gate PASS, 10개 모두 VALID, CONFIG_MISMATCH 없음.
    - `PARTIAL_CHARACTERIZATION`: gate PASS, 1–9개 VALID.
    - `MEASUREMENT_INVALID`: gate FAIL, CONFIG_MISMATCH가 있음, 또는 VALID가 0개.
  - Fidelity:
    - `FIDELITY_COMPARABLE`: 10개 모두 COMPARABLE.
    - `FIDELITY_PARTIAL`: 1개 이상 COMPARABLE.
    - `FIDELITY_NOT_COMPARABLE`: 0개.
- Coverage(지시 §7)는 네 가지로 나눠 보고한다.
  - Static Reproduction / Selected Measurement: Amendment B 값을 그대로 쓴다.
  - Validly Measured Shape: VALID인 형상의 그룹 MAC / 모델 MAC.
  - Model-level Explanation: 수치화하지 않는다. Stage 6의 `INSUFFICIENT_EVIDENCE`는 자동으로 바꾸지 않는다.
  - YOLO, Wav2Letter, RNNoise는 직접 측정 범위 밖이다.

## 5. 해석 금지

다음은 해석하거나 주장하지 않는다.

- NPU_ACTIVE − MAC_ACTIVE를 메모리 stall로 해석하지 않는다. WD_STALLED를 병목 시간으로 환산하지 않는다.
- A2 전체 값이나 오차를 원본 Conv 단독 값이나 MLEK 모델 전체 값으로 바꿔 쓰지 않는다.
- ADD 비용을 빼지 않는다. ADD의 MAC/WD는 0으로 읽는다. 이것은 Stage 4AO-E boot 395–400(다른 형상) 근거이므로 `CONDITION_SPECIFIC`이다.
- 물리적 이용률을 주장하지 않는다. 독립 Conv 결과를 합쳐 모델 전체를 복원하지 않는다.
- MAC 처리율과 Vela 오차가 상관을 보여도 인과로 쓰지 않는다.

## 6. 보존과 복원

- 세션 뒤 다음을 `evidence/stage6b/stage6bb/raw/`로 복사하고 sha256 목록을 남긴다.
  - `~/evsweep_s6bb_run`
  - 세션 로그
  - staging의 plan·ids·conditions·session
- 복원은 `restore_mlek`(m6 digest 확인) → `postflight.sh`(PING state 1, USB_OFF, 카드 분리) 순서다. 카드가 마운트된 상태에서는 `USB_OFF`를 하지 않는다.
