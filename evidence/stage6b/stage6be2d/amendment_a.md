# Stage 6B-E2D Amendment A — 판정 코드 placement identity 정정과 9 boot 재측정 (`POSTHOC_JUDGE_CORRECTION`)

승인: Stage 6B-E2D Amendment A 공식 지시(2026-11-17). 원래 계약 `contract.md`(`3ca60a7`)는 이 문서에 적은 것 외에는 그대로다.

## 1. 원래 세션 보존

- boot 440–442 원시 자료, 세션 로그, 복원 기록은 `raw/`(`07b2dc9`, `raw.sha256` 41 파일)에 그대로 둔다. 원래 판정 MEASUREMENT_INVALID도 바꾸지 않는다.
- 원래 manifest `workloads/e2d_manifest.json`(boot 440–448)과 원래 판정 코드(`3ca60a7`의 `stage6be2d.py`)도 git에 그대로 있다.
- 440–442 값은 결함 진단과 회귀 테스트에만 쓴다. 새 결과와 합치지 않고, 새 세션의 빠진 조건을 대신하지도 않는다.

## 2. 정정 (이 단계 판정 계층에서만; 공유 모듈 `stage4k`·`stage4aoe`·`stage6bb`는 바꾸지 않음)

- `stage4k.identity`의 고정 항 `placement == 0`을 `stage6be2d.placement_identity`가 다음 항으로 바꾼다.
  - **모든 RUN의 placement = 동결 manifest의 기대 placement**(`e2d_manifest_a.json`, 구성별 `PLACEMENT`: W0-P1만 1).
  - 기대값은 manifest를 만들 때 DRWL header word 7과 같아야 하고, 다르면 manifest 생성이 실패한다.
  - 추가 항 `placement_manifest_equals_drwl`: 기대값 = identity_a1의 DRWL 유래 기대 placement.
- 다른 identity 항은 모두 그대로다: REGIONCFG(DRWL placement와 n_base에서 계산), n_base, QCONFIG, REGIONCFG_MATCH 플래그, DRWL placement, model_len, schema, IRQ, 출력 CRC·길이, capabilities, workload sha256, 이미지, boot index.
- 관측값을 기대값으로 복사하지 않는다. CONFIG_MISMATCH 검사를 끄지 않는다.

## 3. 바뀐 것과 바뀌지 않은 것

| 항목 | 상태 |
|---|---|
| boot 번호 | 440–448 → **449–457**(같은 순서: REF, W0-P0, W0-P1, W1-P0, W1-P1 @L500 → W1-P1, W1-P0, W0-P1, W0-P0 @L1000) |
| manifest | 새 파일 `e2d_manifest_a.json`(boot와 placement 필드만 다름) |
| run root·evidence root | `~/evsweep_s6be2d_a_*`(새 경로) |
| 연구 질문, 4구성, 지연 500/1000, DRWL·이미지 digest, Vela 예상값(47,258 / 117,480 / 70,222), MAC 20,736, PMU pass, 5 % 기준, 출력 검증, 판정 규칙·허용폭 | **그대로** |

## 4. 예산

새 세션은 최대 9 boot / 90 RUN(warm-up 18, 측정 72)이다. E2D 누적 상한은 12 boot이고, 추가 재시험은 없다. 새 세션에서 Gate가 실패하면 사전 규칙대로 멈춘다.

## 5. 검증

- 테스트(DRAM/SRAM 기대·관측 4조합, 빈 기록, 일부 RUN 불일치, manifest 대 DRWL)
- boot 440–442 회귀: 정정 후 REF·W0-P0·W0-P1 VALID. 기대 placement를 바꾸면 CONFIG_MISMATCH(`identity placement`), REGIONCFG를 조작하면 CONFIG_MISMATCH(`identity regioncfg`), digest를 바꾸면 workload sha256
- 공유 모듈 테스트는 그대로 통과(`test.sh`)
- mutation 35/35

## 6. 보고 구분

원래 세션(440–442, 원래 계약, 판정 결함, MEASUREMENT_INVALID)과 정정 세션(449–457, Amendment A, 정정 판정 코드, 독립 판정)을 나눠 보고한다. 정정 후 성공을 원래 계약이 처음부터 검증한 결과처럼 쓰지 않는다.
