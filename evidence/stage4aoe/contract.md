# Stage 4AO-E — Elementwise·CB AO 처리율 보드 측정 계약 (**동결 2026-11-15, boot 386 전**)

초안 `contract_draft.md`(같은 날)를 대체한다.

> **개정 A1 (2026-11-15, 세션 1 이후)**: 정체성 REGIONCFG 규칙을 바꾼 재측정 계약은 `contract_a1.md`. 이 문서와 세션 1 (boot 386–387) 판정은 그대로 둔다.

측정 조건 (모든 숫자): FI101 Ethos-U85 1024 MAC, **TA profile 1**, driver runner
이미지 `70090f1`, DDR/EXT (DRWL word 7 = 0), Vela 5.0.0 (MLEK 옵션), pass A/B 각 warm-up 1 + 측정 4 RUN.
근거: `docs/plan/stage4aoe_characterization_plan.md`. 코드: `host/analysis/stage4aoe.py` (test_stage4aoe 16개, 시뮬레이터 34개),
`host/container/stage4aoe_models.py`, `host/board/run_driver_events.py` (출력 보존). mutation 45/45 KILLED.

## 0. owner 결정 (2026-11-15, ChatGPT 경유 owner 지시 "Stage 4AO-E — 보드 측정 계약 승인 및 실행")

- E1 승인: 8 boot / 최대 80 RUN. E2: 이번 측정은 SELECTED 7개만 한다. conv_add, tanh, logistic, act_none은 제외한다 (golden 규칙은
  NPU 출력 보존과 후속 검증을 거쳐 별도 계약에서 정한다). E3 승인: 출력 불일치 보존 기능을 적용한다.
- 동결 때 더한 조건:
  1. 출력 불일치 기록 (`output_mismatch.json`): workload sha256, boot, set·rep, 출력 CRC·sha256, golden CRC·sha256, firmware 불일치
     수·최대 차이, 호스트 int8 비교 (수, 최대 |차이|, 처음 256개의 (위치, NPU, golden)). 출력 수집은 RUN이 끝나고 PMU 기록이
     읽힌 뒤에만 한다 (측정 창 밖). 보존 후에도 fail-fast이며, 실패한 구성을 재실행하거나 다음 구성으로 넘어가지 않는다.
  2. 정상 경로 불변의 사전 검증: 시뮬레이터 `test_campaign_normal_path_unchanged` (출력 일치 시 mismatch 파일 없음, output.bin
     동일, 출력 전송은 마지막 RUN 뒤 1회), `test_stop_on_invalid` (출력이 맞는 invalid RUN에서는 보존 없음).
  3. RQ2 판정 구간 (겹치지 않음): NOMINAL_16 = [15.84, 16.16], CONV_LIKE = [15.449, 15.761] (15.605 × 0.99–1.01),
     BETWEEN = (15.761, 15.84), BELOW_CONV < 15.449, ABOVE_NOMINAL > 16.16. ABOVE_NOMINAL이 나와도 SU의 물리적 최대를
     넘었다고 단정하지 않는다.
  4. H24·H72는 각각 block이 하나지만 block 형상은 다르다 (24×42×96 / 72×42×96). 비례가 성립해도 이 Elementwise 구성의 관측으로만
     보고하고, block 경계 비용의 일반 법칙으로 확정하지 않는다.
  5. ADD→MUL: 최종 OFM 기준 (N/AO)과 논리 원소 기준 (2N/AO)을 모두 보고한다. 비체인 대조군이 없으므로 CB의 인과적 성능 효과는
     주장하지 않는다.
  6. boot 385는 Stage 4AO 계획 번호였으나 실행되지 않았다. 혼동을 피하려고 쓰지 않는다. 확인 결과 마지막으로 사용된 번호는 384다.

## 1. 대상 (고정 순서, 실행 중 추가·삭제·순서 변경 없음)

| 순서 | config | 역할 | 논리 AO 원소 | DRWL sha256 |
|---:|---|---|---:|---|
| 1 | `s4ao_conv1x1_h24` | 재현 Gate (Stage 4AO boot 380과 같은 blob) | 55,296 | `bee0fbcb34fe569174115948da8ff7caef62eeb63f5cf479e71082386f9c087f` |
| 2 | `s4aoe_add_h24` | A, binary | 55,296 | `dfbe74f3d5c579acc280411868546572f617cbcb500dacfea86d66edd381c0ce` |
| 3 | `s4aoe_mul_h24` | A, binary | 55,296 | `3a96dd083afe7564fb84ffce35d5b553384bb40e2fd7cce1b7877202eff66b0c` |
| 4 | `s4aoe_abs_h24` | A, unary | 55,296 | `66e138cc0cbb390aefeb1ce68c635492903b3af50b319576f7a6261c0f12bbf6` |
| 5 | `s4aoe_add_mul_h24` | B, CB 체인 | 110,592 | `c3eab559eaf1912d1415b31d96d3c0fafbb7272433f86b31949a49854e5556de` |
| 6 | `s4aoe_add_h72` | A | 165,888 | `be981ef6916fa19a7c20e4914199ce5e2a25c36bf2d7e97b4a11d51d4846082c` |
| 7 | `s4aoe_mul_h72` | A | 165,888 | `16c238a2178a5005beda65b1e30caaaee45dcfe0349fdd6d38bc02bba84e26b8` |
| 8 | `s4aoe_abs_h72` | A | 165,888 | `e5d5ed2051ced7ba87028a64070bf9cbcaf6a56918658c8772389d56ed94c2e0` |

- boot 번호: **386–393** (순서 1–8).
- 선정 규칙과 결과는 계획서 §5에 있다. NEEDS_GOLDEN_RULE 후보는 이 계약에 넣지 않는다.
- golden: 모든 대상에서 기본 커널과 BUILTIN_REF 출력이 바이트 동일하다. DRWL golden = BUILTIN_REF 출력 (= 기본 커널 출력).

## 2. 이미지·워크로드 SHA-256

- 이미지 `70090f1` (Stage 4K/4AO와 같음): boot `718c4562…ef59`, bram `c80e77df…e99c`, ddr `374708ff…37bb`, images.txt `af688281…423f`.
- 워크로드: §1의 DRWL, `drwl.tflite_ofm.bin`, `ref_ofm.bin`. 재현 boot용으로 4AO의 `s4ao_conv1x1_h24.compile.json`.
  전체 목록: `evidence/stage4aoe/workloads.sha256`, `evidence/stage4ao/workloads.sha256`.
- runner 펌웨어는 바꾸지 않는다. 보드 호스트 스크립트 `run_driver_events.py`만 E3에 따라 바뀐다 (sha256 대조).

## 3. 재현 Gate (boot 1, `stage4aoe.py repro-gate <run> <staging> <staging>/ref/wfe <staging>/ref/capabilities.json`)

- 기준: Stage 4AO boot 380 (`evidence/stage4ao/raw/evsweep_s4ao_run/conds/s4ao_conv1x1_h24`의 사본).
- 검사:
  - `stage4ao.config_result` VALID: identity, workload sha256, PASS_EXACT.
  - `K.reproduce`: MAC, DPU, 출력 sha, 상수 카운터, NPU_ACTIVE max(1 %, ranges).
  - AO_ACTIVE |차이| ≤ max(25, 1 % × 3,534) = 35.34.
- FAIL이면 즉시 중단한다.

## 4. 구성별 Gate (`stage4aoe.py boot-check`)

다음을 모두 만족해야 VALID다.
- pass A/B 각 측정 4 RUN이 모두 valid.
- `K.identity`.
- workload_sha256 (모든 행).
- `output.bin` = DRWL golden (바이트 동일), 모든 행 `output_match` 1, `ofm_mismatch` 0.

하나라도 실패하면 즉시 중단한다. 출력 불일치였다면 `output_mismatch.bin`이 남는다 (E3).

## 5. PMU와 일관성

- Pass A 35, 48, 51, 53, 55, 64, 80, 81. Pass B 35, 128, 130, 132, 135, 384, 386, 391. 53, 55, AO stall 이벤트는 Reserved이므로 해석하지 않는다.
- `MEASUREMENT_UNSTABLE`: AO range > max(50, 2 %), 또는 |B_35 − A_35| > max(5 %, rangeA + rangeB).

## 6. 판정 (데이터 전 고정, `results/fi101_stage4aoe/predictions.json`)

- 관측 처리율 q = 논리 AO 원소 / AO_ACTIVE (CB 체인은 2N으로 나눈다). 최종 OFM 기준 값도 함께 보고한다.
- RQ2 (구성별): NOMINAL_16 (|q/16 − 1| ≤ 1 %), CONV_LIKE (|q/15.605 − 1| ≤ 1 %), BETWEEN, BELOW_CONV, ABOVE_NOMINAL,
  그 밖에 INVALID / MEASUREMENT_UNSTABLE / NOT_MEASURED.
  - 1 %의 근거: Stage 4AO Conv의 q 폭 15.615–15.647 (0.2 %), 두 기준값의 차이 2.5 % (범위가 겹치지 않음).
- RQ1 (연산별): AO(H72)/AO(H24)가 3의 ±2 % 이내이면 PROPORTIONAL, 아니면 NOT_PROPORTIONAL. 기울기와 절편을 보고한다.
  H24와 H72의 block 수는 모두 1이므로, PROPORTIONAL과 절편 ≈ 0이면 "블록당 비용"이 아니라 처리율 자체로 설명된다 (이 경로에 한해).
- Unary와 Binary (ABS 대 ADD/MUL), 체인 (add_mul 대 add_h24 + mul_h24): 기술 통계로만 비교한다 (사전 판정 없음, POST_HOC_DESCRIPTIVE로 표시).
- 해석 제한: IFM 수와 DMA 양이 다르므로 NPU_ACTIVE 차이를 AO 산술 비용으로 보지 않는다. AO_ACTIVE는 SU 점유율이 아니다.
  AO가 병목이라는 결론은 내리지 않는다.

## 7. 실행

- sudo 세션 1회 (Stage 4AO와 같은 구조: boot마다 plan 하나 → boot-check; boot 1 뒤에 repro-gate).
  암호는 main worktree `.env`에서 파이프로만 넘긴다.
- 스테이징 `~/evsweep_s4aoe`: 이미지 4개 파일, §1·§2 파일, conditions/ids (Stage 4K와 같음), plan 8개, `ref/` (4AO boot 380 사본).
  Mac에서 tar로 보낼 때 `COPYFILE_DISABLE=1`로 AppleDouble 파일을 막는다.
- G0: sha256 대조 (스테이징, 이미지, 보드 코드: stage4aoe·stage4ao·stage4k·stage4·stage4c1·stage4c2·run_driver_events·lib),
  보드에서 gate dry run (4AO boot 380 데이터로 repro-gate PASS, boot-check PASS, 미측정 config FAIL), `sudo_session.sh --check`,
  카드 미마운트, m6 복원 기준 존재, boot 번호 미사용.

## 8. Fail-fast

boot-check FAIL, repro-gate FAIL, runner refusal, NPU fault, 무응답, 배포 실패, sha256 불일치 중 하나라도 생기면 즉시 중단하고 복원한다.
**세션이 실패 경로로 끝나면 postflight를 user 단계로 따로 실행한다** (Stage 4AO 교훈).

## 9. 실패·불확실 결과 처리

| 결과 | 처리 |
|---|---|
| 재현 Gate FAIL | 해석하지 않는다 |
| INVALID (출력 불일치 포함) | 재측정하지 않는다. `output_mismatch.bin`으로 원인을 분석해 보고한다 (golden 변경 금지) |
| MEASUREMENT_UNSTABLE | 보고만 한다. 추가 RUN은 owner 승인 |
| NOT_PROPORTIONAL / BETWEEN 등 | 관측값을 보고하고 원인은 배정하지 않는다 |

## 10. 원시 데이터와 복원

원시 데이터를 Mac `evidence/stage4aoe/raw/`로 가져오고 `raw.sha256`을 남긴다 (`._*` 제외).
restore_mlek → m6 digest가 이전과 같은지 확인 → postflight (PING state 1, 카드 분리). push는 하지 않는다.
