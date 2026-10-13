# P0-E2 — mechanism 캠페인 워크로드 2종 확장 (사전등록 계약서, 초안)

상태: **운영자 지시로 실행 승인 (2026-09-16). 매니저 GO 없음 — §9 참조.**
작성: 2026-09-16. 앵커: 데이터가 존재하기 전에 동결한다.

---

## 0. 왜 필요한가

`U85_GROUP_DIFFERENTIAL.csv`에는 5개 워크로드의 그룹별 비용이 있고
Wav2Letter·MobileNetV2가 없다. 배제 사유는 실행 불가가 아니라
`U85_MECHANISM_ANALYSIS_PLAN.md:28`의 워크로드 상한이다.

> Main-track SHAs are the frozen `canonical_cells.csv` values; a mismatch at
> build time is a STOP. `mobilenet_v2` and `wav2letter` are excluded (≤6 cap).

같은 계획서 40행이 `No other MAC, memory mode, or workload may be added under
this plan.` 이므로 **이 계획서 아래에서는 추가할 수 없다.** 본 문서가 그 확장을
별도 계약으로 등록한다.

두 모델은 U85 전 MAC에서 실행된다(`analysis/executability.csv`: 128–2048 전부
`EXECUTABLE / RAN_AT_DEFAULT_ARENA`). `NOT_EXECUTABLE_MEMORY`는 전체 6셀이며
전부 Wav2Letter의 **U55** 32·64·128 MAC이다. U85와 무관하다.

기존 자료로 채울 수 없는 이유:
- `vela_verbose`의 per-layer는 **Vela 추정**이다. 실측과 귀속 단위가 다르다
  (연산 단위 vs IRQ 귀속 클러스터). 두 방식이 모두 있는 5개 모델에서 Conv 비중
  차이가 0.0–41.2%p다. 추정으로 실측 칸을 채우지 않는다.
- 서버 `/tmp/per-layer-profiling/models/{asr,ic}-256-b*`에 IRQ 실측이 있으나
  **`Ethos_U55_High_End_Embedded`**이고, `ETHOSU_PROF_START/END`로 15연산씩
  끊어 돌린 미등록 탐색 실행(7/1·7/4)이다. U85 자료가 아니다.
  `U85_LAYER_PROFILING_PATH.md`의 감사 결론과 일치한다:
  *"Prior runs on U85: NONE FOUND. All recorded artifacts are U55."*

## 1. 범위 (닫힌 집합, 확장 금지)

```
워크로드  wav2letter_pruned_int8, mobilenet_v2_1.0_224_INT8
바인딩    256_Low, 512_Low, 512_Mid512          (기존 5종과 동일)
셀        2 × 3 = 6
셀당      clean 3회 + profiled 3회
플랫폼    FVP_Corstone_SSE-320, TA ON, extra_args 없음(기록)
메모리    Dedicated_Sram
Vela      --optimise Performance --config default_vela.ini
빌드      SOURCE_DATE_EPOCH = 1776763519 (MLEK 커밋 타임스탬프에 고정)
```

다른 MAC·메모리 모드·워크로드·플랫폼은 본 계약에서 추가할 수 없다.
모델 SHA-256은 `analysis/canonical_cells.csv`의 동결값과 일치해야 하며
불일치는 STOP이다.

## 2. 방법 (기존 P0-D2 경로를 그대로 사용)

`patch-vela.py`가 `generate_operation_code(emit, npu_op)` 직후에
`cmd0.NPU_OP_IRQ(param=op_index)`를 삽입(`NpuDmaOperation` 제외),
`patch-driver.py`가 IRQ마다 PMU 스냅샷 → 리셋 → IRQ 클리어 → 세마포어 미신호.
두 패치 모두 백업 후 `--revert` 가능.

**배치 분할을 쓰지 않는다.** 9월 캠페인은 YOLO 138 IRQ를 한 번에 처리했다
(`pd2_orchestrator.log`). 두 모델의 연산 수는 그 범위 안이다.
`PROFILING_MAX_LAYERS = 256` 한도 초과 시 STOP이며, 분할로 우회하지 않는다.

PMU 집합은 P0-A가 `VERIFIED_AVAILABLE`로 분류한 것만:
`CCNT`, `NPU_ACTIVE`, `SRAM_RD/WR_DATA_BEAT_*`, `EXT_RD/WR_DATA_BEAT_*`.
Stall 계열은 `SEMANTICS_UNVERIFIED`이므로 분석 필드에서 제외한다.

## 3. 게이트 (fail-closed, 규칙 id 필수)

| id | 검사 | 실패 시 |
|---|---|---|
| `RULE_P0E2_MODEL_SHA` | 두 모델 SHA-256 = canonical 동결값 | STOP |
| `RULE_P0E2_TOOLCHAIN` | Vela·MLEK·core-driver·FVP 식별자가 9월 캠페인과 동일 | STOP |
| `RULE_P0E2_PATCH_IDENTITY` | 적용된 패치 다이제스트 = 9월 캠페인 패치 | STOP |
| `RULE_P0E2_IRQ_VALID` | U85 명령 스트림에서 `cmd0.NPU_OP_IRQ` 수용, IRQ 수 = 삽입 수 | STOP |
| `RULE_P0E2_LAYER_CAP` | 연산 수 ≤ `PROFILING_MAX_LAYERS` | STOP (분할 금지) |
| `RULE_P0E2_REPS_EXACT` | 3회 프로세스의 전체 지표 벡터가 정확히 동일 | STOP (평균·허용오차 도입 금지) |
| `RULE_P0E2_SUM_COHERENT` | per-op 합 vs clean 전체 = 계측 잔차 상수 이내 | FAIL |
| `RULE_P0E2_OUTPUT_CRC` | clean·profiled 출력 CRC 동일 | FAIL |
| `RULE_P0E2_IDENTITY_JOIN` | (workload, op_index, op_type, IFM/OFM shape)로 조인, 행 순서 금지 | FAIL |
| `RULE_P0E2_RESTORE` | 종료 후 패치 복원, 트리 다이제스트가 사전 상태와 일치 | FAIL |

모든 게이트는 변이 시험한다 — 검사를 무력화하고 스위트가 **RED**가 되는지
확인한 뒤 다이제스트(`shasum -a 256`)로 복원한다. 살아남는 변이는
도달 픽스처가 없다는 뜻이므로 픽스처를 추가한다.

## 4. 사전등록 판정 (닫힌 집합, 사후 작성 금지)

방향 분류는 기존 규칙을 그대로 쓴다(임계값 없음):

```
delta(b) = clean_cycles_512(b) − clean_cycles_256
REGRESSING(b) iff delta > 0 · IMPROVING(b) iff delta < 0 · UNCHANGED(b) iff delta = 0
```

그룹 집계는 `pd_groups.py`의 기존 규칙 — 바인딩 쌍의 **어느 한쪽에서라도**
귀속 단위를 공유하면 union-find로 병합해 양쪽에서 정확한 합이 되는
최소 공통 분할을 만든다. 새 병합 규칙을 만들지 않는다.

각 셀의 결과는 `PASS` / `FAIL` / `UNPROVEN` 삼분값이다. "아마 괜찮다"는 없다.

**예측 (데이터 보기 전 기록).** Vela 추정 기준 Conv 비중은 Wav2Letter 99.9%,
MobileNetV2 80.5%다. 실측이 이와 다르게 나와도 실측을 채택한다. 이 예측은
추정↔실측 불일치 폭을 5개 모델(0.0–41.2%p)에 이어 기록하기 위한 것이며
판정 기준이 아니다.

## 5. 금지

- Vela 추정으로 실측 칸을 채우기
- U55 탐색 실행 자료를 U85 표에 합치기
- 배치 분할로 레이어 한도를 우회하기
- 결과를 본 뒤 게이트·임계값 완화
- 동결 데이터셋(`3_2_whole_model_pmu.csv` 등)에 병합
- 인과 문장("ublock이 원인", "메모리 대역폭이 원인")
- 세대 간 이벤트 ID 등가 주장

## 6. 산출물

```
U85_FORMAL_MATRIX.csv            6행 추가 (기존 행 불변)
U85_ATTRIBUTION_UNITS.csv        두 모델의 unit 행 추가
U85_256_512_DIFFERENTIAL.csv     두 모델 추가
U85_GROUP_DIFFERENTIAL.csv       두 모델 추가
P0E2_RESULTS.md                  계산 결과, 해석 없음
P0E2_LIMITATIONS.md              한계
evidence/2026MMDD-p0e2/          uart·run-vector·manifest, 다이제스트
```

기존 5개 모델의 행은 한 바이트도 바뀌지 않아야 한다 (회귀 검사로 확인).

## 7. 예상 소요

executability 캠페인의 셀 실측 기준(U85-256 빌드+1회: MobileNetV2 75s,
Wav2Letter 150s, 빌드 약 50s 고정):

| 항목 | 추정 |
|---|---|
| 계측 (6셀 × clean 3 + profiled 3) | ~65분 |
| 패치 적용 + core-driver 재빌드 | ~10분 |
| 결정성 사전확인 | ~10분 |
| 분석·게이트·표 | ~15분 |
| 복원 + 다이제스트 검증 | ~10분 |
| **합계** | **1.5 ~ 2시간** |

**추정의 약점:** profiled 실행의 감속 계수가 저장소에 측정된 적이 없다.
1.5–3배로 가정했고, 5배면 Wav2Letter 쪽이 50분 → 100분이 된다.
Wav2Letter가 전체의 약 2/3를 차지한다.

## 8. 승인이 필요한 것

- `U85_MECHANISM_ANALYSIS_PLAN.md`의 워크로드 상한(≤6)을 넘는 확장
- MLEK 사용 (표준 제약상 기본 BLOCKED, 단계별 승인 필요)
- 원격 컨테이너 `benchmark-runner`에서의 빌드·실행

보드 접근은 필요 없다. FVP만 사용한다.

---

## 9. 승인 상태 (2026-09-16 기록)

**매니저 GO 문서는 존재하지 않는다.** H13(`2026-09-14-h1-h3-verification-GO.md`)과
H3-R(`2026-09-15-h3r-verification-GO.md`)처럼 전달받아 축어 기록한 GO가 이
확장에는 없다.

실행은 **운영자(저장소 소유자)의 직접 지시**로 진행한다. 2026-09-16 세션에서
계약서 검토 후 "orca로 다른 에이전트에 계측을 맡기자"는 지시가 있었다.
본 절이 그 승인의 전부이며, 매니저 승인으로 표기하지 않는다.

이 구분은 결과 보고서에도 그대로 남긴다. 산출물에 "매니저 승인 하에 수행"이라고
쓰지 않는다.

범위는 §1의 6셀에서 확장하지 않는다. 보드 접근은 사용하지 않는다.
