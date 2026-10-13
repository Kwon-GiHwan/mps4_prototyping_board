# 공개 TRM 110개 PMU 이벤트 — FI101 보드 실측 기록

생성: `python3 host/report_trm110.py` (증거 트리에서 재생성; 손으로 편집하지 않는다). 2026-09-23.

## 범위와 출처

| 항목 | 값 |
| --- | --- |
| 대상 | Arm Ethos-U85 TRM 102685 r0p0 rev 0000-05, `PMEVTYPER<n>` *Table 2. Field EV_TYPE values* 의 명명된 110개 |
| 보드 | MPS4 FTDI-00FT46259002B, FI101-r1p0 (109762 v0100), NPU APB 0x50004000 |
| 구성(레지스터 실측) | CONFIG=`0x2000251a` → 1024 MAC, SRAM 포트 2, EXT 포트 2, WD 4; PMCR.num_event_cnt=8 |
| Tier A (수용) | 부팅 1, 이미지 APP `4018dacf1f4b2d6c…`, EV_TYPE 0..1023 write→readback, P1(cnt_en=1) 슬롯 0 기준 |
| Tier B (카운트) | 부팅 9 (host-boot-index 9), 이미지 APP `8472eb5a3e3afe8e…`, 22세트×3회=66 RUN 전부 VALID |
| 워크로드 | 러너 내장 고정 `U85 Convolution test` (`apU85Conv_TEST`), 1회 추론/RUN |
| 측정 방법 | EVENTS 모드: `CMD=0` hold → guard → `PMCR=EN\|RST` → guard → `PMCNTENSET=CYCLE\|slots`, `PMEVTYPER[i]=id` → 추론 → 벤더 `"Testing CPM signals"` printf seam(`CMD=0xC` 직전)에서 PMCCNTR·PMEVCNTR 판독 |
| 승인 | 소유자 구두 2026-09-23 (사실만 기록) |
| 증거 | `evidence/pmu_evsweep/boot1/`, `evidence/pmu_events/boot9/{raw_runs.json,per_event.csv,summary.json,POST_HOC.md}` |

판정(닫힌 집합, 3회 반복에서): `COUNTED_NONZERO` 3회 모두 >0 · `COUNTED_ZERO` 3회 모두 0 · `INCONSISTENT` 혼재 · `NOT_OBSERVED` 유효 RUN <3.
**0은 결과이지 부재의 증거가 아니다** — 아래 '비고'는 출처가 있는 사실 분류일 뿐 귀속이 아니다.

## 분류별 요약

| 분류 | 개수 | NONZERO | ZERO | INCONSISTENT | NOT_OBSERVED |
| --- | ---: | ---: | ---: | ---: | ---: |
| NPU 실행 상태 | 3 | 3 | 0 | 0 | 0 |
| MAC / AO | 3 | 3 | 0 | 0 | 0 |
| Weight decoder | 2 | 2 | 0 | 0 | 0 |
| 포트 집계 | 22 | 8 | 14 | 0 | 0 |
| AXI latency | 7 | 2 | 2 | 3 | 0 |
| ECC | 6 | 0 | 6 | 0 | 0 |
| 포트별 개별 | 66 | 16 | 50 | 0 | 0 |
| no_event | 1 | 0 | 1 | 0 | 0 |
| **합계** | **110** | **34** | **73** | **3** | **0** |

`no_event`(0)은 정의상 세지 않는 값이며 표에는 완전성을 위해 남긴다.

## 창(PMCCNTR at seam), 세트별 3회

| set | rep1 | rep2 | rep3 |
| --: | --: | --: | --: |
| 1 | 8495 | 4207 | 4211 |
| 2 | 8502 | 4199 | 4834 |
| 3 | 5445 | 6605 | 9230 |
| 4 | 9066 | 4232 | 4232 |
| 5 | 4705 | 9218 | 4207 |
| 6 | 4220 | 4232 | 4232 |
| 7 | 4230 | 9297 | 4685 |
| 8 | 4228 | 4500 | 9247 |
| 9 | 4228 | 4232 | 4210 |
| 10 | 6411 | 4234 | 4232 |
| 11 | 7240 | 4238 | 4207 |
| 12 | 4228 | 4234 | 9232 |
| 13 | 5907 | 6830 | 9194 |
| 14 | 4228 | 4412 | 4639 |
| 15 | 4228 | 9194 | 4232 |
| 16 | 4768 | 6650 | 4232 |
| 17 | 4230 | 8321 | 6488 |
| 18 | 9293 | 9219 | 4224 |
| 19 | 6024 | 4232 | 4232 |
| 20 | 4222 | 7237 | 9228 |
| 21 | 9134 | 4232 | 7814 |
| 22 | 8216 | 5724 | 3967 |

## 110개 전체 — TRM 정의 · 수용 · 실측값

값 열의 출처: `raw_runs.json` 의 `set_id`/`rep`/`event_values[slot]`; 위치 열이 그 좌표다.

| EV_TYPE | 이름 | TRM 설명 | Tier A | rep1 | rep2 | rep3 | 판정 | 위치 (set/slot) | 비고 |
| ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| 0 | `no_event` | No event. Event never occurs. No event counted | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 1/0 | 이 워크로드·창에서 0 |
| 17 | `cycle` | Elapsed cycle. Event occurs every cycle. Used for counter debug | ACCEPTED | 8744 | 4456 | 4460 | COUNTED_NONZERO | 1/1 |  |
| 32 | `npu_idle` | NPU in stopped state | ACCEPTED | 3742 | 3770 | 3770 | COUNTED_NONZERO | 1/2 |  |
| 35 | `npu_active` | NPU in running state | ACCEPTED | 5026 | 710 | 714 | COUNTED_NONZERO | 1/4 |  |
| 48 | `mac_active` | MAC is doing block traversal. Valid blk_cmd and not stalled | ACCEPTED | 32 | 32 | 32 | COUNTED_NONZERO | 1/5 |  |
| 51 | `mac_dpu_active` | At least one dot product unit is active, meaning the unit has at least one valid weight and activation pair | ACCEPTED | 36 | 36 | 36 | COUNTED_NONZERO | 1/6 |  |
| 64 | `ao_active` | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled | ACCEPTED | 17 | 17 | 16 | COUNTED_NONZERO | 2/3 |  |
| 80 | `wd_active` | WD is decoding weight stream. Valid blk_cmd and not stalled | ACCEPTED | 50 | 50 | 50 | COUNTED_NONZERO | 3/2 |  |
| 81 | `wd_stalled` | WD stalled on lack of weight stream data or lack of free WD buffer space | ACCEPTED | 359 | 349 | 5348 | COUNTED_NONZERO | 3/3 |  |
| 128 | `sram_rd_trans_accepted` | Read transfer (arready & arvalid) sum over SRAM AXI ports | ACCEPTED | 28 | 28 | 28 | COUNTED_NONZERO | 7/6 |  |
| 129 | `sram_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over SRAM AXI ports | ACCEPTED | 28 | 28 | 28 | COUNTED_NONZERO | 7/7 |  |
| 130 | `sram_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over SRAM AXI ports | ACCEPTED | 177 | 177 | 177 | COUNTED_NONZERO | 8/0 |  |
| 131 | `sram_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over SRAM AXI ports | ACCEPTED | 269 | 572 | 10391 | COUNTED_NONZERO | 8/1 |  |
| 132 | `sram_wr_trans_accepted` | Write transfers (awready & awvalid) sum over SRAM AXI ports | ACCEPTED | 4 | 4 | 4 | COUNTED_NONZERO | 8/2 |  |
| 135 | `sram_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over SRAM AXI ports | ACCEPTED | 16 | 16 | 16 | COUNTED_NONZERO | 8/5 |  |
| 136 | `sram_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over SRAM AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 8/6 | 이 워크로드·창에서 0 |
| 137 | `sram_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over SRAM AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 8/7 | 이 워크로드·창에서 0 |
| 140 | `sram_enabled_cycles` | Memory clock cycle (aclken_input), sum over SRAM AXI ports | ACCEPTED | 8912 | 8920 | 8876 | COUNTED_NONZERO | 9/0 |  |
| 142 | `sram_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over SRAM AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 9/1 | 이 워크로드·창에서 0 |
| 143 | `sram_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over SRAM AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 9/2 | 이 워크로드·창에서 0 |
| 160 | `axi_latency_any` | Any latency - measures the total number of transactions for the specified channel | ACCEPTED | 2 | 2 | 2 | COUNTED_NONZERO | 9/3 |  |
| 161 | `axi_latency_32` | Latency was >= 32 cycles | ACCEPTED | 2 | 2 | 2 | COUNTED_NONZERO | 9/4 |  |
| 162 | `axi_latency_64` | Latency was >= 64 cycles | ACCEPTED | 0 | 0 | 1 | INCONSISTENT | 9/5 | 0/1 경계 혼재 |
| 163 | `axi_latency_128` | Latency was >= 128 cycles | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 9/6 | 이 워크로드·창에서 0 |
| 164 | `axi_latency_256` | Latency was >= 256 cycles | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 9/7 | 이 워크로드·창에서 0 |
| 165 | `axi_latency_512` | Latency was >= 512 cycles | ACCEPTED | 1 | 0 | 0 | INCONSISTENT | 10/0 | 0/1 경계 혼재 |
| 166 | `axi_latency_1024` | Latency was >= 1024 cycles | ACCEPTED | 1 | 0 | 0 | INCONSISTENT | 10/1 | 0/1 경계 혼재 |
| 176 | `ecc_dma` | ECC event in DMA controller RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/2 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 177 | `ecc_mac_ib` | ECC event in MAC input buffer RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/3 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 178 | `ecc_mac_ab` | ECC event in MAC AB RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/4 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 179 | `ecc_ao_cb` | ECC event in AO CB RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/5 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 180 | `ecc_ao_ob` | ECC event in AO Output Buffer (OB) RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/6 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 181 | `ecc_ao_lut` | ECC event in AO lookup table RAM. This event is either corrected or uncorrected | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 10/7 | ECC 구성 여부 문서·레지스터로 확인 불가 |
| 384 | `ext_rd_trans_accepted` | Read transfer (arready & arvalid) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/0 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 385 | `ext_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 386 | `ext_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/2 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 387 | `ext_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/3 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 388 | `ext_wr_trans_accepted` | Write transfers (awready & awvalid) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/4 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 391 | `ext_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 11/7 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 392 | `ext_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 12/0 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 393 | `ext_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 12/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 396 | `ext_enabled_cycles` | Memory clock cycle (aclken_input), sum over EXT AXI ports | ACCEPTED | 9002 | 9014 | 19010 | COUNTED_NONZERO | 12/2 |  |
| 398 | `ext_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 12/3 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 399 | `ext_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over EXT AXI ports | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 12/4 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 512 | `sram0_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 0 | ACCEPTED | 14 | 14 | 14 | COUNTED_NONZERO | 12/5 |  |
| 513 | `sram0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 0 | ACCEPTED | 14 | 14 | 14 | COUNTED_NONZERO | 12/6 |  |
| 514 | `sram0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 0 | ACCEPTED | 84 | 84 | 84 | COUNTED_NONZERO | 12/7 |  |
| 515 | `sram0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 0 | ACCEPTED | 194 | 194 | 196 | COUNTED_NONZERO | 13/0 |  |
| 516 | `sram0_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 0 | ACCEPTED | 1 | 1 | 1 | COUNTED_NONZERO | 13/1 |  |
| 519 | `sram0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 0 | ACCEPTED | 4 | 4 | 4 | COUNTED_NONZERO | 13/4 |  |
| 520 | `sram0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 13/5 | 이 워크로드·창에서 0 |
| 521 | `sram0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 13/6 | 이 워크로드·창에서 0 |
| 524 | `sram0_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 0 | ACCEPTED | 6300 | 7223 | 9587 | COUNTED_NONZERO | 13/7 |  |
| 526 | `sram0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 14/0 | 이 워크로드·창에서 0 |
| 527 | `sram0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 14/1 | 이 워크로드·창에서 0 |
| 528 | `sram1_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 1 | ACCEPTED | 14 | 14 | 14 | COUNTED_NONZERO | 14/2 |  |
| 529 | `sram1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 1 | ACCEPTED | 14 | 14 | 14 | COUNTED_NONZERO | 14/3 |  |
| 530 | `sram1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 1 | ACCEPTED | 93 | 93 | 93 | COUNTED_NONZERO | 14/4 |  |
| 531 | `sram1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 1 | ACCEPTED | 75 | 290 | 507 | COUNTED_NONZERO | 14/5 |  |
| 532 | `sram1_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 1 | ACCEPTED | 3 | 3 | 3 | COUNTED_NONZERO | 14/6 |  |
| 535 | `sram1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 1 | ACCEPTED | 12 | 12 | 12 | COUNTED_NONZERO | 15/1 |  |
| 536 | `sram1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 15/2 | 이 워크로드·창에서 0 |
| 537 | `sram1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 15/3 | 이 워크로드·창에서 0 |
| 540 | `sram1_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 1 | ACCEPTED | 4549 | 9515 | 4553 | COUNTED_NONZERO | 15/4 |  |
| 542 | `sram1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 15/5 | 이 워크로드·창에서 0 |
| 543 | `sram1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 15/6 | 이 워크로드·창에서 0 |
| 544 | `sram2_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 15/7 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 545 | `sram2_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/0 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 546 | `sram2_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/1 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 547 | `sram2_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/2 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 548 | `sram2_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/3 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 551 | `sram2_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/6 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 552 | `sram2_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 16/7 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 553 | `sram2_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/0 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 556 | `sram2_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/1 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 558 | `sram2_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/2 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 559 | `sram2_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 2 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/3 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 560 | `sram3_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/4 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 561 | `sram3_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/5 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 562 | `sram3_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/6 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 563 | `sram3_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 17/7 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 564 | `sram3_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/0 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 567 | `sram3_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/3 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 568 | `sram3_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/4 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 569 | `sram3_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/5 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 572 | `sram3_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/6 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 574 | `sram3_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 18/7 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 575 | `sram3_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 3 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/0 | 1024 MAC 구성에 이 포트 없음 (CONFIG.num_axi_sram=1 → 2포트) |
| 640 | `ext0_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 641 | `ext0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/2 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 642 | `ext0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/3 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 643 | `ext0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/4 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 644 | `ext0_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 19/5 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 647 | `ext0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/0 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 648 | `ext0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 649 | `ext0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/2 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 652 | `ext0_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 0 | ACCEPTED | 4519 | 7534 | 9525 | COUNTED_NONZERO | 20/3 |  |
| 654 | `ext0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/4 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 655 | `ext0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 0 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/5 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 656 | `ext1_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/6 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 657 | `ext1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 20/7 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 658 | `ext1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/0 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 659 | `ext1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 660 | `ext1_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/2 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 663 | `ext1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/5 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 664 | `ext1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/6 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 665 | `ext1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 21/7 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 668 | `ext1_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 1 | ACCEPTED | 8444 | 5952 | 4195 | COUNTED_NONZERO | 22/0 |  |
| 670 | `ext1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 22/1 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |
| 671 | `ext1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 1 | ACCEPTED | 0 | 0 | 0 | COUNTED_ZERO | 22/2 | 이 워크로드는 EXT 데이터 트래픽 없음 (ext_enabled_cycles > 0) |

## 레코드 안의 산술 관계 (POST_HOC_DESCRIPTIVE — 판정에 쓰이지 않음)

- 읽기 트랜잭션: `sram0_rd_trans_accepted` 14 + `sram1_rd_trans_accepted` 14 = 28 vs `sram_rd_trans_accepted` 28
- 읽기 비트: 84 + 93 = 177 vs `sram_rd_data_beat_received` 177
- 쓰기 비트: 4 + 12 = 16 vs `sram_wr_data_beat_written` 16
- `cycle`(17) − PMCCNTR 창: [249, 249, 249] (3회 상수; seam 판독 순서 지연 — 사전 등록 ±1 % 검사는 FAIL로 유지)
- `npu_active`(35) + `npu_idle`(32) vs 창: [(8768, 8495), (4480, 4207), (4484, 4211)]

## 이 문서가 말하지 않는 것

값의 크기·비율·성능·효율. 워크로드 1개, 부팅 1회, 3회 반복. 다른 워크로드에서 어느 이벤트가 0이 아닐지는 다시 재야 안다.
TRM 밖의 61개(드라이버 전용 Reserved)는 `evidence/pmu_events/boot9/PER_EVENT.md` 에 있다.
