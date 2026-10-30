# Stage 0 미결 해소 → 다음 단계 진입 순서 (2026-10-31)

Owner 결정 2026-10-31: "제안한 순서대로 기록하고, 단계 하나씩 따라가자". 단계마다 끝나면 결과를 아래 상태 칸과
해당 결과 폴더에 기록하고, 다음 단계로 넘어가기 전에 보고한다. 보드 수치는 전부 TA profile 1.

배경: `results/fi101_stage0/` — S0-1/2/4 PASS(7개 모델), **S0-3 FAIL 5/7**(NPU `PMCCNTR` 구간이 같은 seam 사이
CPU DWT 구간보다 0–31 % 짧음, 모델마다 다르고 RUN 간 안정), S0-5 FAIL 3/7(짧은 모델 ±1.5k 사이클 흔들림),
S0-8 NOT_AVAILABLE(system counter 꺼짐). Stage 2(그룹별 비용, Σgroup vs 전체)는 어느 시계로 비용을 셀지가
정해져야 하므로 S0-3을 먼저 푼다.

| # | 단계 | 내용 | 보드 | 상태 |
| --- | --- | --- | --- | --- |
| 0 | 결과표 규칙 위반 수정 | 계약 규칙 "`COUNTED_NONZERO`가 아닌 이벤트는 비율에 쓰지 않는다"를 어긴 칸(`stage3.csv`, `unit_stalls.csv`: stall 한도 142/143/398/399, 쓰기 stall 137/393, 54/69/72, EXT 쓰기 포트 647/663 불균형)을 판정 라벨로 바꾸고, 분석 코드에 규칙과 시험(뮤테이션 포함)을 넣는다 | 없음 | **완료** |
| 1 | S0-3 상관 분석 | 7개 모델의 CPU−NPU 차이를 Vela 연산 수·명령 수, 채널별 트래픽, DMA(mem2mem), stall 지표와 대조해 가설 후보를 좁힌다. `POST_HOC_DESCRIPTIVE` | 없음 | **완료** |
| 2 | S0-3 보드 진단 A/B | 1의 결과로 범위 확정 후 계약 고정. 후보: (2a) TA profile 1 ↔ 2 한 변수 비교 — mobilenet, yolo + 대조 rnnoise; (2b) U85 TRM에 클록 게이팅 강제 해제 레지스터가 있으면 on/off 비교(NPU 레지스터 쓰기 = 조건 변경, 별도 계약) | 있음 (2–3 h) | 다음 (범위 결정 필요) |
| 3 | CPU 클록 독립 확인 (선택) | system counter 활성화(시스템 레지스터 쓰기 → 승인 필요) 또는 긴 고정 루프 vs 호스트 시간. 초 단위 지연 보고에 필요 | 있음 | 대기 |
| → | 다음 단계 | Stage 2 설계·계약 초안 (S0-3 결론에 따라 비용 시계 결정) | — | 대기 |

S0-5는 해소 대상이 아니다: 원인(짧은 모델의 RUN 간 흔들림)이 알려져 있고, 반복 수와 보고 문구로 처리한다.

## 단계별 기록

(단계가 끝날 때마다 여기에 결과·커밋·검증 수준을 추가한다.)

### 0. 결과표 규칙 위반 수정 — 완료 2026-10-31

- `host/analysis/fi101_s013.py`: `ratio()`와 포트 불균형이 두 이벤트 중 하나라도 `COUNTED_NONZERO`가 아니면 숫자 대신
  판정(`COUNTED_ZERO` / `INCONSISTENT` / `OVERFLOW` / `NOT_OBSERVED`)을 돌려준다. 바이트 수는 비율이 아니므로 그대로.
- 시험 2개 추가(RED 확인 후 GREEN). 뮤테이션 5개 전부 RED, 다이제스트로 복원. `sh test.sh` ALL PASS.
- 같은 원시 데이터(boots 94–100)로 재생성: 바뀐 칸 40개(stage3 32, unit_stalls 8 = COUNTED_ZERO 36 + INCONSISTENT 4)는
  모두 숫자→판정 라벨. 다른 숫자는 하나도 바뀌지 않음. Stage 0 표 3개 동일, Stage 1 숫자 동일(Pass A는 전부 nonzero).
- `results/fi101_stage3/README.md` 표 칸 갱신, 정정 문단 추가. EXT 쓰기 불균형 "1.00"은 계산하지 않음으로 정정.

### 1. S0-3 상관 분석 — 완료 2026-10-31 (`results/fi101_s0_3_correlation/`)

- 차이(CPU − NPU 사이클)는 **SRAM 쓰기 beat**와 7개 모델 순위가 완전히 일치(Spearman +1.00, mobilenet 빼도 +1.00).
  비례는 아님(쓰기 beat당 0.31–0.85 사이클), rnnoise(쓰기 135 beat)는 차이 0.
- 경과 시간·EXT 트래픽과는 맞지 않음: wav2letter는 가장 길고 EXT 읽기가 가장 많은데 차이 0.3 %. → 시간에 따른 주기적
  NPU 클록 정지나 TA EXT 지연 에뮬레이션과는 무관해 보임.
- 비율로 보면 `mac_stalled_by_ib`와 가장 잘 맞음(+0.93), SRAM 트래픽과 공선.
- 2단계 후보(시험 안 함): (a) TA_SRAM — profile 1 ↔ 2, 기존 knob; (b) `CLKFORCE`(0x140, 드라이버 헤더에 "force clocks
  on for clock gating", 드라이버·러너 둘 다 쓰지 않음) — 펌웨어 knob 필요; (c) CPU와 on-chip SRAM 공유(러너는 캐시 끈
  채 on-chip SRAM에서 busy-poll) — 펌웨어 변경 필요.
