# fi101_stage4ao — AO(Activation Output) 처리율: 보드 측정 (boot 379–384) + 정적 분석

조건 (모든 숫자): FI101 Ethos-U85 1024 MAC, **TA profile 1**, driver runner 이미지 `70090f1`, DDR/EXT, Vela 5.0.0 (MLEK 옵션).
계약 `evidence/stage4ao/contract.md` (동결 `f38c8aa`). 원시 데이터: `evidence/stage4ao/raw/` (107개 파일, `raw.sha256`, 보드와 sha256 일치).
설계 해설: `docs/plan/stage4ao_characterization_plan.md`.

## 1. 세션 경과 (2026-11-15, 보드 시각 2026-11-14T17:33–17:53Z)

| boot | config | 결과 |
|---:|---|---|
| 379 | `s4_conv_base` | VALID (10/10 RUN, PASS_EXACT). **재현 Gate PASS**: MAC·DPU·출력·상수 카운터 동일, NPU 21,069 vs 21,629 (허용폭 1,211), AO 3,533.0 vs 3,540.5 (허용폭 35.4) |
| 380 | `s4ao_conv1x1_h24` | VALID, PASS_EXACT |
| 381 | `s4ao_conv1x1_h36` | VALID, PASS_EXACT |
| 382 | `s4ao_conv1x1_h54` | VALID, PASS_EXACT |
| 383 | `s4ao_conv1x1_h72` | VALID, PASS_EXACT |
| 384 | `s4ao_act_none` | **INVALID**: warm-up RUN 1에서 출력 57/55,296 원소가 CPU reference와 다름 (최대 \|차이\| 1). runner가 `RULE_RUN_INVALID`로 거부했고 RUN 1개만 기록됨. boot-check FAIL → **fail-fast로 세션 중단** |
| 385 | `s4ao_act_relu` | **NOT_MEASURED** (중단 후 실행 안 함) |

- RUN 총계: 51 (379–383 각 10, 384는 1). 계약 상한은 70.
- 복원: 세션의 복구 단계 `restore_mlek` → RESTORE VERIFIED. m6 digest 4개 (images.txt `cb78a12e…`, APP `ffa3e5bd…`,
  VECTORS `45e943c5…`, DDR `81d37a21…`)가 Stage 4K 복원 때와 같다. 실패 경로에서는 세션이 postflight를 건너뛰므로 user
  단계로 `postflight.sh`를 따로 실행했다: CPUWAIT 해제, PING state 1, "card withdrawn".
- 스테이징에는 Mac tar가 만든 AppleDouble `._*` 파일 31개가 섞여 있었다. runner는 파일 이름을 지정해서 읽으므로 측정에는
  영향이 없고, 보관본에서는 제외했다.
- 대조: `stage4ao.py judge` 결과와 `runs.csv`를 독립 스크립트로 다시 계산한 값이 같다 (AO 중앙값, 기울기, 절편, workload
  sha256, output_match).

## 2. OFM Sweep 결과 (pass A 중앙값, 측정 RUN 4개)

| config | N_OFM | AO_ACTIVE (range) | N/AO | /16 | 잔차 AO − N/16 | MAC_ACTIVE | NPU_ACTIVE A / B | AO/NPU | MAC/NPU | EXT wr beat | 블록 수 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H24 | 55,296 | 3,534 (3) | 15.647 | 0.978 | 78.0 | 2,304 | 21,008 / 21,155.5 | 0.168 | 0.110 | 3,456 | 16 |
| H36 | 82,944 | 5,304.5 (8) | 15.637 | 0.977 | 120.5 | 3,456 | 30,657 / 30,611 | 0.173 | 0.113 | 5,184 | 24 |
| H54 | 124,416 | 7,953 (20) | 15.644 | 0.978 | 177.0 | 5,184 | 44,848.5 / 44,782 | 0.177 | 0.116 | 7,776 | 36 |
| H72 | 165,888 | 10,623.5 (13) | 15.615 | 0.976 | 255.5 | 6,912 | 58,635 / 58,989.5 | 0.181 | 0.118 | 10,368 | 48 |

모든 구성에서 pass A/B 일관성은 OK이고 AO range도 OK다 (`MEASUREMENT_UNSTABLE` 없음). `base_vs_h24` = SAME_WITHIN_TOL
(AO 차이 +1.0, NPU 차이 −61). base는 회귀에 넣지 않았다.

### 판정 (계약 §6, 데이터 전에 고정한 규칙)

- **RQ1 (H1)**: 기울기 1.0253 (허용 ±2 %) → **`RATE_NOT_CONSISTENT`**. 관측 처리율 15.60 elem/cycle (16의 97.5 %),
  절편 −11.7 cycle (사실상 0).
- **H2**: **`M3_ONLY`**.

| 모델 | H24 | H36 | H54 | H72 | 판정 |
|---|---:|---:|---:|---:|---|
| M1 = N/16 | +78.0 (밖) | +120.5 (밖) | +177.0 (밖) | +255.5 (밖) | NOT_CONSISTENT |
| M2 = N/16 + 79.5 | −1.5 | +41.0 | +97.5 (밖) | +176.0 (밖) | NOT_CONSISTENT |
| M3 = N/16 + 79.5 × 블록/16 | −1.5 | +1.25 | −1.9 | +17.0 | CONSISTENT |
| M4 = Vela ao_cycles | −690 | −647.5 | −591 | −512.5 | NOT_CONSISTENT |

(오차 = 실측 − 예측. "밖" = max(25, 1 %) 밖)

### 해석 범위 (계약 §0-5)

- **M3가 맞았지만 "블록당 비용"이 증명된 것은 아니다.** 이 sweep에서는 블록 수(16/24/36/48)가 N에 정확히 비례한다
  (블록당 3,456 원소). 그래서 M3는 "일정한 처리율 16/(1 + 79.5/3,456) = 15.64 elem/cycle"과 수식상 같다.
  "블록 경계마다 고정 비용"과 "지속 처리율이 16보다 약 2.3 % 낮음"은 이 데이터로 구분되지 않는다.
  M2(고정 오버헤드)는 기각됐다: 절편이 0에 가깝고, 잔차가 N에 비례한다.
- AO_ACTIVE는 SU 이용률이 아니다. N/AO가 공식 16과 2.4 % 다르다는 것은 "AO가 블록을 순회하는 사이클"이 이론 출력 사이클보다
  그만큼 길다는 뜻일 뿐이다. AO가 실행 시간의 병목이라는 결론은 내리지 않는다: AO/NPU는 0.17–0.18이다.
- OFM을 키우면 IFM 행, MAC 양 (MAC_ACTIVE = N/24, 384 MAC/cycle로 일정), DMA 양도 같이 커진다. 출력 원소 수만의 인과 효과로
  주장하지 않는다.
- 공식 문서상 후보 (원인 배정 아님): TRM §4.2 "Partial SBs might be used at block edges", "A bubble might be inserted when
  reading from the AB due to a grant delay of maximum one cycle". 출력 DMA 폭 128 bit/cycle은 INT8 16 elem/cycle과 같다.
  EXT write beat = N/16 (16 B/beat)이므로 AO 1 cycle당 0.976 beat다. DMA 쪽 대기와 SU 쪽 대기는 공식 PMU로 분리할 수 없다
  (AO stall 이벤트는 Reserved).

### 보조 관측 (POST_HOC_DESCRIPTIVE)

- NPU_ACTIVE는 N에 거의 비례한다: 이상적 AO 사이클 1당 약 5.44 NPU cycle (H24→H72).
- WD_ACTIVE 1,052 → 2,993.5, WD_STALLED 7,270 → 24,302. weight 크기는 2,752 B로 같은데 N에 따라 늘었다: 블록마다 weight를
  다시 읽는 것으로 보이며, 미검증.
- EXT rd beat 1,437 → 3,741 (IFM 24H beat + 나머지 증가). SRAM wr beat 252로 일정. SRAM rd beat 2,016 → 6,048.
- 사전 데이터와 비교: Stage 4 DW 56×56×144는 N/AO = 15.85 (0.991)로, 이번 Conv 1×1 (0.976–0.978)보다 높다.
  연산이나 블록 구성에 따라 AO 처리율이 달라질 가능성이 있다 (미검증).

## 3. Activation 비교 (Phase C) — 판정 불가 (확정: INCONCLUSIVE, §3a)

- act_none: INVALID. NPU 출력이 tflite_runtime CPU reference와 **57개 원소에서 1 LSB** 다르다. RELU6 구성은 모두 PASS_EXACT였다.
  NONE은 음수 출력을 클램프하지 않으므로, 음수 영역에서 반올림이 다를 가능성이 있다. 이것은 **미검증 가설**이다:
  출력 파일이 저장되지 않아 어느 원소가 다른지 확인할 수 없다.
- act_relu: NOT_MEASURED. judge는 측정되지 않은 config를 `INVALID`로 표기하는데, 실제 의미는 미측정이다.
- 계약 §9에 따라 재측정하지 않았다 (별도 승인 필요).

## 3a. 확정 판정과 1 LSB 불일치 원인 진단 (2026-11-15, owner 결정 후 추가)

- owner 결정 (ChatGPT 경유): **Phase C = INCONCLUSIVE**. 추가 보드 측정 없이 종료한다. 출력 검증 기준(PASS_EXACT)과 기존 결과는 바꾸지 않는다.
- 원인 진단은 보드 없이 했다 (Stage 4AO-E, `results/fi101_stage4aoe/rounding.json`, `refcheck.json`).
  1. 명령 스트림의 `NPU_SET_OFM_SCALE`: round_mode = double_symmetric (0), dbl_rnd 0, shift 40, scale 1,338,618,422.
  2. TRM §3.6 `rounded_shift_right`대로 이 값으로 출력을 에뮬레이션하면, packed golden(tflite_runtime 2.14 기본 = 최적화 커널)과
     act_none에서 **정확히 57개, 모두 NPU − golden = −1**이 다르다. 보드 관측(57개, 최대 차이 1)과 같다. RELU/RELU6에서는 0개다.
  3. 같은 입력으로 tflite_runtime **BUILTIN_REF (reference 커널)**를 돌리면 에뮬레이션과 세 구성 모두 0개 차이다.
     기본 커널 golden과는 act_none에서만 57개 다르다.
  4. 해석: 두 커널 모두 Q31 곱셈 뒤 2단계 반올림을 쓰지만, 마지막 단계에서 정확히 .5인 값을 reference/NPU는 0에서 먼 쪽으로,
     최적화 커널은 +∞ 쪽으로 보낸다. 그래서 음수 출력의 .5 경계 57곳에서만 1 LSB가 다르다 (예: −13.5 → NPU −14, golden −13).
     ReLU/ReLU6에서는 음수가 0으로 잘려 차이가 보이지 않는다.
  5. 기존 측정 workload 53개 (Stage 4·4C·4C-2·4K·4AO)의 golden은 모두 BUILTIN_REF와 바이트 동일하다. **이미 보고한 PASS_EXACT
     결과에는 영향이 없다.** 기본 커널과 reference 커널이 다른 것은 act_none, chain_conv_add, lut_tanh, lut_logistic뿐이다
     (모두 측정되지 않았거나 INVALID였던 구성).
  6. 남은 증명: NPU 출력 자체를 저장해 확인하지 않았다 (보드 출력 파일 없음). 정적 에뮬레이션과 reference 커널의 일치라는 강한
     근거이지만 보드 증거는 아니다. 출력 보존 기능을 추가했다 (`run_driver_events.py` `output_mismatch.bin`).

## 4. 파일

| 파일 | 내용 |
|---|---|
| `summary.json` | judge 결과: 재현 Gate, RQ1, H2, RQ3, base_vs_h24, 구성별 지표·모델 오차 |
| `phase_a.json`, `phase_a_table.csv` | Stage 4K AO 재분석, C0 보정, OFM 크기가 다른 기존 데이터 (POST_HOC) |
| `static.json`, `stage4ao_static.csv`, `predictions.json` | 정적 분석, 비교 가능성, 예측 (데이터 전 고정) |
| `block_scan.json`, `vela500_SUPPORTED_OPS.md` | 컴파일만 한 block 조사, Vela 지원 연산 보고서 |

명령: `python3 host/analysis/stage4ao.py judge evidence/stage4ao/raw/evsweep_s4ao_run evidence/stage4ao/workloads
results/fi101_stage4ao/predictions.json results/fi101_stage4ao s4ao_conv1x1_h24,s4ao_conv1x1_h36,s4ao_conv1x1_h54,s4ao_conv1x1_h72
s4ao_act_none,s4ao_act_relu evidence/stage4ao/raw/evsweep_s4ao/ref/wfe`
