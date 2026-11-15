# UNSTABLE 3개 형상 사후 진단 (Phase 3) — 판정 변경 없음

- 자료: 6B-B 원시 RUN(TA profile 1, 이미지 `70090f1`, boot 414·416·420)이다. RUN별 값은 `unstable_runs.csv`, 형상별 요약은 `unstable_summary.csv`에 있다.
- G53·G56·G28은 `UNSTABLE`로 남는다. 5 % 기준을 완화하지 않으며, 이들의 MAC 처리율은 공식 결과에 넣지 않는다.
- 아래 내용은 모두 **실측 원시값의 기술**이다. 원인에 대한 언급은 미검증 추론으로 표시한다.

## 1. RUN 순서별 NPU_ACTIVE (warm-up 제외, 측정 RUN 2–5)

| 형상 | pass A | pass A range (%) | pass B | pass B range | 판정 사유 |
| --- | --- | ---: | --- | ---: | --- |
| G53 (boot 414) | 16,926 16,560 17,417 17,278 | 857 (5.01 %) | 16,549 17,384 16,934 16,923 | 835 | range > 5 % |
| G56 (boot 416) | 12,886 13,405 13,487 14,425 | 1,539 (11.4 %) | 14,098 14,093 14,091 13,271 | 827 | range > 5 % |
| G28 (boot 420) | 20,662 20,313 20,435 21,658 | 1,345 (6.5 %) | 20,662 20,710 20,919 20,738 | 257 | range > 5 % |
| 참고: 기준 Cin48 (VALID) | 23,007 23,091 22,271 22,317 | 820 (3.6 %) | | 929 | — |
| 참고: G57 (VALID) | 19,431 19,040 18,676 19,222 | 755 (3.9 %) | | 270 | — |
| 참고: G52 (VALID) | | 29 (0.09 %) | | 926 | — |

- G56의 pass A는 측정 RUN 순서대로 증가한다(12,886 → 14,425). pass B는 마지막 RUN만 떨어진다(14,091 → 13,271).
  - RUN 4개라서 경향이라고 말할 수 없다.
- pass A와 B의 중앙값 차이는 세 형상 모두 Stage 4AO-E 규칙(5 % 또는 두 range의 합) 안이다. 그래서 판정 사유는 pass A range 하나다.

## 2. 함께 변하는 카운터

- **MAC_ACTIVE와 MAC_DPU_ACTIVE**: 세 형상 모두 RUN 간 range 0이다. MAC 계산량은 RUN마다 같다.
- **AO_ACTIVE**: range 1–3 사이클이다(G53 3, G56 1, G28 3). NPU_ACTIVE 변동(800–1,500)에 비해 무시할 수준이다.
- **WD_ACTIVE**: range는 G53 84, G56 5, G28 326이다.
- **WD_STALLED**: range는 G53 885, G56 697, G28 697이다.
  - G53은 두 값(약 1,350과 약 2,200)을 오가지만, NPU_ACTIVE 순서와 맞지 않는다. 예: rep 2는 WD_STALLED 2,264에 NPU_ACTIVE 16,926이고, rep 4는 2,176에 17,417이다.
  - 측정 RUN 4개의 순위 상관(Spearman)은 G53 0.21, G56 0.26, G28 0.40이다. 표본이 4개라 의미를 두지 않는다.
- **메모리 traffic**(pass B): EXT read transaction, EXT read/write beat, SRAM read beat 모두 RUN 간 range 0이다. 전송량은 RUN마다 같다.
- **측정창 − NPU_ACTIVE**: pass A 측정 RUN의 중앙값이 11개 형상 모두 533–582 사이클이다(UNSTABLE 세 형상 577–577.5). 변동은 측정창 쪽이 아니라 NPU 활성 구간 안에 있다.

## 3. 다른 형상과 비교

- NPU_ACTIVE의 절대 range는 VALID 형상에서도 29–1,105 사이클이다(기준 820, G09 1,105). UNSTABLE 세 형상의 857–1,539와 크기가 겹친다.
- UNSTABLE 세 형상은 NPU_ACTIVE 중앙값이 가장 작은 네 형상 중 셋이다(13.4k, 17.1k, 20.5k). 나머지 하나 G57(19.1k)은 3.9 %로 기준 안이었다.
- 같은 절대 변동이 작은 총량에서는 5 %를 넘는다는 관찰과 맞는다. 하지만 작은 OFM 크기나 작은 총량이 원인이라고 확정하지 않는다.
  - VALID인 G52(31.1k)는 range가 29로 매우 작다. 즉 절대 변동이 형상마다 다르다.
- 실행 구성: 세 형상 모두 커널 1개, DepthFirst, Sram→Sram이다.
  - G53·G56은 ublock 2×4×16이다. VALID 중에는 이 ublock이 없다.
  - G28은 ublock 2×2×32에 OFM 4×4, OFM block 4×4×288이다.
  - 구성이 UNSTABLE과 함께 바뀌는 변수(ublock, 출력 크기, 총량)가 여럿이라 하나로 좁힐 수 없다.

## 4. 결론

- MAC_ACTIVE는 일정하고 NPU_ACTIVE만 변했다. 같은 RUN들에서 전송량, MAC, AO는 변하지 않았다.
- 변동은 WD_STALLED의 RUN별 변화와도 일치하지 않는다.
- 이 PMU 집합으로는 원인을 식별할 관측이 **없다**(`CAUSE_UNRESOLVED`).
  - 후보로 메모리 지연·중재, DMA·명령 처리의 타이밍 변동을 생각할 수 있지만 미검증 추론이다.
  - 이런 지연은 reserved 이벤트나 다른 pass에서만 보일 수 있다.
