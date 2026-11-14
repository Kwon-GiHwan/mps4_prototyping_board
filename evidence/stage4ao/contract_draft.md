# Stage 4AO — AO 처리율 보드 측정 계약 **초안** (동결 전, 2026-11-15)

이 문서는 초안입니다. 동결은 owner 승인 뒤에 하며, 그때 개정 기록을 남깁니다.
측정 조건(모든 숫자에 적용): FI101 Ethos-U85 1024 MAC, **TA profile 1**, driver runner 이미지 `70090f1`, DDR/EXT 배치
(DRWL word 7 = 0), Vela 5.0.0(MLEK 옵션, `config/fi101_s013.json`), `config/driver_r5.json` 규칙(pass A/B, pass마다
warm-up 1 + 측정 4 RUN).
근거 문서: `docs/plan/stage4ao_characterization_plan.md`. 분석 코드: `host/analysis/stage4ao.py`
(테스트 27개, mutation 35/35 KILLED). 생성기: `host/container/stage4ao_models.py`.

## 0. owner 결정이 필요한 항목 (동결 전)

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| D1 | Phase B 대상 | (a) 지시 원안 H 12/24/36/48: 정적 판정 `NEEDS_REVISION`. 비교 가능 2개뿐이라 RQ1은 미리 `SCHEDULE_CONFOUNDED`가 확정됩니다. (b) **수정안 R4: H 24/36/54/72** (모두 6×12×96 block, N 55,296–165,888). (c) R5: R4 + H42 | **(b) R4.** 원안과 같은 4개이고, M2와 M3가 54와 72에서 갈립니다 |
| D2 | Phase C 그룹 포함 | 사전 선정 규칙(§1.2)을 정적 단계에서 이미 통과. 포함하면 2 boot, 20 RUN이 늘어납니다 | 포함 |
| D3 | 24×24 기준 이중 측정 | boot 1 = Stage 4K blob `s4_conv_base`(VALID, 재현 Gate), sweep의 24×24 = `s4ao_conv1x1_h24`(SAME, 명령 스트림 동일) | 둘 다 측정 |
| D4 | RUN 총량 | D1(b)+D2+D3: 7 boot × 10 RUN = **70 RUN** | — |

이하 본문은 D1(b), D2 포함, D3을 가정하고 씁니다. 다른 선택을 하면 §1, §2, §6의 해당 행만 바뀝니다.

## 1. 최종 대상과 고정 선정 기준

### 1.1 대상 (D1(b) 기준; 생성 규칙은 계획서 §3)

| 순서 | config | 역할 | N_OFM | DRWL sha256 |
|---:|---|---|---:|---|
| 1 | `s4_conv_base` | 재현 Gate (Stage 4K boot 369와 같은 blob) | 55,296 | `2681c566729ce568f4041df6a69d1b5c5c558d2172bb76b6d75ad64ca2b4f267` |
| 2 | `s4ao_conv1x1_h24` | Phase B, Phase C 기준 (RELU6) | 55,296 | `bee0fbcb34fe569174115948da8ff7caef62eeb63f5cf479e71082386f9c087f` |
| 3 | `s4ao_conv1x1_h36` | Phase B | 82,944 | `da5b904905a2dbe07b4dc6060f9e7e05a642640f0a154132cdfc791e726138fe` |
| 4 | `s4ao_conv1x1_h54` | Phase B | 124,416 | `c0f9255f956d2ee7abae0f692d14278ff2ce82bc40ab5256d17645071887e330` |
| 5 | `s4ao_conv1x1_h72` | Phase B | 165,888 | `aa591b53843b9b81845a6e8901dfbca3bb71db67a3604635f6ce4354023c34e8` |
| 6 | `s4ao_act_none` | Phase C | 55,296 | `863dabc1e33694727516c42daddf56493bdfa266bf8075873c673c9dd3cfa5e2` |
| 7 | `s4ao_act_relu` | Phase C | 55,296 | `4af4c41a3d1c6c9303deacf58f6a749ecd19b8915eff2c8f2f07aea6da252d99` |

참고용(D1 (a)/(c)): h12 `2ec49bda…`, h42 `1d29d69b…`, h48 `d7f00d63…`. 전체 sha256은 `evidence/stage4ao/workloads.sha256`
(130개 파일)에 있습니다.

### 1.2 고정 선정 기준 (데이터 전)

- Phase B 비교 가능: 기준(24×24)과 traversal, OFM·IFM block, ublock, 커널 수와 OFM slice, OFM 정밀도가 같고 Gate B가
  PASS여야 합니다. 3개 이상이면 `COMPARABLE`, 아니면 `NEEDS_REVISION`입니다(`stage4ao.comparable`).
- Phase C 포함: Gate B PASS, 기준과 같은 signature, 명령 수와 순서가 같은 스트림, `NPU_SET_ACTIVATION_MIN/MAX`
  (294/295) 외에 다른 명령 값이 없음, weight stream 길이가 같음(`stage4ao.phase_c_select`). 현재 두 구성 모두 통과.
- 측정 중에는 후보를 추가하거나 제거하지 않고 순서도 바꾸지 않습니다. LUT, INT16, Elementwise, CB 경로는 이 계약의
  대상이 아닙니다(Phase D는 정적 조사만).

## 2. Workload·Firmware SHA-256

- 이미지 `70090f1`(Stage 4K와 같음):
  - boot `718c456283bfd44863d5fb697360b680ff4dc6b297cc0dc74d7ed78a6ca7ef59`
  - bram `c80e77df9fe14b908966a5cebc5045cca93c5fd98bcea50fb1a7aef35f9fe99c`
  - ddr `374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb`
  - images.txt `af688281435a73dda3b2247845149817ecc7a9bbdff5a3ccd2e4dfa52875423f`
- Runner 코드 변경은 없습니다. Phase B·C는 모두 IFM 1개, OFM 1개입니다. 출력은 최대 165,888 B로,
  `OUTPUT_GET_MAX_BYTES` 4000 단위로 분할 전송됩니다(Stage 4 DW에서는 451,584 B 전송 경험이 있음).
  arena는 최대 193,536 B로 2 MiB 안입니다.
- DRWL은 §1.1의 sha256을 씁니다. 동결 전에 Mac, 컨테이너, 보드 staging에서 sha256이 같은지 확인합니다.

## 3. 기준 Stage 4K 재현 Gate (boot 1)

`stage4ao.py repro-gate <root> <wl>`: `s4_conv_base`를 Stage 4K boot 369와 비교합니다.
- Stage 4K `K.reproduce`: MAC_ACTIVE와 MAC_DPU_ACTIVE가 모든 RUN에서 같음, 출력 sha256이 같음, 상수 카운터가 같음,
  NPU_ACTIVE 차이가 max(1 %, ranges) 이내.
- **AO_ACTIVE |차이| ≤ max(25, 1 % × 3,540.5) = 35.4.**
- FAIL이면 세션을 즉시 멈춥니다. 나머지 구성은 `NOT_MEASURED`로 남고 RQ 판정은 `NOT_INTERPRETED`입니다.

## 4. 구성별 실행과 출력 유효성 Gate (boot마다, `stage4ao.py boot-check`)

다음을 모두 만족해야 `VALID`입니다(`config_result`).
- pass A/B 각각 측정 RUN 4개가 모두 valid.
- `K.identity`: RUN 10개, model 길이, schema 4, placement 0, REGIONCFG 0x15F / QCONFIG 3, IRQ 1회, warm-up을 포함해
  CRC가 하나, 출력 길이, capabilities가 기준과 같음.
- 출력이 CPU reference와 바이트 단위로 같음(**PASS_EXACT만 인정**).

하나라도 어기면 `INVALID`이고 세션을 멈춥니다(§8).

## 5. PMU 카운터와 Pass 일관성

- Pass A: 35, 48, 51, 53, 55, 64, 80, 81 / Pass B: 35, 128, 130, 132, 135, 384, 386, 391 (`config/fi101_passes.txt`).
- 53, 55와 AO stall(67–72)은 TRM에서 Reserved입니다. 보고만 하고 결론의 근거로 쓰지 않습니다. AO stall 이벤트는 측정하지 않습니다.
- `MEASUREMENT_UNSTABLE` 조건:
  - pass A AO_ACTIVE range > max(50, 2 % × 중앙값). 기존 최대는 50(3×3 Cin48)입니다.
  - 또는 pass A/B NPU_ACTIVE 중앙값 차이 > max(5 % × A, rangeA + rangeB). Stage 4K 최대는 2.85 %입니다.

## 6. 측정 순서와 Boot 구성

- 고정 순서: §1.1의 1→7. boot 번호는 379–385로 예정하며, 동결 때 마지막 boot 번호로 확정합니다.
- boot마다 구성 하나, plan 파일 하나를 씁니다. 각 boot 뒤에 `boot-check`, boot 1 뒤에 `repro-gate`를 둡니다.
- 승인된 sudo 세션 파일 1개를 한 번만 실행합니다(`board/sudo_session.sh`, Stage 4K와 같은 구조).
  암호는 main worktree의 `.env`에서 파이프로만 넘기고, 출력하거나 저장하지 않습니다.
- staging에는 다음을 둡니다: §1.1 DRWL, `host/`, `config/`, `docs/reference/`, Stage 4K boot 369 `wfe` 폴더와
  `capabilities.json`(재현 기준). 모두 sha256으로 대조합니다.

## 7. 예측 모델과 허용 오차 (데이터 전 고정, `results/fi101_stage4ao/predictions.json`)

- 모델 M1–M4는 계획서 §6과 같습니다. C0 = 79.5(같은 blob 5개 boot의 AO 중앙값에서 3,456을 뺀 값의 중앙값).
- 구성별 일치: |AO − 예측| ≤ max(25, 1 % × 예측).
  - 25의 근거: 1×1 PartKernel의 기존 최대 RUN range(25, Cin64 boot 377).
  - 1 %의 근거: Stage 4 pair rule의 하한과 같음.
- **RQ1 처리율 판정** (`rate_verdict`, 닫힌 집합). 비교 가능하고 valid인 구성에서 AO_ACTIVE를 N_OFM/16에 대해 OLS 회귀합니다.
  - 기울기 b가 |b − 1| ≤ 2 %이면 `RATE_CONSISTENT`(관측 처리율 16/b), 아니면 `RATE_NOT_CONSISTENT`.
  - 2 %의 근거: 점별 오차 ±25 cycle이 이상적 사이클 범위(R4는 6,912)에서 만드는 기울기 오차는 최대 약 0.7 %이고,
    여기에 boot 사이 변동(같은 blob 중앙값 폭 7)을 더해 여유를 두었습니다.
  - valid 구성이 3개 미만이면 `INVALID`.
  - 불안정한 구성이 있으면 `MEASUREMENT_UNSTABLE`.
  - 비교 가능하고 valid인 구성이 3개 미만이면 `SCHEDULE_CONFOUNDED`.
- **M2 대 M3**: 54·72에서 각 모델의 허용폭 안/밖을 보고합니다. 둘 다 안이거나 둘 다 밖이면 "구분 안 됨"입니다.
- **RQ3 (Phase C)** (`act_verdict`): |AO − AO(RELU6)| ≤ max(25, 1 %)이면 `RATE_CONSISTENT`, 아니면 `RATE_NOT_CONSISTENT`.
  무효이면 `INVALID`, 불안정하면 `MEASUREMENT_UNSTABLE`.
- 판정 순서: 재현 Gate → INVALID → MEASUREMENT_UNSTABLE → SCHEDULE_CONFOUNDED → RATE_*.
- 결과를 본 뒤 허용폭, 모델, 대상을 바꾸지 않습니다. 사후 지표는 `POST_HOC_DESCRIPTIVE`로 표기합니다.

## 8. Fail-fast 중단 조건

- boot-check FAIL(INVALID, PASS_EXACT 아님, 정체성 불일치) → 즉시 멈추고 카드를 복원합니다.
- 재현 Gate FAIL → 즉시 멈춥니다.
- runner refusal, 보드 무응답, 배포 실패, sha256 불일치 → 즉시 멈춥니다.
- 결과 수치(AO 값, 모델 불일치)로는 멈추지 않습니다. 판정은 끝난 뒤에 합니다.

## 9. 실패와 불확실한 결과의 처리 (사전 정의)

| 결과 | 처리 |
|---|---|
| 재현 Gate FAIL | 이 계약 범위의 결과는 해석하지 않습니다. 원인 조사는 별도 승인을 받습니다 |
| `INVALID` 구성 | 재측정하지 않습니다(재측정은 별도 승인). 남은 valid 구성이 3개 이상이면 RQ1을 판정합니다 |
| `MEASUREMENT_UNSTABLE` | 해당 구성만 `config/driver_r5.json` 규칙에 따라 5 RUN 추가가 가능하지만, 이 초안에서는 **추가하지 않고 보고만** 합니다(추가는 owner 승인) |
| `SCHEDULE_CONFOUNDED` | 처리율은 결론 내지 않습니다. 블록별 기술 통계만 냅니다 |
| `RATE_NOT_CONSISTENT` | 관측 처리율과 절편을 보고합니다. 원인을 배정하지 않습니다(16 채널 단위 올림, 블록 경계 등은 가설로만) |
| M2와 M3 구분 안 됨 | "구분 안 됨"으로 보고합니다 |

## 10. 원시 데이터 보존과 m6 복원

- 원시 데이터 `evsweep_s4ao_run`과 staging 전체를 Mac `evidence/stage4ao/raw/`로 옮기고 sha256 목록(`raw.sha256`)을 남깁니다.
- 세션 마지막: `restore_mlek` → m6 digest가 이전 복원과 같은지 확인 → `postflight.sh` PING state 1 → 카드 분리 확인.
- `USB_OFF`는 카드가 마운트되지 않았을 때만 실행합니다.

## 11. 이번 계약 밖: INT16, Elementwise 측정에 필요한 변경 (보고만 함)

- INT16 Conv: Vela 컴파일은 되지만 `pack_vela_workload.py`의 DRWL 검증에서 길이 0인 section이 `misplaced`로 거부됩니다.
  `host/lib/drwl.py`의 section 검증이나 패킹 순서를 바꿔야 합니다. 이 패커는 기존 모든 blob을 만드는 공통 경로이므로,
  변경 전에 기존 DRWL을 바이트 단위로 다시 만들어 확인해야 합니다.
- ADD, MUL, 체인(IFM 2–3개): 패킹은 성공합니다(DRWL_IO_MAX 8). runner 변경 없이 가능할 것으로 보이지만, 보드에서
  확인한 적은 없습니다.
