# Stage 6B-R — MAC 처리 메커니즘과 Vela 예측 오차 (보드 없는 사후 분석)

- 이번 단계에서는 새로 측정하지 않았다. 측정값은 모두 기존 보드 데이터이고, 조건은 TA profile 1, 이미지 `70090f1`이다.
  - Stage 4K boot 369–378
  - Stage 4C2
  - Stage 6B-B boot 410–420
- 계약 `analysis_contract.md`(`7613052`)를 산출물보다 먼저 커밋했다.
- 모든 식은 **`POSTHOC_EXPLANATORY`**다. 핵심 식(H1-UC, D-PW)은 계약 전에 탐색으로 찾았고, 계약 서두에 그렇게 밝혔다.

| 파일 | 내용 | 구분 |
| --- | --- | --- |
| `analysis_contract.md` | 가설, 식, 표본, 판정 기준 | 계약 |
| `mac_padding_analysis.csv` | 사례 17개 × 가설·제거 실험 예측과 잔차 | 실측 + 정적 계산 + 사후 가설 |
| `mac_mechanism_report.md` | Phase 1 보고 | 위와 같음 |
| `vela_configuration_audit.md` | Vela resolved 설정 대 보드(TA, AXI, capabilities) | 정적 대조, UNKNOWN 명시 |
| `vela_fidelity_analysis.csv` | Vela 사이클·바이트 대 보드 NPU_ACTIVE·beat | 실측 + Vela 추정 |
| `unstable_diagnostics.md`, `unstable_runs.csv`, `unstable_summary.csv` | Phase 3 | 실측 원시값 기술 |
| `next_experiment_contract_draft.md` | Phase 4 초안(실행 미승인) | 계획 |
| `stage6br_summary.json` | 판정 결과 | 사후 판정 |
| `facts/vela_summary_full.json` | Vela 요약 CSV 전체 필드(10개, 같은 바이너리 확인) | Vela 추정 |
| `mutate.py`, `mutation.txt` | 계산식 mutation 14/14 KILLED | 검증 |

재현:
- `python3 host/analysis/stage6br.py run results/fi101_stage6b/stage6br`
- Vela 요약 수집: 컨테이너에서 `host/container/stage6br_vela.py /work/s6b_ra_compile <out> G12 …`

## MAC (요약; 자세한 내용은 `mac_mechanism_report.md`)

- **H1-UC**: 공식 표본 14/14, 탐색 3/3이 정확히 맞는다. 판정은 `CONSISTENT_WITH_OBSERVATIONS`이고, 일반 법칙은 아니다(사후).
  - 식: MAC_ACTIVE = Σ_커널 (OFM ublock 수) × Σ_Cin조각 max(32, ⌈x,16⌉)/8.
  - 구성요소 넷(공간 ublock padding, 커널별 Cout slice, IFM 깊이 조각, 조각당 최소 32) 중 하나만 빼도 `CONTRADICTED`다.
- 지시서 H1-G(전역 Cin32·Cout16)는 9/14로 `CONTRADICTED`, 지시서 D-R(DPU/MAC = ⌈Cin,8⌉/⌈Cin,32⌉)은 8/14로 `CONTRADICTED`다.
- **768 = 1024 × 96/128**: Stage 4K/4C2의 24×24×96 계열에서 Vela가 Cout을 커널 16 + 80으로 나눴고, 각 slice가 ublock 깊이 32로 올라간 결과로 설명된다.
  - 640은 여기에 Cin 40 → 48이 더해진 값이다. G09의 1024는 손실이 없는 경우다.
- G25·G53은 6B-B의 전역식으로는 맞지 않았지만 H1-UC로는 맞는다.
  - G25: ublock 깊이 32 → Cout 140 → 160, 공간 25×5 → 26×6, Cin 조각 12 → 32.
  - G53: ublock 깊이 16, Cin 44 → 48.
  - G53은 UNSTABLE이므로 탐색 결과로만 쓴다.

## Vela (지시 3.1, 3.3; `vela_fidelity_analysis.csv`)

| 형상 | Vela total | npu | sram_ac | dram_ac | 보드 NPU_ACTIVE | 오차 % | NPU/Vela npu |
|---|---:|---:|---:|---:|---:|---:|---:|
| G12 | 53,052 | 33,314 | 28,800 | 44,709 | 99,555 | +87.7 | 2.99 |
| G25 | 14,909 | 9,534 | 4,603 | 14,820 | 28,902.5 | +93.9 | 3.03 |
| G40 | 30,422 | 23,716 | 8,405 | 30,315 | 46,939.5 | +54.3 | 1.98 |
| G11 | 37,273 | 22,562 | 21,600 | 35,799 | 75,129.5 | +101.6 | 3.33 |
| G52 | 15,393 | 9,891 | 5,400 | 15,277 | 31,147.5 | +102.3 | 3.15 |
| G57 | 10,955 | 7,865 | 3,106 | 10,912 | 19,131 | +74.6 | 2.43 |
| G09 | 29,928 | 19,165 | 13,002 | 29,755 | 56,807 | +89.8 | 2.96 |

- 절대 오차는 54–102 %, 중앙값 90 %(n=7)다. UNSTABLE 3개는 `NOT_COMPARABLE`이다.
- **비용 구성(정적):**
  - 연산별 `op_cycles` = max(npu, sram_ac, dram_ac)다(30/30).
  - `cycles_total`은 연산별 값의 합이다(10/10).
  - 각 성분은 더하지 않는다.
  - 형상마다 `cycles_total`은 `cycles_dram_access`에 가깝다(6개는 1 % 안, G12는 19 %).
- **바이트(실측 beat × 16 B 대 Vela):**
  - SRAM write는 7/7 같다.
  - SRAM read는 보드가 Vela의 0.65–0.80배다.
  - EXT read는 1.03–1.39배다.
  - EXT write는 0.50–0.89배다.
  - 실행 시간의 메모리 몫은 계산하지 않았다.
- **Vela MAC 추정(보조, 정의가 같은지 미확인 → NOT_COMPARABLE):** Conv 행의 `vela_mac_cycles`는 7개 모두 MAC_ACTIVE보다 크다(예: G57 4,179 대 1,728).
  - Vela의 compute 쪽이 작게 잡혀서 과소예측이 생겼다고 볼 근거는 이 표에 없다. 이는 미검증 추론이다.
- **상관(n=7, 기술 통계):**
  - 오차 대 MAC 처리율: Spearman 0.32
  - 오차 대 MAC/NPU: 0.04
  - 오차 대 WD_STALLED: −0.21
  - 이 값으로 인과의 존재·부재를 말하지 않는다.
  - 6B-B README(`results/fi101_stage6b/stage6bb/README.md`)의 0.30(오차 대 MAC 처리율)은 동점 순위(G12·G52 940.4)를 잘못 처리한 계산이었다. 올바른 값은 0.32다. 기존 결과를 바꾸지 않는다는 지시에 따라 그 파일은 그대로 두고, 여기서 정정한다. 나머지 두 값(0.04, −0.04)은 동점이 없어 같다.
- **모델 수준과의 차이(지시 3.3, 조건이 다른 비교):**
  - 종합 문서(§1-7)의 모델 전체 NPU_ACTIVE ÷ Vela `cycles_npu`는 0.79–1.62였다. A2 독립 그래프에서는 1.98–3.33이다.
  - 다른 점:
    - 그래프 크기: 모델 전체는 수십–수백 연산, A2는 3연산이다.
    - 메모리 배치: A2는 graph 입출력이 DRAM이고 Conv IFM/OFM이 SRAM이다. 모델 안에서는 텐서마다 다르다.
    - 가중치 staging: A2는 DRAM에서 스트리밍한다. Vela 추정 바이트에서 G12 등은 가중치를 2회 읽는다.
    - ADD 래퍼 2개.
    - NPU_ACTIVE 범위: 3연산 command stream 전체다.
  - 이 차이 중 어느 것이 원인인지 이번 자료로는 특정할 수 없다(`CAUSE_UNRESOLVED`).
- **판정(근거별):**
  - `CONFIGURATION_MISMATCH_IDENTIFIED` 없음. 확인한 항목은 모두 일치했고, 대역폭·clock scale·burst·포트 수는 UNKNOWN이다.
  - `COST_MODEL_DISCREPANCY_OBSERVED`: 바이트와 사이클에서 차이를 관측했다.
  - `CAUSE_UNRESOLVED`.

## UNSTABLE (요약; `unstable_diagnostics.md`)

- G53·G56·G28은 MAC, DPU, AO, 메모리 전송량이 RUN 간 같고 NPU_ACTIVE만 800–1,500 사이클 변했다.
- WD_STALLED 변화는 NPU_ACTIVE 순서와 맞지 않았다.
- 이 PMU 집합으로는 원인을 식별할 관측이 없다.
- 세 형상은 NPU_ACTIVE 총량이 가장 작은 넷 중 셋이다. 하지만 VALID인 G52는 절대 range가 29로 작아서, 총량이 원인이라고 확정하지 않는다.
- 판정과 5 % 기준은 바꾸지 않았다.

## 불변성

- 6B-B 판정(`stage6bb.py judge`)을 원시 데이터로 다시 실행했다. `stage6bb_summary.json`이 커밋된 파일과 바이트 단위로 같다.
- `a2c7406` 이후 기존 파일 중 수정·삭제된 것은 없다(git).
