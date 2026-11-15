# Stage 6B-B — Model-informed MAC Characterization & Vela Fidelity (보드 결과)

## 조건과 근거

- 측정 조건은 MPS4 FI101, Ethos-U85 1024 MAC, **TA profile 1**, Driver Runner 이미지 `70090f1`, DDR/EXT(placement 0), WAIT_WFE다.
- boot는 410–420이다(2026-11-15 13:00–13:37Z). 11 boot, 110 RUN(측정 RUN 88, warm-up 22)이다.
- 계약 `evidence/stage6b/stage6bb/contract.md`, 판정 코드, manifest는 `0a99697`에서 동결했다. Preflight PASS는 `cc42087`이다.
- 원시 데이터는 `evidence/stage6b/stage6bb/raw/`(127개 파일)에 있다. `raw.sha256`이 보드와 Mac에서 같다.

| 축 | 판정 |
| --- | --- |
| Hardware Characterization | **PARTIAL_CHARACTERIZATION**: 기준 Gate PASS, 대표 형상 7 VALID + 3 UNSTABLE, INVALID·CONFIG_MISMATCH·UNMEASURED 0 |
| Compiler Fidelity | **FIDELITY_PARTIAL**: VALID 7개에서 COMPARABLE, UNSTABLE 3개는 NOT_COMPARABLE |

## 기준 형상 재현 (boot 410)

`s4c2_conv_cin48`은 Stage 4K boot 375와 같은 DRWL(`6eb390be…`)이고 이미지도 같다.
- **repro-gate PASS.**
- MAC_ACTIVE와 MAC_DPU_ACTIVE는 측정 4회 모두 3,456으로 boot 375와 같다.
- 출력 sha256이 같고, 상수 카운터 10개가 같다.
- NPU_ACTIVE는 22,662로, boot 375의 22,251과 비교해 허용폭 820 안이다.

## 형상별 결과 (pass A 측정 RUN 중앙값; MAC/DPU는 4회 모두 같은 값)

| boot | 형상 | 상태 | Cin→Cout, OFM | OFM block / ublock | MAC_ACTIVE | DPU/MAC | NPU_ACTIVE (range) | MAC/NPU | N_MAC/MAC_ACTIVE | ÷1024 |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 410 | 기준 Cin48 | VALID | 48→96, 24×24 | 6x12x96 / 2x2x32 | 3,456 | 1.00 | 22,662 (820) | 0.153 | 768.0 | 0.750 |
| 411 | G12 ad | VALID | 276→276, 16×16 | 8x16x64 / 2x2x32 | 20,736 | 1.00 | 99,555 (886) | 0.208 | 940.4 | 0.918 |
| 412 | G25 kws | VALID | 140→140, 25×5 | 14x6x96 / 2x2x32 | 3,900 | 0.90 | 28,902.5 (252) | 0.135 | 628.2 | 0.613 |
| 413 | G40 mbv2 | VALID | 160→960, 7×7 | 7x8x128 / 1x4x32 | 8,400 | 1.00 | 46,939.5 (431) | 0.179 | 896.0 | 0.875 |
| 414 | G53 vww4 | **UNSTABLE** | 44→268, 8×8 | 8x8x96 / 2x4x16 | 816 | 1.00 | 17,102 (857 = 5.0 %) | 0.048 | (924.9) | (0.903) |
| 415 | G11 ad | VALID | 192→276, 16×16 | 8x16x64 / 2x2x32 | 13,824 | 1.00 | 75,129.5 (225) | 0.184 | 981.3 | 0.958 |
| 416 | G56 vww4 | **UNSTABLE** | 68→172, 8×8 | 8x8x96 / 2x4x16 | 1,056 | 0.75 | 13,446 (1,539 = 11.4 %) | 0.079 | (708.8) | (0.692) |
| 417 | G52 ad | VALID | 276→276, 8×8 | 8x8x96 / 2x2x32 | 5,184 | 1.00 | 31,147.5 (29) | 0.166 | 940.4 | 0.918 |
| 418 | G57 vww4 | VALID | 68→288, 8×8 | 8x8x96 / 2x2x32 | 1,728 | 0.75 | 19,131 (755) | 0.090 | 725.3 | 0.708 |
| 419 | G09 mbv2 | VALID | 64→384, 14×14 | 8x14x64 / 2x2x32 | 4,704 | 1.00 | 56,807 (1,105) | 0.083 | **1024.0** | **1.000** |
| 420 | G28 ad | **UNSTABLE** | 276→276, 4×4 | 4x4x288 / 2x2x32 | 1,296 | 1.00 | 20,548.5 (1,345 = 6.5 %) | 0.063 | (940.4) | (0.918) |

- 모든 형상이 DepthFirst다. A2 Conv의 IFM/OFM은 Sram에 있다.
- 모든 A2 결과는 `INTERNAL_CONV_NOT_OBSERVED`다. 보드 출력 검증(`output.bin` = golden, 모든 RUN `output_match`)은 A2 최종 ADD 출력 기준으로 11개 모두 통과했다.
- UNSTABLE 3개의 사유는 모두 "NPU_ACTIVE pass A range > 5 %" 하나다. MAC_ACTIVE와 DPU는 4회 모두 같다.
  계약에 따라 VALID 집계에서 빼고, 괄호 안 값은 기록만 한다(`POST_HOC_DESCRIPTIVE`).

## MAC 계산부 특성 (VALID 형상 기준; 해석은 POST_HOC_DESCRIPTIVE)

1. **유효 MAC/MAC_ACTIVE의 최댓값은 1024다.**
   - Cin(64)과 Cout(384)이 16·32의 배수이고 공간 padding이 없는 G09에서 정확히 1024(=구성 MAC/CC)가 나왔다.
   - Stage 4K에서 1×1 DepthFirst 처리율로 읽었던 768(Cin 48)과 640(Cin 40)은 하드웨어 상한이 아니었다.
2. **MAC_ACTIVE는 padding된 연산량 ÷ 1024에 가깝다.**
   - 시험한 식: 공간(H, W)을 OFM ublock 배수로, Cin을 32의 배수로, Cout을 16의 배수로 올린 MAC 수 ÷ 1024.
   - 이 식 하나가 11개 중 9개 MAC_ACTIVE와 정확히 같다.
     - 기준 Cin 48 → 64: 1024 × 48/64 = 768.
     - G40: W 7 → 8(ublock 1x4).
     - G57: Cin 68 → 96.
   - 맞지 않는 형상은 다음 두 개다.
     - G25: Cout 140이 32 단위(160)로 맞는다.
     - G53: Cin 44가 48(16 단위)로 맞는다.
   - 형상별로 padding 단위를 따로 고르면 11개 모두 정확히 맞는 조합이 있다. 하지만 모든 형상에 공통인 단일 식은 시험한 범위에서 없었다.
   - 사전 고정한 비교값 `c16_rate_768`(768·Cin/⌈Cin/16⌉·16)은 기준 형상에서만 맞는다(비율 1.00). 대표 형상에서는 0.84–1.33이다.
3. **DPU/MAC.**
   - Cin이 32의 배수가 아닌 일부 형상에서 1보다 작다: G25 0.90, G57·G56 0.75.
   - 값은 Cin을 8(또는 16) 단위로 올린 양 / 32 단위로 올린 양과 같다. 예: G57은 72/96이다.
   - Stage 4K PartKernel Cin 16의 0.5도 같은 형태다.
4. **MAC_ACTIVE/NPU_ACTIVE는 0.08–0.21이다.**
   - A2 그래프 전체 실행 시간 중 MAC 활성 비율이 낮다.
   - NPU_ACTIVE − MAC_ACTIVE를 메모리 대기로 해석하지 않는다(계약 §5).
   - 이 값에는 ADD 2개와 DMA가 포함된다.

## AO / WD / 메모리 (기록만, 원인 배정 없음)

| 형상 | AO_ACTIVE | WD_ACTIVE | WD_STALLED | SRAM rd/wr beat | EXT rd/wr beat | weight B |
|---|---:|---:|---:|---|---|---:|
| 기준 | 3,529 | 1,781 | 9,642 | 3,520 / 440 | 3,929 / 3,456 | — |
| G12 | 14,975 | 5,868 | 24,085 | 25,088 / 9,216 | 27,066 / 7,872 | 87,376 |
| G25 | 4,044 | 1,314 | 4,386 | 3,375 / 2,250 | 6,794 / 1,931 | 21,536 |
| G40 | 9,244 | 2,746 | 15,209 | 6,370 / 3,430 | 12,081 / 2,940 | 167,376 |
| G11 | 12,526 | 3,633 | 12,633 | 16,384 / 7,680 | 13,796 / 7,872 | 58,016 |
| G52 | 3,458 | 1,786 | 8,247 | 3,840 / 2,304 | 9,615 / 1,968 | 87,360 |
| G57 | 2,631 | 635 | 2,991 | 2,624 / 1,472 | 2,751 / 1,152 | 24,096 |
| G09 | 11,166 | 1,583 | 11,916 | 10,192 / 5,488 | 5,046 / 4,704 | 23,664 |

- 53과 55는 TRM 목록 밖이라 `shapes.csv`에만 기록했다.
- AO에는 ADD의 AO가 포함된다. A2의 MAC/WD에 ADD가 기여하지 않는다는 근거는 Stage 4AO-E이고 `CONDITION_SPECIFIC`이다.

## Vela 추정 대비 오차 (A2 그래프 전체, 같은 컴파일 산출물)

Error(%) = (NPU_ACTIVE − Vela cycles_total) / Vela × 100이다. 양수는 Vela의 과소예측을 뜻한다.
- Vela 조건은 `Ethos_U85_SYS_DRAM_Mid_1024` @1 GHz, 보드 조건은 TA profile 1이다. 단위는 둘 다 NPU 사이클이다.
- Vela의 메모리 모델이 보드의 TA 에뮬레이션과 같다는 것은 증명하지 않았다.

| 형상 | Vela | NPU_ACTIVE | Error % |
|---|---:|---:|---:|
| G12 | 53,052 | 99,555 | +87.7 |
| G25 | 14,909 | 28,902.5 | +93.9 |
| G40 | 30,422 | 46,939.5 | +54.3 |
| G11 | 37,273 | 75,129.5 | +101.6 |
| G52 | 15,393 | 31,147.5 | +102.3 |
| G57 | 10,955 | 19,131 | +74.6 |
| G09 | 29,928 | 56,807 | +89.8 |
| G53, G56, G28 | — | — | NOT_COMPARABLE (UNSTABLE) |

- 7개 모두 Vela가 과소예측했다. 범위 +54~+102 %, 중앙값 +89.8 %, 평균 +86.3 %다.
- 오차와 다른 지표의 Spearman 상관(n=7, POST_HOC)은 다음과 같다.
  - MAC 처리율: 0.30
  - MAC/NPU: 0.04
  - Vela 사이클: −0.04
  - 뚜렷한 관계는 보이지 않으며, 인과를 주장하지 않는다.
- 이 오차는 A2 그래프 전체의 오차다. 원본 Conv 단독이나 MLEK 모델 전체의 오차로 바꿔 쓰지 않는다.

## Coverage (모델별 MAC 비율)

| 모델 | Static Reproduction | Selected Measurement | **Validly Measured Shape** | Stage 6 Validated HW (변화 없음) |
|---|---:|---:|---:|---:|
| ad_medium_int8 | 0.954 | 0.954 | 0.935 | 0.000 |
| kws_micronet_m | 0.710 | 0.517 | 0.517 | 0.000 |
| mobilenet_v2 | 0.206 | 0.139 | 0.139 | 0.219 |
| vww4 | 0.227 | 0.227 | 0.067 | 0.196 |
| yolo, wav2letter, rnnoise | 직접 측정 범위 밖 | | 0 | |

- Model-level Explanation Coverage는 수치화하지 않았다(`NOT_QUANTIFIED`). Stage 6의 `INSUFFICIENT_EVIDENCE`는 바꾸지 않는다.
- Validly Measured는 다음 뜻이다.
  - 형상 그룹의 대표 형상을 A2 래퍼 안에서 MLEK 입력으로 측정했다.
  - 원본 모델 안에서 같은 처리율이 나온다는 보장은 없다.
  - 모델 전체 MAC_ACTIVE를 독립 Conv 합으로 복원하지 않는다.

## 파일

- `stage6bb_summary.json`: 판정 결과 전부
- `shapes.csv`: 형상별 지표와 분석 변수
- `fidelity.csv`: Vela 대비 오차
- `coverage.csv`: 모델별 coverage
- `padding_fit.json`: 사후 padding 식 검색 결과
- 재현 명령:

  ```
  python3 host/analysis/stage6bb.py judge evidence/stage6b/stage6bb/raw/evsweep_s6bb_run evidence/stage6b/stage6bb/workloads \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/wfe \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/capabilities.json results/fi101_stage6b/stage6bb
  python3 host/analysis/stage6bb_analysis.py results/fi101_stage6b/stage6bb/stage6bb_summary.json \
    evidence/stage6b/stage6bb/workloads results/fi101_stage6b/stage6bb
  ```

- `stage6bb_analysis.py`는 기술 표를 만드는 코드다. 판정 규칙은 없다. 동결 뒤, 세션이 진행되는 동안(데이터를 보기 전) 작성했다.
