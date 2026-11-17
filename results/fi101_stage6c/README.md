# Stage 6C 결과 — 연산군 F1–F5의 Unit/AXI/Vela 동시 계측

- 계약 `81145da`, preflight `94e9573`.
- 보드 boot 468–476(2026-11-17). **TA profile 1**, EXT RLATENCY 500, runner 이미지 `14077be`(bram `ec0e8c3b…`), placement 0, Pass A·B·C.
- 원시 자료 `evidence/stage6c/raw/`(92개, 보드와 sha256 일치), 세션 로그 `evidence/stage6c/board/session.log`. 카드 RESTORE VERIFIED, postflight 완료.
- 판정 2회 실행 결과가 바이트 동일하다(`stage6c_summary.json`).
- 모든 형상은 단독 연산이며 graph IO는 DDR이다. 모델 안 연산의 실행시간으로 귀속하지 않는다.

## 판정 요약

| 형상 | Measurement | Compute | Pipeline/Memory | Vela(board/Vela) |
|---|---|---|---|---|
| F1 rep (yolo op9, Cin 4) | VALID | PREDICTION_SUPPORTED | ASSOCIATION_ONLY | UNDERESTIMATION (2.00) |
| F1 ctl (Cin 16) | VALID | PREDICTION_SUPPORTED | ASSOCIATION_ONLY | UNDERESTIMATION (2.02) |
| F2 rep (yolo op3, C 8) | VALID | PREDICTION_SUPPORTED | **CONTROLLED_EFFECT_OBSERVED** | OVERESTIMATION (0.12) |
| F2 ctl (C 16) | VALID | PREDICTION_SUPPORTED | **CONTROLLED_EFFECT_OBSERVED** | OVERESTIMATION (0.83) |
| F3 rep (rnnoise op46) | PARTIAL_VALID (UNSTABLE) | INSUFFICIENT_EVIDENCE | MECHANISM_UNRESOLVED | INSUFFICIENT_EVIDENCE (기술 1.09) |
| F3 ctl (Cin 128) | PARTIAL_VALID (UNSTABLE) | INSUFFICIENT_EVIDENCE | MECHANISM_UNRESOLVED | INSUFFICIENT_EVIDENCE (기술 1.20) |
| F4 rep (w2l op17, 1×32) | VALID | PREDICTION_SUPPORTED | ASSOCIATION_ONLY | OVERESTIMATION (0.58) |
| F5 rep (kws op0, Cin 1) | VALID | INSUFFICIENT_EVIDENCE(예측 없음) | ASSOCIATION_ONLY | UNDERESTIMATION (1.32) |

- 전체: Measurement **PARTIAL_VALID**(REF 게이트 PASS, F3 쌍 UNSTABLE: pass A range가 5 %를 넘음), Mechanism **MECHANISM_UNRESOLVED**.
- 가설 판정:

| 가설 | 판정 |
|---|---|
| H-COMPUTE 채널 16 올림 | F1 **SUPPORTED**, F2 **SUPPORTED**, F3 INSUFFICIENT |
| H-COMPUTE F4 처리율 | **SUPPORTED** |
| H-VELA F1·F2 | **REFUTED**(F1 과소예측) |
| H-VELA F3 | INSUFFICIENT |
| H-PIPELINE 관측 비교 | INSUFFICIENT(F3 무효) |

## 연산군별 수치 (pass A·B·C 중앙값, TA profile 1)

| 형상 | NPU_ACTIVE (range) | MAC | DPU | MACs/MAC_ACTIVE | eff_1024 | MAC/NPU | AO | WD | WD_STALLED |
|---|---|---|---|---|---|---|---|---|---|
| F1 rep | 112,513 (846) | 18,432 | 4,608 | 48 | 0.047 | 0.16 | 18,870.5 | 3,864 | 101,408.5 |
| F1 ctl | 113,437 (1,062) | 18,432 | 9,216 | 192 | 0.188 | 0.16 | 18,866.5 | 4,384 | 100,830.5 |
| F2 rep | 16,742 (782) | 10,368 | 10,368 | 64 | 0.063 | 0.62 | 9,304.5 | 63 | 14,656.5 |
| F2 ctl | 28,985 (534) | 10,368 | 10,368 | 128 | 0.125 | 0.36 | 9,309.5 | 64 | 26,203.5 |
| F3 rep | 8,637.5 (980) | 144 | 144 | 228 | 0.223 | 0.017 | 19 | 578.5 | 3,914.5 |
| F3 ctl | 9,492 (972) | 144 | 144 | 256 | 0.250 | 0.015 | 20.5 | 680 | 3,824.5 |
| F4 | 2,753,924.5 (2,300) | 2,386,944 | 2,282,112 | **992** | **0.969** | 0.87 | 18,595 | 796,250 | 1,955,290.5 |
| F5 | 30,973 (692) | 26,090 | 22,515 | 105 | 0.103 | 0.84 | 4,503.5 | 3,097 | 26,040.5 |

**Compute**
- **F1 1×1 PartKernel**:
  - Cin 4와 16에서 MAC_ACTIVE가 18,432로 같다. 채널을 16으로 올려 처리한다는 해석과 일관된다.
  - DPU는 4,608 → 9,216(DPU/MAC 0.25 → 0.5)으로, 유효 가중치·활성 쌍에 비례해 변한다.
  - Cin 16의 유효 처리율 192는 Stage 4 PK Cin 16(24², Cout 96)의 384보다 낮다. 여기서는 Cout이 24라 다른 형상이며, 원인을 판정하지 않았다.
- **F2 Depthwise**: C 8과 16에서 MAC_ACTIVE가 10,368로 같다(16 올림). 유효 처리율 64 → 128이며, DW 클래스 최대 128과 같다(Stage 4).
- **F3 FC**: MAC_ACTIVE 144(Cin 114·128 같음)지만 UNSTABLE이라 판정하지 않는다. MAC/NPU는 1.5–1.7 %로, Stage 4 FC(1.15 %)와 같이 매우 낮다.
- **F4 1×32 PartKernel**:
  - MACs/MAC_ACTIVE 992, 피크의 96.9 %. MAC/NPU 0.87.
  - wav2letter 모델의 높은 MAC 효율(Stage 1: 85 %, 96.8 %)과 같은 방향이다(귀속은 하지 않음).
- **F5 Cin 1 첫 Conv(10×4)**: TFLite 기준 MACs/MAC_ACTIVE 105(피크의 10 %), DPU/MAC 0.86, MAC/NPU 0.84. 실행시간 대부분 MAC은 활성이지만 처리율은 낮다.

## 메모리·AXI (pass B·C, beat = 16 B)

| 형상 | EXT rd beat / 트랜잭션 | EXT wr beat | SRAM rd beat | EXT rd 요청 정체(387) | EXT0 / EXT1 rd beat |
|---|---|---|---|---|---|
| F1 rep | 4,733 / 880 | 23,040 | 3,384 | 2,239.5 | 2,369 / 2,364 |
| F1 ctl | 18,583 / 1,747 | 23,040 | 4,284 | 10,052 | 9,301 / 9,282 |
| F2 rep | 5,555 / 724 | 4,608 | 352 | 4,932.5 | 2,785 / 2,770 |
| F2 ctl | 10,459 / 1,030 | 9,216 | 480 | 9,425.5 | 5,231 / 5,228 |
| F3 rep | 2,533 / 205 | 18 | 0 | 2,162.5 | 1,267 / 1,266 |
| F4 | 1,333,783 / 140,216 | 18,500 | 0 | 1,004,255 | 666,803 / 666,980 |
| F5 | 1,210 / 390 | 7,591 | 2,121 | 2,716 | 656 / 554 |

- EXT0/EXT1 read 분배는 거의 1:1이다(F5만 54:46).
- SRAM read 요청 정체(131)는 0–28, outstanding 한계 정체(142)는 0이다.
- EXT read 요청 정체(387)는 F4에서 NPU_ACTIVE의 36 %, F2 ctl에서 33 % 사이클에 해당한다. 핸드셰이크 정체이며 서비스 대기시간이 아니다.
- F1 OFM write는 23,040 beat(368,640 B)로, OFM 원소(221,184 B)의 1.67배다. 두 Cin에서 같다.
- 바이트 ÷ NPU_ACTIVE는 관측 평균 처리율이다(물리 이용률 아님).

## 통제 쌍

| 연산군 | MAC_ACTIVE | NPU_ACTIVE 변화 | 보드 비 | Vela op 비 | 전송 변화 |
|---|---|---|---|---|---|
| F1 Cin 4→16 | 같음 | +924(tol 1,908) | 1.008 | 1.00 | EXT read ×3.9, write 같음 |
| F2 C 8→16 | 같음 | **+12,243**(tol 1,316) | **1.73** | **0.25** | EXT read ×1.9, write ×2 |
| F3 Cin 114→128 | 같음 | (UNSTABLE) | — | 1.00 | 같음 |

- **F2**: MAC_ACTIVE가 같은데 NPU_ACTIVE가 73 % 늘었다. IFM/OFM 전송이 2배가 됐다. Vela는 반대로 4배 감소를 예측했다(DRAM 항 140,000 → 35,000; C 8 NHWC의 burst 부풀림이 사라지는 계산).
- **F1**: Cin 4→16에서 EXT read가 3.9배 늘었지만 NPU_ACTIVE는 같다. Vela도 같은 값을 예측했다.

## Vela 비교 (board/Vela op cycles)

- **F1**: 약 2.0배 과소예측. Vela는 DRAM 항(56,249; NHWC IFM read 부풀림)이 지배한다고 보았다. 보드는 그보다 2배 느리다. 보드에서 EXT read 요청 정체와 OFM write(23,040 beat)가 크다.
- **F2**: 과대예측(0.12, 0.83). 특히 C 8에서 Vela가 8배 비관적이다(NHWC 좁은 채널의 burst 비용).
- **F4**: 0.58 과대. Vela는 DRAM 항 4.72M이 npu 3.66M보다 크다고 보았다. 보드는 2.75M이다.
- **F5**: 1.32 과소.
- 6C-0의 사전 가설(F1·F2 모두 과대)은 **반박**됐다. NHWC IFM read 부풀림만으로는 방향이 정해지지 않는다. F1(Cin 4, OFM 24채널 NHWC 쓰기)에서는 Vela가 비용을 빠뜨린 쪽이 더 크다(후보; 미검증).

## 모델 수준 연결 (귀속 없음)

| 모델 | 이번 측정 | 연결 |
|---|---|---|
| yolo | PK 1×1 Cin 4: MAC 효율 4.7 %(Cin 16 올림), DW C 8: 6.3 %(C 16 올림) | 채널 정렬 낭비와 AO 우세를 설명할 후보. yolo AO/NPU 46 %와의 관계는 재평가 단계에서 다룬다 |
| wav2letter | 1×32 PK 피크의 96.9 % | 높은 MAC 효율(Stage 1)과 같은 방향 |
| rnnoise | FC MAC/NPU 1.5 % | 낮은 MAC 활성(1.1 %)과 같은 방향. UNSTABLE이라 정량 판정 없음 |
| kws | Cin 1 첫 Conv 효율 10 % | KWS 효율 저하 후보 |

## 미해결

- F1 Cin 16의 유효 처리율 192 대 Stage 4 PK Cin 16의 384
- F1 OFM write 1.67배
- F1 Vela 과소 2배
- F3 불안정
- 처리부별 지연 기여(MECHANISM_UNRESOLVED)
