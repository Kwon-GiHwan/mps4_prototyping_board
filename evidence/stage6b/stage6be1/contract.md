# Stage 6B-E1 — H1-UC 전향적 검증: 계약 (후보 컴파일 전 동결)

- 근거: "Stage 6B-E1 공식 지시"(조건부 보드 승인).
- 검증 대상 H1-UC는 Stage 6B-R(`5c801f7`)의 구현 `host/analysis/stage6br.py`를 **그대로** import해 쓴다. 경쟁 가설도 같은 정의를 쓴다.
  - H1-G, H1-C16, H1-U8, H1-U16
  - 제거 실험 4개
  - DPU: D-U16, D-U8, D-PW
- 측정 결과에 맞춰 보정계수, 예외, 분기를 추가하지 않는다.
- 기존 14/14와 탐색 3/3은 회귀 테스트로만 쓰고, 이번 검증 결과로 집계하지 않는다.
- 기존 Stage 4K / 6B-B / 6B-R 결과는 바꾸지 않는다. E2, E3, Stage 6C는 범위 밖이다.

## 1. 후보 공간 (고정)

**생성기**: `make_op_model.serialize`, Stage 1 양자화 정책을 쓴다.
- 1×1 Conv, stride 1, VALID, RELU6, INT8.
- IFM은 S_IN 1/128, 가중치는 시드 `E1_SEED` = 20261116 균등 int8, bias는 같은 시드다.
- OFM scale은 그 데이터의 누산기 최대값으로 정한다(포화 없음).
- 입력은 같은 시드의 균등 int8이고, `--ifm`으로 패킹한다.

**격자**(8 × 5 × 5 = 200개):
- Cin ∈ {24, 40, 72, 80, 88, 100, 136, 200}
- H×W ∈ {7×7, 8×8, 9×9, 13×13, 14×14}
- Cout ∈ {48, 80, 96, 112, 176}

**컴파일**: Vela 5.0.0, MLEK 옵션(`pack_vela_workload.VELA_OPTIONS`)이다. 정적 정보는 다음과 같이 읽는다.
- Vela debug DB 행: traversal, block, ublock, 연산 목록
- command stream의 Conv 커널 레지스터: 커널별 OFM 크기, IFM 깊이

## 2. 적격 조건 (모두 만족해야 함)

1. Vela 출력에 ethos-u 연산이 1개이고, NPU 논리 행은 `Conv2D`와 그 활성화(`Relu6`, 커널 명령 없음)만 있으며, CPU 연산이 없다.
2. traversal = **DepthFirst**, 커널 1×1.
3. 기존 공식 측정 형상과 겹치지 않는다. 겹친다는 것은 (H, W, Cin, Cout)이 Stage 4K/4C2 1×1, 6B-B 11개, Revision A 후보 26개 중 하나와 같다는 뜻이다.
4. H1-UC의 예측이 경쟁 가설(MAC 8개) 중 **적어도 하나와 다르다**.
5. 패킹이 된다(DRWL `fast_size`·`arena_size`·`model_region`이 6B 한도 안). 패킹은 선정 단계에서 순위대로 시도한다.

## 3. 범주와 선정 규칙 (고정, 결과를 본 뒤 바꾸지 않음)

후보마다 다음을 계산한다.
- 경쟁 가설 8개 중 H1-UC와 예측이 다른 것의 수 `n_split`
- 아래 범주 표시

| 범주 | 조건 |
| --- | --- |
| E1-A Cin 잔여 조각 | Cin mod IFM block 깊이 = r, 0 < r < 32 (조각당 최소 32가 작동) **그리고** H1-UC ≠ "min 32 제거" |
| E1-B 공간 경계 | 어떤 커널에서 H_k mod u_h ≠ 0 또는 W_k mod u_w ≠ 0 **그리고** H1-UC ≠ "공간 패딩 제거" |
| E1-C ublock 깊이 16 | u_c = 16 |
| E1-D Cout 커널 분할 | 커널 수 ≥ 2 **그리고** H1-UC ≠ "전체 Cout" |

순위 키는 다음 순서다.
1. `n_split` 큰 순
2. D-PW ≠ D-U16인 후보 우선
3. N_MAC 작은 순
4. 이름 순

선정은 이 순서로 한다.
1. E1-A, E1-B, E1-C, E1-D에서 각각 순위 1위를 고른다. 이미 고른 후보는 빼고, 패킹에 실패하면 다음 순위로 넘어간다.
2. 나머지 2개는 남은 적격 후보 전체에서 순위대로 고른다. 이미 고른 형상과 (Cin, Cout)이 같으면 건너뛴다.
3. 범주 하나라도 후보가 없거나 6개를 채우지 못하면 **NEEDS_REVISION**으로 보고하고 보드는 실행하지 않는다. 대체하지 않는다.

## 4. 예측 동결

선정한 6개마다 다음을 `predictions.json`에 기록한다.
- 원본 N_MAC, 커널 수, traversal, IFM/OFM block, ublock
- 커널별 OFM 크기와 ublock 수, Cin 조각
- 9개 MAC 가설의 정수 예측값, H1-UC 예상 N_MAC/MAC_ACTIVE
- 3개 DPU 가설, 가설별 예측 차이 표

이 파일과 DRWL·컴파일 digest, 판정 코드를 보드 전에 커밋한다.

결정성: 선정 형상은 두 번 독립 컴파일한다. 다음이 같아야 한다.
- tflite, Vela 출력, command stream, DRWL sha256
- 커널 레지스터, debug 행

다르면 그 형상은 제외하고 NEEDS_REVISION이다.

## 5. 보드 (지시 §6)

- boot 421(기준) – 427(신규 6개)이고, 최대 7 boot / 70 RUN이다.
- 기준은 Stage 4K `s4c2_conv_cin48`이며 6B-B와 같은 DRWL `6eb390be…`다.
- 이미지 `70090f1`, TA profile 1, `wfe 0 0 off 1,2`, pass A·B(Stage 4와 같음), pass마다 warm-up 1 + 측정 4다.
- 판정은 Stage 6B-B 판정 코드(`stage6bb.config_result`, `repro_gate`)를 그대로 쓴다. E1 config는 n_base 5로 `identity_a1`을 쓰고, 출력은 BUILTIN_REF golden과 `output.bin`·RUN별 `output_match`로 본다.
- 상태는 다음 중 하나다: VALID, INVALID_OUTPUT, INVALID_PMU, UNSTABLE, CONFIG_MISMATCH, UNMEASURED.
- 5 % NPU_ACTIVE 안정성 기준은 그대로다.
- 중단 규칙: 기준 `repro-gate`가 실패하거나, 신규 형상이 CONFIG_MISMATCH·UNMEASURED이면 세션을 멈춘다. 그 밖의 상태는 기록하고 계속한다.
- 대체 형상과 추가 RUN은 없다.

## 6. H1-UC 판정 (`host/analysis/stage6be1.py`)

형상별 분류는 다음과 같다.
- **Primary Valid**: 상태 VALID. 측정 RUN 4회의 MAC_ACTIVE가 모두 같고, 그 값이 예측과 정확히 같은지 본다.
- **MAC-only Diagnostic**: 상태 UNSTABLE이고 MAC_ACTIVE·MAC_DPU_ACTIVE가 4회 모두 같은 경우. 일치 여부를 기록하지만 공식 집계에서 뺀다.
- **INVALID / UNRESOLVED**: 그 밖.

최종 판정:
- **PROSPECTIVE_SUPPORT**: 6개 모두 Primary Valid이고, 6개 모두 H1-UC와 정확히 일치한다.
- **H1_UC_CONTRADICTED**: Primary Valid 형상 하나라도 H1-UC와 다르다. 반례로 기록하고 식은 고치지 않는다.
- **INSUFFICIENT_EVIDENCE**: 그 밖. 예를 들어 Primary Valid가 6개 미만이면서 반례가 없는 경우, 또는 기준 gate가 실패한 경우.

경쟁 가설도 Primary Valid 형상마다 일치 여부를 적는다. 예측이 H1-UC와 같았던 형상은 구분 증거로 세지 않는다.

DPU(보조): D-PW·D-U16·D-U8을 같은 방식으로 적는다. D-PW와 D-U16이 갈리는 Primary Valid 형상이 없으면 D-PW는 INSUFFICIENT_EVIDENCE를 유지한다. MAC 판정과 섞지 않는다.

**PROSPECTIVE_SUPPORT여도 보편 법칙이라고 주장하지 않는다.** 범위는 이번 Vela 구성, 이번 형상 영역의 1×1 DepthFirst Conv로 한정한다.
