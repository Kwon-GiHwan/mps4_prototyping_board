# Ethos-U85 PMU 이벤트 — 공식 출처 대조

대조 수행일 2026-09-23. **문서 대조만 수행. 보드 실행·실측 없음.**

## 한 줄 결론

공개 TRM(102685 r0p0)은 PMU 이벤트를 **110개 전부 이름 + 집계 조건까지 문서화**하고 있다.
"이름만 코드에서 확인했다"는 상태의 항목은 사실상 없다.
예외는 단 5개 — `mac_stalled_by_w` / `_acc` / `_ib`, `wd_stalled_by_wd_buf`,
`cc_stalled_on_blockdep` — 이들은 **문서에서 못 찾은 게 아니라, TRM이 해당 ID를 `Reserved`로 명시**한다.

---

## 1. 항목별 판정

판정 기호: **[TRM]** = 공개 TRM 본문에 이름·설명 존재 / **[RSV]** = 드라이버 헤더에는 있으나 공개 TRM이 그 ID를 `Reserved`로 표기

모든 [TRM] 항목의 출처는 동일하다 — 102685 r0p0 rev 0000-05,
`Programmers-model → Register-sets-for-NPU-control → PMU_COUNTERS register summary → PMEVTYPER<n> register`,
*Table 2. Field EV_TYPE values*. `PMEVTYPER0`~`PMEVTYPER7` 8개 페이지를 모두 받아 표를 비교했고 **110개 이름 집합이 완전히 동일**했다.
모든 [RSV] 항목의 출처는 `ethos-u-core-driver` `main` 브랜치 `src/ethosu_interface_u85.h`의 `enum pmu_event` 다.

### NPU 실행 상태

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 17 | `cycle` | Elapsed cycle. Event occurs every cycle. Used for counter debug |
| **[TRM]** | 32 | `npu_idle` | NPU in stopped state |
| **[TRM]** | 35 | `npu_active` | NPU in running state |

### 연산부 활동

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 48 | `mac_active` | MAC is doing block traversal. Valid blk_cmd and not stalled |
| **[TRM]** | 51 | `mac_dpu_active` | At least one dot product unit is active, meaning the unit has at least one valid weight and activation pair |
| **[TRM]** | 64 | `ao_active` | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled |

### MAC stall

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[RSV]** | 52 | `mac_stalled_by_w_or_acc` | — (TRM은 이 ID를 `Reserved`로 표기) |
| **[RSV]** | 53 | `mac_stalled_by_w` | — (TRM은 이 ID를 `Reserved`로 표기) |
| **[RSV]** | 54 | `mac_stalled_by_acc` | — (TRM은 이 ID를 `Reserved`로 표기) |
| **[RSV]** | 55 | `mac_stalled_by_ib` | — (TRM은 이 ID를 `Reserved`로 표기) |

### Weight decoder

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 80 | `wd_active` | WD is decoding weight stream. Valid blk_cmd and not stalled |
| **[TRM]** | 81 | `wd_stalled` | WD stalled on lack of weight stream data or lack of free WD buffer space |
| **[RSV]** | 83 | `wd_stalled_by_wd_buf` | — (TRM은 이 ID를 `Reserved`로 표기) |

### 메모리 전송량

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 130 | `sram_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over SRAM AXI ports |
| **[TRM]** | 135 | `sram_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over SRAM AXI ports |
| **[TRM]** | 386 | `ext_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over EXT AXI ports |
| **[TRM]** | 391 | `ext_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over EXT AXI ports |

### 메모리 요청·stall

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 128 | `sram_rd_trans_accepted` | Read transfer (arready & arvalid) sum over SRAM AXI ports |
| **[TRM]** | 131 | `sram_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over SRAM AXI ports |
| **[TRM]** | 137 | `sram_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over SRAM AXI ports |
| **[TRM]** | 384 | `ext_rd_trans_accepted` | Read transfer (arready & arvalid) sum over EXT AXI ports |
| **[TRM]** | 387 | `ext_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over EXT AXI ports |
| **[TRM]** | 393 | `ext_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over EXT AXI ports |

### AXI latency

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[TRM]** | 160 | `axi_latency_any` | Any latency - measures the total number of transactions for the specified channel |
| **[TRM]** | 161 | `axi_latency_32` | Latency was >= 32 cycles |
| **[TRM]** | 162 | `axi_latency_64` | Latency was >= 64 cycles |
| **[TRM]** | 163 | `axi_latency_128` | Latency was >= 128 cycles |
| **[TRM]** | 164 | `axi_latency_256` | Latency was >= 256 cycles |
| **[TRM]** | 165 | `axi_latency_512` | Latency was >= 512 cycles |
| **[TRM]** | 166 | `axi_latency_1024` | Latency was >= 1024 cycles |

### 명령 의존성

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) |
| ---- | ------: | ---- | -------------------- |
| **[RSV]** | 33 | `cc_stalled_on_blockdep` | — (TRM은 이 ID를 `Reserved`로 표기) |

### 항목별 판정 요약

- 질의된 30개 중 **25개가 [TRM]** — 원 정리표의 "미확인" 열에 있던 `CYCLE`, `NPU_IDLE`, `MAC_DPU_ACTIVE`,
  `WD_ACTIVE`, `SRAM_WR_DATA_BEAT_WRITTEN`, `EXT_*`, `AXI_LATENCY_ANY/_128/_256/_512/_1024`,
  SRAM/EXT 집계형 `*_RD_TRANS_ACCEPTED` · `*_RD_TRAN_REQ_STALLED` · `*_WR_DATA_BEAT_STALLED`는 **전부 TRM 본문에 있다**.
- **[RSV]는 5개뿐**: `mac_stalled_by_w`, `mac_stalled_by_acc`, `mac_stalled_by_ib`, `wd_stalled_by_wd_buf`, `cc_stalled_on_blockdep`.
  (같은 성격의 `mac_stalled_by_w_or_acc`도 [RSV].)

### 해석상 주의 — 확인된 범위

- `axi_latency_32`의 공식 조건은 **`Latency was >= 32 cycles`** 이다. 임계값이며 배타적 히스토그램 bin이 아니다.
  `axi_latency_any`는 "지정된 채널의 **전체 트랜잭션 수**"이므로, 비율을 내려면 `_any`를 분모로 쓴다.
- AXI latency 계열은 `PMCAXI_CHAN`으로 채널·포트를 하나 고른 뒤에만 의미가 있다 (아래 3절).
- `mac_dpu_active`의 공식 정의는 "**적어도 하나의** dot product unit이 활성"이다. MAC 이용률이 아니다.
- `ao_active`는 "accumulation 또는 chaining buffer의 block traversal"이며, `mac_active`와 같은 축이 아니다.
- `cycle`의 공식 설명은 "Event occurs every cycle. **Used for counter debug**"이다.
  경과 사이클 측정에는 전용 `PMCCNTR`을 쓰는 것이 문서가 의도한 경로다.

---

## 2. 공식 TRM EV_TYPE 전체 (110개)

출처: [https://developer.arm.com/documentation/102685/0000/Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary/PMEVTYPER0-register](https://developer.arm.com/documentation/102685/0000/Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary/PMEVTYPER0-register) — *Table 2. Field EV_TYPE values*. (`PMEVTYPER1`~`7` 동일)

| EV_TYPE | 이름 | TRM 설명 |
| ------: | ---- | -------- |
| 0 | `no_event` | No event. Event never occurs. No event counted |
| 17 | `cycle` | Elapsed cycle. Event occurs every cycle. Used for counter debug |
| 32 | `npu_idle` | NPU in stopped state |
| 35 | `npu_active` | NPU in running state |
| 48 | `mac_active` | MAC is doing block traversal. Valid blk_cmd and not stalled |
| 51 | `mac_dpu_active` | At least one dot product unit is active, meaning the unit has at least one valid weight and activation pair |
| 64 | `ao_active` | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled |
| 80 | `wd_active` | WD is decoding weight stream. Valid blk_cmd and not stalled |
| 81 | `wd_stalled` | WD stalled on lack of weight stream data or lack of free WD buffer space |
| 128 | `sram_rd_trans_accepted` | Read transfer (arready & arvalid) sum over SRAM AXI ports |
| 129 | `sram_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over SRAM AXI ports |
| 130 | `sram_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over SRAM AXI ports |
| 131 | `sram_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over SRAM AXI ports |
| 132 | `sram_wr_trans_accepted` | Write transfers (awready & awvalid) sum over SRAM AXI ports |
| 135 | `sram_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over SRAM AXI ports |
| 136 | `sram_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over SRAM AXI ports |
| 137 | `sram_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over SRAM AXI ports |
| 140 | `sram_enabled_cycles` | Memory clock cycle (aclken_input), sum over SRAM AXI ports |
| 142 | `sram_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over SRAM AXI ports |
| 143 | `sram_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over SRAM AXI ports |
| 160 | `axi_latency_any` | Any latency - measures the total number of transactions for the specified channel |
| 161 | `axi_latency_32` | Latency was >= 32 cycles |
| 162 | `axi_latency_64` | Latency was >= 64 cycles |
| 163 | `axi_latency_128` | Latency was >= 128 cycles |
| 164 | `axi_latency_256` | Latency was >= 256 cycles |
| 165 | `axi_latency_512` | Latency was >= 512 cycles |
| 166 | `axi_latency_1024` | Latency was >= 1024 cycles |
| 176 | `ecc_dma` | ECC event in DMA controller RAM. This event is either corrected or uncorrected |
| 177 | `ecc_mac_ib` | ECC event in MAC input buffer RAM. This event is either corrected or uncorrected |
| 178 | `ecc_mac_ab` | ECC event in MAC AB RAM. This event is either corrected or uncorrected |
| 179 | `ecc_ao_cb` | ECC event in AO CB RAM. This event is either corrected or uncorrected |
| 180 | `ecc_ao_ob` | ECC event in AO Output Buffer (OB) RAM. This event is either corrected or uncorrected |
| 181 | `ecc_ao_lut` | ECC event in AO lookup table RAM. This event is either corrected or uncorrected |
| 384 | `ext_rd_trans_accepted` | Read transfer (arready & arvalid) sum over EXT AXI ports |
| 385 | `ext_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over EXT AXI ports |
| 386 | `ext_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over EXT AXI ports |
| 387 | `ext_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over EXT AXI ports |
| 388 | `ext_wr_trans_accepted` | Write transfers (awready & awvalid) sum over EXT AXI ports |
| 391 | `ext_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over EXT AXI ports |
| 392 | `ext_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over EXT AXI ports |
| 393 | `ext_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over EXT AXI ports |
| 396 | `ext_enabled_cycles` | Memory clock cycle (aclken_input), sum over EXT AXI ports |
| 398 | `ext_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over EXT AXI ports |
| 399 | `ext_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over EXT AXI ports |
| 512 | `sram0_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 0 |
| 513 | `sram0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 0 |
| 514 | `sram0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 0 |
| 515 | `sram0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 0 |
| 516 | `sram0_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 0 |
| 519 | `sram0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 0 |
| 520 | `sram0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 0 |
| 521 | `sram0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 0 |
| 524 | `sram0_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 0 |
| 526 | `sram0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 0 |
| 527 | `sram0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 0 |
| 528 | `sram1_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 1 |
| 529 | `sram1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 1 |
| 530 | `sram1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 1 |
| 531 | `sram1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 1 |
| 532 | `sram1_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 1 |
| 535 | `sram1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 1 |
| 536 | `sram1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 1 |
| 537 | `sram1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 1 |
| 540 | `sram1_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 1 |
| 542 | `sram1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 1 |
| 543 | `sram1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 1 |
| 544 | `sram2_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 2 |
| 545 | `sram2_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 2 |
| 546 | `sram2_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 2 |
| 547 | `sram2_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 2 |
| 548 | `sram2_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 2 |
| 551 | `sram2_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 2 |
| 552 | `sram2_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 2 |
| 553 | `sram2_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 2 |
| 556 | `sram2_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 2 |
| 558 | `sram2_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 2 |
| 559 | `sram2_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 2 |
| 560 | `sram3_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 3 |
| 561 | `sram3_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 3 |
| 562 | `sram3_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 3 |
| 563 | `sram3_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 3 |
| 564 | `sram3_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 3 |
| 567 | `sram3_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 3 |
| 568 | `sram3_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 3 |
| 569 | `sram3_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 3 |
| 572 | `sram3_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 3 |
| 574 | `sram3_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 3 |
| 575 | `sram3_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 3 |
| 640 | `ext0_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 0 |
| 641 | `ext0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 0 |
| 642 | `ext0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 0 |
| 643 | `ext0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 0 |
| 644 | `ext0_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 0 |
| 647 | `ext0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 0 |
| 648 | `ext0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 0 |
| 649 | `ext0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 0 |
| 652 | `ext0_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 0 |
| 654 | `ext0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 0 |
| 655 | `ext0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 0 |
| 656 | `ext1_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 1 |
| 657 | `ext1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 1 |
| 658 | `ext1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 1 |
| 659 | `ext1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 1 |
| 660 | `ext1_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 1 |
| 663 | `ext1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 1 |
| 664 | `ext1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 1 |
| 665 | `ext1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 1 |
| 668 | `ext1_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 1 |
| 670 | `ext1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 1 |
| 671 | `ext1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 1 |

`0..16`, `18..31`, `33..34`, `36..47`, `49..50`, `52..63`, `65..79`, `82..127` 등 표에 없는 구간은 모두 `Reserved`로 명시되어 있다.

---

## 3. PMU 레지스터 자원 (TRM 102685)

출처: `Programmers-model/Register-sets-for-NPU-control/PMU-register-summary` 및 그 하위 페이지, 
`.../PMU-COUNTERS-register-summary`.

| 항목 | 값 | 출처 페이지 |
| ---- | -- | ----------- |
| 이벤트 카운터 수 | **8**. `PMCR.num_event_cnt[15:11]`, RO, reset `8` | PMCR register |
| 이벤트 카운터 | `PMEVCNTR0..7` @ PMU_COUNTERS 0x0000–0x001C, 각 32-bit | PMU_COUNTERS register summary |
| 사이클 카운터 | **별도**. `PMCCNTR` @ PMU 0x0020–0x0024. 레지스터 폭은 64-bit이나 **카운터 필드는 `CYCLE_CNT[47:0]`**, [63:48] Reserved | PMCCNTR register |
| 이벤트 선택 | `PMEVTYPER<n>.EV_TYPE[9:0]`, `pmu_event_t`, 기본값 `no_event` | PMEVTYPER<n> register |
| 포트별 게이팅 | `PMEVTYPER<n>.D0..D3` = [12],[13],[14],[15]. 각 AXI 포트의 카운팅을 개별 disable | PMEVTYPER<n> register |
| 사이클 카운터 구간 지정 | `PMCCNTR_CFG.CYCLE_CNT_CFG_START[9:0]`, `CYCLE_CNT_CFG_STOP[25:16]`. 둘 다 `pmu_event_t` 전체 값 사용 가능 | PMCCNTR_CFG register |
| AXI latency 채널 선택 | `PMCAXI_CHAN`: `CH_SEL[3:0]`, `AXI_SEL[8]`, `BW_CH_SEL_EN[10]` (아래 표) | PMCAXI_CHAN register |
| 복합 이벤트 | `PMCLUT`: `PCM_LUT_EN_0[0]`, `PMC_LUT_0[31:16]` | PMCLUT register |
| 커맨드 스트림 게이팅 | `NPU_OP_PMU_MASK` (cmd0), `enable[16]` + `PMCR.mask_en[3]` | NPU_OP_PMU_MASK instruction |
| 오버플로 / 인터럽트 | `PMOVSSET` 0x000C, `PMOVSCLR` 0x0010, `PMINTSET` 0x0014, `PMINTCLR` 0x0018 | PMU register summary |
| 카운터 enable | `PMCNTENSET` 0x0004 / `PMCNTENCLR` 0x0008. 사이클 카운터 비트는 드라이버 기준 bit31 (`ETHOSU_PMU_CCNT_Msk`) | PMU register summary, `ethosu_pmu_types.h` |
| 리셋 | `PMCR.event_cnt_rst[1]` (WO), `PMCR.cycle_cnt_rst[2]` (WO) | PMCR register |

> TRM 주석 (PMU register summary 페이지): *"Register writes to the PMU, other than those that modify
> `PMCR.cnt_en`, are not guaranteed to take effect unless `PMCR.cnt_en=1`."*
> → 이벤트 설정은 `cnt_en=1` 상태에서 수행해야 한다.

### PMCAXI_CHAN.CH_SEL 값 (`pmu_axi_channel_t`)

| 값 | 이름 | 설명 |
| -- | ---- | ---- |
| 0x0 | `rd_cmd` | Command stream read channel |
| 0x1 | `rd_ifm` | IFM read channel |
| 0x2 | `rd_weights` | Weights read channel |
| 0x3 | `rd_scale_bias` | Bias and scale read channel |
| 0x4 | `rd_mem2mem` | Memory to memory read channel |
| 0x5 | `rd_ifm_stream` | IFM to weights or elementwise |
| 0x6 | `rd_mem2mem_idx` | Memory to memory index channel |
| 0x8 | `wr_ofm` | The OFM write channel |
| 0x9 | `wr_mem2mem` | The mem2mem write channel |

`AXI_SEL[8]`: `0` = SRAM AXI 포트(들), `1` = EXT AXI 포트(들). 기본 `sram`.
`BW_CH_SEL_EN[10]`: `0` = AXI bw 이벤트를 전 채널에 대해 측정, `1` = `CH_SEL`이 지정한 채널만.

### PMCLUT — 8개 제약을 우회하는 유일한 문서화된 수단

TRM `PMCLUT` 원문: 카운터 0이 복합 이벤트를 셀 수 있다.
`((PMC_LUT_0 >> k) & 1) == 1`, `k = 8*event[3] + 4*event[2] + 2*event[1] + event[0]`,
여기서 `event[n]`은 `PMEVTYPER[n]`이 설정한 이벤트다.
문서가 명시하는 두 가지 함정:

1. **카운터 n의 counting이 disable이어도 `event[n]`은 k 계산에 포함된다.**
2. 이벤트 n이 한 사이클에 여러 번 발생해도 `event[n]`은 1로 취급된다.

즉 `mac_active AND sram_rd_tran_req_stalled` 같은 교집합을 직접 세는 경로가 존재한다.
동시 8개 제약 하에서 조합을 바꿔 반복 측정하지 않고도 상관을 볼 수 있는 유일한 문서화된 수단이다.

---

## 4. 드라이버 헤더에만 있는 61개 (TRM = Reserved)

`ethosu_interface_u85.h`의 `enum pmu_event`는 **171개**, 공개 TRM은 **110개**.
관계는 엄격한 포함이다 — TRM의 110개는 이름·값이 드라이버와 **전부 일치** (이름 불일치 0건, TRM에만 있는 항목 0건).
나머지 61개는 전부 TRM이 `Reserved`로 둔 ID에 있다.

연구 자료에 쓸 때는 **"Arm 드라이버 헤더에 정의되어 있으나 공개 TRM r0p0에서는 Reserved"** 로 표기해야 정확하다.
`102685`는 공개 버전이 `r0p0` / revision `0000-05` 하나뿐이며 (`/versions`, `/revisions` 모두 단일 항목),
따라서 "더 최신 공개 개정판에 있을 것"이라는 기대는 성립하지 않는다.

| id | 드라이버 이름 |
| -: | ------------- |
| 33 | `cc_stalled_on_blockdep` |
| 52 | `mac_stalled_by_w_or_acc` |
| 53 | `mac_stalled_by_w` |
| 54 | `mac_stalled_by_acc` |
| 55 | `mac_stalled_by_ib` |
| 67 | `ao_stalled_by_bs_or_ob` |
| 68 | `ao_stalled_by_bs` |
| 69 | `ao_stalled_by_ob` |
| 70 | `ao_stalled_by_ab_or_cb` |
| 71 | `ao_stalled_by_ab` |
| 72 | `ao_stalled_by_cb` |
| 83 | `wd_stalled_by_wd_buf` |
| 84 | `wd_stalled_by_ws_fc` |
| 85 | `wd_stalled_by_ws_tc` |
| 89 | `wd_trans_wblk` |
| 90 | `wd_trans_ws_fc` |
| 91 | `wd_trans_ws_tc` |
| 96 | `wd_stalled_by_ws_sc0` |
| 97 | `wd_stalled_by_ws_sc1` |
| 98 | `wd_stalled_by_ws_sc2` |
| 99 | `wd_stalled_by_ws_sc3` |
| 100 | `wd_parse_active_sc0` |
| 101 | `wd_parse_active_sc1` |
| 102 | `wd_parse_active_sc2` |
| 103 | `wd_parse_active_sc3` |
| 104 | `wd_parse_stall_sc0` |
| 105 | `wd_parse_stall_sc1` |
| 106 | `wd_parse_stall_sc2` |
| 107 | `wd_parse_stall_sc3` |
| 108 | `wd_parse_stall_in_sc0` |
| 109 | `wd_parse_stall_in_sc1` |
| 110 | `wd_parse_stall_in_sc2` |
| 111 | `wd_parse_stall_in_sc3` |
| 112 | `wd_parse_stall_out_sc0` |
| 113 | `wd_parse_stall_out_sc1` |
| 114 | `wd_parse_stall_out_sc2` |
| 115 | `wd_parse_stall_out_sc3` |
| 116 | `wd_trans_ws_sc0` |
| 117 | `wd_trans_ws_sc1` |
| 118 | `wd_trans_ws_sc2` |
| 119 | `wd_trans_ws_sc3` |
| 120 | `wd_trans_wb0` |
| 121 | `wd_trans_wb1` |
| 122 | `wd_trans_wb2` |
| 123 | `wd_trans_wb3` |
| 133 | `sram_wr_trans_completed_m` |
| 134 | `sram_wr_trans_completed_s` |
| 389 | `ext_wr_trans_completed_m` |
| 390 | `ext_wr_trans_completed_s` |
| 517 | `sram0_wr_trans_completed_m` |
| 518 | `sram0_wr_trans_completed_s` |
| 533 | `sram1_wr_trans_completed_m` |
| 534 | `sram1_wr_trans_completed_s` |
| 549 | `sram2_wr_trans_completed_m` |
| 550 | `sram2_wr_trans_completed_s` |
| 565 | `sram3_wr_trans_completed_m` |
| 566 | `sram3_wr_trans_completed_s` |
| 645 | `ext0_wr_trans_completed_m` |
| 646 | `ext0_wr_trans_completed_s` |
| 661 | `ext1_wr_trans_completed_m` |
| 662 | `ext1_wr_trans_completed_s` |

---

## 5. FI101 / SSE-320 구성 (109762)

문서 109762 version `0100`, 버전 라벨 원문: **`FI101-r1p0 with Cortex-M85 and Ethos-U85`**.

| 항목 | 값 | 출처 페이지 |
| ---- | -- | ----------- |
| MAC 수 | **1024** ("The SSE-320 subsystem uses 1024 MACs.") | `FPGA/Neural-Processing-Unit` |
| NPU APB base | Non-secure `0x4000_4000`–`0x4000_4FFF`, Secure `0x5000_4000`–`0x5000_4FFF` | `FPGA/Neural-Processing-Unit` |
| AXI manager | 4개: `NPU0M0`..`NPU0M3`. M0/M1 → VM0..VM3, XMSTEXPDEV / M2/M3 → XMSTEPDRAM0, XMSTEPDRAM1 | `FPGA/Neural-Processing-Unit` |
| 타이밍 어댑터 | **4개**, Ethos-U85에 통합. APB 창 `0x4110_2000`–`0x4110_2FFF` (NS) | `FPGA/Neural-Processing-Unit`, `Programmer-s-model/Timing-Adapter` |
| TA base — SRAM | `0x4110_2000`–`0x4110_21FF` (NS). **이 base가 SRAM0과 SRAM1 둘 다 설정한다** | `Programmer-s-model/Timing-Adapter` |
| TA base — DRAM/EXT | `0x4110_2400`–`0x4110_25FF` (NS). **이 base가 DRAM0과 DRAM1 둘 다 설정한다** | `Programmer-s-model/Timing-Adapter` |
| SHIM logic | 각 AXI 인터페이스에 통합. Striped Memory Zone(VM2, VM3) 접근 시 사용 | `FPGA/Neural-Processing-Unit` |
| 파라미터 | `NUMNPU=1`, `NPU0TYPE=3`, `CPU0TYPE=4` | `SSE-320-functional-description/SSE-320-parameter-values` |

### TRM: 구성별 AXI 포트 수

출처: `Functional-description-.../Configuration-pins-and-AXI-port-striping/AXI-ports-per-NPU-configuration`

| NPU 구성 (MACs/CC) | SRAM 포트 (128b, 40-bit addr) | EXT 포트 (128b, 40-bit addr) |
| -----------------: | ----------------------------: | ---------------------------: |
| 128 | 2 | 1 |
| 256 | 2 | 1 |
| 512 | 2 | 1 |
| 1024 **(FI101)** | 2 | 2 |
| 2048 | 4 | 2 |

---

## 6. 이 보드에서 UNPROVEN인 것

**파생 추론이며, 두 문서 어디에도 명시되어 있지 않다.**
FI101은 1024 MAC 구성이고 그 구성의 SRAM 포트는 2개다. 반면 EV_TYPE 표에는 `sram0_*`~`sram3_*`가 모두 있다.
따라서 `sram2_*` / `sram3_*` (id 544–575, 26개)에는 FI101에서 대응하는 포트가 없다.
**그 카운터가 무엇을 읽는지는 어느 문서도 말하지 않는다.** 0이라고 가정하지 말고 이 보드에서는 UNPROVEN으로 둔다.

그 외 UNPROVEN:

- 110개 중 어느 이벤트가 FI101 실물에서 0이 아닌 값을 내는지 — **전혀 측정하지 않았다**.
- `PMCLUT` 복합 이벤트가 이 이미지에서 동작하는지 — 문서상 존재만 확인.
- `NPU_OP_PMU_MASK`의 실제 거동 — TRM이 *debug feature only*로 라벨하고 있고, 실행 검증 없음.
- [RSV] 5개 이벤트를 실제로 `PMEVTYPER`에 써 넣었을 때의 거동 — 미측정. Reserved ID를 쓰는 것이므로
  "동작한다"도 "동작하지 않는다"도 근거가 없다.

### 보드에서의 자가 확인 경로

`BASE.CONFIG` @ `0x0028` 은 RO이고 stopped/running 양쪽에서 읽을 수 있다.

- `macs_per_cc[3:0]` — MAC 수의 **log2**. `ETHOSU85_128`→7, `256`→8, `512`→9, **`1024`→10**, `2048`→11
- `cmd_stream_version[7:4]` — 이 NPU가 받는 커맨드 스트림 버전

앱 노트를 믿는 대신 이 레지스터를 읽어 구성을 확인하는 것이 맞다.

---

## 7. 출처와 재현 절차

### 왜 웹 뷰어에서 본문이 안 보였는가

`developer.arm.com/documentation/...` 는 React SPA다. 초기 HTML에는 `<title>` 외에 본문이 없고,
`curl`이나 일반 페이지 가져오기로는 10KB짜리 셸만 받는다. (현재 `support.arm.com`으로 301 리다이렉트된다.)
본문은 그 SPA가 호출하는 백엔드에 있고, **인증 없이 접근 가능**하다:

```
https://documentation-service.arm.com/documentation/<doc>/<version>[/<topic-slug>]
```

응답은 `application/hal+json`이며 `content` 필드가 **base64로 인코딩된 토픽 HTML**이다.
루트 응답의 `topic.topics`가 전체 목차 트리이고, 각 노드의 `slug`가 곧 위 URL의 topic-slug다.
(`<version>`에 `latest`는 루트에서만 동작한다. slug를 붙일 때는 `0000`, `0100` 처럼 실제 버전을 써야 404가 안 난다.)

### 참조한 정확한 위치

| # | 문서 | 버전 | 토픽 slug |
| - | ---- | ---- | --------- |
| S1 | Arm Ethos-U85 NPU Technical Reference Manual (102685) | r0p0, rev 0000-05 | `Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary/PMEVTYPER0-register` … `PMEVTYPER7-register` |
| S2 | 〃 | 〃 | `Programmers-model/Register-sets-for-NPU-control/PMU-register-summary` + `/PMCR-register`, `/PMCCNTR-register`, `/PMCCNTR-CFG-register`, `/PMCAXI-CHAN-register`, `/PMCLUT-register` |
| S3 | 〃 | 〃 | `Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary` |
| S4 | 〃 | 〃 | `Functional-description-of-the-Arm--Ethos-U85--NPU/Functional-blocks/Configuration-pins-and-AXI-port-striping/AXI-ports-per-NPU-configuration` |
| S5 | 〃 | 〃 | `Programmers-model/Register-sets-for-NPU-control/BASE-register-summary/CONFIG-register` |
| S6 | 〃 | 〃 | `Programmers-model/Instruction-index-for-cmd0-stream/NPU-OP-PMU-MASK-instruction` |
| S7 | Arm Corstone SSE-320 FPGA Image for MPS4 Application Note (109762) | `0100` = *FI101-r1p0 with Cortex-M85 and Ethos-U85* | `FPGA/Neural-Processing-Unit`, `Programmer-s-model/Timing-Adapter`, `SSE-320-functional-description/SSE-320-parameter-values` |
| S8 | ethos-u-core-driver, `gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver`, branch `main` | — | `src/ethosu_interface_u85.h`, `src/ethosu_pmu_u85.c`, `include/ethosu_pmu_types.h` |

### 드라이버 측 교차 확인 (S8)

- `NPU_REG_PMEVCNTR_ARRLEN = 0x0008`, `NPU_REG_PMEVTYPER_ARRLEN = 0x0008` → TRM의 `num_event_cnt=8`과 일치.
- `ETHOSU_PMU_NCOUNTERS`는 `ETHOSU85`일 때 `8`, 아니면 `4` (`ethosu_pmu_types.h`).
- `ethosu_pmu_u85.c`의 `U85_PMU_Set_CCNTR`은 `MASK_32_47_BITS = 0xFFFF00000000`으로 상위를 자른다 → TRM의 `CYCLE_CNT[47:0]`과 일치.
- `EXPAND_PMU_EVENT(FUNC, SEP)` 매크로는 `enum pmu_event`와 **같은 171개**로 전개된다 (`FUNC(` 출현 171회).
- ⚠️ `include/ethosu_pmu_types.h`의 `enum ethosu_pmu_event_type`은 U85 전용이 아니다.
  헤더 주석 원문: *"Abstraction layer list of all combined PMU events for **all devices** … 
  **Not all device types supports all event types.**"* — U55/U65의 `AXI0_*`, `ECC_SB0/1`,
  `CC_STALLED_ON_SHRAM_RECONFIG` 등이 섞여 있으므로 이 목록을 U85 근거로 인용하면 안 된다.
  U85 근거는 `src/ethosu_interface_u85.h` 쪽이다.

### 재현

아래 헬퍼를 `armdoc.py`로 저장한다. 이 문서의 모든 TRM/앱노트 인용은 이 스크립트로 받은 것이다.

```python
import sys,json,base64,re,html,urllib.request,os
def fetch(doc,ver,slug=""):
    u=f"https://documentation-service.arm.com/documentation/{doc}/{ver}"
    if slug: u+="/"+slug
    r=urllib.request.urlopen(u,timeout=60).read()
    return json.loads(r)
def text(d):
    c=d.get('content')
    if not c: return ""
    s=base64.b64decode(c).decode('utf8','replace')
    s=re.sub(r'<(script|style).*?</\1>','',s,flags=re.S)
    s=re.sub(r'</t[dh]>','\t',s); s=re.sub(r'</tr>','\n',s)
    s=re.sub(r'<[^>]+>','',s); s=html.unescape(s)
    return '\n'.join(l.strip() for l in s.split('\n') if l.strip())
def toc(doc,ver):
    d=fetch(doc,ver); rows=[]
    def w(n):
        rows.append((n.get('label'),n.get('slug')))
        for c in n.get('topics') or []: w(c)
    w(d['topic']); return rows
if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="toc":
        for lab,slug in toc(sys.argv[2],sys.argv[3]): print(f"{lab}\t{slug}")
    else:
        print(text(fetch(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)>4 else "")))
```

```sh
python3 armdoc.py toc  102685 0000                     # 전체 목차 (label<TAB>slug)
python3 armdoc.py page 102685 0000 \
  Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary/PMEVTYPER0-register

python3 armdoc.py toc  109762 0100                     # FI101 앱노트
python3 armdoc.py page 109762 0100 Programmer-s-model/Timing-Adapter
```

`toc` 는 `latest` 도 받지만, `page` 에 slug를 붙일 때는 `latest` 가 404가 난다. 실제 버전(`0000`, `0100`)을 쓸 것.

### 원본 digest (sha256)

추출에 쓴 원본과 파싱 결과를 `docs/ethos_u85_pmu_sources/` 에 함께 둔다.

```
34c839957b8c91742a6d40425bd9c5df4a17757bfa18c092a18c8d31694f8332  docs/ethos_u85_pmu_sources/102685_0000_PMEVTYPER0.response.json
ca5047363c734059b0ab3813f5406fdb74a8e0284e161203c3a82b065d8af842  docs/ethos_u85_pmu_sources/trm_events_110.json
79a5785bd2ff948f28dd7d19ceb04a8656ac6b264e33a12b09482aa0fbc4429b  docs/ethos_u85_pmu_sources/driver_events_171.json
d5ca6b5abfba4758fdc811b04780937ccce806a29d4a427ff352e99ec15f355c  docs/ethos_u85_pmu_sources/armdoc.py
```

| 파일 | 내용 |
| ---- | ---- |
| `102685_0000_PMEVTYPER0.response.json` | S1 PMEVTYPER0 토픽의 `documentation-service` 응답 원본 (base64 본문 포함) |
| `trm_events_110.json` | 위 응답에서 파싱한 공식 EV_TYPE 110개 `[id, name, description]` |
| `driver_events_171.json` | `ethosu_interface_u85.h` `enum pmu_event`에서 파싱한 171개 `[id, name]` |
| `armdoc.py` | 재현 헬퍼 |

`src/ethosu_interface_u85.h` 자체(763KB)는 크기 때문에 넣지 않았다. S8 경로에서 다시 받을 수 있으나,
`main` 브랜치 tip이므로 내용이 바뀔 수 있다 — 위 `driver_events_171.json` 이 2026-09-23 취득분의 고정 스냅샷이다.

---

## 검증 수준

```
검증 수준: 문서 대조 (1차 출처 원문 추출 + 프로그램적 집합 비교)

실제 실행한 것:
  - S1~S6 TRM 토픽 본문 추출 및 텍스트화
  - PMEVTYPER0~7 8개 페이지 EV_TYPE 표 집합 동일성 검증 → 110/110 일치, 불일치 0
  - TRM 110개 vs ethosu_interface_u85.h 171개 집합 비교 (이름/값 양방향)
  - 102685 /versions, /revisions 조회 → 공개 버전 단일(r0p0, 0000-05) 확인
  - S7 FI101 토픽 본문 추출, S8 드라이버 3개 파일 다운로드 및 grep

실행하지 않은 것:
  - MPS4 보드 실행, PMU 카운터 실측, 빌드, 펌웨어 수정 — 일절 없음
  - 110개 중 어느 이벤트가 FI101 실물에서 유효한 값을 내는지 — 미검증
  - sram2_*/sram3_* 의 실제 거동 — 파생 추론일 뿐
  - [RSV] 5개 이벤트를 하드웨어에 써 넣었을 때의 거동 — 미검증
  - Arm TRM PDF 원본과의 대조 — 웹 백엔드가 제공하는 토픽 본문만 사용
```
