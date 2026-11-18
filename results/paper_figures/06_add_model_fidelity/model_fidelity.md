# 모델별 Vela Fidelity (Stage 6F-0)

- 출처: Stage 6F-0 (`results/fi101_stage6f0/stage6f0_summary.json`). Board = driver runner `driver_m7`, TA profile 1 (EXT RLATENCY 500), pass A 측정 RUN 중앙값. Vela 5.0.0, `Ethos_U85_SYS_DRAM_Mid_1024`.
- **공식 비교 기준은 cycles_total**(= Σ per-layer Op Cycles = Σ max(NPU, SRAM, DRAM))이다. cycles_npu(= Σ NPU 항)는 값만 함께 적고, 기존 cycles_npu 기반 비율은 이 표에서 쓰지 않는다.
- 상대 오차 = (Board − cycles_total) / cycles_total. 판정: ratio < 0.9 OVER(과대예측), > 1.1 UNDER(과소예측), 그 밖 AGREE. 경계 0.9·1.1 × cycles_total이 Board ± range 안이면 INSUFFICIENT_EVIDENCE.

| 모델 | Board NPU_ACTIVE (range) | Vela cycles_npu | Vela cycles_total | Board / cycles_total | 상대 오차 | 판정 (cycles_total) |
|---|---:|---:|---:|---:|---:|---|
| AD | 145,949.5 (1,774) | 140,277 | 148,328 | 0.984 | -1.6% | AGREE |
| KWS | 91,824.5 (2,423) | 86,324 | 102,248 | 0.898 | -10.2% | INSUFFICIENT_EVIDENCE |
| MobileNetV2 | 1,450,096.0 (3,643) | 1,737,984 | 2,358,886 | 0.615 | -38.5% | OVER |
| RNNoise | 50,508.0 (2,079) | 31,334 | 33,040 | 1.529 | +52.9% | UNDER |
| VWW4 | 234,669.0 (2,924) | 222,478 | 263,411 | 0.891 | -10.9% | INSUFFICIENT_EVIDENCE |
| Wav2Letter | 4,133,297.5 (2,571) | 5,233,545 | 5,761,355 | 0.717 | -28.3% | OVER |
| YOLO-Fastest | 447,601.5 (2,866) | 478,546 | 584,760 | 0.765 | -23.5% | OVER |
