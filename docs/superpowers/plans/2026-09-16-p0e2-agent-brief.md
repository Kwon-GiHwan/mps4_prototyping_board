# P0-E2 작업 브리프 — Orca 워커용

계약서: `docs/superpowers/plans/2026-09-16-p0e2-two-workload-extension-plan.md`
**계약서를 먼저 전부 읽어라.** 이 브리프는 환경 사실과 순서만 담는다.
계약서와 충돌하면 계약서가 이긴다.

## 0. 한 줄 요약

Wav2Letter와 MobileNetV2의 U85 per-layer IRQ 계측을 6셀(2모델 × 256_Low /
512_Low / 512_Mid512) 수행하고, 기존 5개 모델과 같은 기준으로 그룹별 비용을
산출한다.

## 1. 환경 사실

```sh
ssh gihwan                     # ssh.gihwan.uk, cloudflared, x86_64
                               # gihwan-local / gihwan-web 은 다른 장비다. 쓰지 마라.
docker exec benchmark-runner sh -lc "..."
```

컨테이너 안:

| 경로 | 내용 |
|---|---|
| `/workspace/per-layer-profiling/` | 정제된 도구: `patch-vela.py`, `patch-driver.py`, `test-determinism.sh` |
| `/tmp/per-layer-profiling/` | 탐색 사본 + **U55** 결과. 참고만. U85 표에 섞지 마라. |
| `/opt/arm/ml-embedded-evaluation-kit` | MLEK |
| `/usr/local/lib/python3.10/dist-packages/ethosu/vela/` | Vela (패치 대상) |

Mac에서는 아무것도 빌드되지 않는다. `arm-none-eabi-gcc`가 없고 소스 일부가
컨테이너에만 있다.

## 2. 참고할 기존 자료

- `docs/paper/mechanism/U85_MECHANISM_ANALYSIS_PLAN.md` — 방법·게이트의 원본
- `docs/paper/mechanism/U85_LAYER_PROFILING_PATH.md` — 패치 지점과 IRQ 의미론
- `docs/paper/mechanism/evidence/20260902-p0d2-profiled-irqhistory/reports/pd2_orchestrator.log`
  — 9월 캠페인이 실제로 어떻게 돌았는지. IRQ 수, 빌드 다이제스트, `x3 exact-equal` 형식
- `docs/paper/mechanism/pd_analyzer.py`, `pd_groups.py` — 분석·집계. **재사용하라.**
  새 집계 규칙을 만들지 마라.
- `docs/paper/mechanism/U85_FORMAL_MATRIX.csv` — 추가할 표의 형식

## 3. 순서

1. **사전 상태 동결.** 패치 대상 파일들의 `shasum -a 256`을 기록한다.
   복원은 눈으로가 아니라 이 다이제스트로 검증한다.
2. **모델 SHA 확인.** 두 모델의 SHA-256이 `analysis/canonical_cells.csv`의
   동결값과 같은지 확인. 다르면 STOP (`RULE_P0E2_MODEL_SHA`).
3. **툴체인 동일성 확인.** Vela·MLEK·core-driver·FVP 식별자가 9월 캠페인과
   같은지. 다르면 STOP (`RULE_P0E2_TOOLCHAIN`).
4. **clean 6셀 먼저.** 패치 없이 전체 모델 사이클을 3회씩. 이 값이 없으면
   방향 분류(`delta`)도 sum-coherence 검사도 못 한다.
5. **패치 적용 → 결정성 사전확인.** 대표 아티팩트 1개로 profiled 경로를
   3개 프로세스 실행. 전체 지표 벡터가 정확히 같지 않으면 **STOP**.
   평균이나 허용오차를 만들어내지 마라 (`RULE_P0E2_REPS_EXACT`).
6. **profiled 6셀.** 배치 분할 금지. 연산 수가 `PROFILING_MAX_LAYERS`를
   넘으면 STOP이지 분할이 아니다 (`RULE_P0E2_LAYER_CAP`).
7. **게이트 실행 + 변이 시험.** 각 게이트를 무력화해 스위트가 RED가 되는지
   확인하고 다이제스트로 복원한다. 살아남는 변이가 있으면 픽스처를 추가한다.
   **변이를 지우지 마라.**
8. **표 생성.** 기존 4개 CSV에 행을 추가한다. 기존 5개 모델의 행은 한 바이트도
   바뀌면 안 된다 — 회귀 검사로 확인하라.
9. **복원.** 패치를 되돌리고 1번의 다이제스트와 일치하는지 확인.
   `__pycache__`를 지우고 나서 결과를 믿어라.
10. **보고.** `P0E2_RESULTS.md`는 계산만. 해석·인과 문장 금지.

## 4. 금지 (계약서 §5 요약)

- Vela 추정으로 실측 칸 채우기
- `/tmp/per-layer-profiling`의 U55 결과를 U85 표에 합치기
- 배치 분할로 레이어 한도 우회
- 결과를 본 뒤 게이트·임계값 완화
- 동결 데이터셋(`3_2_whole_model_pmu.csv` 등)에 병합
- 인과 문장, 세대 간 이벤트 ID 등가 주장
- `inference_runner` 패치로 지표 얻기 — 못 얻으면 그게 결과다
- `origin/main` 푸시
- 운영자 자격증명을 문서·증거·커밋·환경변수·파일에 기록

## 5. 보고 형식

진행 중에는 셀 단위로 짧게. 완료 시:

```
검증 수준: [구문 | 단위 | 통합 | E2E]
실제 실행한 것: ...
실행하지 않은 것: ...
```

게이트는 통과 수가 아니라 **어떤 픽스처가 어떤 규칙을 밟았는지**로 보고하라.
변이 시험 결과(몇 개가 RED였는지, 살아남은 것이 있었는지)를 반드시 포함하라.

## 6. 막히면

- 계약서가 답하지 않는 판단이 필요하면 **멈추고 물어라.** 범위를 늘리지 마라.
- 실패한 셀은 조용히 빼지 마라. 실패도 결과다.
- 예상 소요는 1.5~2시간이지만 profiled 실행의 감속 계수가 측정된 적이 없다.
  크게 벗어나면 보고하라.
