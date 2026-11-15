# Stage 6B — Model-informed 1×1 DepthFirst MAC Characterization (계획·결과 요약)

지시: ChatGPT 경유 owner 지시 (2026-11-15). 범위는 보드 없는 분석과 계약 초안까지다. 보드 배포·RUN·계약 동결은 하지 않는다.

## 연구 질문과 이번 단계의 답

| RQ | 이번 단계 (정적) |
|---|---|
| RQ1 처리율 | 측정 전이다. 기존 640·768을 적용할 수 있는 같은 형상의 후보는 없다 |
| RQ2 형상·block | 26개 후보의 block 구성 (OFM block 2x2x32 ~ 20x6x64, ublock 2x2x32 / 2x4x16 / 1x4x32)을 정리했다 |
| RQ3 컴파일러 매핑 | 원본 weight로 독립 컴파일하면 **traversal·block·ublock은 26/26 같다**. 배치 (Conv OFM의 Sram/Dram)는 래퍼 형태에 따라 달라진다 |
| RQ4 coverage | 원래 규칙으로는 wav2letter +17.0 %p뿐이다. 개정 A 시 (POST_HOC 계산) ad 95.4 %, kws 71.0 % 등 |

## 단계

1. Phase 1–2: `host/analysis/stage6b.py candidates` → `evidence/stage6b/candidates.json`
2. Phase 3: 컨테이너 `host/container/stage6b_models.py` (F_PLAIN, F_CTX, 2회 컴파일) → `evidence/stage6b/compiled`
3. Phase 2 (선정)–4: `stage6b.py run` → `results/fi101_stage6b/*.csv`, `summary.json`
4. Phase 5: `evidence/stage6b/contract_draft.md`

최종 판정 (원래 규칙): **NEEDS_REVISION**. 상세와 개정 A 제안: `results/fi101_stage6b/README.md`.
