# Stage 4AO — AO 처리율 보드 측정 계약 (**동결 2026-11-15, boot 379 전**)

초안 `contract_draft.md`(같은 날)를 대체한다. 측정 조건(모든 숫자): FI101 Ethos-U85 1024 MAC, **TA profile 1**, driver runner
이미지 `70090f1`, DDR/EXT (DRWL word 7 = 0), Vela 5.0.0 (MLEK 옵션, `config/fi101_s013.json`), pass A/B 각 warm-up 1 + 측정 4 RUN.
근거: `docs/plan/stage4ao_characterization_plan.md`. 코드: `host/analysis/stage4ao.py` (test_stage4ao 30개, mutation 43/43
KILLED), `host/container/stage4ao_models.py`.

## 0. owner 결정과 조건 (2026-11-15, ChatGPT 경유 owner 지시 "Stage 4AO — 수정안 R4 승인 및 FI101 보드 측정")

- D1: R4 채택, H = 24, 36, 54, 72. H42 제외. D2: Phase C 포함 (act_none, act_relu). D3: 기준 재현 boot와 H24를 각각 측정.
  D4: 7 boot, 최대 70 RUN.
- 초안 대비 추가된 조건:
  1. `s4_conv_base`(VALID)와 `s4ao_conv1x1_h24`(SAME)는 DRWL 바이트가 다르다 (tflite padding 필드). 명령 스트림과 CPU
     reference는 바이트 동일 → **같은 실행의 반복 측정**으로 본다. 회귀(RQ1)와 모델 판정(H2)에는 H24만 넣고 base는 넣지 않는다.
     둘의 차이는 `base_vs_h24` (SAME_WITHIN_TOL / DIFFERENT, 기술 통계)로만 보고한다.
  2. M3 블록 수 규칙을 고정 (§6). M2/M3 계수(79.5)는 측정 후 바꾸지 않는다. 79.5는 기존 측정에서 정한 값이며 하드웨어 상수로 증명된 것이 아니다.
  3. H2 판정 집합: BOTH_CONSISTENT / M2_ONLY / M3_ONLY / NEITHER (+ 개별 모델 CONSISTENT / NOT_CONSISTENT).
  4. 모든 구성의 `model_len`이 5568로 같아서, 구성 정체성에 **runs.csv `workload_sha256` = 스테이징 DRWL sha256 (모든 행)**을 추가했다.
  5. 해석 범위: OFM 크기를 바꾸면 MAC 수와 DMA 양도 같이 변한다. AO_ACTIVE의 변화를 출력 원소 수만의 인과 효과로 주장하지 않는다.
     AO_ACTIVE는 SU 이용률이 아니며, AO가 실행 시간의 병목이라는 결론을 내리지 않는다.

## 1. 대상 (고정, 실행 중 추가·삭제·순서 변경 없음)

| boot | config | 그룹 | N_OFM | DRWL sha256 |
|---:|---|---|---:|---|
| 379 | `s4_conv_base` | A 재현 Gate (Stage 4K boot 369와 같은 blob) | 55,296 | `2681c566729ce568f4041df6a69d1b5c5c558d2172bb76b6d75ad64ca2b4f267` |
| 380 | `s4ao_conv1x1_h24` | B sweep, C 기준 (RELU6) | 55,296 | `bee0fbcb34fe569174115948da8ff7caef62eeb63f5cf479e71082386f9c087f` |
| 381 | `s4ao_conv1x1_h36` | B | 82,944 | `da5b904905a2dbe07b4dc6060f9e7e05a642640f0a154132cdfc791e726138fe` |
| 382 | `s4ao_conv1x1_h54` | B | 124,416 | `c0f9255f956d2ee7abae0f692d14278ff2ce82bc40ab5256d17645071887e330` |
| 383 | `s4ao_conv1x1_h72` | B | 165,888 | `aa591b53843b9b81845a6e8901dfbca3bb71db67a3604635f6ce4354023c34e8` |
| 384 | `s4ao_act_none` | C | 55,296 | `863dabc1e33694727516c42daddf56493bdfa266bf8075873c673c9dd3cfa5e2` |
| 385 | `s4ao_act_relu` | C | 55,296 | `4af4c41a3d1c6c9303deacf58f6a749ecd19b8915eff2c8f2f07aea6da252d99` |

boot 379–385는 사용된 적이 없다 (확인 2026-11-15: Mac evidence와 보드 `runs.csv`의 최대 `host_boot_index` = 378).

정적 확인 (`results/fi101_stage4ao/static.json`, `phase_b_revision` = COMPARABLE):
- Group B 네 구성: PartKernel, OFM block 6×12×96, IFM block 6×12×16, ublock 2×2×32, 커널 2개 (OFM slice 16 + 80), OFM INT8,
  weight·bias·scale 동일, CPU fallback 없음, Gate B PASS.
- Group C: 기준과의 명령 차이는 `NPU_SET_ACTIVATION_MIN/MAX`뿐 (`phase_c` selected = true). 추가 커널, block 변경, scale 변경, CPU fallback은 없다.
- 용량: fast scratch 4,032 B (보드 fast 393,216 B), arena 최대 193,536 B (runner arena 2 MiB), DRWL 최대 199,184 B,
  IFM·OFM 각 1개 (DRWL_IO_MAX 8), 출력 최대 165,888 B (GET_OUTPUT 4000 B 단위). **새 이미지·driver 변경 불필요.**

## 2. 이미지·워크로드 SHA-256

- 이미지 `70090f1`: boot `718c4562…ef59`, bram `c80e77df…e99c`, ddr `374708ff…37bb`, images.txt `af688281…423f`
  (전체 값은 `contract_draft.md` §2). 스테이징은 보드 `~/evsweep_s4k`의 같은 파일을 복사하고 sha256으로 대조한다.
- 워크로드: §1 DRWL과 각 `compile.json`, `drwl.tflite_ofm.bin` (전체 목록 `evidence/stage4ao/workloads.sha256`).
  Mac, 컨테이너 빌드, 보드 스테이징의 sha256이 같아야 한다.

## 3. Group A 재현 Gate (boot 379 직후, `stage4ao.py repro-gate <run> <staging> <staging>/ref/wfe`)

- 기준: Stage 4K boot 369 `s4_conv_base` (보드 `~/evsweep_s4k_run/conds/s4_conv_base`의 사본 = 스테이징 `ref/`; 그 안의
  `capabilities.json`이 정체성 기준).
- 검사: `K.reproduce` (MAC_ACTIVE·MAC_DPU_ACTIVE 모든 RUN 동일, 출력 sha256 동일, 상수 카운터 동일, NPU_ACTIVE |차이| ≤
  max(1 %, ranges)), 그리고 **AO_ACTIVE |차이| ≤ 35.4** (= max(25, 1 % × 3,540.5)).
- FAIL이면 세션을 즉시 멈춘다. 나머지 구성은 `NOT_MEASURED`, RQ는 `NOT_INTERPRETED`.

## 4. 구성별 Gate (boot마다, `stage4ao.py boot-check <run> <staging> <config> <staging>/ref/capabilities.json`)

VALID는 다음을 모두 만족할 때만이다.
- pass A/B 각 측정 4 RUN이 모두 valid.
- `K.identity`: RUN 10개, model 길이, schema 4, placement 0, REGIONCFG 0x15F / QCONFIG 3, IRQ 1회, warm-up 포함 CRC 1개, 출력 길이, capabilities = 기준.
- `workload_sha256`: 모든 행 = 해당 DRWL.
- 출력 **PASS_EXACT**.

하나라도 실패하면 INVALID → 세션 중단 (§8).

## 5. PMU와 Pass 일관성

- Pass A: 35, 48, 51, 53, 55, 64, 80, 81. Pass B: 35, 128, 130, 132, 135, 384, 386, 391. Memory stall Pass C는 넣지 않는다.
- 53, 55, AO stall 67–72는 Reserved이므로 결론의 근거로 쓰지 않는다.
- `MEASUREMENT_UNSTABLE` 조건 (둘 중 하나): AO_ACTIVE range > max(50, 2 % × 중앙값), 또는 |B_35 − A_35| > max(5 % × A_35, rangeA + rangeB).

## 6. 예측 모델 (동결, `results/fi101_stage4ao/predictions.json`)

- M1 = N/16. M2 = N/16 + 79.5. M3 = N/16 + 79.5 × (블록 수 / 16). M4 = Vela `ao_cycles`.
- **블록 수 규칙**: 컴파일된 명령 스트림의 커널마다 ⌈H / block_h⌉ × ⌈W / block_w⌉ × ⌈커널 OFM slice 깊이 / block_c⌉를 구해
  모든 커널에 대해 더한다 (`cms_regs.kernels`, Vela OFM block 6×12×96). H24 = 16, H36 = 24, H54 = 36, H72 = 48.

| config | M1 | M2 | M3 | M4 | 허용폭 (M2 기준) |
|---|---:|---:|---:|---:|---:|
| H24 | 3,456 | 3,535.5 | 3,535.5 | 4,224 | 35.4 |
| H36 | 5,184 | 5,263.5 | 5,303.25 | 5,952 | 52.6 |
| H54 | 7,776 | 7,855.5 | 7,954.875 | 8,544 | 78.6 |
| H72 | 10,368 | 10,447.5 | 10,606.5 | 11,136 | 104.5 |

- 구성별 일치: |AO − 예측| ≤ max(25, 1 % × 예측) (예측마다 따로 계산).
- **RQ1 (H1)**: valid하고 비교 가능한 sweep 구성 (≥ 3)의 AO 중앙값을 N/16에 OLS 회귀한다. |기울기 − 1| ≤ 2 %이면
  `RATE_CONSISTENT`, 아니면 `RATE_NOT_CONSISTENT`.
  판정 순서: 재현 Gate → INVALID (valid 구성 < 3) → MEASUREMENT_UNSTABLE → SCHEDULE_CONFOUNDED → RATE_*.
- **H2** (RQ1이 RATE_* 일 때만): 같은 구성들에서 모든 구성이 허용폭 안이면 그 모델은 CONSISTENT.
  M2/M3 조합 → BOTH_CONSISTENT / M2_ONLY / M3_ONLY / NEITHER. 이외에는 NOT_JUDGED.
  M3가 맞아도 블록 경계 비용의 내부 원인은 증명된 것이 아니다.
- **RQ3 (H3)**: act_none, act_relu 각각 H24 (RELU6)와 비교한다. |ΔAO| ≤ max(25, 1 % × AO_H24)이면 `RATE_CONSISTENT`, 아니면
  `RATE_NOT_CONSISTENT`, 그 밖에 INVALID / MEASUREMENT_UNSTABLE. NPU_ACTIVE도 같이 보고한다 (기술 통계).
- 사후 지표는 `POST_HOC_DESCRIPTIVE`로 표시한다. 결과를 본 뒤 허용폭, 모델, 대상을 바꾸지 않는다.

## 7. 실행 (sudo 세션 1회, `evidence/stage4ao/board/session.txt`)

- 순서는 §1 boot 379→385. boot마다 plan 파일 하나 (`run_driver_campaign.sh … 5`, `OUTPUTS=1 STOP_ON_INVALID=1`)를 실행하고 바로 boot-check를 돈다.
  boot 379 뒤에는 repro-gate를 돈다.
- `board/sudo_session.sh`는 한 줄 = 한 단계이며, 실패하면 남은 단계를 건너뛰고 카드를 복원한다. 암호는 main worktree `.env`에서 파이프로만 넘기고,
  출력·저장하지 않는다.
- 스테이징 `~/evsweep_s4ao`: 이미지 4개 파일, §1 워크로드, conditions/ids (Stage 4K와 동일), plan 7개, `ref/`.
  보드 코드 `~/evsweep/host/analysis/stage4ao.py`의 sha256을 대조한다.
- 실행 전 G0: 위 sha256 대조, 보드에서 gate 명령 dry run (Stage 4K boot 369 데이터로 boot-check PASS, repro-gate PASS,
  미측정 config FAIL), `sudo_session.sh --check`, 카드 미마운트, m6 복원 기준 존재.

## 8. Fail-fast

boot-check FAIL, repro-gate FAIL, runner refusal, NPU fault, 보드 무응답, 배포 실패, sha256 불일치, 설정 불일치 중 하나라도
생기면 즉시 중단하고 카드를 복원한다. 결과 수치로는 중단하지 않는다.

## 9. 실패·불확실 결과 처리 (사전 정의)

| 결과 | 처리 |
|---|---|
| 재현 Gate FAIL | 해석하지 않는다. 원인 조사는 별도 승인 |
| INVALID 구성 | 재측정하지 않는다 (별도 승인). valid 구성이 3개 이상이면 RQ1을 판정한다 |
| MEASUREMENT_UNSTABLE | 보고만 한다. 추가 RUN은 owner 승인 |
| SCHEDULE_CONFOUNDED | 처리율 결론 없이 기술 통계만 낸다 |
| RATE_NOT_CONSISTENT | 관측 처리율과 절편을 보고한다. 원인은 배정하지 않는다 |
| H2 NEITHER 또는 BOTH | 그대로 보고한다 (BOTH = 구분 안 됨) |

## 10. 원시 데이터 보존과 복원

- `~/evsweep_s4ao_run`, 스테이징, 세션 로그를 Mac `evidence/stage4ao/raw/`로 가져오고 `raw.sha256`을 남긴다.
- 세션 끝: `restore_mlek` (m6 digest가 이전 복원과 같은지 확인) → `postflight.sh` (PING state 1) → 카드 분리 확인.
  `USB_OFF`는 카드가 마운트되지 않았을 때만.
- 이번 범위 밖: INT16 패커 수정, LUT·Elementwise·CB 측정, WD 실험, Transformer, push.
