# Stage 6B Revision A — 정적 재검증 계약 (A2 컴파일 전에 고정, 2026-11-15)

지시: ChatGPT 경유 owner 지시 "Code Agent 공식 지시 — Stage 6B Revision A" (Revision A를 신규 실험 계약으로 승인, 보드 측정 미승인).
이 문서·판정 코드·후보 출처 manifest는 **A2를 한 번도 컴파일하지 않은 상태에서** 커밋한다. 이후 기준을 결과에 맞춰 바꾸지 않는다.
기준을 바꿔야 하면 개정으로 따로 기록하고 이 계약의 결과도 함께 보고한다.

- 판정 코드: `host/analysis/stage6b_revision_a.py`
- 테스트: `host/tests/test_stage6b_revision_a.py`
- mutation: `evidence/stage6b/revision_a/mutate.py` → `mutation.txt`
- 컨테이너 (사실 기록만, 판정 없음): `host/container/stage6b_revision_a_models.py`
- 후보 출처 고정: `revision_a_manifest.json`
  - 26개 후보마다 원본 모델 sha256, TFLite op 번호, scheduled_id, 그룹, N_MAC, cms offset을 담는다.
  - weight·bias 바이트 sha256, IFM/W/B/OFM의 scale·zero point·dtype·shape도 담는다.
  - 원본 tflite에서 읽었고, 컴파일 전에 만들었다.

## 0. 보존 (변경하지 않는 것)

- Stage 6B 규칙 `b9f3824`, 결과 `0c4bf4c`를 바꾸지 않는다.
  - 원본 Conv 93개, 그룹 57개, 후보 26개
  - EXACT 1 (G14) / PARTIAL 25
  - 기존 coverage 기회
  - 판정 `NEEDS_REVISION`
- 사후 탐색 (`post_hoc/probe_self`)의 "13개 EXACT 예상"은 기록만 한다. 성공 기준이 아니다.
- Stage 4–6 데이터·계약·판정 규칙을 바꾸지 않는다. 기존 모듈 (`stage6b.py`, `stage6b_models.py` 등)은 import만 하고 고치지 않는다.
- Revision A 산출물은 `evidence/stage6b/revision_a/`, `results/fi101_stage6b/revision_a/`에 따로 둔다.

## 1. 후보와 조건

- 후보 집합은 기존 26개로 고정한다 (`candidates.json` sha256 `fadff4cb…`, inventory sha256 `e88662e2…`).
- 컴파일 조건은 Stage 6B와 같다.
  - Vela 5.0.0, `ethos-u85-1024`, `--optimise Performance`, MLEK `default_vela.ini`
  - `Dedicated_Sram`, `Ethos_U85_SYS_DRAM_Mid_1024`
  - 패커 profile `config/fi101_s013.json` (TA profile 1), DRWL placement word 0 (DDR/EXT)
  - IFM은 `S6B_SEED = 20261118`로 뽑고, 범위는 int8 전체다.
- 원본 비교 대상
  - inventory 행 (Stage 4 inventory)
  - 원본 MLEK 모델을 같은 Vela 옵션으로 **다시 컴파일한** command stream: 그 Vela tflite sha256 앞 16자리가 inventory의 `vela_sha256`과 같아야 쓴다.

## 2. 구성 (실험 변수)

| 표시 | 이름 | 그래프 | 비고 |
|---|---|---|---|
| A0 | F_PLAIN | CONV_2D 하나 | Stage 6B와 같은 바이트여야 한다 |
| A1 | F_CTX | ADD(a, b) → CONV_2D → ADD(conv_out, c) | Stage 6B와 같은 바이트여야 한다 |
| A2 | F_CTX_SELF | ADD(a, b) → CONV_2D → ADD(conv_out, conv_out) | 신규 |

A2의 세부 정의:
- 앞 ADD는 A1과 같다. Conv IFM을 중간 텐서로 둔다.
- 마지막 ADD는 conv_out을 두 입력으로 받는다. 출력 scale은 2 × conv_out scale, zero point는 conv_out의 것이다.
- 그래서 최종 출력은 반올림 범위 안에서 conv_out과 같다.
- A2는 중립 identity가 아니다. Conv 결과를 두 번 소비하므로 tensor lifetime, 데이터 의존성, AO 작업량이 바뀐다.
- 이 판정은 **Conv 자체의 실행 구성 동일성**만 다룬다. 래퍼가 더한 실행 비용은 보드 계약에서 따로 제한한다 (§8).

## 3. 판정 1 — EXACT_A / PARTIAL_A / NOT_REPRODUCIBLE_A (기존 정의 그대로)

`stage6b.form_class` (b9f3824 규칙 §4)를 **수정 없이** 각 구성에 적용하고 이름만 바꾼다.

- **EXACT_A** (= EXACT_STATIC_MATCH). 아래가 모두 원본 행과 같다.
  - 형상: npu_ifm_hwc, npu_ofm_hwc, kernel, stride, padding, mac_count
  - 실행 구성: traversal, ifm_block, ofm_block, ofm_ublock
  - 배치: ifm_memory, ofm_memory, ifm_format, ofm_format, cascade
  - weight·fusion: weight_bytes, staging_usage, tflite_activation
  - 실행 가능 항목도 모두 통과한다 (Conv 하나, CPU 연산 없음, 패킹, reference, 러너 한도, 반복 컴파일).
- **PARTIAL_A** (= PARTIAL_STATIC_MATCH): 형상과 실행 가능은 통과했지만 나머지 중 하나 이상이 다르다.
- **NOT_REPRODUCIBLE_A** (= NOT_REPRODUCIBLE): 형상 또는 실행 가능이 실패했다.
- 후보 등급은 세 구성 중 가장 좋은 쪽이다. 같으면 래퍼가 적은 순서 **A0 > A1 > A2**를 따른다.
  - 기존 "둘 다 EXACT면 F_PLAIN"의 확장이다.

EXACT 정의를 강화하거나 완화하지 않는다. 추가 검증은 모두 §4 BOARD_ELIGIBLE로 분리한다.

## 4. 판정 2 — BOARD_ELIGIBLE (구성별, 추가 검증)

구성 하나가 BOARD_ELIGIBLE이려면 EXACT_A이고, 아래 6개 검사가 모두 **PASS**여야 한다.
NOT_VERIFIED는 PASS가 아니다 (tri-state).

| 검사 | 내용 (FAIL 조건) |
|---|---|
| params | 생성 그래프에서 다시 읽은 Conv 텐서가 manifest의 원본과 다르다. weight·bias는 바이트 sha256, IFM/W/B/OFM은 scale·zero point·dtype·shape·qdim을 비교한다. Conv 출력 quantization 변경도 여기서 잡는다. |
| reference | (1) BUILTIN_REF 출력이 없거나, golden sha256 ≠ BUILTIN_REF 출력 sha256<br>(2) 독립 numpy Conv와 BUILTIN_REF conv_out의 최대 차이 > 1 LSB. numpy Conv는 원본 weight/bias/scale로 계산한다 (int64 누산, float64 재양자화, activation clamp). 입력은 reference가 보존한 Conv 입력 텐서다.<br>(3) conv_out 원소 중 clamp 범위 안쪽 값 비율 < 10 %<br>(4) 최종 출력에서 −128/127이 아닌 값 비율 < 10 %<br>(5) A2만: 최종 출력과 conv_out의 최대 차이 > 1 LSB |
| repeat | 독립 컴파일 2회의 다음 항목 중 하나라도 다르다: 입력 tflite, Vela 출력, DRWL, 패커 manifest (경로 키 `model`·`ifm_file`·`golden_file` 제외), command stream sha256, Conv 행 전체, Conv kernel 레지스터 상태 |
| fusion | 다음 중 하나다.<br>- scheduled NPU 연산 순서가 A0 [Conv2D], A1·A2 [Add, Conv2D, Add]가 아니다 (래퍼 제거·Conv 제거·치환을 잡는다)<br>- CPU 연산이 있다<br>- Conv 행의 fused_names가 1이 아니다<br>- Conv 행의 출력 텐서가 conv_out이 아니다 (A0은 ofm) |
| registers | 원본 command stream과 Conv kernel 레지스터를 stripe(kernel 명령)마다 비교했을 때 kernel 수가 다르거나 아래 레지스터 중 하나가 다르다. 원본 재컴파일이 inventory와 다르거나 ethos-u 연산이 1개가 아니면 NOT_VERIFIED다. |
| package | 다음 중 하나다.<br>- 실행 가능 항목 실패<br>- 패커 TA profile ≠ 1<br>- DRWL placement ≠ 0<br>- A1 정체성 n_base가 1–8 밖이다 (Vela 모델의 ethos-u 연산 inputs − 1 + outputs) |

registers 검사에서 비교하는 레지스터:
- 실행 구성
  - IFM/OFM 크기·깊이·precision(dtype·format 포함)
  - block (BLK width·height·depth), acc_format
  - IFM tile 크기, kernel 크기·stride
  - IFM/OFM stride x/y/c
  - stripe마다 weight 길이 (weight0–3 length)
- 배치: IFM·OFM·weight region 번호

비교하지 않는 것과 이유:
- base 주소: region 안의 위치일 뿐이다.
- 마지막 DMA 길이 레지스터, 직전 kernel 이후 시작된 DMA: weight prefetch 위치는 앞뒤 연산이라는 문맥에 따라 달라진다.

후보는 A0 → A1 → A2 순서에서 처음으로 BOARD_ELIGIBLE인 구성이 있으면 BOARD_ELIGIBLE이다. 그 구성이 보드 구성이다.

정적으로 검증하지 않는 것 (NOT_VERIFIED로 보고하고 BOARD_ELIGIBLE 조건에는 넣지 않는다. 보드 단계 또는 범위 밖이다):
- region → AXI 포트 물리 매핑
  - 러너의 REGIONCFG는 A1 정체성으로 boot마다 확인한다.
  - MLEK 쪽 매핑은 reference environment 동등성 (D1–D6)에 기댄다.
- 인코딩된 weight 바이트 내용: 크기와 stripe별 길이만 비교한다. 원본 weight 텐서 바이트는 params에서 비교한다.
- weight DMA prefetch 시점, 앞뒤 연산과의 실행 겹침, TA 아래 실제 접근 순서
- staging_usage가 같다는 것은 보조 증거일 뿐이다. 실행 경로가 같다는 증명이 아니다.

## 5. 출처 오류 — INVALID

다음 중 하나면 Revision A 전체를 INVALID로 판정한다. 실행을 중단하고 오류 범위를 보고한다.
- 후보 집합이 고정 26개와 다르다.
- 후보 기록이 없다.
- A0/A1/A2 중 하나가 없다.
- 원본 모델 sha256 또는 원본 Conv 텐서가 manifest와 다르다.
- A0/A1 DRWL sha256이 Stage 6B `0c4bf4c` 기록 (F_PLAIN/F_CTX)과 다르다. 이는 컴파일 환경 재현성이 깨졌다는 뜻이다.

## 6. 대표 형상 재선정

- 기존 `stage6b.select`를 그대로 쓴다.
  - 모델 floor (모델 이름 순), 정규화 점수, 동률 처리 4단계, 최대 10개
  - 적격 = **BOARD_ELIGIBLE**만이다. EXACT_A이지만 BOARD_ELIGIBLE이 아닌 후보는 목록에 남기되 선정하지 않는다.
- 선정 재현성
  - 두 번째 컴파일의 Conv 행으로 분류한 결과에도 같은 규칙을 적용한다.
  - 선정 순서가 첫 번째 컴파일 결과와 같아야 한다.
- 기존 규칙에서 해석이 모호한 항목은 찾지 못했다. 실행 중 발견하면 그 항목을 명시하고 중단한다.

## 7. Coverage (측정값 아님)

모델마다 다음 N_MAC을 기록한다.
- 정의: Vela `mac_count`. Stage 6/6B의 기존 정의를 유지한다. 1×1 Conv에서는 H·W·Cin·Cout과 같다.
- 모델 전체 (NPU 행 합)
- 1×1 DepthFirst
- 26개 후보에 속한 연산
- EXACT_A
- BOARD_ELIGIBLE
- 선정 대표 형상

그룹 등급은 같은 실행 구성을 가진 그룹 구성원 전체에 적용한다. 모델마다 자기 연산만 센다 (중복 없음).

| 값 | 정의 |
|---|---|
| Static Reproduction Coverage | EXACT_A 그룹 연산의 비중 |
| (보조) Board-eligible coverage | BOARD_ELIGIBLE 그룹 연산의 비중 |
| Selected Measurement Coverage | 선정 그룹 연산의 비중 |
| Validated HW Coverage | Stage 6 calibrated MAC coverage. 이번 단계에서 늘지 않는다. |
| 보드 후 상한 | Stage 6 coverage + 선정 연산 중 Stage 6에서 T0·T1_INTERP가 아니었던 연산의 비중 (집합 기준, 중복 없음) |

모델 상태:
- NOT_APPLICABLE: 1×1 DepthFirst 대상이 없다 (RNNoise).
- NO_CANDIDATE: 대상은 있지만 후보가 없다.
- NO_ELIGIBLE: 후보는 있지만 BOARD_ELIGIBLE이 없다.
- ELIGIBLE

## 8. 판정 3 — Revision A 최종 (닫힌 집합)

- **INVALID**: §5 오류가 하나라도 있다.
- **READY_FOR_BOARD_REVIEW**: 아래를 모두 만족한다.
  - INVALID가 아니다.
  - G14 외에 BOARD_ELIGIBLE 후보가 1개 이상이다.
  - 선정이 비어 있지 않고, 두 컴파일에서 같다.
  - 보드 계약 문서 (`revision_a_board_contract.md`)가 있다.
- **NEEDS_REVISION**: 그 밖. 실패 원인과 수정 가능한 계약 항목을 보고하고, 추가 탐색은 자동으로 하지 않는다.

READY_FOR_BOARD_REVIEW는 보드 측정 승인이 아니다.

보드 계약은 BOARD_ELIGIBLE 선정 결과로 작성한다. 다음을 보드 데이터 전에 고정한다.
- 대상: 기준 재현 + 대표 형상, 최대 11개
- 예산: 구성당 1 boot, 5 RUN 세트 2개, 최대 110 RUN
- 지표와 판정
- 래퍼 해석 제한
  - A2의 AO_ACTIVE, NPU_ACTIVE를 Conv 단독 값으로 해석하지 않는다.
  - ADD 비용을 차감하지 않는다.
  - MAC_ACTIVE를 물리 활용률로 쓰지 않는다.
  - 640·768을 새 형상에 적용하지 않는다.
  - A2에서도 MAC·WD 활동이 Conv만의 것인지 보드에서 확인한다.

## 9. 실행 순서

1. (이 커밋) 계약, 판정 코드, 테스트, mutation, 후보 출처 manifest
   - 도구 점검은 A0/A1만으로 했다. G01의 A0/A1 DRWL이 0c4bf4c와 같았다.
2. 컨테이너에서 26개 후보 × A0/A1/A2 × 2회 컴파일 → `<cfg>.ra.json`
3. `stage6b_revision_a.py run` → `revision_a_results.csv`, `revision_a_coverage.csv`, `revision_a_summary.json`
4. 보드 계약, coverage 보고, 최종 보고서 → 결과 커밋. push·보드 실행은 하지 않는다.
