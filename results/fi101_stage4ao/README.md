# fi101_stage4ao — AO(Activation Output) 특성: 정적 분석과 예측 (보드 측정 없음)

조건: FI101 Ethos-U85 1024 MAC, TA profile 1, 이미지 `70090f1`, DDR/EXT, Vela 5.0.0(MLEK 옵션).
이 폴더의 보드 수치는 모두 기존 Stage 4/4C/4K 원시 RUN에서 다시 계산한 것입니다. Stage 4AO 자체의 보드 RUN은 없습니다.
해설: `docs/plan/stage4ao_characterization_plan.md`. 계약 초안: `evidence/stage4ao/contract_draft.md`. 판정: `NEEDS_REVISION`.

| 파일 | 내용 | 만든 명령 |
|---|---|---|
| `phase_a.json`, `phase_a_table.csv` | Stage 4K 10개 구성의 AO 재분석, C0 보정(5 boot), OFM 크기가 다른 기존 데이터(POST_HOC) | `python3 host/analysis/stage4ao.py phase-a results/fi101_stage4ao` |
| `static.json`, `stage4ao_static.csv` | Phase B/C 컴파일 정보, 비교 가능성 판정(원안 `NEEDS_REVISION`, 수정안 `COMPARABLE`), Phase C 스트림 차이, Phase D probe | `… static evidence/stage4ao/workloads results/fi101_stage4ao` |
| `predictions.json` | M1–M4 예측과 허용폭(보드 데이터 전 고정) | `… predict evidence/stage4ao/workloads results/fi101_stage4ao` |
| `block_scan.json` | 컴파일만 한 block 조사(H, W 6–72). 측정 후보 목록이 아님 | `stage4ao_models.py <out> scan` (컨테이너) |
| `vela500_SUPPORTED_OPS.md` | Vela 5.0.0 `--supported-ops-report` 원문 | 컨테이너 |

요약:
- Stage 4K: AO_ACTIVE 3,484.5–3,562.5(N/AO 15.52–15.87, 16의 97.0–99.2 %). MAC_ACTIVE는 18배 차이. OFM이 모두 같아 비례 검증은 불가.
- Phase B 원안: 24·36만 6×12×96 block으로 같음. 12는 8×24×32, 48은 10×8×96 → `NEEDS_REVISION`.
- Phase C: NONE/RELU/RELU6의 차이는 `NPU_SET_ACTIVATION_MIN/MAX` 값뿐 → 선정 규칙 통과.
- Phase D: LUT는 Conv AO에 융합, Conv→ADD·ADD→MUL은 CB(CHAINED) 사용, LEAKY_RELU는 POOL+LUT, INT16은 DRWL 패킹 실패.
