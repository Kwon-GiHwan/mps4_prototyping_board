# Ethos-U85 PMU 이벤트 — 공식 출처 대조

대조 수행일 2026-09-23. **문서 대조만 수행. 보드 실행·실측 없음.**

## 한 줄 결론

공개 TRM(102685 r0p0)은 PMU 이벤트를 **110개 전부 이름 + 집계 조건까지 문서화**하고 있다.
"이름만 코드에서 확인했다"는 상태의 항목은 사실상 없다.
예외는 단 5개 — `mac_stalled_by_w` / `_acc` / `_ib`, `wd_stalled_by_wd_buf`,
`cc_stalled_on_blockdep` — 이들은 **문서에서 못 찾은 게 아니라, TRM이 해당 ID를 `Reserved`로 명시**한다.

---

## 0. 출처 키 (표의 `출처` 열 읽는 법)

2절·4절의 모든 이벤트 행과 1절의 모든 판정 행은 **행마다** 출처를 달고 있다. 표기는 세 조각이다.

| 키 | 가리키는 것 |
| -- | ----------- |
| `S1`§`<id>` | **Arm Ethos-U85 NPU TRM, 문서 102685, r0p0, revision 0000-05** → `Programmers-model / Register-sets-for-NPU-control / PMU_COUNTERS register summary / PMEVTYPER0 register` → *Table 2. Field EV_TYPE values* 의 **`EV_TYPE = <id>` 행**. `EV_TYPE` 값이 그 표 안의 고유 키다.<br>URL: <https://developer.arm.com/documentation/102685/0000/Programmers-model/Register-sets-for-NPU-control/PMU-COUNTERS-register-summary/PMEVTYPER0-register><br>`PMEVTYPER1`~`PMEVTYPER7` 페이지에도 같은 표가 실려 있고, 8개 페이지의 이름 집합이 동일함을 확인했다. 대표로 `PMEVTYPER0`을 인용한다. |
| `S1`§`<id>`=Reserved | 같은 표의 같은 위치에 이름이 없고 `Reserved`로 표기되어 있다는 뜻. **"검색으로 못 찾음"이 아니라 "문서가 비워 둠"이다.** |
| `S8e`:L*n* | **ethos-u-core-driver**, commit `5f0b9d1e17b2` (*Bump version to 2.0.0*, 2026-08-26) 의 `src/ethosu_interface_u85.h` → `enum pmu_event` 의 **n번째 줄**.<br>영구링크: <https://gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver/-/blob/5f0b9d1e17b245aefc308ee0d5a4543833b96b11/src/ethosu_interface_u85.h> (`#L<n>` 을 붙이면 해당 줄) |
| `S8x`:L*n* | 같은 파일·같은 commit 의 `EXPAND_PMU_EVENT(FUNC, SEP)` 매크로 전개 목록의 **n번째 줄**. `enum pmu_event` 와 171개로 동일하게 대응함을 확인했다. |

`src/ethosu_interface_u85.h` 의 sha256 은 `79aa695a7a35cabfdda83856661ceabb1169d2ece1e08b86c48d2fadd0f09ece` 이며,
위 commit 에서 다시 받아 대조했다. 줄 번호는 이 commit 에 고정된 값이고, `main` tip 이 움직이면 달라진다 —
이름·값 쌍이 안정적인 키다. 줄 번호 전체 매핑은 `docs/ethos_u85_pmu_sources/driver_lines.json` 에 있다.

---

## 1. 항목별 판정

판정 기호: **[TRM]** = 공개 TRM 본문에 이름·설명 존재 / **[RSV]** = 드라이버 헤더에는 있으나 공개 TRM이 그 ID를 `Reserved`로 표기

모든 [TRM] 항목의 출처는 동일하다 — 102685 r0p0 rev 0000-05,
`Programmers-model → Register-sets-for-NPU-control → PMU_COUNTERS register summary → PMEVTYPER<n> register`,
*Table 2. Field EV_TYPE values*. `PMEVTYPER0`~`PMEVTYPER7` 8개 페이지를 모두 받아 표를 비교했고 **110개 이름 집합이 완전히 동일**했다.
모든 [RSV] 항목의 출처는 `ethos-u-core-driver` `main` 브랜치 `src/ethosu_interface_u85.h`의 `enum pmu_event` 다.

### NPU 실행 상태

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 17 | `cycle` | Elapsed cycle. Event occurs every cycle. Used for counter debug | `S1`§`17` · `S8e`:L1428 · `S8x`:L24378 |
| **[TRM]** | 32 | `npu_idle` | NPU in stopped state | `S1`§`32` · `S8e`:L1429 · `S8x`:L24379 |
| **[TRM]** | 35 | `npu_active` | NPU in running state | `S1`§`35` · `S8e`:L1431 · `S8x`:L24381 |

### 연산부 활동

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 48 | `mac_active` | MAC is doing block traversal. Valid blk_cmd and not stalled | `S1`§`48` · `S8e`:L1432 · `S8x`:L24382 |
| **[TRM]** | 51 | `mac_dpu_active` | At least one dot product unit is active, meaning the unit has at least one valid weight and activation pair | `S1`§`51` · `S8e`:L1433 · `S8x`:L24383 |
| **[TRM]** | 64 | `ao_active` | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled | `S1`§`64` · `S8e`:L1438 · `S8x`:L24388 |

### MAC stall

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[RSV]** | 52 | `mac_stalled_by_w_or_acc` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`52`=Reserved · `S8e`:L1434 · `S8x`:L24384 |
| **[RSV]** | 53 | `mac_stalled_by_w` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`53`=Reserved · `S8e`:L1435 · `S8x`:L24385 |
| **[RSV]** | 54 | `mac_stalled_by_acc` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`54`=Reserved · `S8e`:L1436 · `S8x`:L24386 |
| **[RSV]** | 55 | `mac_stalled_by_ib` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`55`=Reserved · `S8e`:L1437 · `S8x`:L24387 |

### Weight decoder

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 80 | `wd_active` | WD is decoding weight stream. Valid blk_cmd and not stalled | `S1`§`80` · `S8e`:L1445 · `S8x`:L24395 |
| **[TRM]** | 81 | `wd_stalled` | WD stalled on lack of weight stream data or lack of free WD buffer space | `S1`§`81` · `S8e`:L1446 · `S8x`:L24396 |
| **[RSV]** | 83 | `wd_stalled_by_wd_buf` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`83`=Reserved · `S8e`:L1447 · `S8x`:L24397 |

### 메모리 전송량

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 130 | `sram_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over SRAM AXI ports | `S1`§`130` · `S8e`:L1483 · `S8x`:L24433 |
| **[TRM]** | 135 | `sram_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over SRAM AXI ports | `S1`§`135` · `S8e`:L1488 · `S8x`:L24438 |
| **[TRM]** | 386 | `ext_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over EXT AXI ports | `S1`§`386` · `S8e`:L1509 · `S8x`:L24459 |
| **[TRM]** | 391 | `ext_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over EXT AXI ports | `S1`§`391` · `S8e`:L1514 · `S8x`:L24464 |

### 메모리 요청·stall

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 128 | `sram_rd_trans_accepted` | Read transfer (arready & arvalid) sum over SRAM AXI ports | `S1`§`128` · `S8e`:L1481 · `S8x`:L24431 |
| **[TRM]** | 131 | `sram_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over SRAM AXI ports | `S1`§`131` · `S8e`:L1484 · `S8x`:L24434 |
| **[TRM]** | 137 | `sram_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over SRAM AXI ports | `S1`§`137` · `S8e`:L1490 · `S8x`:L24440 |
| **[TRM]** | 384 | `ext_rd_trans_accepted` | Read transfer (arready & arvalid) sum over EXT AXI ports | `S1`§`384` · `S8e`:L1507 · `S8x`:L24457 |
| **[TRM]** | 387 | `ext_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over EXT AXI ports | `S1`§`387` · `S8e`:L1510 · `S8x`:L24460 |
| **[TRM]** | 393 | `ext_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over EXT AXI ports | `S1`§`393` · `S8e`:L1516 · `S8x`:L24466 |

### AXI latency

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[TRM]** | 160 | `axi_latency_any` | Any latency - measures the total number of transactions for the specified channel | `S1`§`160` · `S8e`:L1494 · `S8x`:L24444 |
| **[TRM]** | 161 | `axi_latency_32` | Latency was >= 32 cycles | `S1`§`161` · `S8e`:L1495 · `S8x`:L24445 |
| **[TRM]** | 162 | `axi_latency_64` | Latency was >= 64 cycles | `S1`§`162` · `S8e`:L1496 · `S8x`:L24446 |
| **[TRM]** | 163 | `axi_latency_128` | Latency was >= 128 cycles | `S1`§`163` · `S8e`:L1497 · `S8x`:L24447 |
| **[TRM]** | 164 | `axi_latency_256` | Latency was >= 256 cycles | `S1`§`164` · `S8e`:L1498 · `S8x`:L24448 |
| **[TRM]** | 165 | `axi_latency_512` | Latency was >= 512 cycles | `S1`§`165` · `S8e`:L1499 · `S8x`:L24449 |
| **[TRM]** | 166 | `axi_latency_1024` | Latency was >= 1024 cycles | `S1`§`166` · `S8e`:L1500 · `S8x`:L24450 |

### 명령 의존성

| 판정 | EV_TYPE | 이름 | 공식 설명 (TRM 원문) | 출처 |
| ---- | ------: | ---- | -------------------- | ---- |
| **[RSV]** | 33 | `cc_stalled_on_blockdep` | — (TRM은 이 ID를 `Reserved`로 표기) | `S1`§`33`=Reserved · `S8e`:L1430 · `S8x`:L24380 |

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

| EV_TYPE | 이름 | TRM 설명 | 출처 |
| ------: | ---- | -------- | ---- |
| 0 | `no_event` | No event. Event never occurs. No event counted | `S1`§`0` · `S8e`:L1427 · `S8x`:L24377 |
| 17 | `cycle` | Elapsed cycle. Event occurs every cycle. Used for counter debug | `S1`§`17` · `S8e`:L1428 · `S8x`:L24378 |
| 32 | `npu_idle` | NPU in stopped state | `S1`§`32` · `S8e`:L1429 · `S8x`:L24379 |
| 35 | `npu_active` | NPU in running state | `S1`§`35` · `S8e`:L1431 · `S8x`:L24381 |
| 48 | `mac_active` | MAC is doing block traversal. Valid blk_cmd and not stalled | `S1`§`48` · `S8e`:L1432 · `S8x`:L24382 |
| 51 | `mac_dpu_active` | At least one dot product unit is active, meaning the unit has at least one valid weight and activation pair | `S1`§`51` · `S8e`:L1433 · `S8x`:L24383 |
| 64 | `ao_active` | AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled | `S1`§`64` · `S8e`:L1438 · `S8x`:L24388 |
| 80 | `wd_active` | WD is decoding weight stream. Valid blk_cmd and not stalled | `S1`§`80` · `S8e`:L1445 · `S8x`:L24395 |
| 81 | `wd_stalled` | WD stalled on lack of weight stream data or lack of free WD buffer space | `S1`§`81` · `S8e`:L1446 · `S8x`:L24396 |
| 128 | `sram_rd_trans_accepted` | Read transfer (arready & arvalid) sum over SRAM AXI ports | `S1`§`128` · `S8e`:L1481 · `S8x`:L24431 |
| 129 | `sram_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over SRAM AXI ports | `S1`§`129` · `S8e`:L1482 · `S8x`:L24432 |
| 130 | `sram_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over SRAM AXI ports | `S1`§`130` · `S8e`:L1483 · `S8x`:L24433 |
| 131 | `sram_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over SRAM AXI ports | `S1`§`131` · `S8e`:L1484 · `S8x`:L24434 |
| 132 | `sram_wr_trans_accepted` | Write transfers (awready & awvalid) sum over SRAM AXI ports | `S1`§`132` · `S8e`:L1485 · `S8x`:L24435 |
| 135 | `sram_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over SRAM AXI ports | `S1`§`135` · `S8e`:L1488 · `S8x`:L24438 |
| 136 | `sram_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over SRAM AXI ports | `S1`§`136` · `S8e`:L1489 · `S8x`:L24439 |
| 137 | `sram_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over SRAM AXI ports | `S1`§`137` · `S8e`:L1490 · `S8x`:L24440 |
| 140 | `sram_enabled_cycles` | Memory clock cycle (aclken_input), sum over SRAM AXI ports | `S1`§`140` · `S8e`:L1491 · `S8x`:L24441 |
| 142 | `sram_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over SRAM AXI ports | `S1`§`142` · `S8e`:L1492 · `S8x`:L24442 |
| 143 | `sram_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over SRAM AXI ports | `S1`§`143` · `S8e`:L1493 · `S8x`:L24443 |
| 160 | `axi_latency_any` | Any latency - measures the total number of transactions for the specified channel | `S1`§`160` · `S8e`:L1494 · `S8x`:L24444 |
| 161 | `axi_latency_32` | Latency was >= 32 cycles | `S1`§`161` · `S8e`:L1495 · `S8x`:L24445 |
| 162 | `axi_latency_64` | Latency was >= 64 cycles | `S1`§`162` · `S8e`:L1496 · `S8x`:L24446 |
| 163 | `axi_latency_128` | Latency was >= 128 cycles | `S1`§`163` · `S8e`:L1497 · `S8x`:L24447 |
| 164 | `axi_latency_256` | Latency was >= 256 cycles | `S1`§`164` · `S8e`:L1498 · `S8x`:L24448 |
| 165 | `axi_latency_512` | Latency was >= 512 cycles | `S1`§`165` · `S8e`:L1499 · `S8x`:L24449 |
| 166 | `axi_latency_1024` | Latency was >= 1024 cycles | `S1`§`166` · `S8e`:L1500 · `S8x`:L24450 |
| 176 | `ecc_dma` | ECC event in DMA controller RAM. This event is either corrected or uncorrected | `S1`§`176` · `S8e`:L1501 · `S8x`:L24451 |
| 177 | `ecc_mac_ib` | ECC event in MAC input buffer RAM. This event is either corrected or uncorrected | `S1`§`177` · `S8e`:L1502 · `S8x`:L24452 |
| 178 | `ecc_mac_ab` | ECC event in MAC AB RAM. This event is either corrected or uncorrected | `S1`§`178` · `S8e`:L1503 · `S8x`:L24453 |
| 179 | `ecc_ao_cb` | ECC event in AO CB RAM. This event is either corrected or uncorrected | `S1`§`179` · `S8e`:L1504 · `S8x`:L24454 |
| 180 | `ecc_ao_ob` | ECC event in AO Output Buffer (OB) RAM. This event is either corrected or uncorrected | `S1`§`180` · `S8e`:L1505 · `S8x`:L24455 |
| 181 | `ecc_ao_lut` | ECC event in AO lookup table RAM. This event is either corrected or uncorrected | `S1`§`181` · `S8e`:L1506 · `S8x`:L24456 |
| 384 | `ext_rd_trans_accepted` | Read transfer (arready & arvalid) sum over EXT AXI ports | `S1`§`384` · `S8e`:L1507 · `S8x`:L24457 |
| 385 | `ext_rd_trans_completed` | Read complete (rready & rvalid & rlast) sum over EXT AXI ports | `S1`§`385` · `S8e`:L1508 · `S8x`:L24458 |
| 386 | `ext_rd_data_beat_received` | Read bandwidth (rready & rvalid) sum over EXT AXI ports | `S1`§`386` · `S8e`:L1509 · `S8x`:L24459 |
| 387 | `ext_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) sum over EXT AXI ports | `S1`§`387` · `S8e`:L1510 · `S8x`:L24460 |
| 388 | `ext_wr_trans_accepted` | Write transfers (awready & awvalid) sum over EXT AXI ports | `S1`§`388` · `S8e`:L1511 · `S8x`:L24461 |
| 391 | `ext_wr_data_beat_written` | Write bandwidth (wvalid & wready) sum over EXT AXI ports | `S1`§`391` · `S8e`:L1514 · `S8x`:L24464 |
| 392 | `ext_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) sum over EXT AXI ports | `S1`§`392` · `S8e`:L1515 · `S8x`:L24465 |
| 393 | `ext_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) sum over EXT AXI ports | `S1`§`393` · `S8e`:L1516 · `S8x`:L24466 |
| 396 | `ext_enabled_cycles` | Memory clock cycle (aclken_input), sum over EXT AXI ports | `S1`§`396` · `S8e`:L1517 · `S8x`:L24467 |
| 398 | `ext_rd_stall_limit` | Read stalls due to max outstanding transactions limit, sum over EXT AXI ports | `S1`§`398` · `S8e`:L1518 · `S8x`:L24468 |
| 399 | `ext_wr_stall_limit` | Write stalls due to max outstanding transactions limit, sum over EXT AXI ports | `S1`§`399` · `S8e`:L1519 · `S8x`:L24469 |
| 512 | `sram0_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 0 | `S1`§`512` · `S8e`:L1520 · `S8x`:L24470 |
| 513 | `sram0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 0 | `S1`§`513` · `S8e`:L1521 · `S8x`:L24471 |
| 514 | `sram0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 0 | `S1`§`514` · `S8e`:L1522 · `S8x`:L24472 |
| 515 | `sram0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 0 | `S1`§`515` · `S8e`:L1523 · `S8x`:L24473 |
| 516 | `sram0_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 0 | `S1`§`516` · `S8e`:L1524 · `S8x`:L24474 |
| 519 | `sram0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 0 | `S1`§`519` · `S8e`:L1527 · `S8x`:L24477 |
| 520 | `sram0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 0 | `S1`§`520` · `S8e`:L1528 · `S8x`:L24478 |
| 521 | `sram0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 0 | `S1`§`521` · `S8e`:L1529 · `S8x`:L24479 |
| 524 | `sram0_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 0 | `S1`§`524` · `S8e`:L1530 · `S8x`:L24480 |
| 526 | `sram0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 0 | `S1`§`526` · `S8e`:L1531 · `S8x`:L24481 |
| 527 | `sram0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 0 | `S1`§`527` · `S8e`:L1532 · `S8x`:L24482 |
| 528 | `sram1_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 1 | `S1`§`528` · `S8e`:L1533 · `S8x`:L24483 |
| 529 | `sram1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 1 | `S1`§`529` · `S8e`:L1534 · `S8x`:L24484 |
| 530 | `sram1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 1 | `S1`§`530` · `S8e`:L1535 · `S8x`:L24485 |
| 531 | `sram1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 1 | `S1`§`531` · `S8e`:L1536 · `S8x`:L24486 |
| 532 | `sram1_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 1 | `S1`§`532` · `S8e`:L1537 · `S8x`:L24487 |
| 535 | `sram1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 1 | `S1`§`535` · `S8e`:L1540 · `S8x`:L24490 |
| 536 | `sram1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 1 | `S1`§`536` · `S8e`:L1541 · `S8x`:L24491 |
| 537 | `sram1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 1 | `S1`§`537` · `S8e`:L1542 · `S8x`:L24492 |
| 540 | `sram1_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 1 | `S1`§`540` · `S8e`:L1543 · `S8x`:L24493 |
| 542 | `sram1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 1 | `S1`§`542` · `S8e`:L1544 · `S8x`:L24494 |
| 543 | `sram1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 1 | `S1`§`543` · `S8e`:L1545 · `S8x`:L24495 |
| 544 | `sram2_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 2 | `S1`§`544` · `S8e`:L1546 · `S8x`:L24496 |
| 545 | `sram2_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 2 | `S1`§`545` · `S8e`:L1547 · `S8x`:L24497 |
| 546 | `sram2_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 2 | `S1`§`546` · `S8e`:L1548 · `S8x`:L24498 |
| 547 | `sram2_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 2 | `S1`§`547` · `S8e`:L1549 · `S8x`:L24499 |
| 548 | `sram2_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 2 | `S1`§`548` · `S8e`:L1550 · `S8x`:L24500 |
| 551 | `sram2_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 2 | `S1`§`551` · `S8e`:L1553 · `S8x`:L24503 |
| 552 | `sram2_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 2 | `S1`§`552` · `S8e`:L1554 · `S8x`:L24504 |
| 553 | `sram2_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 2 | `S1`§`553` · `S8e`:L1555 · `S8x`:L24505 |
| 556 | `sram2_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 2 | `S1`§`556` · `S8e`:L1556 · `S8x`:L24506 |
| 558 | `sram2_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 2 | `S1`§`558` · `S8e`:L1557 · `S8x`:L24507 |
| 559 | `sram2_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 2 | `S1`§`559` · `S8e`:L1558 · `S8x`:L24508 |
| 560 | `sram3_rd_trans_accepted` | Read transfer (arready & arvalid) for SRAM AXI port 3 | `S1`§`560` · `S8e`:L1559 · `S8x`:L24509 |
| 561 | `sram3_rd_trans_completed` | Read complete (rready & rvalid & rlast) for SRAM AXI port 3 | `S1`§`561` · `S8e`:L1560 · `S8x`:L24510 |
| 562 | `sram3_rd_data_beat_received` | Read bandwidth (rready & rvalid) for SRAM AXI port 3 | `S1`§`562` · `S8e`:L1561 · `S8x`:L24511 |
| 563 | `sram3_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for SRAM AXI port 3 | `S1`§`563` · `S8e`:L1562 · `S8x`:L24512 |
| 564 | `sram3_wr_trans_accepted` | Write transfers (awready & awvalid) for SRAM AXI port 3 | `S1`§`564` · `S8e`:L1563 · `S8x`:L24513 |
| 567 | `sram3_wr_data_beat_written` | Write bandwidth (wvalid & wready) for SRAM AXI port 3 | `S1`§`567` · `S8e`:L1566 · `S8x`:L24516 |
| 568 | `sram3_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for SRAM AXI port 3 | `S1`§`568` · `S8e`:L1567 · `S8x`:L24517 |
| 569 | `sram3_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for SRAM AXI port 3 | `S1`§`569` · `S8e`:L1568 · `S8x`:L24518 |
| 572 | `sram3_enabled_cycles` | Memory clock cycle (aclken_input), for SRAM AXI port 3 | `S1`§`572` · `S8e`:L1569 · `S8x`:L24519 |
| 574 | `sram3_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for SRAM AXI port 3 | `S1`§`574` · `S8e`:L1570 · `S8x`:L24520 |
| 575 | `sram3_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for SRAM AXI port 3 | `S1`§`575` · `S8e`:L1571 · `S8x`:L24521 |
| 640 | `ext0_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 0 | `S1`§`640` · `S8e`:L1572 · `S8x`:L24522 |
| 641 | `ext0_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 0 | `S1`§`641` · `S8e`:L1573 · `S8x`:L24523 |
| 642 | `ext0_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 0 | `S1`§`642` · `S8e`:L1574 · `S8x`:L24524 |
| 643 | `ext0_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 0 | `S1`§`643` · `S8e`:L1575 · `S8x`:L24525 |
| 644 | `ext0_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 0 | `S1`§`644` · `S8e`:L1576 · `S8x`:L24526 |
| 647 | `ext0_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 0 | `S1`§`647` · `S8e`:L1579 · `S8x`:L24529 |
| 648 | `ext0_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 0 | `S1`§`648` · `S8e`:L1580 · `S8x`:L24530 |
| 649 | `ext0_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 0 | `S1`§`649` · `S8e`:L1581 · `S8x`:L24531 |
| 652 | `ext0_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 0 | `S1`§`652` · `S8e`:L1582 · `S8x`:L24532 |
| 654 | `ext0_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 0 | `S1`§`654` · `S8e`:L1583 · `S8x`:L24533 |
| 655 | `ext0_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 0 | `S1`§`655` · `S8e`:L1584 · `S8x`:L24534 |
| 656 | `ext1_rd_trans_accepted` | Read transfer (arready & arvalid) for EXT AXI port 1 | `S1`§`656` · `S8e`:L1585 · `S8x`:L24535 |
| 657 | `ext1_rd_trans_completed` | Read complete (rready & rvalid & rlast) for EXT AXI port 1 | `S1`§`657` · `S8e`:L1586 · `S8x`:L24536 |
| 658 | `ext1_rd_data_beat_received` | Read bandwidth (rready & rvalid) for EXT AXI port 1 | `S1`§`658` · `S8e`:L1587 · `S8x`:L24537 |
| 659 | `ext1_rd_tran_req_stalled` | Read stalls (arvalid & ~arready) for EXT AXI port 1 | `S1`§`659` · `S8e`:L1588 · `S8x`:L24538 |
| 660 | `ext1_wr_trans_accepted` | Write transfers (awready & awvalid) for EXT AXI port 1 | `S1`§`660` · `S8e`:L1589 · `S8x`:L24539 |
| 663 | `ext1_wr_data_beat_written` | Write bandwidth (wvalid & wready) for EXT AXI port 1 | `S1`§`663` · `S8e`:L1592 · `S8x`:L24542 |
| 664 | `ext1_wr_tran_req_stalled` | write transfer stalled by memory (awvalid & ~awready) for EXT AXI port 1 | `S1`§`664` · `S8e`:L1593 · `S8x`:L24543 |
| 665 | `ext1_wr_data_beat_stalled` | Write beat stalled by memory (wvalid & ~wready) for EXT AXI port 1 | `S1`§`665` · `S8e`:L1594 · `S8x`:L24544 |
| 668 | `ext1_enabled_cycles` | Memory clock cycle (aclken_input), for EXT AXI port 1 | `S1`§`668` · `S8e`:L1595 · `S8x`:L24545 |
| 670 | `ext1_rd_stall_limit` | Read stalls due to max outstanding transactions limit, for EXT AXI port 1 | `S1`§`670` · `S8e`:L1596 · `S8x`:L24546 |
| 671 | `ext1_wr_stall_limit` | Write stalls due to max outstanding transactions limit, for EXT AXI port 1 | `S1`§`671` · `S8e`:L1597 · `S8x`:L24547 |

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

| id | 드라이버 이름 | 출처 |
| -: | ------------- | ---- |
| 33 | `cc_stalled_on_blockdep` | `S1`§`33`=Reserved · `S8e`:L1430 · `S8x`:L24380 |
| 52 | `mac_stalled_by_w_or_acc` | `S1`§`52`=Reserved · `S8e`:L1434 · `S8x`:L24384 |
| 53 | `mac_stalled_by_w` | `S1`§`53`=Reserved · `S8e`:L1435 · `S8x`:L24385 |
| 54 | `mac_stalled_by_acc` | `S1`§`54`=Reserved · `S8e`:L1436 · `S8x`:L24386 |
| 55 | `mac_stalled_by_ib` | `S1`§`55`=Reserved · `S8e`:L1437 · `S8x`:L24387 |
| 67 | `ao_stalled_by_bs_or_ob` | `S1`§`67`=Reserved · `S8e`:L1439 · `S8x`:L24389 |
| 68 | `ao_stalled_by_bs` | `S1`§`68`=Reserved · `S8e`:L1440 · `S8x`:L24390 |
| 69 | `ao_stalled_by_ob` | `S1`§`69`=Reserved · `S8e`:L1441 · `S8x`:L24391 |
| 70 | `ao_stalled_by_ab_or_cb` | `S1`§`70`=Reserved · `S8e`:L1442 · `S8x`:L24392 |
| 71 | `ao_stalled_by_ab` | `S1`§`71`=Reserved · `S8e`:L1443 · `S8x`:L24393 |
| 72 | `ao_stalled_by_cb` | `S1`§`72`=Reserved · `S8e`:L1444 · `S8x`:L24394 |
| 83 | `wd_stalled_by_wd_buf` | `S1`§`83`=Reserved · `S8e`:L1447 · `S8x`:L24397 |
| 84 | `wd_stalled_by_ws_fc` | `S1`§`84`=Reserved · `S8e`:L1448 · `S8x`:L24398 |
| 85 | `wd_stalled_by_ws_tc` | `S1`§`85`=Reserved · `S8e`:L1449 · `S8x`:L24399 |
| 89 | `wd_trans_wblk` | `S1`§`89`=Reserved · `S8e`:L1450 · `S8x`:L24400 |
| 90 | `wd_trans_ws_fc` | `S1`§`90`=Reserved · `S8e`:L1451 · `S8x`:L24401 |
| 91 | `wd_trans_ws_tc` | `S1`§`91`=Reserved · `S8e`:L1452 · `S8x`:L24402 |
| 96 | `wd_stalled_by_ws_sc0` | `S1`§`96`=Reserved · `S8e`:L1453 · `S8x`:L24403 |
| 97 | `wd_stalled_by_ws_sc1` | `S1`§`97`=Reserved · `S8e`:L1454 · `S8x`:L24404 |
| 98 | `wd_stalled_by_ws_sc2` | `S1`§`98`=Reserved · `S8e`:L1455 · `S8x`:L24405 |
| 99 | `wd_stalled_by_ws_sc3` | `S1`§`99`=Reserved · `S8e`:L1456 · `S8x`:L24406 |
| 100 | `wd_parse_active_sc0` | `S1`§`100`=Reserved · `S8e`:L1457 · `S8x`:L24407 |
| 101 | `wd_parse_active_sc1` | `S1`§`101`=Reserved · `S8e`:L1458 · `S8x`:L24408 |
| 102 | `wd_parse_active_sc2` | `S1`§`102`=Reserved · `S8e`:L1459 · `S8x`:L24409 |
| 103 | `wd_parse_active_sc3` | `S1`§`103`=Reserved · `S8e`:L1460 · `S8x`:L24410 |
| 104 | `wd_parse_stall_sc0` | `S1`§`104`=Reserved · `S8e`:L1461 · `S8x`:L24411 |
| 105 | `wd_parse_stall_sc1` | `S1`§`105`=Reserved · `S8e`:L1462 · `S8x`:L24412 |
| 106 | `wd_parse_stall_sc2` | `S1`§`106`=Reserved · `S8e`:L1463 · `S8x`:L24413 |
| 107 | `wd_parse_stall_sc3` | `S1`§`107`=Reserved · `S8e`:L1464 · `S8x`:L24414 |
| 108 | `wd_parse_stall_in_sc0` | `S1`§`108`=Reserved · `S8e`:L1465 · `S8x`:L24415 |
| 109 | `wd_parse_stall_in_sc1` | `S1`§`109`=Reserved · `S8e`:L1466 · `S8x`:L24416 |
| 110 | `wd_parse_stall_in_sc2` | `S1`§`110`=Reserved · `S8e`:L1467 · `S8x`:L24417 |
| 111 | `wd_parse_stall_in_sc3` | `S1`§`111`=Reserved · `S8e`:L1468 · `S8x`:L24418 |
| 112 | `wd_parse_stall_out_sc0` | `S1`§`112`=Reserved · `S8e`:L1469 · `S8x`:L24419 |
| 113 | `wd_parse_stall_out_sc1` | `S1`§`113`=Reserved · `S8e`:L1470 · `S8x`:L24420 |
| 114 | `wd_parse_stall_out_sc2` | `S1`§`114`=Reserved · `S8e`:L1471 · `S8x`:L24421 |
| 115 | `wd_parse_stall_out_sc3` | `S1`§`115`=Reserved · `S8e`:L1472 · `S8x`:L24422 |
| 116 | `wd_trans_ws_sc0` | `S1`§`116`=Reserved · `S8e`:L1473 · `S8x`:L24423 |
| 117 | `wd_trans_ws_sc1` | `S1`§`117`=Reserved · `S8e`:L1474 · `S8x`:L24424 |
| 118 | `wd_trans_ws_sc2` | `S1`§`118`=Reserved · `S8e`:L1475 · `S8x`:L24425 |
| 119 | `wd_trans_ws_sc3` | `S1`§`119`=Reserved · `S8e`:L1476 · `S8x`:L24426 |
| 120 | `wd_trans_wb0` | `S1`§`120`=Reserved · `S8e`:L1477 · `S8x`:L24427 |
| 121 | `wd_trans_wb1` | `S1`§`121`=Reserved · `S8e`:L1478 · `S8x`:L24428 |
| 122 | `wd_trans_wb2` | `S1`§`122`=Reserved · `S8e`:L1479 · `S8x`:L24429 |
| 123 | `wd_trans_wb3` | `S1`§`123`=Reserved · `S8e`:L1480 · `S8x`:L24430 |
| 133 | `sram_wr_trans_completed_m` | `S1`§`133`=Reserved · `S8e`:L1486 · `S8x`:L24436 |
| 134 | `sram_wr_trans_completed_s` | `S1`§`134`=Reserved · `S8e`:L1487 · `S8x`:L24437 |
| 389 | `ext_wr_trans_completed_m` | `S1`§`389`=Reserved · `S8e`:L1512 · `S8x`:L24462 |
| 390 | `ext_wr_trans_completed_s` | `S1`§`390`=Reserved · `S8e`:L1513 · `S8x`:L24463 |
| 517 | `sram0_wr_trans_completed_m` | `S1`§`517`=Reserved · `S8e`:L1525 · `S8x`:L24475 |
| 518 | `sram0_wr_trans_completed_s` | `S1`§`518`=Reserved · `S8e`:L1526 · `S8x`:L24476 |
| 533 | `sram1_wr_trans_completed_m` | `S1`§`533`=Reserved · `S8e`:L1538 · `S8x`:L24488 |
| 534 | `sram1_wr_trans_completed_s` | `S1`§`534`=Reserved · `S8e`:L1539 · `S8x`:L24489 |
| 549 | `sram2_wr_trans_completed_m` | `S1`§`549`=Reserved · `S8e`:L1551 · `S8x`:L24501 |
| 550 | `sram2_wr_trans_completed_s` | `S1`§`550`=Reserved · `S8e`:L1552 · `S8x`:L24502 |
| 565 | `sram3_wr_trans_completed_m` | `S1`§`565`=Reserved · `S8e`:L1564 · `S8x`:L24514 |
| 566 | `sram3_wr_trans_completed_s` | `S1`§`566`=Reserved · `S8e`:L1565 · `S8x`:L24515 |
| 645 | `ext0_wr_trans_completed_m` | `S1`§`645`=Reserved · `S8e`:L1577 · `S8x`:L24527 |
| 646 | `ext0_wr_trans_completed_s` | `S1`§`646`=Reserved · `S8e`:L1578 · `S8x`:L24528 |
| 661 | `ext1_wr_trans_completed_m` | `S1`§`661`=Reserved · `S8e`:L1590 · `S8x`:L24540 |
| 662 | `ext1_wr_trans_completed_s` | `S1`§`662`=Reserved · `S8e`:L1591 · `S8x`:L24541 |

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
| S8 | ethos-u-core-driver, `gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver` | commit `5f0b9d1e17b245aefc308ee0d5a4543833b96b11` (*Bump version to 2.0.0*, 2026-08-26) | `src/ethosu_interface_u85.h`, `src/ethosu_pmu_u85.c`, `include/ethosu_pmu_types.h` |

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

### 인용 게이트

행마다 붙은 출처는 눈으로 확인한 것이 아니라 **기계로 되짚을 수 있게** 되어 있다.

```sh
curl -sLO https://gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-core-driver/-/raw/\
5f0b9d1e17b245aefc308ee0d5a4543833b96b11/src/ethosu_interface_u85.h
python3 docs/ethos_u85_pmu_sources/verify_citations.py ethosu_interface_u85.h
```

`S1`§`<id>` 는 `trm_events_110.json` 으로, `S8e`/`S8x` 의 줄 번호는 헤더 실물로 되짚는다.
커버리지도 함께 본다 — 드라이버 171개 중 인용되지 않은 이벤트가 하나라도 있으면 실패한다.

GREEN: `rows checked 202 / distinct events 171 / failures 0`.

게이트가 실제로 실패하는지 확인했다 (2026-09-23, 문서를 변조하고 복원, 복원은 digest 대조):

| 변조 | 결과 |
| ---- | ---- |
| `S8e` 줄번호 1428 → 1429 | RED — `cycle: S8e L1429 -> 'PMU_EVENT_NPU_IDLE = 32,'` |
| `S8x` 줄번호 24378 → 24379 | RED — `cycle: S8x L24379 -> 'FUNC(pmu_event, NPU_IDLE) SEP'` |
| 문서화된 `17` 을 `=Reserved` 로 위조 | RED — `claimed Reserved but TRM documents 17` |
| Reserved 인 `53` 을 문서화됨으로 위조 | RED — `TRM 53 is None, not 'mac_stalled_by_w'` |
| 이벤트 행 1개 삭제 | RED — `<coverage>: 1 driver events uncited: ['ext1_wr_stall_limit']` |
| 이름 위조 `npu_idle` → `npu_active` | RED — 4건 |

복원 후 digest 일치, GREEN 재확인.

### 원본 digest (sha256)

추출에 쓴 원본과 파싱 결과를 `docs/ethos_u85_pmu_sources/` 에 함께 둔다.

```
34c839957b8c91742a6d40425bd9c5df4a17757bfa18c092a18c8d31694f8332  docs/ethos_u85_pmu_sources/102685_0000_PMEVTYPER0.response.json
ca5047363c734059b0ab3813f5406fdb74a8e0284e161203c3a82b065d8af842  docs/ethos_u85_pmu_sources/trm_events_110.json
79a5785bd2ff948f28dd7d19ceb04a8656ac6b264e33a12b09482aa0fbc4429b  docs/ethos_u85_pmu_sources/driver_events_171.json
34f918cd2febb3aff35cd730cfcd362e14c03e6208b1cf2342bd727e1c6a6383  docs/ethos_u85_pmu_sources/driver_lines.json
d5ca6b5abfba4758fdc811b04780937ccce806a29d4a427ff352e99ec15f355c  docs/ethos_u85_pmu_sources/armdoc.py
d43e4cbfb03ec2855c885c1396fc29afe6c454f10e217946eb329206c1132768  docs/ethos_u85_pmu_sources/verify_citations.py
```

| 파일 | 내용 |
| ---- | ---- |
| `102685_0000_PMEVTYPER0.response.json` | S1 PMEVTYPER0 토픽의 `documentation-service` 응답 원본 (base64 본문 포함) |
| `trm_events_110.json` | 위 응답에서 파싱한 공식 EV_TYPE 110개 `[id, name, description]` |
| `driver_events_171.json` | `ethosu_interface_u85.h` `enum pmu_event` 에서 파싱한 171개 `[id, name]` |
| `driver_lines.json` | 이벤트 이름 → `enum pmu_event` / `EXPAND_PMU_EVENT` 줄 번호 (`S8e` / `S8x` 의 근거) |
| `armdoc.py` | Arm 문서 추출 헬퍼 |
| `verify_citations.py` | 인용 게이트 |

`src/ethosu_interface_u85.h` 자체(763KB)는 크기 때문에 넣지 않았다. commit `5f0b9d1e` 에서 다시 받을 수 있고,
sha256 `79aa695a7a35cabfdda83856661ceabb1169d2ece1e08b86c48d2fadd0f09ece` 로 대조하면 된다.
`main` tip 이 아니라 이 commit 을 쓸 것 — 줄 번호가 그 commit 에 고정되어 있다.

---

## 검증 수준

```
검증 수준: 문서 대조 (1차 출처 원문 추출 + 프로그램적 집합 비교)

실제 실행한 것:
  - S1~S6 TRM 토픽 본문 추출 및 텍스트화
  - 이벤트 행 202건(고유 171개)의 출처를 1차 원본으로 되짚는 게이트 실행 → failures 0
  - 그 게이트를 변조 6종으로 mutation test → 전부 RED, 복원은 digest 대조
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
