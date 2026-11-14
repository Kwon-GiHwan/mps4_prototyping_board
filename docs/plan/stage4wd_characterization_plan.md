# Stage 4WD — Weight Decoder 특성: 기존 결과 재분석과 실험 설계 (보드 없음)

상태: **2026-11-15 보드 없는 단계 완료. 판정 `READY_FOR_BOARD_CONTRACT_REVIEW`**. 계약 초안: `evidence/stage4wd/contract_draft.md`.
모든 수치의 조건: TA profile 1, driver runner 이미지 70090f1 (Stage 4 boot 330 이후의 driver-runner 데이터), Vela 5.0.0 (MLEK 옵션).
보드 데이터는 모두 기존 원시 RUN에서 다시 계산했다 (`results/fi101_stage4wd/inventory.json`, 39개 측정). 표시하지 않은 해석은
POST_HOC_DESCRIPTIVE다.

## 1. 공식 자료 (Arm Ethos-U85 TRM 102685 issue 05)

| 항목 | 공식 내용 | 출처 |
|---|---|---|
| WD 동작 | "reads the weight stream from the DMA controller ... decompresses and stores this stream in a double-buffered register, ready for the MAC unit" | §2.4 |
| 디코더 종류 | SWD: 무손실 압축 (0 run + Golomb-Rice, LUT), SWD당 최대 64 bit/cycle (= 8 B/cycle). FWD: 최대 256 bit/cycle, raw 8 bit 또는 테이블 4/2 bit 모드, DW는 지원하지 않음 | §2.4, §3.9.1 |
| U85-1024 | num_wd = 4 (weight stream 4개) → SWD 합계 최대 32 B/cycle | Table 3-90 |
| weight 공급 | "The traversal unit triggers these [weight] channels for blocks that require the transfer of weights." 무손실 압축; 0이 75 %를 넘는 weight는 3 bit/weight 미만까지 압축될 수 있음 | §2.2 DMA |
| padding | weight block에 맞추려고 0을 넣으므로, 압축하지 않은 stream이 원래 weight보다 크다 | §3.9.1 |
| WD_ACTIVE (80) | "WD is decoding weight stream. Valid blk_cmd and not stalled" | PMEVTYPER |
| WD_STALLED (81) | "WD stalled on lack of weight stream data **or** lack of free WD buffer space" — 공급 부족과 buffer backpressure가 한 카운터에 섞여 있다 | PMEVTYPER |
| 원인 분리 이벤트 | **없음.** 82–127은 Reserved이다 (드라이버 헤더의 wd_stalled_by_wd_buf 등은 공식 정의가 없으므로 원인 지표로 쓰지 않는다) | PMEVTYPER |

명령 스트림 확인: 기존 workload 전부 `NPU_SET_WEIGHT_FORMAT` = 0 (SWD, sparsity 없음). FWD 사용 사례는 없다.

## 2. 기존 결과 통합 비교 (`wd_inventory.csv`)

| 그룹 | 대표 | spatial block | staged B (weight + bias/scale) | encoded B | WD_ACTIVE | WD_STALLED | SRAM rd B / WD_ACTIVE | 비고 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Conv 1×1 Cin16 (5 boot) | 330, 338, 344, 369, 380 | 8 | 4,032 | 2,752 | 1,051–1,056 | 6,146–7,270 | 30.5–30.7 | |
| Conv 1×1 H sweep | 380–383 | 8/12/18/24 | 4,032 | 2,752 | 1,052 / 1,563 / 2,298 / 2,993.5 | 7,270 → 24,302 | 30.7–32.3 | 같은 weight |
| Conv 1×1 Cin 32–128 | 345–350, 371–377 | 8 | 6,208–15,696 | 4,928–14,416 | 1,670–4,165 | 8,929–21,035 | 28.2–35.6 | PartKernel·DepthFirst 섞임 |
| Conv 3×3 Cin 16–64 | 370–378 | 3 | 17,712–66,704 | 16,432–65,424 | 1,886–7,637 | 13,206–43,081 | 25.0–28.2 | |
| DW 3×3 56×56 | 333, 334, 341–343 | 6 | 3,216–3,408 | 1,776–1,808 | 195–210 | 156,816–185,209 | 97.4–99.4 | |
| FC 96→288 | 335–337 | 1 (SRAM 사용 0) | 0 | 31,920–32,208 | 765–919 | 2,471–3,346.5 | — (encoded/WD 34.7–42.0) | weight를 EXT에서 직접 읽음 |
| 배치 DDR / SRAM | 367 / 368 | 8 | 4,032 | 2,752 | 1,052 / 1,048 | **6,583.5 / 2,414** | 30.7 / — | IFM·OFM 위치만 바뀜 |

### 기존 결과로 설명할 수 있는 것

1. **weight 재스트리밍 (정적 + 카운터 규칙, 39개 중 35개 DDR 측정 전부 정확히 일치).**
   - SRAM write beat = staged bytes / 16: 이 크기는 weight와 bias/scale의 DMA 길이와 같고, fast scratch에 **한 번** 쓰인다.
   - SRAM read beat = **spatial OFM block 수 × staged bytes / 16**: block마다 staged 영역 전체를 **다시 읽는다**.
   - 예: H24 8 × 252 = 2,016, H72 24 × 252 = 6,048, 3×3 3 × 1,107 = 3,321, DW 6 × 202 = 1,212.
   - 공식 §2.2의 "블록마다 weight 채널을 trigger"와 맞는다. 다만 다시 읽힌 데이터 중 무엇이 WD로 가고 무엇이 AO (bias/scale)로 가는지는 카운터로 나뉘지 않는다.
2. **같은 weight에서 WD_ACTIVE는 block 수와 함께 늘어난다** (4AO sweep): WD = 60.6 × block + 96.7 (r² 0.9996).
   이 sweep에서는 block 수 ∝ N이므로 **block 효과와 출력 원소 효과는 아직 분리되지 않았다** → 실험 B.
3. **Conv의 SRAM 재읽기 B / WD_ACTIVE ≈ 25–36 B/cycle**로, SWD 4개의 공식 최대 32 B/cycle 근처다.
   Conv에서는 WD_ACTIVE가 "재스트리밍된 바이트 / ~32 B"로 대략 설명된다. 이것은 가설일 뿐이다.
4. **배치 실험**: WD_ACTIVE는 같고 (1,052 / 1,048) WD_STALLED만 63 % 줄었다. WD_STALLED가 weight 처리량만으로 정해지지 않는다는 기존 관측과 맞는다.
   메모리 위치, AXI 포트, TA 경로, SRAM 포트 공유가 함께 바뀌었으므로 원인별 기여는 계산하지 않는다.

### 원인이 분리되지 않은 것

- WD_ACTIVE가 block 수 때문인지 출력 원소 수 때문인지 (실험 B).
- WD_ACTIVE가 encoded stream 크기, staged 크기 (bias/scale 포함), 원래 weight 수 중 무엇을 따르는지 (실험 A).
- DW의 SRAM 재읽기 B / WD = 97–99 B/cycle: 32를 크게 넘는다. staged 영역에서 bias/scale 비중이 크거나 WD를 거치지 않는 데이터가 있다는 뜻이지만 미검증이다.
- **Open Issue WD-1**: FC는 EXT에서 직접 읽는 encoded weight / WD_ACTIVE = 34.7–42.0 B/cycle로, 공식 SWD 최대 32 B/cycle보다 크다. WD_ACTIVE의 계수 범위, FWD와 비슷한 경로, padding 해석 중 무엇인지 알 수 없다.
- WD_STALLED: 공급 부족과 backpressure를 공식 PMU로 구분할 수 없다. 기존 데이터에서는 WD_STALLED가 NPU_ACTIVE와 함께 움직였다. 원인은 배정하지 않는다.

### 7개 MLEK 모델 (`mlek_wd.json`, driver_m7, TA profile 1, 추론 전체)

| 모델 | WD_ACTIVE | WD_STALLED | MAC_ACTIVE | NPU_ACTIVE | WD/NPU | STALLED/NPU |
|---|---:|---:|---:|---:|---:|---:|
| ad_medium | 21,319 | 117,148 | 93,672 | 145,893 | 0.146 | 0.80 |
| kws_micronet_m | 11,421 | 64,117 | 56,450 | 91,540 | 0.125 | 0.70 |
| mobilenet_v2 | 169,343 | 1,212,443 | 574,795 | 1,450,168 | 0.117 | 0.84 |
| rnnoise | 2,852 | 12,744 | 548 | 50,531 | 0.056 | 0.25 |
| vww4 | 13,412 | 134,125 | 56,512 | 234,929 | 0.057 | 0.57 |
| wav2letter | 1,133,549 | 2,982,245 | 3,521,802 | 4,133,419 | 0.274 | 0.72 |
| yolo-fastest | 27,272 | 323,328 | 171,576 | 447,340 | 0.061 | 0.72 |

WD_STALLED가 커도 MAC_ACTIVE가 높은 모델이 있다 (wav2letter: MAC/NPU 0.85, STALLED/NPU 0.72). 정체가 MAC 정지를 뜻하지는 않는다.
층별로 나누지 않았으므로 원인은 배정하지 않는다.

## 3. 실험 설계 (후보 컴파일 완료, `evidence/stage4wd/workloads`, `results/fi101_stage4wd/static.json`)

### 실험 A — weight 값만 바꿈 (압축률)

- 기준: Stage 4AO H24 (`s4ao_conv1x1_h24`, dense). IFM, bias, OFM scale, RELU6, 형상은 같다.
- 후보: `s4wd_w_small` ([−3, 3] 균등), `s4wd_w_sparse75` (기준 weight의 75 %를 0으로), `s4wd_w_sparse90` (90 %).
- 명령 스트림 차이: weight와 그 뒤 base·length·DMA 레지스터뿐이다 (opcode 32–34, 48–50, 144–149). block 6×12×96, PartKernel, 커널 2개, SWD는 같다.

| config | 0 비율 | encoded B | staged B | 예측 SRAM rd beat (8 × staged/16, 정확) | WD 예측: encoded ∝ | staged ∝ | 일정 |
|---|---:|---:|---:|---:|---:|---:|---:|
| dense (h24) | 0.4 % | 2,752 | 4,032 | 2,016 | 1,052 | 1,052 | 1,052 |
| small | 13.8 % | 1,536 | 2,816 | 1,408 | 587 | 735 | 1,052 |
| sparse75 | 75.2 % | 1,168 | 2,448 | 1,224 | 446 | 639 | 1,052 |
| sparse90 | 90.3 % | 640 | 1,920 | 960 | 245 | 501 | 1,052 |

출력 정확성: 4개 모두 기본 커널과 BUILTIN_REF가 같다 → golden이 모호하지 않다. 판정 집합: ENCODED_PROPORTIONAL / STAGED_PROPORTIONAL / CONSTANT / MONOTONE / OTHER.

### 실험 B — block 수와 출력 원소 수 분리

- 근거: block 스캔 (`wd_block_scan.json`, H 18–36, W 24). Vela는 H ∈ {23, 24, 32, 34, 36}에서 6×12×96 block을 유지하고,
  부분 block 행 때문에 **block 수가 같은데 N이 다른** 두 묶음이 생긴다.

| config | H | N_OFM | spatial block | 전체 block | WD 예측: block ∝ (4AO fit) | N ∝ (4AO fit) | SRAM rd 예측 |
|---|---:|---:|---:|---:|---:|---:|---:|
| s4wd_h23 | 23 | 52,992 | 8 | 16 | 1,067 | 1,026.5 | 2,016 |
| s4ao_conv1x1_h24 | 24 | 55,296 | 8 | 16 | 1,067 | 1,067 | 2,016 |
| s4wd_h32 | 32 | 73,728 | 12 | 24 | 1,552 | 1,390 | 3,024 |
| s4wd_h34 | 34 | 78,336 | 12 | 24 | 1,552 | 1,471 | 3,024 |
| s4ao_conv1x1_h36 | 36 | 82,944 | 12 | 24 | 1,552 | 1,552 | 3,024 |

- 판정 집합:
  - BLOCK_LIKE: 같은 block 묶음 안에서 같고, 묶음 사이에서는 다름.
  - N_LIKE: 묶음 안에서 N 순서대로 허용폭을 넘어 증가.
  - NEITHER / INCOMPLETE.
- 검정력: H32와 H34에서 두 가설의 차이는 162 / 81 cycle이고 허용폭은 max(25, 2 %, range 합)이다.
  H23과 H24의 차이 (40)는 range가 크면 구분되지 않을 수 있다. 그 경우 12-block 묶음이 주 판정 근거다.
- 기타: block 형상은 바꿀 수 없다 (Vela 선택). 같은 N에서 block 수를 바꾸는 형상은 block 형상이 함께 바뀌어 제외했다.

### 실험 C — WD 정체 원인 (이번에는 측정하지 않음, 제안만)

공식 PMU로는 공급 부족과 backpressure를 나눌 수 없다. 앞으로의 후보:
- weight만 SRAM에 두고 IFM·OFM 경로는 그대로 둔다 (`--fast-base`나 placement 조합; runner 기능 확인 필요).
- 같은 weight에서 MAC 소비 속도를 바꾼다 (PartKernel·DepthFirst 쌍).
WD_STALLED의 증감만으로 원인을 분류하지 않는다. 자동으로 보드 대상에 넣지 않는다.

## 4. 승인이 필요한 것

1. 실험 A·B 보드 측정: 8 boot / 80 RUN (h24, small, sparse75, sparse90, h23, h32, h34, h36). 이미지 70090f1, A1 정체성 Gate 그대로.
2. 실험 C는 제안으로만 두고 이번 측정에는 넣지 않는다.
3. Open Issue WD-1 (FC encoded / WD > 32 B/cycle), AO-1 (ABS N/32)은 보존만 한다.
