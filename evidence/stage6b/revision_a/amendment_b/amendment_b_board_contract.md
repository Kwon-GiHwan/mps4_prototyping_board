# Stage 6B Revision A / Amendment B — 보드 측정 계약 (초안 텍스트 고정, **보드 실행 미승인**)

- 작성 2026-11-15. 근거: `amendment_b_contract.md`(`62da843`), 판정 결과 `results/fi101_stage6b/revision_a/amendment_b/`.
- 상태: **계약 텍스트만 고정했다. 보드 실행은 승인되지 않았다.** 보드 판정 코드(§9 R1)는 아직 구현하지 않았고, 구현·테스트·
  mutation·dry run이 끝나기 전에는 boot하지 않는다.
- 대상은 `POSTHOC_AMENDMENT` 판정으로 BOARD_ELIGIBLE이 된 형상에서 Stage 6B 선정 규칙으로 고른 10개다. 이 선정은 원래 계약의
  결과가 아니라 사후 수정 규칙의 결과임을 모든 보고에 적는다.
- `BOARD_ELIGIBLE_WITH_ADDITIONAL_VALIDATION`인 G23·G41(MLEK 입력 fixture로만 saturation 통과)은 이 계약에 넣지 않는다.
  넣으려면 별도 지시가 필요하다(§10).

## 1. 대상 (최대 11 boot)

| boot 순서 | group | config (A2 DRWL) | 원본 대표 연산 | Cin→Cout, IFM→OFM (HWC) | N_MAC = H·W·Cin·Cout (= Vela mac_count) | DRWL sha256 (앞 16) | golden sha256 (앞 16) | n_base / REGIONCFG |
|---:|---|---|---|---|---:|---|---|---|
| 1 (기준) | — | `s4c2_conv_cin48` (Stage 4K) | 합성 Conv 1×1 | 48→96, 24x24x48→24x24x96 | 2,654,208 | `6eb390be2874088b` | Stage 4K와 같음 | 5 / 0x15F |
| 2 | G12 | `s6b_g12_f_ctx_self` | ad_medium_int8 op 4 | 276→276, 16x16x276→16x16x276 | 19,501,056 | `769c2337f69e3116` | `f13d5223df2763af` | 6 / 0x55F |
| 3 | G25 | `s6b_g25_f_ctx_self` | kws_micronet_m op 2 | 140→140, 25x5x140→25x5x140 | 2,450,000 | `1ad3ea94d956ab68` | `ee8fbe97018b4bdf` | 6 / 0x55F |
| 4 | G40 | `s6b_g40_f_ctx_self` | mobilenet_v2 op 50 | 160→960, 7x7x160→7x7x960 | 7,526,400 | `685351c61512ce00` | `b4a3c72b82057c50` | 6 / 0x55F |
| 5 | G53 | `s6b_g53_f_ctx_self` | vww4 op 28 | 44→268, 8x8x44→8x8x268 | 754,688 | `59a6f6c9d172c219` | `c1ff85f7071c1b4f` | 6 / 0x55F |
| 6 | G11 | `s6b_g11_f_ctx_self` | ad_medium_int8 op 2 | 192→276, 16x16x192→16x16x276 | 13,565,952 | `a3049847403f6d46` | `05f23f135aad4b7b` | 6 / 0x55F |
| 7 | G56 | `s6b_g56_f_ctx_self` | vww4 op 46 | 68→172, 8x8x68→8x8x172 | 748,544 | `a0cf349910ecc7f1` | `41e8753e06d074a7` | 6 / 0x55F |
| 8 | G52 | `s6b_g52_f_ctx_self` | ad_medium_int8 op 8 | 276→276, 8x8x276→8x8x276 | 4,875,264 | `33804c8440046afc` | `a53fe520f074f54b` | 6 / 0x55F |
| 9 | G57 | `s6b_g57_f_ctx_self` | vww4 op 55 | 68→288, 8x8x68→8x8x288 | 1,253,376 | `ad2dcc0d06d87734` | `5a51b5224d07ce6c` | 6 / 0x55F |
| 10 | G09 | `s6b_g09_f_ctx_self` | mobilenet_v2 op 24 | 64→384, 14x14x64→14x14x384 | 4,816,896 | `e11bb0af3d58b424` | `3a08fe5c18fbe054` | 6 / 0x55F |
| 11 | G28 | `s6b_g28_f_ctx_self` | ad_medium_int8 op 10 | 276→276, 4x4x276→4x4x276 | 1,218,816 | `79345eb7af7c4a06` | `2c11b0f1d3941401` | 6 / 0x55F |

- 전체 digest는 `evidence/stage6b/revision_a/compiled/<cfg>.ra.json`의 `forms.A2`(`drwl_sha256`, `golden_sha256`,
  `vela_sha256`, `cms_sha256`)에 있다. 보드에 올리는 DRWL은 Revision A 컴파일(`/work/s6b_ra_compile`) 산출물 그대로이고,
  배포 전에 sha256이 레코드와 같은지 확인한다. 다시 컴파일하지 않는다.
- 입력은 Revision A의 seed 입력(`S6B_SEED` 20261118)이다. golden은 같은 A2 그래프의 BUILTIN_REF 출력이다.
  MLEK 입력 fixture DRWL은 쓰지 않는다.
- 모든 대상: A2 = ADD(a, b) → Conv2D(원본 가중치·bias·scale, 원본의 fused RELU6) → ADD(conv_out, conv_out).
  placement 0(DDR/EXT), TA profile 1, Vela 5.0.0·MLEK 옵션(`config/fi101_s013.json`).

## 2. 고정 조건

- 펌웨어: Driver Runner 이미지 `70090f1`(Stage 4K·4AO-E와 같고 재빌드 없음). staging 이미지의 sha256을 Stage 4K 기록과 대조한다.
- TA profile 1(MLEK sys_dram_mid). 모든 표와 보고에 TA profile 1을 적는다.
- `wfe 0 0 off 1,2`, `OUTPUTS=1`, `STOP_ON_INVALID=1`. Dedicated_Sram, WAIT_WFE, D-cache on, region 1 = DDR/EXT.
- 순서는 §1 표 하나로 고정한다(기준 → Stage 6B 선정 순서). 반복·교차는 하지 않으며 순서 효과는 통제하지 않았다고 보고한다.

## 3. 프로토콜 (최대 11 boot, 110 RUN)

- boot마다 구성 하나. pass A(set 2)와 pass B(set 3), pass마다 warm-up 1 + 측정 4 = 5 RUN, 구성마다 10 RUN.
- 5 RUN 추가 trigger는 두지 않는다. 실패 boot의 재시도도 없다.
- 세션: owner 승인 sudo 세션 하나(`board/sudo_session.sh`, 암호는 `.env`에서 파이프로만). boot마다 한 단계, 각 단계 뒤
  `boot-check`, boot 1 뒤 `repro-gate`. 실패한 단계에서 세션을 멈추고 카드를 복원한다.

| pass | 이벤트 (번호 이름) | 구분 |
| --- | --- | --- |
| A (set 2) | 35 npu_active, 48 mac_active, 51 mac_dpu_active, 64 ao_active, 80 wd_active, 81 wd_stalled | TRM 공개 |
| A (set 2) | 53 mac_stalled_by_w, 55 mac_stalled_by_ib | driver 목록에만 있음(TRM 110 밖). 기록만, 결론에 쓰지 않음 |
| B (set 3) | 35 npu_active, 128 sram_rd_trans_accepted, 130 sram_rd_data_beat_received, 132 sram_wr_trans_accepted, 135 sram_wr_data_beat_written, 384 ext_rd_trans_accepted, 386 ext_rd_data_beat_received, 391 ext_wr_data_beat_written | TRM 공개 |

## 4. Gate와 중단 조건

| Gate | 내용 | 실패 시 |
| --- | --- | --- |
| G0 배포 | deploy digest, 재부팅 마커, PING | 세션 중단·복원, RUN 없음 |
| G1 재현 (boot 1) | `s4c2_conv_cin48`를 Stage 4K boot 375와 `stage4k.reproduce` 규칙으로 비교: 측정 RUN마다 MAC_ACTIVE·MAC_DPU_ACTIVE가 같고 기준(3,456)과 같음, 출력 sha256 같음·PASS_EXACT, 양쪽 상수 카운터(pass B beat 포함) 같음, NPU_ACTIVE pass A 중앙값 차이 ≤ max(기준의 1 %, 두 range). 기준 값은 판정 코드가 boot 375 원시 데이터에서 읽는다 | 나머지 10개 미실행(`NOT_MEASURED`), 원시 보존 |
| G2 boot마다 (`boot-check`) | 두 pass 모두 측정 RUN 4회, 모든 RUN 유효(`record_v2.validity`), 출력 **PASS_EXACT**(golden = BUILTIN_REF), 정체성 `stage4aoe.identity_a1`: n_base(기준 5, A2 6)와 REGIONCFG at IRQ = `placement_regioncfg(n_base, 0)`(0x15F / 0x55F), QCONFIG 3, placement 0, workload sha256, capabilities가 boot 1과 같음(TA 22개 레지스터 포함) | 세션 중단·복원. 이후 구성 `NOT_MEASURED`, 재측정 없음 |
| boot 안 | `--stop-on-invalid`: 무효 RUN, 출력 불일치, NPU fault, timeout, refusal, 무응답 | G2 FAIL로 처리 |

- REGIONCFG를 고정 상수로 검사하지 않는다(Stage 4AO-E boot 387의 실패 원인). 형상·주소·RUN 수·순서를 바꿔 재시도하지 않는다.

## 5. 지표와 공식 (보드 전 고정)

| 지표 | 정의 | 사용 |
| --- | --- | --- |
| N_MAC | H·W·Cin·Cout(§1, Vela mac_count와 같음을 판정 코드가 다시 확인) | 분자 |
| MAC_ACTIVE (48), MAC_DPU_ACTIVE (51) | 측정 RUN 4회 값. 모두 같아야 함 | 판정 |
| N_MAC / MAC_ACTIVE | MAC 활성 사이클당 유효 MAC | 보고 (값만) |
| N_MAC / (1024 · MAC_ACTIVE) | 구성 MAC/CC 1024 대비 비율 | 보고 (값만) |
| NPU_ACTIVE (35) | A2 그래프 전체(ADD 2개 + Conv) 실행 사이클, pass A 중앙값과 range | 보고 |
| N_MAC / (1024 · NPU_ACTIVE) | 그래프 전체 기준 비율 | 보고, "Conv 단독"으로 쓰지 않음 |
| AO_ACTIVE (64), WD_ACTIVE (80), WD_STALLED (81), pass B beat·transaction | 보조 | 기록만, 원인 배정 없음 |

- 처리율 범주(예: 640/768 계열)를 재사용하지 않는다. 형상별 값과 측정 범위만 보고한다.
- 출력 정확성은 PASS_EXACT만 통과다(Stage 4K §0와 같음).

**결과 범주(닫힌 집합).** 구성마다 `INVALID`(G2 실패, 출력 불일치, RUN 수 ≠ 4) > `MEASUREMENT_UNSTABLE`(측정 RUN 간
MAC_ACTIVE 또는 MAC_DPU_ACTIVE가 다름) > `COUNTER_IMPLAUSIBLE`(MAC_ACTIVE < N_MAC/1024, 물리 상한을 넘는 값) > `MEASURED`.
G1 실패 또는 G2 중단 뒤 구성은 `NOT_MEASURED`.

## 6. A2 래퍼 해석 한계

- NPU_ACTIVE와 AO_ACTIVE에는 ADD 2개의 비용이 들어 있다. 이 값을 Conv 단독 값으로 해석하지 않고, ADD 비용을 빼서 Conv
  값을 만들지 않는다.
- **MAC/WD 오염 검사.** Stage 4AO-E 보드 데이터(boot 395–400, TA profile 1, 이미지 `70090f1`)에서 ADD·MUL 커널 단독은
  MAC_ACTIVE 0, WD_ACTIVE 0이었다(H24·H72). 이 계약은 이를 근거로 A2의 MAC_ACTIVE·WD_ACTIVE를 Conv 커널의 값으로 읽되,
  `CONDITION_SPECIFIC`(다른 형상의 ADD에서 확인됨)으로 표시한다. 같은 형상의 ADD 단독 대조군은 예산에 없으므로 형상별로
  증명했다고 쓰지 않는다. 보드에서 MAC_ACTIVE ≠ MAC_DPU_ACTIVE이거나 `COUNTER_IMPLAUSIBLE`이면 그 구성의 MAC 지표를 결론에
  쓰지 않는다.
- WD_STALLED를 병목 시간으로 환산하지 않는다. NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 배정하지 않는다.
- 물리적 이용률(하드웨어가 실제로 놀고 있는 비율)을 주장하지 않는다. 1024는 구성 MAC/CC이고 Conv 공식 peak가 아니다.
- 결과는 "원본 모델과 같은 Conv 설정·가중치·활성화의 대표 형상을 A2 래퍼 안에서 잰 값"이다. 원본 모델 안의 실행 시간이나
  모델 전체 이용률로 바꿔 쓰지 않는다. Coverage는 정적 재현·측정 가능 범위이며 하드웨어 검증 coverage(Stage 6 값)는
  이번 측정으로 늘리지 않는다.

## 7. 모델 수준 적용

- 모델별로 원본 TFLite MAC, 1×1 DepthFirst MAC, EXACT_A MAC, BOARD_ELIGIBLE MAC, 선정 형상이 덮는 MAC을
  `amendment_b_coverage.csv` 값 그대로 보고한다. 측정 뒤에도 Validated HW coverage는 바꾸지 않는다.
- wav2letter(G14, `EXECUTION_CHANGED`: 원본 Conv 커널에 LeakyReLU LUT가 융합됨)와 yolo(EXACT_A 없음)는 `NO_ELIGIBLE`,
  rnnoise는 `NOT_APPLICABLE`이다. 이 모델들에 측정값을 외삽하지 않는다.

## 8. Vela 추정 대비 오차 (보조 분석, 보드 뒤에만 계산)

| 비교 | Vela 값 | 보드 값 | 상태 |
| --- | --- | --- | --- |
| 그래프 전체 | 같은 A2 컴파일의 Vela 성능 요약 `cycles_total` (아래 표) | NPU_ACTIVE (pass A 중앙값) | `COMPARABLE`: 같은 컴파일(`vela_sha256` = 레코드, 12개 모두 확인), 같은 범위(A2 그래프 전체). Vela 조건은 `Ethos_U85_SYS_DRAM_Mid_1024`, 1 GHz이며, 보드는 TA profile 1(SYS_DRAM_Mid 에뮬레이션)이다. 클록·메모리 모델이 같다는 것은 증명하지 않았으므로 오차는 이 조건과 함께만 보고한다 |
| Conv MAC | Conv 행 `vela_mac_cycles` | MAC_ACTIVE | `NOT_COMPARABLE`: 두 값의 정의가 같다는 근거가 없음 |
| Conv 전체 | Conv 행 `vela_op_cycles` | NPU_ACTIVE | `NOT_COMPARABLE`: 측정은 래퍼 전체 |

- 공식: Prediction Error (%) = (Board Cycles − Vela Estimated Cycles) / Vela Estimated Cycles × 100. 같은 컴파일 산출물이고
  실행 범위가 같은 비교에만 계산한다. 이번 작업에서는 계산하지 않는다.
- Vela 연산별 추정값은 `amendment_b_summary.json`의 `vela_estimates`에 있다. 네트워크 총계(`facts/vela_total.json`, 컨테이너
  `stage6b_amendment_b.py vela`)는 10개 모두 연산별 `vela_op_cycles`의 합과 같다.

| group | Vela cycles_total | cycles_npu | cycles_dram_access | cycles_sram_access |
|---|---:|---:|---:|---:|
| G12 | 53,052 | 33,314 | 44,709 | 28,800 |
| G25 | 14,909 | 9,534 | 14,820 | 4,603 |
| G40 | 30,422 | 23,716 | 30,315 | 8,405 |
| G53 | 10,631 | 7,227 | 10,566 | 2,700 |
| G11 | 37,273 | 22,562 | 35,799 | 21,600 |
| G56 | 7,520 | 5,213 | 7,469 | 2,022 |
| G52 | 15,393 | 9,891 | 15,277 | 5,400 |
| G57 | 10,955 | 7,865 | 10,912 | 3,106 |
| G09 | 29,928 | 19,165 | 29,755 | 13,002 |
| G28 | 12,947 | 11,714 | 9,969 | 963 |

## 9. 보드 실행 전 필수 조건 (R3만 완료)

- R1 보드 판정 코드 `host/analysis/stage6b_board.py`: §4 Gate, §5 범주, §6 검사. 테스트와 mutation 전부 KILLED. Stage 4K boot 375,
  Stage 4AO-E boot 395 원시 데이터로 dry run(정체성: n_base 5/6 두 경우를 모두 통과해야 함).
- R2 staging: 이미지 `70090f1` digest, DRWL 11개와 sha256, plan 11개, `ids.txt`, `conditions.txt`, 기준 원시(boot 375).
- R3 Vela 네트워크 총계: **완료**(§8 표, `facts/vela_total.json`). G23·G41도 수집했다.
- R4 `sh test.sh` ALL PASS, `sync.sh board`, 세션 파일 `--check` OK.
- R5 ChatGPT/owner의 보드 실행 승인.

## 10. 결정이 필요한 항목 (이 계약 밖)

- G23·G41: 원래 seed 입력에서 saturation 10 % 기준 미달(Original/Amendment 모두 FAIL), MLEK 입력 fixture에서는 PASS
  (`ADDITIONAL_VALIDATION`). 넣으려면 fixture DRWL(입력·golden만 다르고 `vela_sha256`·`cms_sha256` 같음)로 재는 별도 지시가 필요하다.
  넣는 경우 선정 시나리오(`additional_validation.selection_scenario`)는 G09·G28 대신 G23·G41이 들어간다.

## 11. 원시 데이터 보존과 장비 복원

- Stage 4K §8과 같다: 세션 뒤 원시 데이터를 `evidence/stage6b/revision_a/amendment_b/raw/`로 복사하고 sha256 목록을 남긴다.
- `restore_mlek`(m6 digest 확인) → `postflight.sh`(PING state 1, USB_OFF, 카드 분리). 카드가 마운트된 상태에서 `USB_OFF` 금지.
