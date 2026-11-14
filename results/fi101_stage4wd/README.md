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

## 보드 측정 (계약 `contract.md` 동결 fc2330f; boot 402–409, 보드 시각 19:37–20:04Z, TA profile 1, 이미지 70090f1, DDR/EXT)

8 boot / 80 RUN 모두 VALID: PASS_EXACT, workload sha256, A1 정체성 (n_base 5, REGIONCFG 0x15F, QCONFIG 3, placement 0, 펌웨어 플래그).
재현 Gate PASS (boot 394 기준: AO 허용폭 안, WD 1,042.5 vs 1,051, range 합 안). 출력 불일치는 없었다.
복원: RESTORE VERIFIED (m6 digest가 이전과 같음), postflight PING state 1, 카드 분리, SESSION DONE.
원시 데이터 134개 파일 (`evidence/stage4wd/raw`, `raw.sha256`, 보드와 sha256 일치). judge 결과와 독립 재계산이 같다.

| boot | config | encoded / staged B | spatial block | N_OFM | WD_ACTIVE (range) | WD_STALLED | MAC / DPU | SRAM rd / wr (예측과 같음) | NPU_ACTIVE A / B |
|---:|---|---|---:|---:|---:|---:|---|---|---:|
| 402 | h24 dense | 2,752 / 4,032 | 8 | 55,296 | 1,042.5 (94) | 6,837 | 2,304 / 1,152 | 2,016 / 252 | 21,086 / 21,124 |
| 403 | w_small | 1,536 / 2,816 | 8 | 55,296 | 1,152 (39) | 6,532 | 2,304 / 1,152 | 1,408 / 176 | 21,246.5 / 21,180 |
| 404 | w_sparse75 | 1,168 / 2,448 | 8 | 55,296 | 914 (49) | 6,542.5 | 2,304 / 1,152 | 1,224 / 153 | 21,458.5 / 21,791.5 |
| 405 | w_sparse90 | 640 / 1,920 | 8 | 55,296 | 934.5 (42) | 6,811.5 | 2,304 / 1,152 | 960 / 120 | 21,122.5 / 21,221.5 |
| 406 | h23 | 2,752 / 4,032 | 8 | 52,992 | 1,080 (29) | 6,491 | 2,208 / 1,104 | 2,016 / 252 | 20,917.5 / 20,477 |
| 407 | h32 | 2,752 / 4,032 | 12 | 73,728 | 1,589 (18) | 11,005 | 3,072 / 1,536 | 3,024 / 252 | 27,128.5 / 27,873 |
| 408 | h34 | 2,752 / 4,032 | 12 | 78,336 | 1,568.5 (37) | 10,578.5 | 3,264 / 1,632 | 3,024 / 252 | 29,374.5 / 29,162 |
| 409 | h36 | 2,752 / 4,032 | 12 | 82,944 | 1,532 (74) | 11,313 | 3,456 / 1,728 | 3,024 / 252 | 30,715.5 / 30,651 |

### 판정 (사전 규칙)

- **실험 B: BLOCK_LIKE.** 같은 spatial block 수 안에서는 WD_ACTIVE가 같고 (8개: 1,080 ≈ 1,042.5; 12개: 1,589 ≈ 1,568.5 ≈ 1,532), 두 묶음은 다르다.
  - N을 따르는 증가는 없다. 12-block 묶음에서는 오히려 N이 커질수록 약간 줄었다.
  - N 가설 예측 (h32 1,390, h34 1,471)은 실측과 맞지 않는다.
  - → 같은 weight에서 WD_ACTIVE는 출력 원소 수가 아니라 **spatial OFM block 수 (= weight 재스트리밍 횟수)**와 함께 움직인다.
  - 내부 재디코딩 메커니즘은 PMU로 직접 관측한 것이 아니다.
- **실험 A: CONSTANT** (also_satisfied 없음).
  - encoded가 2,752 → 640 B (1/4.3)로 줄어도 WD_ACTIVE는 914–1,152 범위에 머물러, 허용폭 (range 합)으로 dense와 같다.
  - encoded 비례 예측 (sparse90 242)과 staged 비례 예측 (496)은 기각된다.
  - POST_HOC_DESCRIPTIVE: small +10.5 %, sparse −11 ~ −12 %로 크기 순서와 맞지 않는다 (MONOTONE 아님).
  - 해석 (가설): 이 Conv에서 WD 활동은 압축된 바이트 수가 아니라, 풀어서 내보내는 weight 수와 block 반복으로 정해지는 쪽에 가깝다.
- **계산 활동: MAC_SAME + DPU_SAME.** 0 weight가 90 %여도 MAC_ACTIVE 2,304, MAC_DPU_ACTIVE 1,152는 그대로다 (모든 RUN). 0 weight 건너뛰기는 관측되지 않았다.
- **SRAM 재스트리밍 규칙: HOLDS** (8개 모두 정확히). staged 크기만 바뀐 실험 A에서도 SRAM rd = 8 × staged/16이다.
  - 따라서 SRAM 재읽기 바이트는 1,920 / 4,032로 줄었는데 WD_ACTIVE는 거의 그대로다.
  - **"SRAM 재읽기 B ÷ WD ≈ 32 B/cycle"은 WD 처리율이 아니다** (dense 30.9, sparse90 16.4 B/cycle). 계약 §0-5의 제한과 맞는다.
- **실행 비용 (기술 통계)**:
  - 실험 A에서 NPU_ACTIVE는 21,086–21,458.5로 거의 같고 WD_STALLED는 6,532–6,837이다.
  - 실험 B에서 NPU_ACTIVE와 WD_STALLED는 block·N과 함께 늘었다.
  - WD_STALLED를 실행 시간 원인으로 배정하지 않는다.
