# 논문용 그림·표 (요청 순서)

모든 값은 기존 동결 결과에서 생성했다(새 측정 없음). 생성 코드는 `host/analysis/fig*.py`이며 matplotlib이 필요하다.

| 순서 | 폴더 | 요청 | 산출물 | 출처·조건 |
|---|---|---|---|---|
| 1 | `01_fig1` | 그림 1 | 1-A `fig1a_mac_per_cycle.png`, 1-B `fig1b_mac_vs_npu_active.png`, 보조 표 `fig1_shape_table.png`, Raw `fig1_raw_data.csv` | Stage 6C F1·F2·F4·F5, image 14077be, TA profile 1 |
| 2 | `02_add_prediction_check` | 추가 그림 (AD G_0 외삽, G_V H1-UC 일치) | `add_prediction_vs_inmodel.png`, `add_prediction_raw_data.csv` (모델 내부 그룹 / 독립 연산 구분) | X3 Amendment C + 6C F5 + 6B H1-UC, TA profile 1 |
| 3 | `03_fig2` | 그림 2 (원본·직렬 명령 흐름, 측정창) | 2-A `fig2a_kws_command_stream.png`, 2-B `fig2b_ad_command_stream.png`, `fig2_command_order.csv` | X3 Amendment C DRWL 명령 스트림(실제 순서), image f0baf8c |
| 4 | `04_add_x3_validation` | 추가 그림 (계측 검증 Raw Data) | `x3_validation_table.png`, `x3_validation_raw_data.csv` | X3 Amendment C B0/B1/B2–B4 |
| 5 | `05_fig3` | 그림 3 (F2 C8/C16) | `fig3_f2_vela_vs_board.png`, 상세 표 `fig3_f2_detail.csv` | Stage 6C F2, image 14077be, TA profile 1 |
| 6 | `06_add_model_fidelity` | 추가 표 (모델별 Fidelity, Notion 토글용) | `model_fidelity.md`, `model_fidelity.csv` | Stage 6F-0, cycles_total 공식 기준 |
