# Stage 6 근거: 기준 데이터 출처, 매핑 검증, 미해결 목록 (보드 RUN 없음)

판정 규칙과 허용폭: `rules.md` (커밋 `cbf8e23`). 추정과 비교를 계산하기 **전에** 고정했다.
구현: `host/analysis/stage6.py`. 테스트: test_stage6 10개. mutation 18/18 KILLED (`mutate.py`, `mutation.txt`).
mutation 중 하나 ("T2 for MAC ops only")는 절대 거짓이 될 수 없는 조건이어서 살아남았다. 그래서 그 조건 자체를 코드에서 지웠다.

## 1. Whole-model 기준 (driver_m7)

- 원시 데이터: `evidence/driver_m7/raw/wfe/<model>/runs.csv`, boot 308–316, TA profile 1 (README·capabilities로 확인), FI101 U85-1024,
  이미지 65cf963 (driver runner). 이후 Stage 4K–4WD는 이미지 70090f1을 썼다 — **조건 차이로 기록**한다.
- D1–D6, M1–M4 (`results/driver_m7/README.md`): 7개 모두 플랫폼은 MLEK과 같고, 실행·측정 창·반복 안정성이 OK이며, MLEK과 동등하다.
  예외: **wav2letter M4 (MAC/DPU/AO)는 UNPROVEN**이다.
- 이 단계의 점검 (`stage6.baseline`): 7개 모두 RUN 10개, 모두 valid. 인벤토리의 Vela 출력 sha256 = 측정 DRWL의 `vela_sha256`.
- 중앙값 정의: pass A (set 2)와 pass B (set 3)에서 측정 RUN (rep > 2, warm-up 2개 제외)의 중앙값.
  - 대조: 원시 RUN 전체 세트의 NPU_ACTIVE 중앙값 (kws 91,261.5, ad 146,039.5)은 driver_m7 README의 보고값 (91,262 / 146,040)과 같다.
  - pass A만 쓴 중앙값은 그와 최대 0.6 % 다르다.
  - 참고: Stage 4WD의 `mlek_wd.json`은 warm-up을 1개만 뺐다. 차이는 0.3 % 이하이고, Stage 6은 2개를 뺀다.

## 2. 매핑 검증 (`vela_kernel_mapping.csv`)

| 모델 | 인벤토리 행 | NPU 연산 (fused·CPU 제외) | 0-cycle fused 활성화 | CPU/제거 (Reshape 등) | 출력 dtype |
|---|---:|---:|---:|---:|---|
| kws | 25 | 13 | 12 | 1 | INT8 전부 |
| ad | 25 | 13 | 12 | 1 | INT8 |
| mobilenet_v2 | 128 | 69 | 59 | 1 | INT8 |
| vww4 | 118 | 81 | 37 | 1 | INT8 |
| rnnoise | 73 | 39 | 34 | 13 | INT8 |
| yolo-fastest | 171 | 94 | 77 | 5 | INT8 |
| wav2letter | 51 | 27 | 24 | 1 | INT8 |

- 인벤토리 = Vela debug DB의 scheduled operation과 그 출처 TFLite 연산이다 (`source.ext_key`).
- fused 활성화 (Relu6 등, cycle 0·MAC 0)는 별도 AO pass로 세지 않는다 (중복 집계 방지).
- MAC은 **Vela mac_count** (nn_macs)를 쓴다. TFLite MAC과는 구분한다 (kws에서 둘이 다름).
- dtype: 원본 tflite에서 연산별 출력 텐서 형식을 추출했다 (`results/fi101_stage6/tflite_dtypes.json`). 7개 모두 INT8이다.

## 3. 미해결·제한 목록

- **MAC 축**:
  - 모델 MAC의 대부분 (kws 85 %, ad 95 %, mobilenet 69 %, vww4 65 %, yolo 43 %)이 **1×1 DepthFirst Conv**이고, 측정 범위 밖이다.
  - 측정한 DepthFirst 처리율 (Cin 40: 640, 48·64·128: 768)이 일정하지 않으므로 T1_EXTRAP다.
  - wav2letter는 1×32·1×7 PartKernel (T2)이 81 %, rnnoise는 FC (T2)가 99 %다.
- **AO 축**:
  - Conv INT8은 T1이지만 DW와 FC는 T2다. 그래서 calibrated coverage가 57–67 %에 그친다 (wav2letter만 97.5 %).
  - 체인 여부는 판정하지 않았다 (NHCWB16 출력의 Elementwise는 U).
- **WD 축**:
  - 수치 모델은 1×1 PartKernel Cin16 Cout96 계열뿐이다 (yolo 14 %만 해당). 나머지는 구조 지표 (spatial block × weight bytes)다.
- **층별 귀속**: Stage 2B의 연산별 PMU 귀속은 쓰지 않았다. QREAD prefix도 쓰지 않았다.
- Open Issue (보존): AO-1 (ABS N/32), WD-1 (FC encoded/WD > 32 B/cycle), WD-2 (WD_STALLED 원인).
