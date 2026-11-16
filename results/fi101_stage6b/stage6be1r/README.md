# Stage 6B-E1-R — H1-UC 전향적 재검증 (보드 결과)

## 조건과 근거

- 측정 환경: MPS4 FI101, Ethos-U85 1024 MAC, **TA profile 1**, Driver Runner 이미지 `70090f1`, DDR/EXT, WAIT_WFE.
- boot 428–434(2026-11-16 05:35–06:01Z): 7 boot, 70 RUN(warm-up 14, 측정 56).
- 경과:
  - Phase 0 감사·errata `ab2e420`(`evidence/stage6b/stage6be1r/phase0/errata.md`)
  - 개정 계약 `9daceaf`(후보 컴파일 전 동결, `POSTHOC_DESIGN_REVISION`)
  - 선정·예측·판정 동결 `5094e74`(`predictions.md`)
  - Preflight PASS `fa4e93c`
- 원시 자료: `evidence/stage6b/stage6be1r/raw/`(105개 파일). `raw.sha256`은 보드와 Mac이 경로별로 같다.
- 복원: `RESTORE VERIFIED`, postflight에서 카드 분리, `SESSION DONE`.

| 판정 | 값 |
| --- | --- |
| **H1-UC (주 판정)** | **PROSPECTIVE_SUPPORT** — 기준 gate PASS, Primary Valid 6/6, H1-UC 예측 6/6 정확 일치 |
| D-PW (보조) | **D-PW_CONSISTENT**. D-PW≠D-U16인 Primary Valid 5개, D-PW≠D-U8인 Primary Valid 1개에서 모두 D-PW가 맞았다 |
| 기준 형상 (boot 428) | repro-gate PASS: MAC·DPU 3,456, 출력, 상수 카운터가 boot 375와 같다. NPU_ACTIVE 22,879.5 대 22,251(허용폭 981 안). pass A range 4.29 % |

## 결과 (모두 VALID = Primary Valid; MAC/DPU는 측정 4회 모두 같은 값)

| boot | 형상 | 범주 역할 | H1-UC 예측 | 실측 MAC_ACTIVE | 잔차 | 같이 맞은 경쟁 가설 | 경쟁 가설 판별 수 |
|---:|---|---|---:|---:|---:|---|---:|
| 429 | Cin200 37×37 Cout96 | E1-A | 40,432 | 40,432 | 0 | 없음 | 8/8 |
| 430 | Cin200 33×33 Cout96 | E1-B | 32,368 | 32,368 | 0 | 없음 | 8/8 |
| 431 | Cin200 37×37 Cout176 (ublock 2x4x16, 커널 16+160) | E1-C | 58,520 | 58,520 | 0 | H1-G, 전체 Cout | 6/8 |
| 432 | Cin200 29×29 Cout96 | E1-D | 25,200 | 25,200 | 0 | 없음 | 8/8 |
| 433 | Cin100 37×37 Cout96 | 추가(DPU) | 20,216 | 20,216 | 0 | H1-U16, Cin 조각 없음, min32 제거 | 5/8 |
| 434 | Cin136 37×37 Cout96 | 추가 | 28,880 | 28,880 | 0 | 없음 | 8/8 |

- 경쟁 가설 8개는 모두 적어도 한 Primary Valid 형상에서 틀렸다.
  - H1-G·"전체 Cout": 5개 형상에서 틀렸다(boot 431에서만 H1-UC와 같은 값이었다).
  - H1-U16·"Cin 조각 없음"·"min32 제거": 5개에서 틀렸다(boot 433에서만 같은 값).
  - H1-C16·H1-U8·"공간 패딩 제거": 6개 모두에서 틀렸다.
- 경쟁 가설이 H1-UC와 같은 값을 예측한 형상은 그 가설에 대한 구분 증거로 세지 않았다.
- 출력·환경·PMU 검사는 모두 통과했다. 보드 `output.bin`은 TFLite reference golden과 같고, 모든 RUN이 `output_match`다.

## NPU_ACTIVE 안정성 (사전 지정 보조 분석, 판정 입력 아님)

| 형상 | NPU_ACTIVE pass A 측정 4회 | 절대 range | 상대 range | pass B 중앙값 | Vela 예상 | 실측/Vela |
|---|---|---:|---:|---:|---:|---:|
| 기준 Cin48 24×24 | 22,887 22,194 22,872 23,175 | 981 | 4.29 % | 22,994.5 | — | — |
| Cin200 37×37 o96 | 104,306 104,392 104,803 104,809 | 503 | 0.48 % | 104,836 | 85,815 | 1.22 |
| Cin200 33×33 o96 | 84,989 84,927 85,032 84,595 | 437 | 0.51 % | 84,450 | 68,481 | 1.24 |
| Cin200 37×37 o176 | 131,820 130,793 131,250 130,861 | 1,027 | 0.78 % | 130,700 | 171,630 | 0.76 |
| Cin200 29×29 o96 | 65,603 65,053 65,955 65,780 | 902 | 1.37 % | 65,574 | 58,593 | 1.12 |
| Cin100 37×37 o96 | 66,351 65,712 66,862 65,454 | 1,408 | 2.13 % | 66,055.5 | 59,374 | 1.11 |
| Cin136 37×37 o96 | 75,337 75,217 75,096 75,576 | 480 | 0.64 % | 74,868 | 59,374 | 1.27 |

- 6개 모두 5 % 기준을 통과했다. 상대 range는 0.48–2.13 %다.
- 절대 range는 437–1,408 사이클이다. E1의 작은 형상(300–1,260)이나 기준 형상(981)과 비슷한 크기다.
  - 이 자료는 다음 해석과 **일치한다**: 절대 변동은 형상 크기와 크게 상관없고, 총량이 크면 상대 변동이 작아진다.
  - 원인은 확인하지 않았다. 형상 크기만 바꾼 통제 비교가 아니다(Cin·Cout·공간이 함께 다르다).
  - 따라서 "작은 형상이 변동의 원인"이라는 인과관계는 여전히 검증되지 않았다.
- 실측/Vela는 Vela 오차 분석(E2)이 아니다. 기술 통계로만 적는다. 범위는 0.76–1.27이다.

## MAC 처리율 (보조)

| 형상 | N_MAC | N_MAC/MAC_ACTIVE (예측 = 실측) | /1024 | MAC_ACTIVE/NPU_ACTIVE |
|---|---:|---:|---:|---:|
| Cin200 37×37 o96 | 26,284,800 | 650.1 | 0.63 | 0.39 |
| Cin200 33×33 o96 | 20,908,800 | 646.0 | 0.63 | 0.38 |
| Cin200 37×37 o176 | 48,188,800 | 823.5 | 0.80 | 0.45 |
| Cin200 29×29 o96 | 16,147,200 | 640.8 | 0.63 | 0.38 |
| Cin100 37×37 o96 | 13,142,400 | 650.1 | 0.63 | 0.31 |
| Cin136 37×37 o96 | 17,873,664 | 618.9 | 0.60 | 0.38 |

- MAC_ACTIVE 1회당 유효 MAC는 이론 최대치 1024의 60–80 %다.
- 이 손실은 H1-UC의 패딩 항으로 정수 단위까지 설명된다. 패딩 항은 세 가지다.
  - 커널별 Cout 분할 패딩: 16 → 32, 80 → 96, 160 → 160(ublock 깊이 16)
  - 공간 ublock 패딩: 홀수 변 → 짝수, 2x4x16에서는 W → 4의 배수
  - Cin 나머지 조각: 8 → 32, 36 → 48
- 하지만 NPU_ACTIVE 중 MAC_ACTIVE가 켜진 비율은 0.31–0.45뿐이다. 나머지 55–69 %는 H1-UC 범위 밖이며 설명하지 않았다(메모리·weight decode 등은 확인하지 않음).

## 해석과 한계

1. **공식 판정은 PROSPECTIVE_SUPPORT다.**
   - 측정 전에 동결한 정수 예측이 6/6 정확히 맞았다.
   - 측정 뒤 식, 예외, 기준을 바꾸지 않았다. 5 % 기준도 그대로다.
2. **세 자료를 구분한다.**

   | 단계 | 성격 | 결과 |
   | --- | --- | --- |
   | Stage 6B-R | 사후 도출, 기존 자료 | 14/14 |
   | Stage 6B-E1 | 전향 예측 | MAC-only 진단 6/6, Primary Valid 0/6, 공식 판정 INSUFFICIENT_EVIDENCE(유지) |
   | **Stage 6B-E1-R** | 신규 전향 검증 | **Primary Valid 6/6 일치** |

3. **유효 범위.** 이번 결과는 아래 조건 안에서만 지지된다. 모든 1×1 Conv의 하드웨어 법칙이라고 주장하지 않는다.
   - Vela 5.0.0, MLEK 옵션(Ethos_U85_SYS_DRAM_Mid_1024)
   - 1×1 DepthFirst Conv, Dram→Dram, IFM block 깊이 64
   - ublock 2x2x32 또는 2x4x16
   - OFM 29–37 정사각, Cin 100–200, Cout 96·176
   - 커널 분할(16+80, 16+160)은 H1-UC의 **입력**이다. Vela가 커널을 나누는 규칙 자체는 이번에 예측하거나 검증하지 않았다.
4. **설계 개정은 사후적이다.** 형상 선정 규칙의 개정(`POSTHOC_DESIGN_REVISION`)은 E1 결과를 본 뒤 정했다. 이 개정은 형상 선정과 안정성 하한에만 해당한다. 예측식과 판정 기준은 E1 계약 그대로다.
5. **측정 후 수정 1건(판정과 무관).** 보조 표를 만드는 `stage6be1r.npu_table`이 `stage6bb.rates()`와 다른 키 이름(`A_35`)을 읽어, 첫 판정 실행에서 보조 표가 빈칸이었다.
   - 키 이름(`npu_active` 등)과 그 테스트 fixture를 고쳤다. 판정·분류 코드와 판정 결과는 그대로다.
   - 고친 뒤 테스트 19개 OK, mutation 31/31 KILLED.
   - 표의 값은 `runs.csv`에서 직접 다시 계산한 값과 같다.

## DPU/MAC (보조, 주 판정과 별개)

- D-PW는 6/6 맞았다.
  - D-U16은 boot 433 하나에서만 맞았다(그 형상에서는 D-PW와 같은 값).
  - D-U8은 boot 433에서 틀렸다. 실측 20,216, D-U8 예측 18,772였다. 나머지 5개에서는 D-PW와 같은 값이었다.
- 따라서 D-PW가 D-U16과 D-U8 양쪽과 구분된 Primary Valid 형상이 있으므로 계약 §7에 따라 **D-PW_CONSISTENT**다.
- D-U8과 구분된 형상은 1개(Cin100의 36 조각)뿐이다. 약한 근거다.
- DPU/MAC 비율을 회로 점유율로 해석하지 않는다.

## Stage 6 연결과 남은 항목

- H1-UC는 위 범위에서 MAC_ACTIVE를 정적으로 계산하는 식으로 쓸 수 있다.
  - Stage 6의 MAC 모델 설명력 재평가가 다음 검토 대상이다(지시 §9). 이번에는 실행하지 않았다.
  - 모델 수준에 적용하려면 Vela 커널 분할·ublock 선택을 컴파일 산출물에서 읽어야 한다. 이 산출물은 정적으로 얻을 수 있다.
- 확인하지 못한 것:
  - NPU_ACTIVE 중 MAC 비활성 구간(55–69 %)의 원인
  - NPU_ACTIVE 절대 변동(수백–1,400 사이클)의 원인(6B-R E3와 같은 항목)
  - PartKernel traversal, 3×3 이상 커널, Sram 배치, 범위 밖 형상에서의 H1-UC
  - Vela 커널 분할 규칙
  - Vela 사이클 오차(E2)

## 다음 단계 권고 (실행하지 않음, 별도 승인 필요)

- 지시 §9 순서대로 진행한다.
  1. Stage 6 MAC 모델 설명력을 H1-UC로 재평가한다. 보드 없이 기존 자료로 할 수 있다.
  2. 그다음 E2(Compiler Fidelity)를 검토한다.
- E2·E3·Stage 6C와 추가 보드 측정은 시작하지 않았다.

## 파일

- `stage6be1r_summary.json`: 판정, 형상별 결과, NPU 보조 표
- `selection.json`, `candidates.csv`: 680개 후보와 선정
- `predictions.md`: 동결 예측(보드 전 `5094e74`)
- 재현 명령:

  ```
  python3 host/analysis/stage6be1r.py judge evidence/stage6b/stage6be1r/raw/evsweep_s6be1r_run evidence/stage6b/stage6be1r/workloads \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/wfe \
    evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48/capabilities.json results/fi101_stage6b/stage6be1r
  ```
