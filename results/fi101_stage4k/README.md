# Stage 4K — Conv 1×1·3×3: 정적 분석과 기존 결과 재계산 (보드 측정 없음, 2026-11-14)

본문: `docs/plan/stage4k_conv_kernel_plan.md`. 보드 계약 초안: `evidence/stage4k/contract_draft.md` (동결 전).

| 파일 | 내용 | 만든 명령 |
| --- | --- | --- |
| `static.json`, `stage4k_static.csv` | 10개 구성의 Vela 전략, block·ublock, 채움률, IFM step, weight 크기, Vela 추정 사이클, MAC 정의 3종, 커널 레지스터, 1×1 SAME 대조군, 커널 간 IFM 동일 여부 | `python3 host/analysis/stage4k.py static evidence/stage4k/workloads results/fi101_stage4k` |
| `prior.json` | 기존 1×1 측정(Stage 4 boot 330, 4C-2 344–346, 4C-2b 348–350: `83398c7`; placement A 367: `70090f1`)을 원시 RUN에서 다시 계산한 값. 모두 TA profile 1 | `python3 host/analysis/stage4k.py prior results/fi101_stage4k` |
| `predictions.json` | 사전 등록 MAC_ACTIVE 가설 8개 × 10개 구성 | `python3 host/analysis/stage4k.py predict evidence/stage4k/workloads results/fi101_stage4k` |

여기의 수치는 모두 컴파일 산출물이나 기존 측정에서 나왔다. 새 보드 측정값은 없다.
