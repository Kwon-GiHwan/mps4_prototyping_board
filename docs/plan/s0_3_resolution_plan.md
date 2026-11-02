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
| 2 | S0-3 보드 진단 A/B | 1의 결과로 범위 확정 후 계약 고정. 후보: (2a) TA profile 1 ↔ 2 한 변수 비교 — mobilenet, yolo + 대조 rnnoise; (2b) U85 TRM에 클록 게이팅 강제 해제 레지스터가 있으면 on/off 비교(NPU 레지스터 쓰기 = 조건 변경, 별도 계약) | 있음 (2–3 h) | 2a **완료**: TA_NOT_EXPLAINS |
| 2a′ | TA 레지스터 의미 확인 | 2a의 처리 조건(profile 2: `pulse_on` 0xFFFF, `pulse_off` 0, `bwcap` 0, 한도·지연 0, mode 1)이 실제로 "제한 없음"인지 timing adapter 소스·문서로 확인. 2b 계약 전에 끝낸다 | 없음 | **완료**: 한도 값은 문서대로지만 MODE bit 0(dynamic clocking)이 두 profile 모두 켜짐 |
| 2c | TA `MCLK_OFF` 계수 (2a′에서 제안, 2b보다 먼저) | 두 TA PERFCTRL = 19, inference 구간의 NPU 클록 정지 사이클을 세어 CPU−NPU 차이와 비교. profile 1, 7개 모델. 펌웨어 knob·계약 필요. 2d(dynamic clocking 끔) 같은 캠페인에 포함 | 있음 | **완료**: CAUSE_CONFIRMED → S0-3 해소 |
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

### 2a. TA profile 1 ↔ 2 — 완료 2026-11-02 (`results/fi101_s0_3_ta/`)

- Owner 결정: 7개 모델 전부. 계약 `evidence/s0_3_ta/contract.md`(aadc143, boot 129 전 고정), 판정 코드
  `host/analysis/s0_3_ta.py`(5619e79, 데이터 전 커밋; 뮤테이션 12개 중 1개 생존 → 시험 추가 후 사망).
- 이미지 `2bb04bfa` 배포 확인(evidence_s03ta_deploy), boots 129(mobilenet profile 1 drift) + 130–136(profile 2).
- 판정: drift OK, 5개 모델 모두 TA_NO_EFFECT → **TA_NOT_EXPLAINS**. 기술: profile 2에서 차이가 7개 모델 모두 크게
  커짐(NPU 구간의 48–160 %). NPU 사이클은 줄었는데 CPU 경과 시간은 6/7 모델에서 늘었다 → NPU 계수 사이클 ≠ 경과 시간.
- 다음 후보: TA 레지스터 값(profile 2의 `pulse_off` 0, `bwcap` 0 등)의 의미를 문서로 확인(보드 없음),
  2b `CLKFORCE`. 보드 복원·postflight 완료.

#### 2a 특이사항 (2026-11-02 기록, 후속 단계에서 다시 꺼낼 것)

1. **방향이 예상과 반대.** profile 2에서 NPU 계수 사이클은 7개 모델 모두 줄었는데(−14 ~ −80 %) CPU DWT 경과 시간은
   6/7 모델에서 늘었다(+18 ~ +44 %). rnnoise만 둘 다 줄었다(−80 % / −64 %). 차이(CPU − NPU)는 7개 모델 모두 커졌고,
   profile 1에서 차이가 없던 rnnoise(0 % → 82 %)·wav2letter(0.3 % → 48 %)도 마찬가지.
2. **트래픽은 같다.** SRAM·EXT 읽기·쓰기 beat 중앙값 4개가 7개 모델 모두 두 profile에서 동일. 바뀐 것은 시간뿐.
3. **profile 1 rnnoise는 NPU·CPU 중앙값이 1 사이클 차이**(53,040.5 / 53,039.5, `describe.csv`). 두 계수기가 같은 클록으로 셀 수 있다는
   방증이지만, 클록 주파수 자체(공칭 50 MHz)는 확인하지 않았다.
4. **"pass-through"는 검증하지 않은 이름.** profile 2 값은 러너에서 정했고(`firmware/common/ta.c`, `host/lib/pmwl.py`),
   `pulse_off` 0·`bwcap` 0·`pulse_on` 0xFFFF가 "제한 없음"인지 timing adapter 문서로 확인한 적이 없다 → 2a′.
5. **해석 가설(시험 안 함):** NPU 계수기가 실행 중 일부 구간에서 멈춘다(클록 게이팅·정지). 멈추는 비율이 TA 설정에
   따라 달라진다 → 2b `CLKFORCE`가 직접 시험.
6. **이전 결론에 미치는 영향.** `evidence/ta_ab/`의 "TA 상태가 NPU 사이클을 3.7–7배 바꿈"과 "profile 2 = 최고 속도"는
   NPU 계수 사이클 기준이다. 경과 시간 기준으로는 확인되지 않았다(이 실험에서는 오히려 느려짐). CLAUDE.md의 문장은
   "NPU-active cycles"라 틀린 것은 아니지만, 속도로 읽으면 안 된다. CLAUDE.md는 승인 없이 고치지 않는다.
7. **profile 1(MLEK 조건) 결과는 영향 없음.** 이 실험은 profile 1 데이터를 바꾸지 않았고 drift도 OK.
8. **확인하지 않은 것:** profile 2 출력(OFM)의 정답 비교, CPU 클록 주파수, `CLKFORCE` 효과.
9. **과정 오류:** README 표를 손으로 옮겨 최대 0.4 % 틀림 → CSV 값으로 교체(`3a435bc`). "트래픽 동일" 문장은 작성 후
   CSV로 확인했다.

### 2a′. TA 레지스터 의미 확인 — 완료 2026-11-02 (`results/fi101_s0_3_ta/ta_semantics.md`, 보드 없음)

- 근거: MLEK core-platform `timing_adapter.h`/`.c`(02d02901842f), MLEK `docs/sections/timing_adapters.md`,
  `ta_config_u85_sys_dram_mid.cmake`. FI101 application note는 찾지 못함.
- profile 2의 한도 값(MAXR/W/RW 0 = 무한, latency 0 = 추가 최소 지연 없음, PULSE_OFF 0 = 차단 없음, BWCAP 0 = 무한,
  MODE 주파수 배율 0 = 최고 속도)은 문서대로 "제한 없음"이 맞다.
- **그러나 MODE bit 0 = 1 ("enable dynamic clocking to avoid underrun")이 두 profile 모두 켜져 있다.** TA 계수기 이벤트에
  `MCLK_ON`(18)/`MCLK_OFF`(19) "DUT clock is on/off"가 있다 → TA가 NPU 클록을 멈출 수 있다. MLEK 문서는 같은 비트를
  "QoS throttling"으로 다르게 설명한다(어느 쪽이 FI101에 맞는지 미확인).
- **2a의 한계:** 2a는 한도·지연 값만 바꿨고 dynamic clocking 비트는 변수가 아니었다. `TA_NOT_EXPLAINS`는 "한도·지연 값이
  차이를 없애지 못한다"까지만 뜻한다. 계약 문구 "one variable: the TA state"는 실제보다 넓게 썼다(계약은 수정하지 않고
  여기와 결과 문서에 기록).
- 가설(시험 안 함): 실제 FPGA 메모리가 에뮬레이션 지연을 못 맞추면 TA가 NPU 클록을 멈춘다 → NPU `PMCCNTR`은 멈춘 구간을
  세지 않고 CPU DWT는 센다. SRAM 쓰기 beat와의 순위 일치, profile 2에서 차이 증가를 모두 설명. profile 2에서 CPU 경과
  시간이 늘어나는 이유는 설명 못 함.
- **원래 목적(Stage 2 비용 시계)과의 연결:** 가설이 맞으면 NPU `PMCCNTR` = MLEK가 보고하는 "에뮬레이션된 시스템"의 시계이고,
  S0-3의 기대(NPU 구간 = CPU 구간)가 FI101에서는 틀린 기대가 된다.
- 다음 단계 제안(2b 앞에 둠): **2c TA `MCLK_OFF` 계수** — 두 TA의 PERFCTRL = 19, start seam에서 PERFCNT 0, CPM seam에서
  읽기, profile 1, 7개 모델. 예측: `MCLK_OFF` ≈ `infer_cpu − infer_npu`. 펌웨어 knob·계약 필요. 계수기 선택이 TA 타이밍을
  바꾸지 않는다는 것은 가정이며 drift 확인으로 점검. 2b `CLKFORCE`(NPU 레지스터 쓰기 = 조건 변경)는 그 뒤.

### 2c/2d. TA `MCLK_OFF` 계수 + dynamic clocking 끔 — 완료 2026-11-03 (`results/fi101_s0_3_clk/`)

- Owner 2026-11-02 "원인 알아낼 때 까지 진행해". 펌웨어 `d76acbd`(word 28 TA 계수기 선택, TA profile 3), 이미지
  `a7e9feeb`, 계약 `evidence/s0_3_clk/contract.md`(`3c71ef6`, boot 137 전 고정, 판정 코드 뮤테이션 23개 사망).
- boots 137–157, 7개 모델 × (c1 profile 1 MCLK_OFF / c2 profile 1 CYCLES·MCLK_ON / d profile 3), 21/21 부팅 전 RUN 유효.
- 판정 **CAUSE_CONFIRMED** (`1666fa1`): 5개 모델 모두 CLOCK_STOP_MATCHES(e 0.995–1.000) + MODE0_REMOVES_GAP, drift 7/7 OK.
- 기술: c1의 56 RUN 전부에서 두 TA의 MCLK_OFF = CPU − NPU, 사이클 단위로 정확히 일치. d에서는 차이 0.
- **S0-3 해소:** 차이는 TA가 에뮬레이션 지연을 맞추려고 NPU 클록을 멈춘 시간. NPU 사이클 = 에뮬레이션된 시스템(MLEK
  기준)의 시계 → **Stage 2 비용 시계는 NPU 사이클**. 2b `CLKFORCE`는 불필요(원인 확정). 3(CPU 클록)은 c2에서 TA root
  clock = CPU clock 관찰로 일부 답함(절대 주파수는 여전히 미확인).
- 데이터 후 수정: 서술 열 계산의 0 나눗셈(rnnoise) — 판정 규칙 불변, 결과 README에 기록.
- 다음: Stage 2 설계·계약 초안 (비용 시계 = NPU 사이클, TA profile 1).
