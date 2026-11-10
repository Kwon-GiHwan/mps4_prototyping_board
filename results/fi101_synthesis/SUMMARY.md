# FI101 Ethos-U85 1024 연구 요약 — 핵심 결론과 답하지 못한 질문 (2026-11-11)

상세와 근거는 `results/fi101_synthesis/README.md`(종합 보고서)에 있다. 이 요약은 새 측정이나 새 판정을 담지 않는다.
기본 실험은 Stage 5-2와 AD 64 KiB 정적 분석으로 끝났다(owner, 2026-11-11).

**조건 (모든 보드 숫자에 공통).**
- **TA profile 1** (MLEK sys_dram_mid, TA가 흉내 낸 SYS_DRAM_Mid).
- FI101 Ethos-U85 1024 MAC, Vela 5.0.0(MLEK 옵션, Dedicated_Sram), MLEK 입력 하나.
- Stage 1·2A·3은 기존 runner 데이터 중 Driver Runner(m7)로 재검증된 지표만 쓴다. Stage 4·5는 Driver Runner 이미지 `83398c7`에서 측정했다.
- 실행 비용 = NPU_ACTIVE (NPU 사이클). 유효 MAC = 원본 tflite 정의.

## 연구의 흐름

1. **모델별 관측 (Stage 1·2A·3, 일곱 모델).** 같은 NPU에서 모델마다 MAC 활동 비중, MAC 효율, 메모리 접근, 단위 stall이 크게 다르다는 것을 측정했다.
2. **연산별 귀속 시도 (Stage 2B).** 모델 안 연산별 시간·카운터를 나누려 했으나 실패했다. H1/H2는 무효이고, 연산별 시간은 얻지 못했다.
3. **독립 연산 통제 실험 (Stage 4·4C).** 연산 종류, 채널 수, 처리 구성이 MAC 활동과 실행 비용을 어떻게 바꾸는지 하나씩 확인했다(DRAM 입출력 조건).
4. **컴파일 구성 비교 (Stage 5, AD 정적 분석).** 같은 모델에서 SRAM 예산·최적화 전략을 바꾸면 Vela가 다른 실행 구성을 만들고 실행 비용이 크게 달라진다는 것을 보였다. AD 64 KiB에서는 그 구성의 구체적 차이를 원본 연산 단위로 추적했다.

## 핵심 결론 (실측으로 확인, 범위 한정)

| # | 결론 | 근거 | 범위 |
| --- | --- | --- | --- |
| 1 | **계산량만으로 실행 비용을 설명할 수 없다.** | 모델의 MAC 활동 비중 1.1–85 %. 채널을 줄여도 MAC_ACTIVE 동일. 계산량 ×2에 NPU_ACTIVE +19–27 %. 계산량이 늘어도 비용이 줄어든 경우(Cin 32 → 64) | 시험한 모델·연산 |
| 2 | **MAC 처리율은 연산 종류·채널 조건·처리 구성에 따라 다르다.** | DW는 클래스 최대치 128/cycle. Conv 1×1은 PartKernel 384 / DepthFirst 768 / Cin 40 640. MAC_ACTIVE는 채널을 16의 배수로 올린 양과 부합. ublock 변경(Conv 97) | 시험한 shape, 사후 기술 포함 |
| 3 | **MAC 활동과 전체 실행 비용은 따로 움직일 수 있다.** | Conv 97(MAC 효율↑·비용↑), SRAM 예산(MAC 거의 같음·비용 +24–158 %), kws Size(MAC +605·비용 미판정) | MAC_ACTIVE와 NPU_ACTIVE는 항상 따로 보고 |
| 4 | **메모리 전송량은 유효 데이터 크기만으로 정해지지 않는다.** | 출력 쓰기 beat 규칙 A가 새 채널 4개에서 사전 예측과 일치. 채널 하나 감소에 EXT 쓰기 +93 % | 메커니즘 미검증 |
| 5 | **SRAM 예산을 늘리거나 특정 최적화 옵션을 쓴다고 같은 방향의 성능 변화가 보장되지 않는다.** | AD 64 KiB가 0보다 느림(×2.58 vs ×1.61). Size·Performance 차이는 미판정. Size가 SRAM을 같거나 더 씀. 예산 64–128 KiB에서 kernel 수·가중치 이동이 단조롭지 않음(정적) | kws·ad·독립 연산, Vela 5.0.0 |
| 6 | **AD 64 KiB가 느린 실행 구성은 원본 연산 단위로 특정했다.** | 연산 1–7의 stripe 분할(kernel +52), 연산 3 가중치 DRAM 재stream 16회, 5·7은 3회, 중간 데이터의 DRAM 경유, WD_ACTIVE ×2.15 | 개별 요인의 인과적 기여는 미분리 |
| 7 | **Vela 추정은 보드 변화를 항상 재현하지 않는다.** | Cout 95·DW 143: Vela ≤ 1 % vs 보드 +6–10 %. 5-1: 방향은 같고 폭이 다름 | 보드 `UNRESOLVED`인 경우는 예측 오류로 분류하지 않음 |

측정 도구에 대해 확인한 것:
- Driver Runner는 MLEK와 출력·beat·NPU_ACTIVE가 같다(일곱 모델; MAC/DPU/AO는 wav2letter만 `UNPROVEN`).
- MAC_ACTIVE는 독립 연산에서 RUN 간 결정적이다.
- 유효 MAC의 정의를 정정했다(Stage 5). 판정은 바뀌지 않았다.

## 답하지 못한 질문

| 질문 | 현재 상태 | 이유 |
| --- | --- | --- |
| 원본 모델 안에서 연산별로 시간이 얼마나 걸리는가 | **답 없음** | PMU Mask 창이 실행이 아니라 명령 해석을 따라감(2B-2). QREAD는 경계는 보이나 PMU 귀속 실패. 독립 연산 결과로 복원하지 않음 |
| 확인한 요인(채널 올림, ublock, 처리 구성, SRAM 배치)이 일곱 모델의 실행 시간에서 각각 얼마를 차지하는가 | **분리 못 함** | 독립 연산은 DRAM 조건. 모델 구성 비교는 여러 설정이 함께 바뀜 |
| NPU_ACTIVE 중 MAC 활동 밖의 부분(모델 15–99 %, 독립 연산 70–99 %)은 무엇으로 이루어지는가 | **분해 못 함** | 시간 분해 계측 없음. 전송 증가는 함께 관측되었을 뿐 메모리 대기로 배정하지 않음 |
| AD 64 KiB의 추가 시간 중 반복 가중치 이동·작업 분할·데이터 배치의 몫 | **미분리** | 네 예산에서 단일 요인만 다른 구성 없음 |
| vww4·yolo의 낮은 MAC 활성 사이클 효율(block fill은 높음), depthwise 모델의 MAC stalled by IB, rnnoise 보드 ÷ Vela 1.62, AO > MAC | **미설명** | 통제 실험이 이 모델·연산 조건을 직접 다루지 않음 |
| PartKernel → DepthFirst 전환에서 처리율을 바꾼 설정(traversal, IFM block, weight order) | **미분리** | 세 설정이 함께 바뀜 |
| kws Size MAC_ACTIVE +605, ad 64 KiB MAC_DPU −144, 출력 쓰기 규칙의 하드웨어 메커니즘 | **미확인** | 관측만 |
| 다른 입력, 다른 메모리 모드, 실제 DRAM(TA 없이)에서도 같은가 | **범위 밖** | 입력 하나, Dedicated_Sram만 검증, TA 에뮬레이션 |

## 남은 후보 (목록만, 자동으로 착수하지 않음)

1. MAC 활동이 같거나 좋아졌는데 전체 비용이 늘어나는 부분 (Conv 97, Cout 95, DW 143, kws·ad 예산) — 계약 필요
2. 모델의 낮은 MAC 활성 사이클 효율과 채널 올림·ublock padding의 관계 — Vela 산출물로 정적 계산
3. depthwise 비중 모델의 MAC stalled by IB — Reserved-ID 의미 확인이 먼저
4. rnnoise 보드 ÷ Vela 1.62 — 구성 확인
5. kws Size MAC_ACTIVE +605 — 가중치 stream 차이 산출물 비교

연산별 시간 귀속(2B H1/H2 재구성)은 새 방법 없이는 다시 시도하지 않는다. AD 관련 추가 탐색과 보드 측정은 종료했다.

## 보존물

**원시 데이터.**
- `evidence/fi101_s013/`, `evidence/driver_m7/`, `evidence/s2_groups/`, `evidence/qread_op_pilot/`
- `evidence/stage4/`, `evidence/stage4c1/`, `evidence/stage4c2/`, `evidence/stage4c2b/`
- `evidence/stage5/`, `evidence/stage5_2/`
- 보드 host의 캠페인 폴더는 정리하지 않았다.

**컴파일 산출물.**
- `evidence/stage5/stage5_0.json`, `evidence/stage5/workloads/`, `evidence/stage5_2/workloads/`
- `evidence/ad64k_static/vela_map/`(측정 구성), `evidence/ad64k_static/scan/`(예산 탐색)

**계약.** 각 stage의 `evidence/*/contract.md`. 측정 전에 동결했고, 정정은 Amendment로만 한다(예: 5-2 Amendment A).

**정정 이력.**
- Stage 5 유효 MAC: Vela 집계 → tflite 정의(`11b15d9`, 판정 불변을 `verdicts_unchanged.py`로 확인).
- 4C-2의 "Cin 33–63" 표현 범위 축소.
- 종합 보고서의 비례 관계 범위 정정, Vela 비교 분류 정정.
- AD kernel 수 표기(66 = 60 + 6).
