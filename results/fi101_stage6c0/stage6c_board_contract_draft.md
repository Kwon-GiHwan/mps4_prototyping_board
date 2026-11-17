# Stage 6C 보드 계약 초안 — PartKernel·DW·FC·1D·첫 Conv 연산군의 Unit/AXI/Vela 동시 계측 (초안, 동결 전, 실행 미승인)

## 1. 구성 (Stage 6C-0 선정 `selection.json`, 컴파일 사실 `evidence/stage6c0/compile/compile_facts.json` `f77884ec…`)

| boot | 형상 | 원본 | IFM → OFM | 커널·traversal | ofm_block / ublock | Vela op / npu / mac cycles |
|---|---|---|---|---|---|---|
| 1 | REF | Stage 4K s4c2_conv_cin48 | 24×24×48 → 96 | 1×1 DepthFirst | — | — |
| 2 | F1 rep | yolo op9 | 96×96×4 → 24 | 1×1 PartKernel | 8×32×32 / 2×2×32 | 56,249 / 26,884 / 9,684 |
| 3 | F1 ctl (Cin 16) | 같음, Cin 4→16 | 96×96×16 → 24 | 1×1 PartKernel | 같음 | 56,249 / 27,711 / 18,900 |
| 4 | F2 rep | yolo op3 | 96×96×8 DW | 3×3 Depthwise | 30×24×16 / 2×4×16 | 140,000 / 22,974 / 14,184 |
| 5 | F2 ctl (C 16) | 같음, C 8→16 | 96×96×16 DW | 3×3 Depthwise | 같음 | 35,000 / 15,303 / 14,544 |
| 6 | F3 rep | rnnoise op46 | 114 → 288 | FC | 2×2×288 / 2×2×32 | 7,929 / 7,929 / 7,929 |
| 7 | F3 ctl (Cin 128) | 같음, Cin 114→128 | 128 → 288 | FC | 같음 | 7,929 / 7,929 / 7,929 |
| 8 | F4 rep | wav2letter op17 | 1×148×250 → 2000 | 1×32 PartKernel | 1×84×96 / 1×4×32 | 4,716,796 / 3,662,770 / 3,639,123 |
| 9 | F5 rep | kws op0 | 49×10×1 → 140 | 10×4 PartKernel | 24×10×32 / 2×2×32 | 23,501 / 23,501 / 13,125 |

- 모든 대표 형상은 원본 MLEK 텐서로 다시 만든 단독 연산이다. traversal·block·ublock은 모델 안 연산과 같다(`MAPPING_SAME`).
- **조건 차이(통제 불가, 명시)**: 단독 연산은 graph IO가 DDR/EXT(Dram→Dram)이다. 모델 안에서는 대부분 Sram→Sram이다. 그래서 단독 측정의 NPU_ACTIVE를 모델 안 연산의 실행시간으로 귀속하지 않는다.
- 통제 형상은 대표 형상과 traversal·block·ublock이 같다(`mapping_vs_rep` MAPPING_SAME). 늘어난 채널의 가중치는 고정 시드 난수다.
- 이미지: 새 runner 이미지(`14077be`, L500 bram `ec0e8c3b…`). placement 0(DDR). **TA profile 1**, EXT RLATENCY 500. REF 재현 게이트는 boot 375 사본 대비다.

## 2. PMU (8 카운터, 모든 pass에 NPU_ACTIVE)

| pass | 이벤트 | 목적 |
|---|---|---|
| A | 35 48 51 53* 55* 64 80 81 | NPU, MAC, DPU, AO, WD, WD_STALLED(*Reserved 탐색용) |
| B | 35 128 130 132 135 384 386 391 | SRAM/EXT read·write beat, 트랜잭션 |
| C (신규) | 35 131 142 387 640 642 656 658 | SRAM/EXT read 요청 정체, SRAM outstanding 한계 정체, EXT0/EXT1 포트별 read 트랜잭션·beat — 모두 FI101 VERIFIED |

- 398(ext_rd_stall_limit)은 INCONSISTENT이고, axi_latency(160–166)는 TRM에만 있어 쓰지 않는다. PMCAXI_CHAN 채널 필터는 driver runner에 없다.
- boot당 3 pass × 5 RUN(1 + 4) = 15 RUN. 9 boot면 135 RUN(warm-up 27, 측정 108). Pass C를 빼면 90 RUN.

## 3. 가설 (사전 예측 / 반례; Unit 카운터를 합산하지 않음)

**H-COMPUTE (채널 16 올림)**
- 근거: 4C-1 DW C 145 → MAC ×10/9, 4C-2b Cin 40 → 640, Stage 4 FC in 95 = 96.
- 예측: F1·F2·F3에서 MAC_ACTIVE(대표) = MAC_ACTIVE(통제), 차이 ≤ 1 %. 통제 형상은 채널을 16 배수로 올린 것이다.
- 반례: 차이 > 1 %. 이 경우 그 연산군은 16 올림이 아니다.

**H-COMPUTE (처리율, 방향만)**
- 기록할 값: MACs/MAC_ACTIVE, N_MAC/(1024 × MAC_ACTIVE), DPU/MAC.
- 예측:
  - F1 Cin 4: 16 올림이면 유효 MAC 효율 ≤ 4/16 × 384/1024.
  - F4 1×32: 384 ≤ MACs/MAC_ACTIVE ≤ 1024(Vela mac cycles 기준 약 650).
  - F5 Cin 1: 수치 예측 없음(판정 불가 조건: 근거 없음).

**H-PIPELINE (방향)**
- 예측: 단독 연산은 graph IO가 DDR이다. NPU_ACTIVE/MAC_ACTIVE는 F1·F2(Vela DRAM 항이 지배)에서 F3·F4보다 크다.
- 반례: F1·F2의 MAC_ACTIVE/NPU_ACTIVE가 F4 이상이다.
- 원인(WD·AO·DMA 기여)은 판정하지 않는다.

**H-VELA (방향)**
- F1·F2: Vela op cycles를 NHWC IFM read가 지배한다(DRAM 항 56,249 / 140,000 > npu). E2E-A의 burst 부풀림 근거로 board/Vela < 0.9(`OVER_PREDICTS`)를 예측한다. 반례는 > 1.1.
- F3: npu가 지배한다(7,929 ≥ DRAM 7,031). Stage 4 FC(1.08–1.19)와 같은 방향인 board/Vela > 1.0을 예측한다. 반례는 < 0.9.
- F4·F5: 방향 예측 없음. 기록만 한다.
- 통제 쌍:
  - F1(Cin 4 → 16): Vela total이 같다(56,249). 보드 비가 1 ± tol이면 Vela와 일치한다.
  - F3(114 → 128): Vela total이 같다(7,929). 판정 방식은 F1과 같다.
  - F2(C 8 → 16): Vela total이 140,000 → 35,000으로 변한다. 보드가 이 4배 감소를 따르는지 기록만 한다.

## 4. 유효성·중단

- E2D/E2E와 같다: 공유 identity(placement 0), 이미지 digest, TA readback, 출력 PASS_EXACT(BUILTIN_REF golden), RUN 유효성, pass 간 NPU_ACTIVE 일관성, range ≤ 5 %.
- REF 게이트 FAIL, CONFIG_MISMATCH, UNMEASURED이면 멈춘다. 재측정·대체는 하지 않는다.

## 5. 종료 기준(연산군별)

다음이 확보되면 그 연산군을 종료한다(6C-0 지시 §7).
- 처리율과 Unit 활동
- 메모리 전송
- NPU_ACTIVE 대 Vela
- 검증된 설명 범위와 미해결 메커니즘
- 모델 수준 적용 범위

새 현상은 후속 과제로 기록하고, 이 계약 안에서 확장하지 않는다.
