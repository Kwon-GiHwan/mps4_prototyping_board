# 정오표 — 모델 board/Vela 비율의 Vela 값은 NPU 항 합이다 (2026-11-18, X3 계약 준비 중 발견)

- **발견 경위**: Vela 5.0.0 `--verbose-performance` 출력(`evidence/stage6ex3/vela/`)을 확인했다. kws·ad 컴파일의 명령 스트림은 m7 측정 스트림과 같다(`21564a54`, `093dcda9`).
- **Vela summary의 두 값**:
  - `cycles_npu`(kws 86,324, ad 140,277)는 per-layer NPU 열(연산 계산 항)의 합이다.
  - `cycles_total`(kws 102,248, ad 148,328)은 per-layer Op Cycles(연산별 max(NPU, SRAM AC, DRAM AC))의 합이다.
- **기존 결과가 쓴 값**: `results/fi101_stage6/whole_model_comparison.csv`의 `vela_npu_cycles`는 `cycles_npu`, 즉 NPU 항 합이다. 6-M·6D·6E-0의 모델 board/Vela 비율은 모두 이 값을 기준으로 한다.

**틀린 서술**(결과 파일은 바꾸지 않는다):
- 6E-0 README §8 "Vela 모델 값은 연산별 max(항)의 합이며 중첩 없는 실행을 가정한다": 모델 board/Vela에 쓴 값은 max의 합이 아니라 NPU 항의 합이다. max의 합은 `cycles_total`이다.
- 6E-0 §8 표 "Σ Vela op cycles 대 모델 값 차이는 매핑 범위 차이": 실제로는 Σ op cycles = `cycles_total`이고, 모델 값 = `cycles_npu`다. 범위 차이가 아니라 서로 다른 항이다.

**영향**:
- 6D·6E-0의 모델 board/Vela 비율은 "보드 NPU_ACTIVE ÷ Vela 계산 항 합"으로 읽어야 한다.
- `cycles_total` 기준으로 다시 쓰면 kws 91,824.5/102,248 = 0.898, ad 145,949.5/148,328 = 0.984다(기술; 판정 재계산 없음).
- X3 계약은 두 값을 구분해 쓴다.
