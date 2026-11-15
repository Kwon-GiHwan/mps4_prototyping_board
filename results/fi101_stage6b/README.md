# Stage 6B — 실제 모델의 1×1 DepthFirst Conv 형상 추출과 정적 재현 (보드 없음)

- 규칙: `evidence/stage6b/rules.md` (커밋 `b9f3824`, 후보 컴파일 전에 고정).
- 구현: `host/analysis/stage6b.py` (test_stage6b 12개, mutation 18/18 KILLED), `host/container/stage6b_models.py`.
- 기준: Stage 6 인벤토리 (Vela 5.0.0, MLEK 옵션, 591행).
- **보드 RUN은 없다.** 이 단계의 숫자는 모두 Vela 정적 정보다.
- 향후 측정 조건 (계약 초안): FI101 U85-1024, TA profile 1, 이미지 70090f1, DDR/EXT.

## 최종 판정 (사전 고정 규칙 그대로): **NEEDS_REVISION**

- 후보 26개 중 EXACT_STATIC_MATCH는 1개 (G14, wav2letter)다. 나머지 25개는 PARTIAL_STATIC_MATCH이고 NOT_REPRODUCIBLE은 0개다.
- 그래서 선정도 1개다. coverage 개선 가능성은 wav2letter 하나 (+17.0 %p)뿐이다. 나머지 6개 모델은 0이다.
- 원인은 형상이나 실행 구성이 아니라 **배치**다.
  - 26개 모두 두 형태 (F_PLAIN, F_CTX)에서 traversal, IFM block, OFM block, ublock이 원본과 같다 (RQ3의 block 매핑 부분 = 재현됨).
  - 어긋난 항목:
    - F_PLAIN: IFM/OFM이 Dram·NHWC다 (그래프 입출력이므로 당연함).
    - F_CTX: IFM은 원본과 같은 Sram·NHCWB16이 됐다. 하지만 **Conv OFM이 Dram에 놓였다** (원본은 Sram인 경우가 19개).
    - 이와 함께 staging_usage가 달랐다. 4개는 weight_bytes도 달랐다.

## 1. 모델별 1×1 DepthFirst MAC 비중 (Vela mac_count, 분모 = 모델 NPU MAC)

| 모델 | 1×1 DF 비중 | 연산 수 | 그룹 수 | 후보 (상위 5) 비중 | Stage 6 MAC coverage | 개선 상한 (원래 규칙) |
|---|---:|---:|---:|---:|---:|---:|
| ad | 95.4 % | 6 | 5 | 95.4 % | 0 % | 0 % |
| kws | 84.9 % | 6 | 4 | 84.9 % | 0 % | 0 % |
| mobilenet_v2 | 68.9 % | 28 | 16 | 38.6 % | 21.9 % | 21.9 % |
| vww4 | 65.2 % | 21 | 17 | 34.8 % | 19.6 % | 19.6 % |
| yolo-fastest | 42.7 % | 30 | 13 | 34.6 % | 22.0 % | 22.0 % |
| wav2letter | 17.2 % | 2 | 2 | 17.2 % | 0 % | **17.0 %** |
| rnnoise | 0 % | 0 | 0 | — | 0 % | 0 % (대상 연산 없음; MAC의 99 %가 FC) |

- 전체: 대상 연산 93개, 실행 그룹 57개. 모델 사이에 공통 그룹은 없다 (형상이 모두 다름).
- 상세: `depthfirst_operator_inventory.csv`, `depthfirst_execution_groups.csv`, `coverage_opportunity.csv`.

## 2. 후보 26개와 정적 재현 (원본의 실제 weight·bias·scale 사용)

| 그룹 | 모델 | IFM→Cout | OFM block | 원본 IFM/OFM 배치 | 모델 내 비중 | F_PLAIN | F_CTX (다른 항목) | (POST_HOC) F_CTX_SELF |
|---|---|---|---|---|---:|---|---|---|
| G01 | yolo | 12x12x120→120 | 4x12x128 | Sram/Sram | 10.7 % | PARTIAL | PARTIAL (ofm_memory weight_bytes staging) | PARTIAL (weight_bytes staging) |
| G03 | yolo | 12x12x136→24 | 6x12x32 | Sram/Dram | 4.8 % | PARTIAL | PARTIAL (staging) | PARTIAL (ofm_memory staging) |
| G08 | mobilenet | 14x14x576→96 | 6x14x96 | Sram/Dram | 7.2 % | PARTIAL | PARTIAL (weight_bytes staging) | PARTIAL (ofm_memory weight_bytes staging) |
| G09 | mobilenet | 14x14x64→384 | 8x14x64 | Sram/Sram | 6.4 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G10 | mobilenet | 14x14x96→576 | 6x14x96 | Sram/Sram | 10.8 % | PARTIAL | PARTIAL (ofm_memory weight_bytes staging) | PARTIAL (weight_bytes staging) |
| G11 | ad | 16x16x192→276 | 8x16x64 | Sram/Sram | 22.1 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G12 | ad | 16x16x276→276 | 8x16x64 | Sram/Sram | 63.5 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G13 | vww4 | 16x16x96→28 | 8x16x32 | Sram/Sram | 7.3 % | PARTIAL | PARTIAL (ofm_memory staging) | PARTIAL (staging) |
| **G14** | wav2letter | 1x148x2000→2000 | 1x76x96 | Sram/Dram | 17.0 % | PARTIAL | **EXACT** | EXACT |
| G15 | wav2letter | 1x148x2000→29 | 1x76x32 | Dram/Sram | 0.2 % | PARTIAL | PARTIAL (ifm_memory ofm_memory staging) | PARTIAL (ifm_memory staging) |
| G18 | kws | 1x1x196→12 | 2x2x32 | Sram/Dram | 0.0 % | PARTIAL | PARTIAL (ofm_format) | PARTIAL |
| G19 | ad | 1x1x276→8 | 2x2x32 | Sram/Dram | 0.0 % | PARTIAL | PARTIAL (ofm_format) | PARTIAL |
| G22 | yolo | 24x24x96→16 | 4x24x16 | Sram/Dram | 9.1 % | PARTIAL | PARTIAL (staging) | PARTIAL (ofm_memory staging) |
| G23 | kws | 25x5x112→196 | 20x6x64 | Sram/Sram | 19.3 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G24 | kws | 25x5x140→112 | 10x6x128 | Sram/Sram | 13.8 % | PARTIAL | PARTIAL (ofm_memory weight_bytes staging) | PARTIAL (weight_bytes staging) |
| G25 | kws | 25x5x140→140 | 14x6x96 | Sram/Sram | 51.7 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G28 | ad | 4x4x276→276 | 4x4x288 | Sram/Sram | 2.0 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G36 | yolo | 6x6x224→48 | 6x6x64 | Sram/Dram | 5.0 % | PARTIAL | PARTIAL (staging) | PARTIAL (ofm_memory staging) |
| G37 | yolo | 6x6x48→224 | 6x6x224 | Sram/Sram | 5.0 % | PARTIAL | PARTIAL (ofm_memory staging) | PARTIAL (staging) |
| G40 | mobilenet | 7x7x160→960 | 7x8x128 | Sram/Sram | 7.5 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G41 | mobilenet | 7x7x320→1280 | 7x8x128 | Sram/Sram | 6.7 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G51 | vww4 | 8x8x268→52 | 8x8x64 | Sram/Sram | 4.8 % | PARTIAL | PARTIAL (ofm_memory staging) | PARTIAL (staging) |
| G52 | ad | 8x8x276→276 | 8x8x96 | Sram/Sram | 7.9 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G53 | vww4 | 8x8x44→268 | 8x8x96 | Sram/Sram | 8.0 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G56 | vww4 | 8x8x68→172 | 8x8x96 | Sram/Sram | 8.0 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |
| G57 | vww4 | 8x8x68→288 | 8x8x96 | Sram/Sram | 6.7 % | PARTIAL | PARTIAL (ofm_memory staging) | EXACT |

- 모든 후보가 실행 가능하다.
  - Conv가 scheduled operation 하나이고, CPU 연산이 없고, 패킹이 성공했다.
  - fast scratch ≤ 384 KiB, arena ≤ 2 MiB.
  - 두 번 컴파일한 tflite·Vela·DRWL sha256이 같다.
- 출력: golden은 BUILTIN_REF다. 기본 커널과 다른 원소 수 (opt_vs_ref)는 0–80개이고, 기록만 한다 (`compile.log`).
- 마지막 열 F_CTX_SELF는 **POST_HOC_DESCRIPTIVE**다. 사전 고정 규칙에 없는 형태다. 판정·선정에 쓰지 않았고 실행 가능 검사 (패킹, 반복 컴파일)도 하지 않았다. 아래 §4에서 설명한다.

## 3. 정적 차이의 성격 (POST_HOC_DESCRIPTIVE, `evidence/stage6b/post_hoc/`)

- **staging_usage**: Vela가 그 연산 시점에 fast storage (Sram)에 두는 바이트다.
  - F_CTX 26개 중 19개에서 Sram에 놓인 IFM·OFM 텐서 바이트 (NHCWB16 기준)와 정확히 같다.
  - 나머지 7개 (G01 G03 G08 G10 G13 G22 G24)는 그보다 크다. weight를 SRAM에 버퍼링한 몫으로 보인다.
    이 중 4개 (G01, G08, G10, G24)는 weight_bytes도 원본과 다르다.
  - 원본 모델에서는 이 값에 그래프의 다른 살아 있는 텐서 (예: skip 연결)가 포함될 수 있다.
    그래서 "OFM 배치만 다름"과 "다른 텐서가 함께 살아 있음"이 모두 staging_usage 차이로 나타난다.
- **OFM 배치**: F_CTX의 뒤쪽 `ADD(conv_out, c)`에서 Vela는 Conv OFM을 Dram에 둔다.
  - 프로브 (G25, G12, G09) 결과, `ADD(conv_out, conv_out)` (F_CTX_SELF)는 OFM을 Sram에 두고 staging_usage도 원본과 같아진다.
  - ABS 또는 ADD 두 개 체인은 Dram이었다.
- **MAC 축 오염 없음의 근거**: Stage 4AO-E (TA profile 1)에서 INT8 ADD는 MAC_ACTIVE 0, WD 0이었다.
  F_CTX 계열의 AO_ACTIVE·NPU_ACTIVE·beat에는 ADD가 포함된다.

## 4. 개정 제안 (승인 필요, 아직 적용하지 않음)

- **개정 A**: 정적 재현 형태에 F_CTX_SELF (ADD(a, b) → Conv → ADD(conv_out, conv_out))를 더한다.
  - 등급 = 세 형태 중 좋은 쪽이다. 동률이면 F_PLAIN > F_CTX > F_CTX_SELF 순으로 고른다.
  - 비교 항목과 적격 조건 (EXACT만)은 바꾸지 않는다.
- POST_HOC 계산상, 적격은 13개다: G09 G11 G12 G14 G23 G25 G28 G40 G41 G52 G53 G56 G57.
- 그 경우 모델별 1×1 DF 중 재현 가능한 비중: ad 95.4 %, kws 71.0 %, mobilenet 20.6 %, vww4 22.7 %, wav2letter 17.0 %, yolo 0 %.
- yolo의 큰 그룹은 남는 차이 때문에 재현되지 않는다:
  - weight 버퍼링 (G01)
  - 원본 OFM이 Dram인데 F_CTX_SELF는 Sram이고, F_CTX는 staging이 다름 (G03, G22, G36)
- 개정 A를 적용하면 선정 규칙 (모델별 1개 보장 → 정규화 점수)으로 최대 10개를 다시 고르고, 계약 초안의 대상 표를 바꾼다.

## 5. 기존 Cin40/48/64/128 측정과의 비교 가능성

- 기존 DepthFirst 측정은 OFM 24×24×96 한 계열이다. block은 6×12×96, 배치는 Dram·NHWC다 (Stage 4C-2/4K).
- 후보 26개 중 Cin·Cout·block이 같은 것은 **없다**. 그래서 640·768을 어떤 후보에도 적용하지 않는다.
- 4K에서 Cin40과 Cin48은 둘 다 MAC_ACTIVE 3,456이었다 (TA profile 1). 그래서 640 = 3,456 cycle에 Cin40의 MAC을 나눈 값이다 (4K 분류 `R768_c16`).
  이것이 채널 정렬만의 효과인지는 판정하지 않는다 (지시의 금지 주장).

## 6. 제한

- EXACT_STATIC_MATCH는 Vela 정적 정보가 같다는 뜻이다. 모델 레이어의 PMU 활동이 같다는 뜻이 아니다. Stage 6의 T0를 주지 않는다.
- 그룹 안 weight 값 차이 (예: kws G25 3개 연산의 weight_bytes 21,536–22,288)는 MAC에 영향이 없다고 가정한다.
  근거는 Stage 4WD 실험 A의 MAC_SAME이지만, PartKernel 형상에서 얻은 것이다.
- wav2letter는 whole-model 동등성 M4 (MAC/DPU/AO)가 UNPROVEN이다. G14 측정값을 나중에 모델에 적용할 때 이 조건을 함께 적는다.
- 물리 배치: 모델 (driver_m7)의 fast storage 위치와 독립 구성 (DDR/EXT 기본 배치, REGIONCFG)은 다를 수 있다. Stage 6처럼 조건 차이로 기록한다.
