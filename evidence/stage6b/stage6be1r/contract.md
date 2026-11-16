# Stage 6B-E1-R — H1-UC 전향적 재검증: 개정 계약 (후보 컴파일 전 동결)

- 근거: "Stage 6B-E1-R 공식 지시". 정적 설계·계약 동결과 보드 측정을 조건부로 승인받았다.
- Phase 0 감사: `evidence/stage6b/stage6be1r/phase0/errata.md`(`ab2e420`). 형상-예측-측정 불일치 없음.
- 이 계약은 E1 계약(`evidence/stage6b/stage6be1/contract.md`, `d39448c`)의 **개정**이다. E1 계약 파일은 고치지 않는다.
- **`POSTHOC_DESIGN_REVISION`**: 바뀌는 것은 후보 격자와 선정 규칙뿐이다.
  - 이 개정은 E1 결과를 본 뒤에 설계했다. E1에서 형상 6개가 모두 NPU_ACTIVE 3.7k–18k 사이클로 작았고, 6개 모두 pass A range 6–9 %로 UNSTABLE이었다.
  - Vela 사이클 하한 50,000은 이 E1 변동 결과에서 정했다. 기준 형상 NPU_ACTIVE ~22k의 2배 이상이고, E1에서 본 RUN 간 절대 변동 300–1,260 사이클의 수십 배다.
  - 이 하한은 **안정성을 보장하지 않는다.** 후보를 고르는 조건일 뿐이다.
  - "작은 형상이 변동의 원인"이라는 인과관계는 검증되지 않았다.
- H1-UC의 새 실측값을 보기 전에 예측을 동결한다. 측정 뒤 식, 예외, 기준을 바꾸지 않는다.
- E2, E3, Stage 6C, E1 UNSTABLE 형상의 재측정은 범위 밖이다.

## 0. 바꾸지 않는 것 (E1 계약 그대로)

| 항목 | 출처 |
| --- | --- |
| H1-UC 식과 경쟁 가설 MAC 8개(H1-G, H1-C16, H1-U8, H1-U16, 제거 실험 4개) | `host/analysis/stage6br.py`(`5c801f7`)를 import해 그대로 쓴다 |
| DPU 가설 D-U16, D-U8, D-PW | 같음 |
| 범주 E1-A·B·C·D의 정의 | `host/analysis/stage6be1.py`의 `categories`(`3a83175`)를 import해 그대로 쓴다 |
| 모델 생성기, 양자화, 시드 `E1_SEED` 20261116, RELU6, Vela 5.0.0과 MLEK 옵션 | `host/container/stage6be1_models.py`를 import해 쓴다. 바뀌는 것은 격자와 형상 이름 접두어(`e1r_`)뿐이다 |
| 형상 분류(Primary Valid / MAC-only Diagnostic / INVALID), 주 판정 규칙 | `stage6be1.classify`, `shape_result`, `verdict`를 그대로 쓴다 |
| 보드 상태 판정, 5 % NPU_ACTIVE 안정성 기준, 출력·PMU·환경 검사, 기준 재현 gate | `stage6bb.config_result`, `repro_gate`, `boot-check`(`0a99697`) 그대로 |
| 측정 조건 | Driver Runner 이미지 `70090f1`, **TA profile 1**, DDR/EXT, `wfe 0 0 off 1,2`, pass A·B(Stage 4와 같음), pass마다 warm-up 1 + 측정 4 |
| 예산 | 최대 7 boot / 70 RUN(warm-up 14, 측정 56) |

## 1. 후보 격자 (고정)

- Cin ∈ {24, 40, 72, 80, 88, 100, 136, 200}: E1과 같다.
- Cout ∈ {48, 80, 96, 112, 176}: E1과 같다.
- **OFM H×W ∈ {24×24, 25×25, …, 40×40}**: 정사각형이고 간격은 1이다(17개).
  - 짝수와 홀수를 모두 넣는다. ublock 경계(E1-B)가 생기는 형상과 생기지 않는 형상이 함께 있게 하려는 것이다.
- 8 × 17 × 5 = **680개**. 이름은 `e1r_c{Cin}_h{H}w{W}_o{Cout}`이다.
- 컴파일과 정적 정보 읽기는 E1과 같다(`stage6be1_models.vela_facts`).

## 2. 적격 조건 (모두 만족)

E1 계약 §2의 1–5에 아래를 더한다. 번호는 지시 §3.1을 따른다.

1. 1×1 DepthFirst Conv다. ethos-u 연산 1개, NPU 행은 `Conv2D`+`Relu6`(커널 명령 없음), CPU 연산 없음, 커널 1×1, traversal DepthFirst.
2. **메모리 배치가 E1과 같다**: Conv 행의 `ifm_memory`·`ofm_memory`가 모두 `Dram`이다.
3. 같은 Vela 구성(Vela 5.0.0, MLEK 옵션). 컨테이너 Vela 패키지 digest를 동결 자료에 적는다(§5).
4. **Vela 예상 전체 사이클 ≥ 50,000**.
   - 이 값은 ethos-u 연산의 Vela debug DB 행 `vela_op_cycles`의 합이다. `Relu6` 행은 0이다.
   - 6B-R의 Vela summary `cycles_total` = Σ op_cycles와 같은 정의다.
5. H1-UC 예측이 경쟁 가설 MAC 8개 중 적어도 하나와 다르다(`n_split` ≥ 1).
6. 수치 출력 reference를 검증할 수 있다.
   - 빌드에서 TFLite reference 커널 출력(`ref_ofm`)을 만들고, 그것이 DRWL golden과 같다(`golden_sha256` = `ref_sha256`).
   - 출력 길이는 H·W·Cout이다.
7. 기존 형상과 겹치지 않는다. E1 계약 §2.3의 집합(Stage 4K/4C2 1×1, 6B-B, Revision A 후보)에 **E1 선정 형상 6개**를 더한 것과 (H, W, Cin, Cout)이 달라야 한다.
8. 하드웨어 실행 가능한 산출물이 있다.
   - 패킹 성공(`pack_rc` 0).
   - DRWL `fast_size`·`arena_size`·`model_region`이 6B 한도 안이다.
   - 두 번 독립 빌드가 같다(E1 §4 결정성 키).

조건 1–5와 7은 격자의 정적 정보로 판단한다. 조건 6과 8은 빌드가 필요하다. 선정 단계에서 순위대로 빌드하며, 실패한 후보는 건너뛴다(§3).

## 3. 순위와 선정 (고정)

범주 표시는 E1 `categories` 그대로다.

**순위 키**(지시 §3.2 순서, E1의 "N_MAC 작은 순"은 쓰지 않는다):
1. `n_split`(H1-UC와 예측이 다른 경쟁 가설 수) 큰 순
2. `min_gap` 큰 순: H1-UC와 예측이 다른 경쟁 가설들과의 |예측 차이| 중 최소값. 정확 일치 기준에서 가장 가까운 경쟁 가설과의 여유가 큰 형상을 앞에 둔다.
3. Vela 예상 전체 사이클(§2.4) 큰 순
4. 형상 이름 오름차순

**"사실상 같은 실행 구성"**: 다음이 모두 같은 두 후보를 말한다. 이런 후보는 두 번 고르지 않는다.
- 커널별 OFM 크기 목록, ublock, OFM block, IFM block
- Cin 조각별 H1-UC 비용 `max(32, ceil16(x))` 목록

이 묶음이 같으면 H1-UC 계산 입력이 같다.

**선정 순서**:
1. E1-A, E1-B, E1-C, E1-D 차례로 범주마다 순위 1위를 고른다. 다음 후보는 건너뛰고 다음 순위로 간다.
   - 이미 고른 형상
   - 이미 고른 것과 실행 구성이 같은 형상
   - 빌드 조건(§2.6, §2.8)을 통과하지 못한 형상
2. **추가 1**(DPU 보조, 지시 §8): 남은 적격 후보 중 D-PW와 D-U8의 예측이 다른 순위 1위를 고른다. 없으면 남은 후보 순위 1위다.
3. **추가 2**: 남은 적격 후보 순위 1위다.
4. 추가 1·2는 위 1의 건너뛰기 규칙에 더해, 이미 고른 형상과 (Cin, Cout)이 같으면 건너뛴다(E1 규칙).
5. 범주 하나라도 고를 형상이 없거나 6개를 채우지 못하면 **NEEDS_REVISION**이다. 그때는 다음을 하지 않고 보고한다: 하한 50,000 낮추기, 범주 바꾸기, 격자 바꾸기, 보드 실행.

빌드는 결정적으로 진행한다. 정적 순위로 선정 → 고른 형상을 빌드 → 빌드 실패가 있으면 그 후보를 빼고 같은 규칙으로 다시 선정한다. 이를 선정이 바뀌지 않을 때까지 반복하고, 시도한 빌드 전부를 기록한다.

새 보드 측정값은 선정에 쓰지 않는다. E1 보드 결과도 형상별 선정에는 쓰지 않는다. E1 결과는 하한 50,000의 근거로만 썼다.

## 4. 예측 동결

선정한 6개마다 `workloads/predictions.json`에 다음을 기록한다.
- 형상 ID, Cin/Cout, OFM H×W, traversal
- 커널 수, 커널별 OFM 크기(Cout 분할), IFM/OFM block, ublock, 공간 ublock 수, Cin 조각
- H1-UC와 경쟁 가설 8개의 MAC_ACTIVE 예측, H1-UC 예상 N_MAC/MAC_ACTIVE
- D-U16·D-U8·D-PW 예측과 D-PW≠D-U16, D-PW≠D-U8 여부
- Vela 예상 전체 사이클
- `n_split`, `min_gap`
- 산출물 digest(tflite, Vela 출력, command stream, DRWL, golden), 컴파일러 digest

계약, 선정 결과, 예측, 판정 코드, 테스트를 보드 전에 커밋한다.

## 5. Preflight (전부 PASS여야 보드 실행)

E1 Preflight 항목을 모두 다시 확인하고, 다음을 더한다.
- **컴파일러 digest**: 컨테이너 Vela 패키지(버전 5.0.0, 설치 파일 sha256 묶음)가 동결 기록과 같다. 선정 형상을 다시 컴파일하면 Vela 출력 sha256이 동결값과 같다.
- **boot 번호**: 428–434를 쓴 적이 없다. 보드 기록 최대값을 확인한다.
- 세션 파일, staging digest(Mac = 보드), `sudo_session.sh --check`, 복구 경로를 확인한다.

FAIL이나 UNRESOLVED가 하나라도 있으면 보드를 실행하지 않는다.

## 6. 보드

- boot 428(기준), 429–434(신규 6개)를 순서대로 돈다.
- 기준은 Stage 4K `s4c2_conv_cin48`, DRWL `6eb390be…`(E1과 같음)이고, 재현 대상은 Stage 4K boot 375다.
- 중단 규칙(E1과 같음): 기준 `repro-gate`가 실패하면 즉시 중단한다. 신규 형상이 CONFIG_MISMATCH·UNMEASURED이면 세션을 멈춘다. 그 밖의 상태는 기록하고 계속한다.
- 실패 형상을 교체하지 않고, 같은 형상을 다시 측정하지 않는다.
- 측정 뒤 원본 이미지를 복원한다(`RESTORE VERIFIED`, postflight).

## 7. 판정

**주 판정**(`stage6be1.verdict` 그대로):
- **PROSPECTIVE_SUPPORT**: 기준 gate PASS, 6개 모두 Primary Valid, H1-UC 6/6 정확 일치.
- **H1_UC_CONTRADICTED**: Primary Valid 형상 하나라도 H1-UC와 다르다.
- **INSUFFICIENT_EVIDENCE**: 그 밖(유효 표본 부족, 기준 gate 실패 등).

- NPU_ACTIVE가 5 %를 넘으면 MAC_ACTIVE가 예측과 같아도 Primary Valid가 아니다. MAC-only Diagnostic으로 따로 적고 공식 개수에 넣지 않는다.
- 경쟁 가설은 형상마다 일치 여부를 적는다. H1-UC와 예측이 같았던 경쟁 가설은 그 형상에서 구분 증거로 세지 않는다.
- 보고는 세 자료를 구분한다.
  - Stage 6B-R: 사후 도출, 기존 자료
  - Stage 6B-E1: 전향 예측 일치, Primary Valid 0/6
  - Stage 6B-E1-R: 이번 신규 전향 검증
- PROSPECTIVE_SUPPORT여도 범위는 이번 Vela 구성과 이번 격자의 1×1 DepthFirst Conv(Dram→Dram)로 한정한다. 하드웨어 법칙이라고 주장하지 않는다.

**DPU 보조 판정**(새 함수 `stage6be1r.dpu_verdict`, 주 판정과 섞지 않음):
- 경쟁 가설 D-U16, D-U8 각각에 대해, D-PW와 예측이 갈리는 Primary Valid 형상 집합을 본다.
- 판정은 다음 순서로 정한다.
  1. 어느 집합에서든 D-PW가 하나라도 틀리면 **D-PW_CONTRADICTED**다.
  2. 두 집합이 모두 비어 있지 않고 D-PW가 전부 맞으면 **D-PW_CONSISTENT**다.
  3. 그 밖에는 **INSUFFICIENT_EVIDENCE**다.
- DPU/MAC 비율을 회로 점유율로 해석하지 않는다.

**보조 분석**(사전 지정, 판정에 쓰지 않음):
- 형상별 NPU_ACTIVE pass A·B 값, range, 절대 range
- 형상별 H1-UC 예상 처리율 N_MAC/MAC_ACTIVE와 실측 처리율
