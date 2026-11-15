# Stage 6B Revision A — Amendment B 결과 (보드 측정 없음)

조건: 정적 컴파일·CPU reference만 사용했다. 보드 RUN은 없다. 보드 계약의 TA 조건은 TA profile 1이다. Vela 5.0.0, MLEK 옵션
(`Ethos_U85_SYS_DRAM_Mid_1024`, Dedicated_Sram)으로 컴파일했다. 계약은 `evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md`(`62da843`)이다.

세 결과를 구분한다.

| 결과 | 무엇 | 판정 |
| --- | --- | --- |
| **Original Contract Result** | `37b6268` 계약 그대로(`original_result_snapshot.md`, `ab02431`) | EXACT_A 13 / PARTIAL_A 13, BOARD_ELIGIBLE 0, **NEEDS_REVISION** |
| **Amendment Result** (`POSTHOC_AMENDMENT`) | 같은 컴파일, fusion 검사만 B-1으로 교체. saturation 10 % 규칙은 원래 입력 그대로 | EXACT_A 13 / PARTIAL_A 13, BOARD_ELIGIBLE 10, 선정 10, **READY_FOR_BOARD_REVIEW** |
| **Additional Validation Result** (`ADDITIONAL_VALIDATION`) | EXACT_A 13개의 A2를 MLEK 입력 fixture로 다시 검사(B-2b) | 13/13 PASS. 이것으로 추가로 자격이 생기는 형상은 G23·G41(별도 필드, 선정에 넣지 않음) |

## B-1 ReLU6 실행 구조

- Vela는 Conv에 융합된 활성화를 별도 논리 행으로 기록한다(`npu_op` `Relu6`, Conv와 같은 `tflite_op_index`). 이 행에는 커널 명령이
  없다(`cms_offsets` 비어 있음, `vela_op_cycles` 0, `mac_count` 0). 원본 인벤토리에서도 같은 형태다(예: mobilenet op 24).
- 명령 스트림을 직접 디코딩해 확인했다(`facts/fusion_facts.json`).
  - A2의 커널 명령은 `ELEMENTWISE, CONV, ELEMENTWISE` 3개다.
  - Conv 커널의 `NPU_SET_ACTIVATION`, `ACTIVATION_MIN/MAX`, `OFM_ZERO_POINT`, `OFM_SCALE`이 원본 모델 Conv 커널과 같다.
  - 결론: ReLU6는 Conv 커널 안에서 clamp로 실행되며, 추가 커널은 없다.
- A2 EXACT_A 13개 중 12개가 `ORIGINAL_ACTIVATION_PRESERVED`이다.
- **G14는 `EXECUTION_CHANGED`이다.**
  - 원본 wav2letter의 Conv(op 19)는 활성화가 NONE이다. 그런데 Vela가 바로 다음 `LEAKY_RELU`(op 20)를 Conv 커널의 LUT로 융합한다
    (`activation_function` 4 = LUT_S8_S8, table 1).
  - A2 래퍼의 Conv 커널에는 LUT가 없다(`activation` 0). 원본의 실행 구조가 재현되지 않았다는 뜻이다.
  - Stage 6B 원래 정적 일치 기준(Conv 행의 형상·block·메모리)으로는 이 차이가 드러나지 않았다. Stage 6B 원본 결과(G14 EXACT)는
    바꾸지 않았으며, 이 사실은 여기에만 기록한다.
- 폼별 분류:
  - A0: 26개 모두 `EXECUTION_CHANGED`. 레지스터의 precision·region·stride가 다르다. A0는 원래부터 PARTIAL이다.
  - A1: 3개 PRESERVED, 23개 CHANGED.
  - A2: 15개 PRESERVED(PARTIAL_A 3개 포함), 11개 CHANGED.

## B-2a Saturation 진단 (G14, G23, G41)

`facts/diagnose.json`. 검사 정의에서 결함은 찾지 못했다.

- **대상 텐서.**
  - `conv_out`: BUILTIN_REF로 실행하며 보존한 Conv 출력이다. fused 활성화를 적용한 뒤의 값이다.
  - `final`: 그래프 출력이다.
  - 기록된 비율은 저장된 IFM으로 다시 계산해도 정확히 같다(3개 후보 × 3개 폼, conv_out·final 모두).
  - A0/A1/A2 모두 같은 공식을 썼다.
- **경계.**
  - RELU6이고 OFM scale이 6/255, zp −128인 경우(G23, G41) 범위는 [−128, 127]이다.
  - NONE인 경우(G14, scale 0.764, zp 49)도 범위는 [−128, 127]이다.
- **원인: 입력 분포.**
  - seed 고정 균등 분포 int8 입력을 쓰면 클램프 전 conv 출력이 출력 범위를 크게 벗어난다.

    | group | 1 % | 중앙값 | 99 % |
    | --- | ---: | ---: | ---: |
    | G14 | −460 | −194 | 84 |
    | G23 | −848 | −358 | 205 |
    | G41 | −3,009 | −333 | 2,357 |

  - 이 때문에 대부분의 값이 하한에 붙는다.
  - 래퍼가 없는 A0에서도 G41은 8.4 %로 낮다.
  - A1/A2에서는 첫 ADD(a, b)가 Conv 입력의 26–50 %를 ±128로 포화시켜 비율이 더 낮아진다.
- **A1에서 가려짐.** A1의 final은 ADD(conv_out, c)의 rescale 때문에 비율이 높게 나온다(G14 99 %). conv_out의 포화가 final에서
  가려지는 경우이므로, conv_out과 final을 따로 검사한 것이 맞았다.

## B-2b MLEK 입력 fixture (EXACT_A 13개 전부, A2)

입력은 모델마다 하나이며 재시도는 없다. 원본 MLEK 모델을 MLEK 입력(equivalence C 파일, digest 확인)으로 실행했고, 그 Conv의 입력 텐서를
A2의 `a`로, IFM zero point로 채운 텐서를 `b`로 넣었다. `facts/fixture/fixture.json`, 컨테이너 파일 digest는 `facts/fixture.sha256`에 있다.

| group | model | 원 입력 conv_out / final | MLEK 입력 conv_out / final | V2 입력 일치 | V3 모델 Conv 출력 불일치 | V4 | V5 | V7 vela·cms 동일 | 판정 |
|---|---|---|---|---|---|---|---|---|---|
| G09 | mobilenet | 0.510 / 0.510 | 0.695 / 0.695 | True | 0 | 1 | 0 | True | PASS |
| G11 | ad | 0.266 / 0.266 | 0.489 / 0.489 | True | 0 | 1 | 0 | True | PASS |
| G12 | ad | 0.263 / 0.263 | 0.479 / 0.479 | True | 0 | 1 | 0 | True | PASS |
| G14 | wav2letter | 0.050 / 0.050 | 0.984 / 0.984 | True | 0 | 1 | 0 | True | PASS |
| G23 | kws | 0.064 / 0.064 | 0.547 / 0.547 | True | 0 | 1 | 0 | True | PASS |
| G25 | kws | 0.119 / 0.119 | 0.363 / 0.363 | True | 0 | 1 | 0 | True | PASS |
| G28 | ad | 0.260 / 0.260 | 0.571 / 0.571 | True | 0 | 1 | 0 | True | PASS |
| G40 | mobilenet | 0.417 / 0.417 | 0.657 / 0.657 | True | 0 | 1 | 0 | True | PASS |
| G41 | mobilenet | 0.070 / 0.070 | 0.163 / 0.163 | True | 0 | 1 | 0 | True | PASS |
| G52 | ad | 0.290 / 0.290 | 0.533 / 0.533 | True | 0 | 1 | 0 | True | PASS |
| G53 | vww4 | 0.465 / 0.465 | 0.466 / 0.466 | True | 0 | 1 | 0 | True | PASS |
| G56 | vww4 | 0.468 / 0.468 | 0.436 / 0.436 | True | 0 | 1 | 0 | True | PASS |
| G57 | vww4 | 0.485 / 0.485 | 0.505 / 0.505 | True | 0 | 1 | 0 | True | PASS |

- V3이 13개 모두 0이다. 이는 A2 Conv가 원본 모델 Conv와 같은 출력을 낸다는 뜻이다(CPU BUILTIN_REF 기준, 실제 데이터).
  NPU 실행 결과는 확인하지 않았다.
- G14는 fixture를 통과해도 B-1(`EXECUTION_CHANGED`) 때문에 자격이 없다.
- G23·G41은 원래 입력에서 `SATURATION_GATE_FAIL`을 유지한다. 다만 MLEK 입력에서는 통과하므로
  `BOARD_ELIGIBLE_WITH_ADDITIONAL_VALIDATION`이다.

## EXACT_A·BOARD_ELIGIBLE 변화

| | Original | Amendment | + Additional (별도 필드) |
| --- | ---: | ---: | ---: |
| EXACT_A | 13 | 13 (변화 없음, 승격 없음) | — |
| BOARD_ELIGIBLE | 0 | 10: G09 G11 G12 G25 G28 G40 G52 G53 G56 G57 | 12: 왼쪽 10개 + G23, G41 |

BOARD_ELIGIBLE이 된 근거는 다음과 같다.
- EXACT_A다.
- params, reference, repeat, registers, package가 모두 PASS다. reference는 원래 입력과 10 % 규칙으로 판정했다.
- B-1 결과가 `ORIGINAL_ACTIVATION_PRESERVED`다.
- 두 번째 컴파일로 판정해도 결과가 같다.

## 선정 (Stage 6B 규칙, 변경 없음)

선정 순서는 G12, G25, G40, G53(모델별 최소 1개), 그다음 G11, G56, G52, G57, G09, G28(점수순)이다. 두 번째 컴파일로 선정해도 같다.
G23·G41까지 포함한다는 가정의 시나리오(라벨 표시)에서는 G09·G28 대신 G23·G41이 들어간다.

## 모델별 Coverage (정적 재현·측정 가능 범위, Amendment 기준)

| model | 상태 | 원본 MAC | 1×1 DF MAC | EXACT_A MAC | BOARD_ELIGIBLE MAC | 선정 MAC | 선정 / 원본 | Validated HW (변화 없음) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ad_medium_int8 | ELIGIBLE | 61,466,400 | 58,664,352 | 58,662,144 | 58,662,144 | 58,662,144 | 0.954 | 0.000 |
| kws_micronet_m | ELIGIBLE | 14,208,852 | 12,056,352 | 10,094,000 | 7,350,000 | 7,350,000 | 0.517 | 0.000 |
| mobilenet_v2 | ELIGIBLE | 300,840,274 | 207,404,288 | 61,917,184 | 41,846,784 | 41,846,784 | 0.139 | 0.219 |
| vww4 | ELIGIBLE | 18,763,264 | 12,237,056 | 4,259,840 | 4,259,840 | 4,259,840 | 0.227 | 0.196 |
| wav2letter | NO_ELIGIBLE | 3,491,110,876 | 600,584,000 | 592,000,000 | 0 | 0 | 0 | 0.000 |
| yolo-fastest | NO_ELIGIBLE | 38,807,136 | 16,588,800 | 0 | 0 | 0 | 0 | 0.220 |
| rnnoise | NOT_APPLICABLE | 87,510 | 0 | 0 | 0 | 0 | 0 | 0.000 |

- "선정 / 원본"은 측정 대상 형상이 정적으로 덮는 MAC 비율이다. 하드웨어 처리율로 검증한 coverage가 아니다.
- 보드 측정 뒤에도 Validated HW 값은 이 계약으로 늘리지 않는다.

## Vela 추정 사이클

- `facts/vela_total.json`에 12개(선정 10 + G23, G41)의 Vela 성능 요약 `cycles_total`을 기록했다. 같은 컴파일임을 `vela_sha256`으로 확인했다.
- 범위는 A2 그래프 전체이며, 연산별 `vela_op_cycles`의 합과 같다.
- Conv 범위의 값(`vela_op/mac/ao_cycles`)은 `amendment_b_summary.json`의 `vela_estimates`에 있다.
- 보드 측정이 없으므로 오차는 계산하지 않았다.
- 비교 가능성은 다음과 같다(보드 계약 §8).
  - NPU_ACTIVE 대 `cycles_total`: COMPARABLE.
  - Conv 범위: NOT_COMPARABLE.

## 재현

```
python3 host/analysis/stage6b_amendment_b.py run evidence/stage6b/revision_a/compiled \
  evidence/stage6b/revision_a/amendment_b/facts/fusion_facts.json \
  evidence/stage6b/revision_a/amendment_b/facts/fixture/fixture.json results/fi101_stage6b/revision_a/amendment_b
```

컨테이너 사실 수집(`benchmark-runner`, `/work/s6b_host`) 명령은 다음과 같다.

```
stage6b_amendment_b.py fusion|diagnose|fixture|vela /work/s6b_ra_compile /work/s6b_ra_manifest.json …
```

두 번 실행해도 결과 파일이 바이트 단위로 같다.
