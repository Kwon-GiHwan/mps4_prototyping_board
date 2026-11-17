# Unit별 확보·미확보 지표 (Stage 6C-0, 근거: results 인벤토리)

AXI 이용률: 포트 물리 한도와 클럭 조건이 검증되지 않아 계산하지 않는다 (`AXI_UTILIZATION_NOT_COMPUTED`). 바이트 ÷ NPU_ACTIVE는 관측 평균 처리율(B/cycle)이다.

## MAC/DPU

확보:
- 1x1 DepthFirst: H1-UC MAC_ACTIVE PROSPECTIVE_SUPPORT (6B-B, E1-R, E2D/E2E; 768 not a cap: G09 1024)
- 1x1 PartKernel Cin 16/32: 384 MAC/MAC-active cycle, DPU/MAC 0.5 (4C-2, 4K)
- 3x3 PartKernel Cin 16-64: 768 nominal (4K), PROPORTIONAL_TO_CIN
- DW 3x3 C144: 128 MAC/MAC-active cycle (Stage 4); C rounded up to 16 (4C-1)
- FC 96->288: 256 MAC/MAC-active cycle, MAC/NPU 1.15 % (Stage 4)

미확보:
- 1x1 PartKernel at Cin < 16 and large spatial
- DW at C < 16, 5x5, other resolutions
- FC beyond one shape (out 287 not reproduced, RUN ranges 7-9 %)
- 1D large-kernel PartKernel (wav2letter)
- first Conv Cin 1 (kws 10x4)

## AO

확보:
- Conv INT8 output ~15.6 elem/AO cycle (4AO), DW ~15.85
- ADD/MUL N/16, ADD->MUL 2N/16 (4AO-E)
- model AO/NPU: yolo 46 %, vww4 27 % (Stage 1)

미확보:
- LUT / TANH / LOGISTIC (compiled only)
- activation NONE vs RELU (INCONCLUSIVE)

Open issue:
- AO-1: ABS N/32 unexplained

## WD

확보:
- WD_ACTIVE follows spatial OFM blocks (BLOCK_LIKE, 4WD)
- not proportional to encoded bytes (CONSTANT)
- WD_STALLED moves with memory condition (placement, EXT latency: E2D, E2E-B/D)

미확보:
- WD vs other units' backpressure separation
- FC weight-decode rate

Open issue:
- WD-1: FC 34.7-42 encoded B/WD cycle > documented 32
- WD-2

## DMA/AXI

확보:
- SRAM/EXT read/write beats, transactions per model (Stage 3) and per isolated / A2 config
- per-port EXT0/EXT1 beats/trans (640/642/656/658) VERIFIED
- 387 ext_rd_tran_req_stalled VERIFIED
- channel-filtered read traffic (rd_weights/ifm/mem2mem, Stage 3 legacy)
- graph IO vs weight path EXT latency sensitivity (E2E-B/D)

미확보:
- physical port bandwidth limit under FI101 clocks (no AXI utilisation computed)
- axi_latency 160-166 (TRM only)
- outstanding-limit stall 398 INCONSISTENT
- PMCAXI_CHAN in the driver runner (not implemented)

Open issue:
- B3w slower at L500 (E2E-D, unresolved)
