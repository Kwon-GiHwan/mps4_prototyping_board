# A5 — 실효 메모리 대역폭 대 Timing Adapter 상한 (POST_HOC_DESCRIPTIVE)

**2026-09-14.** REPORT 부록 B의 `effective bandwidth: NOT_EVALUABLE` 행을 평가한다.
동결 당시 등록되지 않은 지표이므로 결론에 쓰지 않고 `POST_HOC_DESCRIPTIVE`로만 표시한다.
계약: `docs/superpowers/plans/2026-09-14-unresolved-items-evaluation-plan.md` §1,
계약 커밋 `4631acc`(값 계산 전). 계산기 `a5_effective_bandwidth.py`, 게이트 검사 9개,
돌연변이 3종 RED 확인 후 digest 복원. 결과 `a5_effective_bandwidth.csv` (74셀).

## 입력

- beat 수·사이클: `canonical_cells.csv`(U55/U65, SSE-300 TA ON 39셀),
  `R1_MEMORY_COUNTERS.csv`(U85, 35셀, R1 첫 반복).
- TA 파라미터: `ta_parameters.csv` — 서버 MLEK `scripts/cmake/timing_adapter/*.cmake`의
  Shared/Dedicated 분기 값 (2026-09-14 read-only 확인).
- 식: `eff = Σbeat × bytes_per_word / npu_total_cycles`,
  `cap = BWCAP × bytes_per_word / (PULSE_ON + PULSE_OFF)`, `util = eff / cap`(포트 1개 기준).

## 가정과 확인 상태

계산 당시에는 네 가지를 가정했다. 같은 날 서버의 MLEK 문서
`docs/sections/timing_adapters.md`(read-only)로 1·2가 확인됐고 3은 부분 확인이다.

1. **확인됨.** "`BWCAP`: Maximum number of bus-width words (beats) transferred per pulse
   cycle … The bus-width word size depends on the NPU AXI bus width: U55 64-bit, U65 128-bit,
   U85 128-bit." TA word = beat.
2. **확인됨.** "A pulse cycle is defined by `PULSE_ON` and `PULSE_OFF`." 즉 cap =
   BWCAP ÷ (PULSE_ON + PULSE_OFF)이 문서의 정의와 같다. 아래의 "PULSE_ON 창만" 민감도는
   더 이상 필요 없다. 같은 문서의 주의: "The bandwidth cap operates on the transaction
   level and, because of its simple implementation, the accuracy is limited" — 트랜잭션
   단위로 세므로 cap을 약간 넘는 값(1.01–1.08)이 나올 수 있다. util > 1은 모델의 반올림이지
   측정 오류가 아니다.
3. **부분 확인.** 문서는 TA가 "two AXI buses used by Ethos-U NPU — one for SRAM, one for
   flash/DDR"를 제어한다고 적고, 펌웨어도 TA 인스턴스 두 개(TA_SRAM, TA_EXT)만 설정한다.
   따라서 cap은 포트가 아니라 **경로(SRAM/EXT) 단위**로 읽는 것이 문서와 맞다. 다만
   SSE-320 FVP에서 U85의 SRAM 포트 2–4개가 실제로 그 한 TA를 지나는지는 확인하지 못했다.
   포트 1개 기준 값이 문서와 일치하는 읽기이고, 포트 전체 기준 값은 보수적 하한으로만 남긴다.
4. **미확인.** NPU 사이클 카운터와 TA가 같은 클럭이라는 가정.

## 매니저 검토(2026-09-14) 반영 — 표현 범위 축소, 값 변경 없음

- `AT_LIMIT`는 "**TA가 설정한 명목 대역폭 예산에 근접**"으로 읽는다. TA cap은 물리 Flash/DRAM의
  최대 대역폭이 아니라 시뮬레이터가 부과한 장기 평균 전송 예산이며, 이 결과는 실제 소자의
  포화를 입증하지 않는다.
- U85 `SATURATION_RULED_OUT`는 "**전체 추론 평균에서 외부 경로의 지속적 집계 대역폭 포화를
  뒷받침하지 않는다**"까지다. 일부 구간에 전송이 몰려 그때만 cap에 걸리는 경우, 포트별 집중,
  낮은 요청 동시성으로 평균이 낮은 경우는 배제하지 못한다. 배제에 가까워지려면 같은 프로그램·
  지연에서 BWCAP을 완화해도 사이클이 변하지 않음을 보여야 한다(캠페인 B·E).
- U55의 AXI1 write도 U65와 같이 **측정하지 않았다**. "구조적으로 없다"는 Vela 설정(Shared_Sram의
  외부 영역 read-only 가정)에서 온 추론이지 측정값 0이 아니다. 표에서 U55 EXT를 complete로
  처리한 것은 이 추론에 의존한다.
- 113k 전송 시간과 105–112k 측정 사이클의 근접은 같은 cap 공식에서 나온 값이므로 독립 측정
  두 개의 일치가 아니다. 보조 근거로만 쓴다.
- TA cap과 Vela ini 주석의 일치는 두 설정이 같은 레퍼런스를 표현하도록 작성됐다는 일관성
  확인이지 성능 검증이 아니다.

## 결과 요약 (닫힌 집합)

| 포트 | NPU | SATURATION_RULED_OUT | NEAR_LIMIT | AT_LIMIT | LOWER_BOUND_ONLY |
|---|---|---|---|---|---|
| SRAM | U55 (25) | 15 | 10 | 0 | – |
| SRAM | U65 (14) | 10 | 4 | 0 | – |
| SRAM | U85 (35) | 21 | 12 | 2 (포트 1개 기준) | – |
| EXT | U55 (25) | 16 | 4 | 5 | – |
| EXT | U65 (14) | – | – | 0 | 14 (AXI1 write 미수집, 하한 0.47–0.61) |
| EXT | U85 (35) | 32 | 2 | 1 | – |

`NOT_EVALUABLE` 0건. 규칙 발동 0건.

## 주목할 셀

**U55 RNNoise, EXT(Flash) — 4/4 AT_LIMIT.**

| MAC | 측정 사이클 | AXI1 read beat | eff (B/cyc) | util | beat×8 B ÷ cap |
|---|---|---|---|---|---|
| 32 | 112,059 | 14,178 | 1.012 | 1.01 | 113,426 |
| 64 | 109,059 | 14,176 | 1.040 | 1.04 | 113,410 |
| 128 | 106,059 | 14,165 | 1.069 | 1.07 | 113,324 |
| 256 | 105,059 | 14,165 | 1.079 | 1.08 | 113,317 |

가중치를 Flash에서 읽어 오는 데 TA 상한으로 필요한 최소 사이클(≈113k)이 측정 사이클과
1–8% 안에서 일치하며, MAC을 8배 늘려도 사이클이 그대로인 구간과 정확히 겹친다. 17장의
"U55 RNNoise 효율 0.50–0.51"에 대한 메모리 쪽 설명이 처음으로 수치로 나온 것이다.
util이 1을 넘는 것은 가정 2의 cap이 너무 낮게 잡혔다는 뜻이다. PULSE_ON 창만 쓰면
cap 1.25 B/cyc, util 0.81–0.86으로 `NEAR_LIMIT`가 된다. 어느 해석이든 "Flash 대역폭이
거의 전부 쓰였다"는 서술은 유지되고, "포화" 단어는 가정 2가 확인될 때까지 쓰지 않는다.

**U55 Wav2Letter 256 MAC, EXT — util 0.90 (AT_LIMIT 경계).** 가중치 13.8 MB를 Flash에서
읽는 모델이며, 실행 가능했던 유일한 U55 구성이다.

**U85 Wav2Letter 2048 MAC, EXT — util 0.94 (포트 1개 기준), 포트 2개 기준 0.47.**
가정 3 때문에 판정을 채택하지 않는다.

**U85 SRAM AT_LIMIT 2건(YOLO 1024·2048)** 도 포트 1개 기준이며, 포트 전체 기준으로는
0.48·0.28이다. 가정 3 미확인 → 채택하지 않음.

**U85 RNNoise, EXT — util 0.45 (128·256), 0.19–0.21 (512 이상). 전부 RULED_OUT.**
U55와 달리 U85에서는 외부 대역폭이 남는다. RNNoise의 U85 256→512 사이클 증가는
대역폭 상한으로 설명되지 않으며, 18장의 소형 연산 그룹 설명과 어긋나지 않는다.

**U65 EXT 전부 LOWER_BOUND_ONLY.** AXI1 write가 없어 하한(0.47–0.61)만 있다. 부록 A4의
U85 추정(외부 write 0–4%)을 적용해도 0.9를 넘는 셀은 없다.

## 요인 판정에 미치는 영향 (제안, 동결 판정은 amendment로만 갱신)

| 요인 | 동결 판정 | 이 분석 후 |
|---|---|---|
| 1 SRAM 대역폭 | NOT_EVALUABLE | U55/U65: 포트 1개 기준으로도 0.9 미만 → `SATURATION_RULED_OUT` 또는 `NEAR_LIMIT`. U85: 가정 3 미확인으로 `NOT_SEPARATED` |
| 2 외부 메모리 | NOT_EVALUABLE | **U55 RNNoise: Flash 대역폭 상한과 `CONSISTENT_WITH`** (4/4 AT_LIMIT, 전송 시간 ≈ 측정 사이클). U85 RNNoise: `SATURATION_RULED_OUT`. 지연(latency) 자체는 여전히 미평가 — 이 분석은 대역폭만 본다 |

"원인"이라고 쓰지 않는다. 대역폭이 상한에 있었다는 것과 그것이 사이클을 결정했다는
것은 다른 주장이며, 후자는 TA 대역폭만 바꾼 실험(계획 §5의 두 번째 캠페인)이 있어야 한다.

## 확인이 필요한 것 (다음 단계)

- 가정 2: Arm Timing Adapter 문서에서 BWCAP·PULSE 의미 확인. 문서만으로 해소된다.
- 가정 3: SSE-320 FVP에서 TA 인스턴스가 포트마다 있는지 (`--list-params`의 TA 관련
  파라미터 수로 확인 가능, read-only).
- U55 RNNoise가 정말 Flash 대역폭에 묶였는지는 계획 §5의 BWCAP 변주(1건, U55 256 MAC)로
  직접 검증할 수 있다. GO 필요.

## 재현

```sh
python3 docs/paper/raw_data_report/amendments/a5_effective_bandwidth.py
python3 -m unittest docs.paper.raw_data_report.amendments.test_a5_effective_bandwidth
```
