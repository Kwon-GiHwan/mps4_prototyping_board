# Stage 4AO — Ethos-U85 AO(Activation Output) 하드웨어 특성: 분석·설계 (보드 없음)

상태: **2026-11-15 보드 없는 단계 완료.** 판정 `NEEDS_REVISION`. 지시된 Phase B 형상 4개 중 Vela 실행 구성(OFM block)이
같은 것은 2개뿐입니다. 수정안과 계약 초안은 `evidence/stage4ao/contract_draft.md`에 있고, 동결·보드 실행은 하지 않았습니다.
모든 보드 수치의 조건은 TA profile 1, 이미지 `70090f1`, DDR/EXT 배치, Vela 5.0.0(MLEK 옵션)입니다.

## 1. 공식 자료로 확인한 것 (Arm Ethos-U85 TRM 102685 issue 05, Technical Overview 102684 issue 03)

로컬 PDF(`~/Downloads/arm_ethos-u85_npu_technical_reference_manual_102685_0000_05_en.pdf`)를 `pdftotext`로 읽었습니다.
인용은 원문 그대로 옮겼습니다.

| 질문 | 공식 자료 | 출처 |
|---|---|---|
| 1. U85-1024의 Scaling Unit 수 | **NUM_SU = 16** ("1024/2048 16/32") | TRM §4.2 Table 4-11, Table 4-13 |
| 2. AB→OB 처리율 | SU당 사이클당 원소 수: OB_8 **1**, OB_16 **1/2 (DMA)**, OB_32 1/4 (DMA), OB_64 1/8 (DMA). 1024 구성에서는 각각 16, 8, 4, 2 elements/cycle | Table 4-11 ("Multiply this number with NUM_SU to get the number of processed elements per clock cycle") |
| 3. AB→CB, CB→CB, CB→OB | AB→CB_8/16 1, CB_32 1/2 (CB). CB→CB 8/16→8/16 1, 32 bit 입출력 1/2 (CB). CB_8/16→OB_8 1, →OB_16 1/2 (DMA) | Table 4-11, 4-12 |
| 4. Unary와 Binary | CB_32→OB_8/16: Unary 1/2 (DMA), Binary 1/2 (CB, DMA). CB_32→OB_32: Unary 1/4 (DMA), Binary 1/4 (DMA). 8/16 bit CB 입력에서는 표상 차이가 없습니다 | Table 4-12 |
| 5. 출력 DMA 대역폭 | AO_DMA_OFM_IF의 OFM_DATA_W는 **128 bit/cycle**(U85-1024)입니다. OFM 16 ratio는 0.5, 32는 0.25, 64는 0.125입니다. 따라서 8 bit OFM 16 elem/cycle = 128 bit는 이 폭과 정확히 같습니다 | Table 4-13 |
| 6. ReLU, ReLU6, LUT | "ReLU and LUT can be applied directly to the output of any AO operation. Leaky ReLU is a separate elementwise AO operation." 명령어 `NPU_SET_ACTIVATION`의 activation_function 필드에는 lut_none, lut_s8_s8, …, lut_tanh, lut_sigmoid가 있고, clip range는 `NPU_SET_ACTIVATION_MIN/MAX`가 정합니다 | TRM §2.6, §2.6.2, §3.10.14 |
| 7. AO_ACTIVE 정의 | EV_TYPE 64 `ao_active`: "AO is doing block traversal of accumulation or chaining buffer. Valid blk_cmd and not stalled" | TRM PMEVTYPER Table 2 (issue 05 본문에서 다시 확인) |
| 8. AO stall을 직접 관측할 수 있는가 | **없습니다.** TRM은 "65..79 Reserved"로 표기합니다. 드라이버 헤더에는 67–72 `ao_stalled_by_*` 이름이 있지만 공식 정의가 없으므로 해석에 쓰지 않습니다 | TRM PMEVTYPER, `docs/reference/ETHOS_U85_PMU_REFERENCE.md` |

공식 성능표의 일반 조건(같은 절): "A slow block affects all following blocks", "Partial SBs might be used at block
edges", "A bubble might be inserted when reading from the AB due to a grant delay of maximum one cycle".
이 문장들은 블록 경계와 AB 읽기에서 16 elem/cycle보다 느려질 수 있는 공식 근거입니다. 다만 그 크기는 표에 없습니다.

**공식 수치와 실측 추정치를 구분합니다.** 16 elements/cycle(INT8 AB→OB)과 8(INT16)은 공식 수치입니다.
아래 §2의 15.5–15.9 elements/cycle은 실측 AO_ACTIVE로 계산한 값이며, SU 점유율을 직접 잰 것이 아닙니다.

## 2. Phase A — Stage 4K AO 재분석 (원시 RUN에서 다시 계산, `results/fi101_stage4ao/phase_a.json`)

`runs.csv`를 독립 스크립트로 다시 읽었습니다(pass A, 측정 RUN 2–5의 중앙값). `stage4ao.py phase-a`와 숫자가 같습니다.
OFM은 모든 구성에서 24×24×96 = 55,296 원소, INT8, RELU6이고 OFM ublock은 2×2×32입니다.
EXT write beat는 모든 구성에서 3,456입니다(16 B/beat이면 55,296 B로 OFM 크기와 같습니다).

| 구성 | AO_ACTIVE (range) | MAC_ACTIVE | NPU_ACTIVE | AO/NPU | N/AO | 잔차 (AO − 3,456) | Vela AO 추정 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1×1 Cin16 | 3,540.5 (10) | 2,304 | 21,629 | 0.164 | 15.62 | 84.5 | 4,224 |
| 3×3 Cin16 | 3,562.5 (18) | 10,368 | 22,777 | 0.156 | 15.52 | 106.5 | 4,896 |
| 1×1 Cin32 | 3,533 (10) | 4,608 | 25,470 | 0.139 | 15.65 | 77 | 4,992 |
| 3×3 Cin32 | 3,529.5 (11) | 20,736 | 30,494.5 | 0.116 | 15.67 | 73.5 | 6,336 |
| 1×1 Cin40 | 3,530 (13) | 3,456 | 21,927.5 | 0.161 | 15.67 | 74 | 3,840 |
| 3×3 Cin40 | 3,484.5 (13) | 25,920 | 37,635 | 0.093 | 15.87 | 28.5 | 7,776 |
| 1×1 Cin48 | 3,533 (7) | 3,456 | 22,251 | 0.159 | 15.65 | 77 | 3,840 |
| 3×3 Cin48 | 3,507.5 (50) | 31,104 | 40,156 | 0.087 | 15.77 | 51.5 | 7,776 |
| 1×1 Cin64 | 3,538 (25) | 4,608 | 24,257 | 0.146 | 15.63 | 82 | 3,888 |
| 3×3 Cin64 | 3,524.5 (35) | 41,472 | 55,015 | 0.064 | 15.69 | 68.5 | 9,216 |

- **MAC보다 OFM 원소 수와 더 밀접한가?** MAC_ACTIVE는 18배까지 차이 나지만 AO_ACTIVE의 폭은 78 cycle(2.2 %)입니다.
  이 데이터에서 AO_ACTIVE는 MAC 양을 따라가지 않습니다. 오히려 Spearman 순위상관이 −0.68로, MAC이 큰 3×3 Cin40·48에서
  AO가 약간 작습니다. 원인은 분리되지 않았습니다.
- **"같은 출력 크기"만으로 일정함을 설명할 수 있는가?** 그것과 모순되지는 않습니다. 하지만 10개 모두 OFM 크기가 같으므로
  **출력 원소 수에 대한 비례를 직접 검증한 데이터는 아닙니다.** 구성 사이 차이(78)가 RUN range(최대 50)보다 커서,
  같은 OFM에서도 구성에 따른 작은 차이가 남아 있습니다.
- **Vela의 AO 추정(M4)은 실측과 맞지 않습니다.** Vela는 커널과 Cin에 따라 3,840–9,216을 내지만, 실측은 약 3,500으로 일정합니다.

### 기존 TA profile 1 데이터 중 OFM 크기가 다른 것 (POST_HOC_DESCRIPTIVE, 사전 등록 아님)

Stage 4·4C-1·4C-2 원시 RUN입니다. 이미지 83398c7과 70090f1이 섞여 있고 모두 TA profile 1입니다.

| 구성 | OFM | AO_ACTIVE | 정확한 원소 수 기준 잔차 | 채널을 16 단위로 올림한 기준 잔차 | 올림 기준 N/AO/16 |
|---|---|---:|---:|---:|---:|
| Conv Cout 94 / 95 | 24×24×94/95 | 3,537.5 / 3,536.5 | 153.5 / 116.5 | 81.5 / 80.5 | 0.977 |
| Conv Cout 97 | 24×24×97 | 4,127.5 | 635.5 | **95.5** | 0.977 |
| DW 144 (2 boot) | 56×56×144 | 28,491 / 28,474.5 | 267 / 250.5 | 267 / 250.5 | 0.991 |
| DW 142 / 143 | 56×56×142/143 | 28,477 / 28,484.5 | 645 / 456.5 | 253 / 260.5 | 0.991 |
| DW 145 | 56×56×145 | 31,641.5 | 3,221.5 | **281.5** | 0.991 |
| FC 288 / 287 | 288 / 287 | 19–20 | 1–2 | 1–2 | 0.90–0.95 |

이 데이터를 보고 세운 가설일 뿐 검증된 결과가 아닙니다. 출력 채널을 16 단위로 올린 원소 수에 대해 AO_ACTIVE는
연산 종류(Conv, DW, FC)와 OFM 크기(288–501,760)가 달라도 16 elem/cycle의 0.90–0.99배로 설명됩니다.
남는 차이는 Conv 24×24에서 약 80, DW 56×56에서 약 250–280입니다. 이 차이가 OFM 블록 수나 공간 위치 수에
비례하는지는 이 데이터로 판단할 수 없습니다(블록 구성과 연산이 함께 다르기 때문).

## 3. Phase B — OFM 원소 수 Sweep 정적 분석 (`results/fi101_stage4ao/static.json`)

생성 규칙: 1×1 Conv, Cin 16, Cout 96, stride 1, SAME, RELU6, INT8.
- weight, bias, OFM scale은 `s4_conv_base`의 것을 그대로 씁니다.
- IFM은 base 24행(seed 1)에서 시작합니다. H < 24이면 앞 H행을 잘라 쓰고, H > 24이면 `AO_SEED = 20261115`로 한 번
  생성한 행(H 72까지 만든 뒤 잘라 씀)을 덧붙입니다. 그래서 작은 구성의 행은 모두 큰 구성에도 그대로 들어 있습니다.
- `s4ao_conv1x1_h24`(SAME)의 명령 스트림과 CPU reference는 Stage 4K `s4_conv_base`(VALID)와 바이트 단위로 같습니다.
- 두 번 빌드한 결과가 바이트 단위로 같습니다(결정적). Stage 4K `s4_conv_base` DRWL도 다시 빌드하니 바이트가 같았습니다.

| 형상 | N_OFM | 이상적 AO | traversal | OFM block | IFM block | ublock | 커널 (OFM slice) | weight B | OFM 블록 수 | Vela AO | 비교 가능 |
|---|---:|---:|---|---|---|---|---|---:|---:|---:|---|
| 12×24 | 27,648 | 1,728 | PartKernel | **8×24×32** | 8×24×16 | 2×2×32 | 2 (16, 80) | 2,752 | 8 | 2,112 | 아니오 |
| 24×24 | 55,296 | 3,456 | PartKernel | 6×12×96 | 6×12×16 | 2×2×32 | 2 (16, 80) | 2,752 | 16 | 4,224 | 기준 |
| 36×24 | 82,944 | 5,184 | PartKernel | 6×12×96 | 6×12×16 | 2×2×32 | 2 (16, 80) | 2,752 | 24 | 5,952 | 예 |
| 48×24 | 110,592 | 6,912 | PartKernel | **10×8×96** | 10×8×16 | 2×2×32 | 2 (16, 80) | 2,752 | 30 | 7,680 | 아니오 |

모든 형상에서 같은 것: OFM 정밀도는 INT8(OFM precision word 1), 배치는 IFM·OFM 모두 DDR/EXT, weight stream 길이,
Vela 단일 연산(CPU fallback 없음), Gate B 5개 검사 모두 PASS.
SRAM scratch와 DMA 양(Vela `sram_ac`/`dram_ac`)은 H에 비례해 늘어납니다(`stage4ao_static.csv`).

**판정: `NEEDS_REVISION`.** 비교 가능성은 데이터를 보기 전에 정의했습니다(`stage4ao.py comparable`).
기준(24×24)과 traversal, OFM·IFM block, ublock, 커널 수와 OFM slice, OFM 정밀도가 모두 같아야 합니다.
이 정의로는 2개(24, 36)만 비교 가능합니다. 12×24와 48×24는 block이 달라, 출력 원소 수만의 효과로 볼 수 없습니다.
지시에 따라 대체 형상을 측정 대상으로 확정하지 않았습니다.

**참고: owner 검토용 수정안 (확정 아님).** 컴파일만 해서 block을 조사했습니다(`block_scan.json`, H 또는 W를 6–72 범위에서
6 간격으로). W = 24에서는 **H = 24, 36, 42, 54, 72가 6×12×96 block을 유지**합니다. 이 다섯 개(h42/h54/h72 포함)는
빌드와 Gate B까지 마쳤고, 비교 가능성 판정은 `COMPARABLE`입니다. W를 바꾸는 방식에서는 W = 24·48만 같은 block이었습니다.

## 4. Phase C — Activation 비교 정적 분석

같은 24×24 Conv(텐서와 OFM scale이 동일)에서 fused activation만 NONE, RELU, RELU6으로 바꿨습니다.

- 명령 스트림 길이(88개 명령)와 순서는 같습니다. **다른 것은 `NPU_SET_ACTIVATION_MIN`(294)과 `_MAX`(295)의 값뿐입니다.**
  - RELU6: min 0, max 120 (6/OFM scale)
  - RELU: min 0, max 127
  - NONE: min −128, max 127
- `NPU_SET_ACTIVATION`(lut_none), block, weight, OFM scale, 커널 수는 같습니다. 별도 NPU 커널은 추가되지 않습니다.
- 사전 선정 규칙(Gate B, 같은 signature, 정렬된 스트림, ACTIVATION_MIN/MAX 외 차이 없음, 같은 weight stream)을
  두 구성 모두 **통과**합니다.
- 해석 제한: 출력 값(CPU reference)은 구성마다 다릅니다. ReLU 포화나 음수 출력이 바뀌므로 OFM 데이터 패턴이 같지 않습니다.
  공식 자료상 클램프는 같은 AO 출력 경로에서 적용됩니다(§2.6). 따라서 이 비교는 "같은 경로에서 clip 범위만 다를 때
  AO_ACTIVE가 같은가"를 볼 뿐이며, ReLU 기능 하나의 독립된 비용을 측정하는 것이 아닙니다.

## 5. Phase D — LUT, INT16, Elementwise, CB 정적 조사 (측정 계약에 넣지 않음)

모든 probe가 Vela 5.0.0에서 NPU 단일 custom op로 컴파일되었고 CPU fallback은 없었습니다
(`evidence/stage4ao/workloads/*.static.json`).

| probe | Vela 스케줄 | 커널 (명령 스트림) | AO 관련 관측 | DRWL 패킹 |
|---|---|---|---|---|
| Conv→TANH | Conv2D + LUT (0 cycle) | CONV×2 | LUT이 Conv의 AO에 융합됨. `NPU_SET_ACTIVATION` = 0x4 (lut_s8_s8). Vela AO 추정은 base와 같은 4,224 | 성공 |
| Conv→LOGISTIC | Conv2D + LUT | CONV×2 | 위와 같음 | 성공 |
| Conv INT16 (16x8) | Conv2D | CONV×2 | OFM 정밀도 16 bit. block 8×8×64(INT8과 다름). Vela AO 추정 7,424 | **실패**: DRWL 파서 `section (24112, 0) misplaced`. 패커 또는 runner 수정이 필요합니다 |
| ADD int8 | Add | ELEMENTWISE×1 | Vela NPU 추정 3,456 = 55,296/16 | 성공 (IFM 2개) |
| MUL int8 | Mul | ELEMENTWISE×1 | 위와 같음 | 성공 |
| ABS int8 | Abs | ELEMENTWISE×1 | 위와 같음 | 성공 |
| LEAKY_RELU int8 | **LUT (MAC 55,296)** | **POOL×1** | Vela는 int8 Leaky ReLU를 Pool+LUT로 매핑합니다. AO 단독 elementwise가 아닙니다 | 성공 |
| Conv→ADD | Conv2D + Add (0 cycle) | CONV, ELEMENTWISE, CONV, ELEMENTWISE | **CB 사용**: Conv OFM storage = CHAINED(2), ADD IFM storage = CHAINED | 성공 (IFM 2개) |
| ADD→MUL | Add + Mul (0 cycle) | ELEMENTWISE×2 | **CB 사용**: ADD OFM CHAINED → MUL IFM CHAINED. Vela AO 추정 6,912 = 2×3,456 | 성공 (IFM 3개) |

CB 사용 여부는 연산자 이름이 아니라 명령 스트림의 `NPU_SET_{IFM,OFM}_PRECISION` activation_storage 필드
(`ethosu85_interface.h`: TILE2X2 0, TILE3X1 1, **CHAINED 2**)로 판정했습니다.
INT16 측정에는 패커/runner 변경이 필요합니다. 변경 범위는 계약 초안 §11에 적었고, 이번에는 고치지 않았습니다.

## 6. 예측 모델 (`results/fi101_stage4ao/predictions.json`, 보드 데이터 전에 고정)

- M1 = N/16
- M2 = N/16 + C0. C0 = 79.5는 같은 blob(`s4_conv_base`)의 5개 boot(330, 338, 344, 367, 369) AO 중앙값에서 3,456을 뺀 값들의 중앙값입니다.
- M3 = N/16 + C0 × (OFM 블록 수 / 16). 블록 경계 비용이 블록 수에 비례한다고 보는 모델입니다.
- M4 = Vela `ao_cycles`

| 형상 | M1 | M2 | M3 | M4 | 허용폭 (M2 기준) |
|---|---:|---:|---:|---:|---:|
| 24×24 | 3,456 | 3,535.5 | 3,535.5 | 4,224 | 35.4 |
| 36×24 | 5,184 | 5,263.5 | 5,303.2 | 5,952 | 52.6 |
| 42×24 | 6,048 | 6,127.5 | 6,187.1 | 6,816 | 61.3 |
| 54×24 | 7,776 | 7,855.5 | 7,954.9 | 8,544 | 78.6 |
| 72×24 | 10,368 | 10,447.5 | 10,606.5 | 11,136 | 104.5 |

M2와 M3는 54×24(차이 99)와 72×24(차이 159)에서만 허용폭 밖으로 갈립니다. 36·42에서는 구분되지 않습니다.
M1과 M4는 기존 24×24 데이터(3,540.5)에서 이미 허용폭 밖입니다. 이는 보드 측정 전에 알려진 사실로 기록합니다.

## 7. 보드에서 측정해야 할 가설

1. H1: 같은 실행 구성에서 AO_ACTIVE는 N_OFM/16에 기울기 1(±2 %)로 비례합니다(RQ1, 처리율 16 elem/cycle).
2. 절편(overhead)이 일정한지(M2), 블록 수에 비례하는지(M3).
3. RQ3: clip 범위만 다른 activation(NONE, RELU, RELU6)에서 AO_ACTIVE가 같은지.
4. 보조: NPU_ACTIVE가 AO_ACTIVE 증가분과 어떤 관계인지. 이것은 기술 통계만 내며 인과로 해석하지 않습니다.

## 8. 아직 증명되지 않은 것

- AO_ACTIVE가 N_OFM에 비례한다는 것. 기존 데이터는 같은 OFM이거나, 블록·연산이 함께 다른 사후 비교뿐입니다.
- 16 채널 단위 올림. 사후 관측일 뿐입니다.
- 잔차(약 80 cycle)의 원인. 공식 문서는 partial SB와 AB grant bubble 가능성만 언급합니다.
- 3×3 Cin40·48에서 AO가 약간 낮은 이유.
- INT16, Elementwise, CB 경로의 실측 처리율. 정적 매핑만 확인했습니다.
- AO stall 비율. 공식 PMU 이벤트가 없습니다.
