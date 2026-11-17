# Stage 6C-0 결과 — Unit/AXI/Vela 통합 분석과 Stage 6C 설계 (보드 없음)

- 계약·규칙 동결 `74aa09d`. 정오표 두 건(`evidence/stage6c0/erratum_compile.md`): 컴파일 도구의 per-channel zero point(`93d4fbc`), 통합 로더의 4WD 원천. 둘 다 규칙은 바꾸지 않았다.
- 분석 `stage6c0.py run`을 2회 실행했고 출력이 바이트 단위로 같다. 컴파일 검증은 컨테이너에서 2회 실행했고 `compile_facts.json` `f77884ec…`가 같다.
- 보드 자료는 기존 파일만 읽었다. 조건(runner, 이미지, TA, 지연, 배치)은 행마다 적었다. 보드 값은 모두 TA profile 1이다.

## 1. 커밋

| 커밋 | 내용 |
|---|---|
| `74aa09d` | 계약·통합·분류·선정 규칙·컴파일 스크립트·테스트·mutation 동결 |
| `93d4fbc` | 컴파일 도구 수정과 정오표 |
| 결과 커밋 | 이 파일 |
| `2e7bd42` | E2E-D 결과 |
| `fadcf6d` | 결정 기록 |

## 2. 기존 데이터 통합 (`integrated.csv`, 95행)

- **모델 14행**:
  - driver runner `65cf963`(NPU, MAC, AO, WD, WD_STALLED, Vela total/npu)
  - legacy `2bb04bfa`(Stage 1 비율 × ACTIVE)
- **독립 연산 55행**: Stage 4, 4C-2, 4K(+Vela static), 4AO OFM sweep, 4AO-E, 4WD(boot 402–409, 정오표 2로 로더 수정), Stage 4 placement A/B, E2A의 E1-R·REF.
- **그래프 26행**: E2A의 6B-B A2 10개(Vela compute/SRAM/DRAM/total과 보드 바이트), E2D 8칸, E2E-B 4칸, E2E-D 4칸.
- 값이 없는 칸은 비워 두었다. 이미지·runner·지연이 다른 행은 같은 비교 쌍으로 묶지 않았다.

## 3. Unit별 확보된 특성 (`unit_inventory.md`)

| Unit | 확보 | 미확보 / Open issue |
|---|---|---|
| MAC/DPU | 1×1 DepthFirst H1-UC(PROSPECTIVE_SUPPORT, G09는 1024로 768 상한 아님). 1×1 PK Cin 16/32: 384, DPU/MAC 0.5. 3×3 PK: 768. DW 3×3 C144: 128(C는 16 올림). FC 96→288: 256 | PK Cin < 16 대형 공간, DW C < 16·5×5, FC 다른 형상, 1D 대형 커널, Cin 1 첫 Conv |
| AO | Conv 출력 약 15.6 elem/cycle, ADD/MUL N/16, ADD→MUL 2N/16. 모델 AO/NPU: yolo 46 %, vww4 27 % | LUT/TANH/LOGISTIC 미측정. **AO-1**: ABS N/32 |
| WD | WD_ACTIVE ∝ 공간 OFM block(BLOCK_LIKE), 인코딩 바이트와 무관(CONSTANT). WD_STALLED는 배치·EXT 지연과 함께 변함(E2D, E2E-B/D) | 다른 Unit 역압력과 분리 안 됨. **WD-1**: FC 34.7–42 B/cycle > 문서 32. WD-2 |
| DMA/AXI | 모델별 SRAM/EXT beat·트랜잭션(Stage 3), 독립·A2 구성별 beat·트랜잭션, EXT0/1 포트별(640/642/656/658) VERIFIED, 387 요청 정체 VERIFIED, 채널 필터 read(legacy). graph IO와 가중치 경로의 지연 민감도(E2E-B/D) | 포트 물리 한도 미검증 → **AXI 이용률은 계산하지 않음**. 398 INCONSISTENT, axi_latency 미측정, driver runner에 PMCAXI_CHAN 없음 |

## 4. AXI 전송량·트랜잭션·포트

- 모델(Stage 3, legacy):
  - EXT read 요청 정체 6–18 %(포트 사이클 기준), SRAM ≤ 0.6 %.
  - outstanding 한계 정체 ≈ 0.
  - 측정 바이트 < Vela 예상(7개 모두).
  - 바이트/MAC: rnnoise 1.500 – wav2letter 0.011.
- A2(E2E-B/D):
  - graph IO EXT 읽기는 평균 1.64 beat 요청 9,624개였다.
  - 남은 가중치 읽기는 약 14.3 beat burst 793개였다.
  - 배치를 바꿔도 read·write 전송 합은 보존된다.
- 바이트 ÷ NPU_ACTIVE는 관측 평균 처리율(B/cycle)이다. 포트의 물리 이용률로 부르지 않는다.

## 5. NPU_ACTIVE 증감과 Unit 활동 (`comparisons.csv`, 21쌍, 태그는 비배타)

| 유형 | 쌍 | 태그 |
|---|---|---|
| 채널 −1 | Stage 4 Cout 95, DW 143 | DATA_TRANSFER_CHANGE + PIPELINE_DEPENDENCY_CANDIDATE(MAC 불변, NPU +1,477 / +9,744) |
| 채널 −1 | Cin 15, FC in 95, FC out 287 | NPU 변화가 tol 안 |
| Cin sweep | 4C-2 16→32, 64→128 | COMPUTE_COST_CHANGE(MAC ×2) |
| Cin sweep | 32→64 | COMPUTE + COMPILER_MAPPING_CHANGE(traversal PK→DF), MAC 불변·NPU 감소 |
| 1×1 → 3×3 | 4K | COMPUTE + DATA_TRANSFER + COMPILER_MAPPING |
| OFM 크기 | 4AO H24→H72 | COMPUTE + DATA_TRANSFER |
| 배치·지연 | 4P, E2D, E2E-B, E2E-D | MEMORY_SERVICE_CONDITION + PIPELINE_DEPENDENCY_CANDIDATE(MAC 불변, NPU −10,731 ~ +59,271) |

- 배치·지연 계열에서는 MAC이 같은데 NPU_ACTIVE가 크게 움직인다. 데이터 공급 조건이 실행시간을 바꾼다는 근거다.
- 다만 어느 Unit의 대기인지는 분리되지 않았다(`MECHANISM_UNRESOLVED` 유지).

## 6. Vela 오차 (`vela_fidelity.csv`, 57행; 기준 표기)

| 사례 | board/Vela | 방향 |
|---|---|---|
| 7개 모델(driver, Vela total) | ad 0.98, kws 0.90, vww4 0.89, yolo 0.76, w2l 0.72, mobilenet 0.61, **rnnoise 1.53** | 대체로 과대예측, rnnoise만 과소 |
| 독립 1×1 PK / DW / FC(Stage 4, Vela npu) | 1.08–2.08 | 과소 |
| 4K 1×1(Vela op) | 0.87–1.02 | 대체로 일치 |
| 4K 3×3 Cin ≥ 32(Vela op) | **0.26–0.30** | 크게 과대 |
| 1×1 DepthFirst E1-R(Vela total) | 0.76–1.27 | 혼재 |
| A2 래퍼 6B-B / E2D W1-P1 / E2E-B B0 | 1.54–2.02 | 과소 |
| Conv 단독 DRAM(E2D W0-P0) | 0.48–0.51 | 과대(NHWC burst 부풀림, E2E-A) |
| E2D W1-P0(전부 DRAM) | 1.13–1.20 | 과소 |

- 오차 방향이 갈리는 조건 후보는 두 가지다.
  - **과대**: Vela DRAM 항을 NHWC IFM read가 지배하는 경우(burst 부풀림) — Conv 단독 DRAM, 4K 3×3 후보.
  - **과소**: 작은 요청이 많은 graph IO 경로, 또는 의존성이 있는 다중 연산 그래프(A2) — Vela가 요청 수와 연산 간 의존을 세지 않음.
- 3×3 0.26–0.30은 새로 정리된 사실이다. 원인이 NHWC burst 비용인지는 확인하지 않았다(CAUSE_UNRESOLVED).
- 하나의 보정 계수로 묶지 않는다. H1-UC MAC_ACTIVE와 Vela compute는 다른 지표로 둔다.

## 7. Stage 6C 우선 연산군 선정 (`selection.json`, 규칙 동결 후 기계적 선정)

| 연산군 | 최대 모델 비중(TFLite) | C1 | C2 | C3 | C4 | C5 | 선정 |
|---|---|---|---|---|---|---|---|
| F1 1×1 PartKernel | yolo 0.343 | 2형상 | ✓ | ✓(Cin 4) | MAPPING_SAME | ✓ | ✓ |
| F2 Depthwise | yolo 0.214 | 1 | ✓ | ✓(C 8) | ✓ | ✓ | ✓ |
| F3 FC | rnnoise 1.0 | 1 | ✓ | ✓(Cin 114) | ✓ | ✓ | ✓ |
| F4 1D 대형 커널 PK | w2l 0.828 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ |
| F5 Cin < 16 첫 Conv | kws 0.176 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ |

제외: 1×1 DepthFirst(H1-UC 검증 완료, 반복 금지), 3×3 PK Cin 16–64(4K).

## 8. 대표 형상과 통제 조건 (`stage6c_board_contract_draft.md`)

- 대표: yolo op9(96²×4→24, 1×1 PK), yolo op3(96²×8 DW 3×3), rnnoise op46(FC 114→288), wav2letter op17(1×148×250→2000, 1×32 PK), kws op0(49×10×1→140, 10×4 PK).
- 통제: F1 Cin 4→16, F2 C 8→16, F3 Cin 114→128. 셋 다 traversal·block·ublock이 대표와 같다(MAPPING_SAME).
- 8개 모두 단일 NPU 연산, CPU 연산 0, DRWL 포장 성공, runner 한도 안(F4 모델 9.78 MB)이다.
- 통제할 수 없는 조건이 하나 있다. 단독 연산의 graph IO는 DDR이다(모델 안은 대부분 SRAM).

## 9. 가설의 예상 관측과 반례 (초안 §3)

- **H-COMPUTE**: F1·F2·F3에서 채널을 16 배수로 올려도 MAC_ACTIVE가 같다(≤ 1 %). 반례는 > 1 %. F4는 MACs/MAC_ACTIVE 384–1024다.
- **H-PIPELINE**: F1·F2의 NPU/MAC 비는 F3·F4보다 크다(방향만).
- **H-VELA**:
  - F1·F2: board/Vela < 0.9(NHWC IFM read 지배). 반례 > 1.1.
  - F3: board/Vela > 1.0. 반례 < 0.9.
  - 통제 쌍: F1·F3은 Vela가 같은 값을 예측한다. F2는 Vela가 4배 감소를 예측한다(140,000 → 35,000).
- 형상 선정에 쓴 정적 자료(Vela 값)와 보드 검증 결과는 구분한다.

## 10. 보드 측정 지표와 예산 (승인 전)

- 9 boot(REF + 8).
- Pass A(Unit)·B(트래픽)·C(요청 정체·outstanding 한계·EXT 포트별, 모두 VERIFIED) → 135 RUN(측정 108). Pass C를 빼면 90 RUN.
- TA profile 1, 새 runner 이미지(`14077be`, placement 0).

## 11. 모델 수준 설명력 확대 가능성 (`stage6_reassessment_plan.md`)

- 측정이 덮지 못하는 MAC이 줄어든다(TFLite 기준).
  - yolo: 1×1 PK 34 % + DW 21 %
  - vww4: PK 24 % + DW 9 %
  - mobilenet: PK 21 % + DW 7 %
  - wav2letter: 1D PK 83 %
  - rnnoise: FC 100 %
  - kws: 첫 Conv 17.6 %
- 다시 볼 현상: KWS 대 AD 효율, rnnoise의 낮은 MAC 활성(1.1 %, Vela 과소 1.53), yolo/vww4의 AO 우세, wav2letter의 높은 MAC 효율.
- 독립 연산 결과를 모델 안 연산의 시간으로 직접 귀속하지 않는다.

## 12. 더 반복할 필요가 없는 실험

- 1×1 DepthFirst MAC_ACTIVE(H1-UC).
- EXT 지연 민감도 경로 귀속(E2E-B/D로 종료).
- 3×3 PK Cin 16–64의 MAC 처리율.
- ADD/MUL AO 처리율.
- Stage 4 채널 −1 계열.

## 13. 남은 연구 범위와 종료 기준

- 남은 것:
  - Stage 6C(F1–F5)
  - 모델 수준 재평가
  - 미해결: AO-1, WD-1/2, B3w L500 비용, 3×3 Vela 과대, MECHANISM_UNRESOLVED 계열
- 종료 기준: 연산군마다 처리율·Unit 활동, 메모리 전송, NPU_ACTIVE 대 Vela, 설명 범위와 미해결, 모델 적용 범위를 확보하면 그 연산군을 종료한다.
- 그다음 모델 수준 재평가로 연구를 종합한다.

## 14. 테스트·무결성

- 테스트 25개(4WD 행 검사 추가), mutation 43/43 KILLED(로더 수정 뒤 재실행), `test.sh` ALL PASS.
- 분석 2회 바이트 동일, 컴파일 2회 동일.
- 기존 결과 파일 불변(git diff 없음).
- 정오표 2건(도구·로더 결함, 규칙 불변).

## 15. 최종 권고

Stage 6C 보드 측정(9 boot, F1–F5 대표 5 + 통제 3, Pass A·B·C)을 승인 요청한다. 승인되면 계약·판정을 이 초안 기준으로 동결하고 preflight 뒤 실행한다. 보드 측정은 승인 전까지 하지 않는다.
