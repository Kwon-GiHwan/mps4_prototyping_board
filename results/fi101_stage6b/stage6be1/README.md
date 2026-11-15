# Stage 6B-E1 — H1-UC 전향적 검증 (보드 결과)

## 조건과 근거

- MPS4 FI101, Ethos-U85 1024 MAC, **TA profile 1**, Driver Runner 이미지 `70090f1`, DDR/EXT, WAIT_WFE.
- boot 421–427(2026-11-15 14:48–15:11Z): 7 boot, 70 RUN(측정 RUN 56).
- 계약 `evidence/stage6b/stage6be1/contract.md`(`d39448c`, 후보 컴파일 전 동결).
- 선정·예측·판정 코드 동결 `3a83175`, Preflight PASS `2c667b1`.
- 원시 데이터 `evidence/stage6b/stage6be1/raw/`(83개 파일, `raw.sha256` 보드 = Mac).
- 복원: `RESTORE VERIFIED`, postflight 카드 분리.

| 판정 | 값 |
| --- | --- |
| **H1-UC (주 판정)** | **INSUFFICIENT_EVIDENCE** — Primary Valid 0/6(6개 모두 UNSTABLE). 동결된 5 % 기준에 따른 결과다 |
| MAC-only Diagnostic (공식 집계 밖) | 6/6이 H1-UC 예측과 정확히 일치. 6개 중 4개는 경쟁 가설 8개 중 어느 것도 일치하지 않았다 |
| D-PW (보조) | INSUFFICIENT_EVIDENCE 유지(Primary Valid 없음). 진단 6/6에서 D-PW 일치, D-U16은 1/6 |
| 기준 형상 | repro-gate PASS: MAC·DPU 3,456, 출력, 상수 카운터가 boot 375와 같다. NPU_ACTIVE 22,734.5 대 22,251(허용폭 안) |

## 선정과 예측 (측정 전 동결, `evidence/stage6b/stage6be1/workloads/predictions.json`)

- 격자 200개 → 적격 175개(PartKernel 25개 제외). 계약 §3 규칙으로 6개를 골랐다.
- 6개 모두 두 번 독립 빌드했고 결과가 같았다. 모두 커널 1×1, DepthFirst, IFM block 깊이 64, Sram 없음(Dram→Dram).

| boot | 형상 | 역할 / 범주 | OFM block / ublock | 커널 (OFM) | Cin 조각 | N_MAC | H1-UC 예측 | H1-UC와 다른 경쟁 가설 수 |
|---:|---|---|---|---|---|---:|---:|---:|
| 422 | Cin72 13×13 Cout96 | E1-A (A, B, D) | 8x14x64 / 2x2x32 | 16 + 80 | 64+8 | 1,168,128 | 2,352 | 8 |
| 423 | Cin136 13×13 Cout96 | E1-B (A, B, D) | 6x14x96 / 2x2x32 | 16 + 80 | 64+64+8 | 2,206,464 | 3,920 | 8 |
| 424 | Cin72 7×7 Cout48 | E1-C (A, B, C) | 8x8x48 / **2x4x16** | 48 | 64+8 | 169,344 | 288 | 6 |
| 425 | Cin200 13×13 Cout96 | E1-D (A, B, D) | 6x14x96 / 2x2x32 | 16 + 80 | 64×3+8 | 3,244,800 | 5,488 | 8 |
| 426 | Cin80 13×13 Cout96 | extra (A, B, D) | 8x14x64 / 2x2x32 | 16 + 80 | 64+16 | 1,297,920 | 2,352 | 8 |
| 427 | Cin72 7×7 Cout112 | extra (A, B) | 7x8x128 / 1x4x32 | 112 | 64+8 | 395,136 | 672 | 7 |

## 측정 결과 (pass A 측정 RUN; MAC/DPU는 4회 모두 같은 값)

| 형상 | 상태 | 예측 | 실측 MAC_ACTIVE | 잔차 | 예측 / 실측 N_MAC/MAC_ACTIVE | 일치한 경쟁 가설 | DPU 실측 (D-PW / D-U16 예측) | NPU_ACTIVE pass A (range) |
|---|---|---:|---:|---:|---|---|---|---|
| Cin72 13×13 o96 | UNSTABLE | 2,352 | 2,352 | 0 | 496.7 / 496.7 | 없음 | 1,764 (1,764 / 1,960) | 10,985 10,148 11,153 10,822 (1,005 = 9.2 %) |
| Cin136 13×13 o96 | UNSTABLE | 3,920 | 3,920 | 0 | 562.9 / 562.9 | 없음 | 3,332 (3,332 / 3,528) | 14,003 12,976 13,987 13,748 (1,027 = 7.4 %) |
| Cin72 7×7 o48 | UNSTABLE | 288 | 288 | 0 | 588.0 / 588.0 | H1-G, 전체 Cout | 216 (216 / 240) | 3,944 3,839 4,052 3,744 (308 = 7.9 %) |
| Cin200 13×13 o96 | UNSTABLE | 5,488 | 5,488 | 0 | 591.3 / 591.3 | 없음 | 4,900 (4,900 / 5,096) | 16,868 17,794 18,125 17,307 (1,257 = 7.2 %) |
| Cin80 13×13 o96 | UNSTABLE | 2,352 | 2,352 | 0 | 551.8 / 551.8 | 없음 | 1,960 (1,960 / 1,960) | 10,685 10,582 10,026 10,191 (659 = 6.3 %) |
| Cin72 7×7 o112 | UNSTABLE | 672 | 672 | 0 | 588.0 / 588.0 | 전체 Cout | 504 (504 / 560) | 5,173 5,295 5,394 5,537 (364 = 6.8 %) |
| 기준 Cin48 | VALID | — | 3,456 | — | 768 | — | 3,456 | 865 (3.8 %) |

- UNSTABLE 사유는 6개 모두 "NPU_ACTIVE pass A range > 5 %" 하나다.
- 출력·환경·PMU 검사는 모두 통과했다(보드 `output.bin` = BUILTIN_REF golden, 모든 RUN `output_match`).
- 진단 결과에서 경쟁 가설 8개의 일치 수: H1-G 1, "전체 Cout" 2, 나머지 6개는 0.
- 공간 패딩 제거, min 32 제거, Cin 조각 없음, H1-U16, H1-U8, H1-C16은 6개 모두에서 틀렸다. 진단 자료다.

## 해석과 한계

1. **공식 판정은 INSUFFICIENT_EVIDENCE다.**
   - 지시 §7.1에 따라 MAC-only Diagnostic은 성공 개수에 넣지 않는다.
   - 사후에 5 % 기준이나 판정 규칙을 바꾸지 않는다.
2. **설계 결함(작성자 책임).**
   - 6개 형상의 NPU_ACTIVE는 3.7k–18k 사이클이고, RUN 간 절대 변동은 300–1,260 사이클이다.
   - 6B-R 진단에서 이미 다음이 보였다. NPU_ACTIVE 총량이 작은 형상이 UNSTABLE이 되기 쉽다. 절대 변동은 VALID 형상에서도 수백–천 사이클이다.
   - 그런데 E1 계약은 다음과 같이 정했다. 동률 처리를 "N_MAC 작은 순"으로 두었다. 공간 격자를 7–14로 작게 잡았다. 안정성(최소 NPU_ACTIVE 크기)을 선정 조건에 넣지 않았다.
   - 그 결과 반증 가능한 형상은 골랐지만, 기준을 통과할 수 있는 형상을 고르지 못했다.
   - 이 결함은 계약 작성자(Claude)의 판단 잘못이다.
3. **진단 자료가 보여 주는 것(공식 아님).**
   - 6개 모두 측정 전에 동결한 정수 예측과 같았다.
   - 그중 4개(Cin72·136·200·80, 13×13)는 경쟁 가설 8개 모두와 예측이 갈렸다.
   - 다음 요소가 보인 예측을 전향적으로 맞혔다.
     - 13×13 → 14×14 공간 ublock 패딩
     - Cout 16+80 커널별 패딩
     - Cin 나머지 조각 8·16 → 32
     - ublock 깊이 16(Cin72 7×7 o48)
   - 이 자료로 H1-UC를 반증할 수는 있었지만 반증되지 않았다. 지지 판정은 동결 규칙상 낼 수 없다.
4. 이 결과를 바탕으로 보편 법칙이나 PROSPECTIVE_SUPPORT를 주장하지 않는다.

## DPU/MAC (보조)

- D-PW는 공식 판정상 INSUFFICIENT_EVIDENCE를 유지한다.
- 진단에서는 6/6 일치했다. D-PW와 D-U16을 가르는 5개 형상에서 모두 D-PW가 맞았다(조각 8 → DPU 1사이클, MAC 4사이클).
- D-U8도 6/6이다. 이번 형상에서는 D-PW와 D-U8이 갈리지 않는다.
- DPU/MAC 비율을 회로 점유율로 해석하지 않는다.

## Stage 6 모델 연결 가능성 (지시 §9)

- 결론이 INSUFFICIENT_EVIDENCE이므로 Stage 6 모델 수준 설명력 재평가에 H1-UC를 적용하지 않는다.
- 기존 Stage 6의 `INSUFFICIENT_EVIDENCE`를 유지한다.
- 진단 결과는 다음 조건에서 쓸 수 있는 정적 계산 틀의 후보로만 기록한다: 1×1 DepthFirst, IFM block 깊이 64, ublock 2×2×32·2×4×16·1×4×32.

## 미해결 항목

- H1-UC의 공식 전향 검증. 이번 결과는 진단 6/6뿐이다.
- 작은 형상에서 NPU_ACTIVE 변동이 크게 나오는 원인. 6B-R E3와 같은 항목이다.
- D-PW와 D-U8을 가르는 형상(조각 ≤ 8 중 8의 배수가 아닌 것, 예: Cin 68). 이번 6개에는 없다.
- Vela 커널 분할·ublock 선택 규칙(H1-UC의 입력).

## 다음 단계 권고 (실행하지 않음, 별도 승인 필요)

E1 재시험(E1-R)을 권고한다. H1-UC의 정의, 범주, 예측 규칙은 그대로 두고 **선정 조건 하나만 추가**한다. 이 수정은 기준이 아니라 형상 선정에 관한 것이며 측정 전에 동결한다.
- 추가할 선정 조건: Vela `cycles_total` ≥ 50,000. 기준 형상(22k)의 2배 이상으로, NPU_ACTIVE가 절대 변동 ~1,000 사이클의 20배 이상이 되게 한다.
- 이를 위해 공간 격자를 크게 잡는다(예: 24×24–40×40).
- 5 % 기준은 바꾸지 않는다. 예산은 이번과 같은 7 boot / 70 RUN이다.
- 이번 6개를 그대로 다시 재지는 않는다(같은 결과가 예상되고 반복 측정 금지).

E2·E3·Stage 6C는 시작하지 않는다.

## 파일

- `stage6be1_summary.json`: 판정, 형상별 결과
- `selection.json`, `candidates.csv`: 선정
- 동결 예측과 manifest: `evidence/stage6b/stage6be1/workloads/`
- 재현 명령:

  ```
  python3 host/analysis/stage6be1.py judge evidence/stage6b/stage6be1/raw/evsweep_s6be1_run evidence/stage6b/stage6be1/workloads \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/wfe \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/capabilities.json results/fi101_stage6b/stage6be1
  ```
