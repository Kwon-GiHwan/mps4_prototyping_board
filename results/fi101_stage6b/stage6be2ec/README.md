# Stage 6B-E2E-C 결과 — 잔여 EXT 경로 귀속 가능성 (보드 없음)

- 계약·분석 동결 `4ba841e`. 선행 유지보수 `df4aed0`.
- `stage6be2ec.py run`을 2회 실행했고 출력이 바이트 단위로 같다(`stage6be2ec_summary.json`, `ext_transactions.csv`).
- 다시 쓴 보드 자료는 모두 **TA profile 1**(E2D boot 449–457, E2E-B boot 458–462)이다.
- 보드 자료를 쓰는 분석은 모두 `POSTHOC_DIAGNOSTIC`이다.

## 최종 판정: **READY_FOR_TARGETED_BOARD_REVIEW** — 방법 B(가중치·scale 배치 통제) 하나

보드는 실행하지 않았다. 후속 계약 초안: `e2ed_board_contract_draft.md`(승인 필요).

## 1. Phase 0 — E2E-B 재현: 15개 검사 모두 통과

- summary 바이트 동일, 판정 6개 동일.
- B0/B3 NPU_ACTIVE(99,044 / 159,122.5, 60,320 / 72,526.5), LE(60,078.5 / 12,206.5), MAC 20,736.
- EXT read 감소 15,744 beat / 9,624 트랜잭션. B3 EXT read 11,322 / 793.
- read beat·트랜잭션·write beat 합 보존.
- AO·WD_ACTIVE 1 % 안.
- 출력 VALID.
- DRWL은 offset 28만 다르다.

## 2. EXT read 요청 구조 (`ext_transactions.csv`, TA profile 1)

| 구성 | EXT read beat / 트랜잭션 | beat/트랜잭션 | EXT 트랜잭션 / 1k NPU (L500) | LE |
|---|---|---|---|---|
| W1-P0 (A2, 전부 DDR) | 52,153 / 12,545 | 4.16 | 103.9 | 106,006.5 |
| B0 = W1-P1 (graph IO DDR) | 27,066 / 10,417 | 2.60 | 105.2 | 60,078.5 |
| **B3** (graph IO SRAM) | 11,322 / 793 | **14.28** | 13.1 | **12,206.5** |
| W0-P0 (Conv 단독 DDR) | 29,864 / 6,028 | 4.95 | 108.7 | 47,149 |
| **W0-P1** (Conv 단독, IO SRAM) | 11,304 / 788 | **14.35** | 29.1 | **13,545** |

- 쌍별 비교(기술값):

| 쌍 | 제거된 read | 평균 크기 | ΔLE | ΔLE/제거 트랜잭션 | 남은 경로 LE/트랜잭션 |
|---|---|---|---|---|---|
| B0 → B3 | 15,744 beat / 9,624 트랜잭션 | 1.64 beat(약 26 B) | 47,872 | 4.97 | 15.4 |
| W0-P0 → W0-P1 | 18,560 / 5,240 | 3.54 beat | 33,604 | 6.41 | 17.2 |

- 지연 효과의 대부분은 **작은 graph IO 읽기 요청이 많은 경로**와 함께 사라졌다. 남은 경로는 **큰 burst(약 14.3 beat = 228 B)의 가중치 읽기 약 790개**다.
- 같은 가중치 경로만 EXT에 남은 두 구성(W0-P1, B3)은 EXT 트랜잭션 수(788/793)와 LE(13,545/12,206.5)가 비슷하다. 남은 지연 반응이 가중치 경로와 함께 움직인다는 관찰과 일관된다. 그러나 상관일 뿐 원인 확인이 아니다.
- ΔLE/트랜잭션은 트랜잭션당 서비스 시간이 아니다(outstanding, 두 EXT 포트 분산, 실행 중첩 때문).
- 트래픽은 두 지연에서 같다. 지연이 바꾼 것은 시간뿐이다.

## 3. PMCAXI_CHAN과 FI101 적용 가능성

| 항목 | 상태 | 근거 |
|---|---|---|
| 1 PMCAXI_CHAN 인터페이스 | VERIFIED_SOURCE | TRM: PMU+0x2C(abs 0x11AC), CH_SEL[3:0], AXI_SEL[8], BW_CH_SEL_EN[10] |
| 2 CH_SEL과 AXI_SEL | VERIFIED_BOARD | Stage 3은 AXI_SEL = 0으로 SRAM·EXT read 이벤트 둘 다 필터됐다. AXI_SEL은 axi_latency 이벤트의 포트 선택(TRM) |
| 3 BW_CH_SEL_EN 범위 | VERIFIED_BOARD | read beat·트랜잭션은 필터된다. write beat는 0, write 트랜잭션은 필터 안 됨(해석 불가) |
| 4 모든 카운터에 같은 필터 | VERIFIED_SOURCE | 레지스터 하나이므로 pass 하나에 채널 하나 |
| 5 채널별 beat·트랜잭션 | VERIFIED_BOARD | Stage 3 표 |
| 6 실행 영향 없음 | VERIFIED_BOARD | npu_active·mac_active 불변(CHANNEL_FILTER_WORKS 7개 모델) |
| 7 합 대 전체 | VERIFIED_BOARD | 세 채널이 전체 read의 83.6–96 %. rd_cmd·rd_scale_bias는 측정한 적 없음 |
| 8 8 카운터 | VERIFIED_SOURCE | NPU_ACTIVE 앵커 1 + 7 |
| 9 driver runner 설정·readback | **NOT_IMPLEMENTED** | driver runner 소스에 없다. legacy runner는 쓰고 되읽는다(header word 16) |

- 채널: rd_weights·rd_ifm·rd_mem2mem = READ_FILTER_VERIFIED. **rd_cmd·rd_scale_bias**·rd_ifm_stream·rd_mem2mem_idx·wr_mem2mem = UNVERIFIED. wr_ofm = WRITE_NOT_INTERPRETABLE.

## 4. 공개 PMU 이벤트 (FI101)

| 상태 | 이벤트 |
|---|---|
| VERIFIED_ON_FI101 | 384 ext_rd_trans_accepted, 386 ext_rd_data_beat_received, 387 ext_rd_tran_req_stalled, 640/642/656/658 포트별 accepted·beat |
| INCONSISTENT_ON_FI101 | 398 ext_rd_stall_limit(kws에서 RUN마다 0/366) |
| TRM_ONLY_UNVERIFIED | 385 ext_rd_trans_completed, 643/659 포트별 req_stalled, **160–166 axi_latency_\*** |
| RESERVED(근거로 쓰지 않음) | 53, 55 |

- 387의 의미는 `arvalid & ~arready`, 즉 주소 채널에서 요청이 받아들여지지 않은 사이클이다. 데이터가 돌아오기까지의 대기시간이 아니다.
- axi_latency_N은 "지연 ≥ N 사이클" 임계 누적이며, 선택한 채널·포트 하나에만 적용된다.
- 이 이벤트들은 **트래픽과 지연 분포**를 줄 수 있다. 그러나 NPU_ACTIVE 증가를 채널에 배분하지는 못한다.

## 5. 채널별 계측과 Weight/Command 분리

- 정적 채널 기대(B3):
  - rd_weights 174,752 B(10,922 beat)
  - rd_scale_bias 5,760 B(360)
  - rd_cmd 628 B(39.25)
  - rd_ifm/mem2mem 0
- 합 11,321.25 대 보드 11,322 beat(+12 B, 배분하지 않음).
- 방법 A(채널 필터)는 이 분할을 측정으로 확인할 수 있다. 하지만 H-R1과 H-R2 모두 같은 채널 바이트를 예측하므로 **원인을 가르지 못한다**(`discriminating = False`).
- 방법 B는 region 0(가중치·scale)만 옮기고 command stream(QBASE)은 EXT에 둔다. 두 가설이 다른 결과를 예측하므로 원인을 가를 수 있다.
- scale/bias와 가중치는 같은 region 0이라 함께 움직인다. 이 둘은 분리되지 않는다.

## 6. Vela 비용 모델의 요청·burst 처리 (Vela 5.0.0, E2A 소스 감사)

| 항목 | 모델 |
|---|---|
| 읽기량 | 원소 바이트 × burst 효율 부풀림 |
| burst | ChannelBW = burst × min(RB/(burst/16), outstanding × ports × 0.8) / latency × 0.8 |
| latency | ChannelBW(처리율 상한)에만 들어간다. 요청별·의존성 대기는 없다 |
| outstanding | max_reads × ports × 0.8을 꽉 찬 burst로 다 쓴다고 가정 |
| 작은 요청 | 비용 없음. 요청 크기는 설정 burst이고 요청 수는 식에 없다 |
| 연산별 MAX | op = max(npu, SRAM, DRAM), 그래프 = 합. 연산 사이 중첩·의존 없음 |

- A2(B0)에서 Vela의 graph IO 비용은 Add1 DRAM 21,562(L500) / 43,124(L1000)이다. 141,312 B를 6.55 B/cycle로 나눈 값이다.
- 보드에서 같은 경로는 약 26 B짜리 읽기 요청 9,624개였다. Vela는 요청을 설정 burst 크기로 가정하므로, 요청이 이렇게 작으면 outstanding 한계에서 실제 처리율이 Vela 식보다 훨씬 낮을 수 있다. 이것이 B0 과소예측(1.87/1.91배)과 일관된 후보다(POSTHOC, 미검증).
- Vela A2 Conv의 가중치 DRAM 항은 16,409 → 32,818로 늘고, 연산 비용은 24,290 → 32,818이다. 이는 Vela가 가중치 경로를 세는 방식을 보여주는 사실일 뿐이며, B3 예측값이나 오차로 쓰지 않는다.
- Conv 단독 DRAM의 과대예측(NHWC burst 부풀림, C1 정오표 보존)은 반대 방향이다. **두 오차를 하나의 보정 계수로 묶지 않는다.**

## 7. 잔여 지연 민감도 가설

| 가설 | 지금 근거 | 방법 B 예측 | 가를 수 없는 것 |
|---|---|---|---|
| H-R1 가중치·scale 공급 | W0-P1과 B3에서 남은 LE가 가중치 경로 트랜잭션 수와 함께 비슷함(상관) | LE(B3w) ≤ 0.25 LE(B3), EXT read 약 39 beat | 가중치 대 scale, 그 파이프라인 효과 |
| H-R2 command fetch | command stream 628 B(39 beat). 크기는 작지만 순차 fetch라 배제할 수 없음 | LE(B3w) ≥ 0.75 LE(B3) | fetch 지연 대 kernel 시작 의존 |
| H-R3 파이프라인 의존성 | 공개 카운터로 사이클 배분 불가 | 직접 관측 없음(H-R1·H-R2를 매개) | DMA·WD·AO·MAC 중첩 |

## 8. 후속 실험의 식별력과 Gate

| 방법 | 상태 | 가설 구분 | Gate 1–5 | BOARD_CHECK_REQUIRED |
|---|---|---|---|---|
| A 채널 필터(Pass C) | AVAILABLE | **아니오** | 2번 실패 | 2(rd_cmd·scale_bias 필터, runner 구현) |
| **B 가중치 배치(B3w)** | AVAILABLE | **예** | 모두 통과 | 2(새 이미지 동등성, 측정창 밖 복사·cache) |

방법 B의 전제(VERIFIED_SOURCE):
- 훅 위치: `ethosu_address_remap`이 QBASE(147행)와 BASEP i(158행)에 따로 호출되고, `ethosu_config_select`가 REGIONCFG를 정한다(163행). MLEK core-driver는 수정되지 않았다.
- 내용: region 0에는 WEIGHT·SCALE만 있다(E2E-A region 표). 따라서 command stream·QCONFIG는 그대로다.
- SRAM 용량: 사본 `0x31280420–0x312964B0` < `0x31400000`. arena(`…0x31276770`)와도 fast memory와도 겹치지 않는다.

## 9. Stage 6C로 넘어갈 수 있는지

- Memory/Pipeline에서 남은 질문은 하나다: B3의 지연 효과 12,206.5가 가중치·scale 공급 때문인가, command fetch 때문인가.
- 방법 B 하나로 이를 가를 수 있다(5 boot).
- 이 실험을 승인하지 않으면 현재 범위를 종료하고 Stage 6C로 넘어가도 된다. 지금까지의 결론(graph IO 경로가 지연 민감도의 약 80 %, 남은 EXT는 가중치·scale·command)은 그대로 유효하다.

## 10. 한계

- 방법 B는 runner 펌웨어 변경과 새 이미지 두 개(L500/L1000)가 필요하다. 대조군 B3가 E2E-B를 재현하는지로 동등성을 확인해야 한다.
- B3w에서는 가중치가 SRAM 포트(TA_SRAM)로 읽히므로, 포트와 물리 메모리가 함께 바뀐다.
- 기존 테스트의 임시 파일 누수는 test.sh 1회에 0.9 MB가 남아 있다(더 오래된 단계의 테스트, 수정하지 않음).
