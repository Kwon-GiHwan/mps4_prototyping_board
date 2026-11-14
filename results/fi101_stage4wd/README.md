# fi101_stage4wd — Weight Decoder: 기존 결과 재분석과 실험 후보 (보드 측정 없음)

조건: TA profile 1, 이미지 70090f1, Vela 5.0.0 (MLEK 옵션). 보드 수치는 모두 기존 원시 RUN에서 다시 계산했다.
해설: `docs/plan/stage4wd_characterization_plan.md`. 계약 초안: `evidence/stage4wd/contract_draft.md`. 판정: `READY_FOR_BOARD_CONTRACT_REVIEW`.

| 파일 | 내용 | 명령 |
|---|---|---|
| `inventory.json`, `wd_inventory.csv` | weight stream이 있는 기존 측정 39개: WD/MAC/AO/NPU/beat + 정적 정보 (encoded·staged B, block, SRAM 규칙) | `python3 host/analysis/stage4wd.py inventory results/fi101_stage4wd` |
| `mlek_wd.json` | 7개 MLEK 모델의 WD·MAC·AO·NPU (driver_m7) | 같음 |
| `static.json` | 실험 A·B 후보의 정적 정보와 전제 검사 | `… static evidence/stage4wd/workloads results/fi101_stage4wd` |
| `predictions.json` | 4AO sweep fit (WD = 60.6 × block + 96.7), 실험 B·A 예측 | `… predict results/fi101_stage4wd` |
| `wd_block_scan.json` | H 18–36 block 스캔 (컴파일만) | 컨테이너 `stage4wd_models.py <out> scan` |

요점 (POST_HOC_DESCRIPTIVE):
- DDR 배치 측정 35개 모두: SRAM write beat = staged/16 (한 번), SRAM read beat = spatial block × staged/16 (block마다 다시 읽음).
- 같은 weight에서 WD_ACTIVE는 block 수를 따라 늘었다. 이 sweep에서는 block 수 ∝ N이라 둘이 분리되지 않았다 → 실험 B.
- Open Issue WD-1: FC의 encoded / WD_ACTIVE = 34.7–42 B/cycle로, 공식 SWD 최대 32 B/cycle보다 크다.
