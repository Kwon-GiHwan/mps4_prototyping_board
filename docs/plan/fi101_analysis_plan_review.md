# FI101 분석 계획(Stage 0–5) 실행 가능성 검토 — 2026-10-28

대상: 소유자가 제시한 "Stage 0 실보드 환경 및 PMU 검증 ~ Stage 5 메모리 배치·컴파일 조건 비교, PMU Pass A–D" 계획.
이 문서는 **검토 기록**이다. 계약이 아니며 측정을 하지 않았다. 각 Stage를 실행할 때 별도 계약을 먼저 동결한다.
모든 보드 수치는 **TA profile 1** (MLEK `ta_config_u85_sys_dram_mid`) 기준이다.

판정 표기: **가능** = 지금 러너·도구로 바로 측정 가능 / **조건부** = 측정은 되지만 정의·창·해석을 바꿔야 함 /
**개발 필요** = 펌웨어 또는 호스트 기능 추가 후 가능 / **부적합** = 지표의 의미가 맞지 않음.

## 검토 근거 (이미 확보된 사실)

| 사실 | 근거 |
| --- | --- |
| 이벤트 카운터 8개(32-bit), 사이클 카운터 `PMCCNTR` 별도(필드 48-bit `CYCLE_CNT[47:0]`, 레지스터 64-bit) | `docs/reference/ETHOS_U85_PMU_REFERENCE.md` §3 |
| FI101 = 1024 MAC, SRAM 포트 2 · EXT 포트 2(각 128-bit = 16 B/beat), WD 4 — `CONFIG=0x2000251a`로 보드에서 확인 | 같은 문서 §5, §8 Tier A |
| `EV_TYPE` 0–1023 전부 쓰기 수용(수용 ≠ 카운트). 테스트 conv(TA untouched)에서 TRM-110 중 34개, Reserved-61 중 42개가 nonzero | 같은 문서 §8 Tier B |
| `*_stall_limit` 전부 0, `axi_latency_64/512/1024` 0/1 경계에서 INCONSISTENT (작은 테스트 연산, TA untouched) | `refactor/unified-mlek-campaigns:evidence/pmu_events/boot9/PER_EVENT.md` |
| Pass A의 8개 이벤트(35, 48, 51, 52, 55, 64, 80, 81)는 Stage 2A에서 TA profile 1로 이미 측정됨 (conv3x3, dw3x3, pw1x1) | `config/stage2a_ids.txt`, `evidence/stage2a/tables.md` |
| Stage 2A에서 `mac_dpu_active / mac_active` = **1.000** (세 연산 모두) | `evidence/stage2a/tables.md` |
| **러너의 `PMCCNTR` 창은 CPU 복사를 포함한다**: wav2letter `PMCCNTR` 250,254,490 vs `npu_active` 4,132,552; kws 2,625,515 vs 91,481 | boot 93 / boot 80 `raw_runs.json` |
| `sram_enabled_cycles`(140) ≈ 2 × `PMCCNTR` (wav2letter 500,509,914; kws 5,251,964) → 집계형 이벤트는 **포트 2개의 합**이고 창 전체를 센다 | 같은 기록 |
| NPU `PMCCNTR`(250.25 M)와 CPU DWT 창(250.64 M)이 0.15 % 안에서 같다 → 두 카운터는 같은 클럭(선언값 `SYSTEM_CLOCK` 50 MHz, 미검증) | 같은 기록, selftest `clock_definition.h` |
| 러너 RUN당 기록: 8 이벤트, PMCCNTR, overflow 상태(`seam_ovf`), seam 1회 발생, knob read-back, OFM 비교. 한 부팅에 여러 이벤트 세트 가능(blob 1회 업로드) | `firmware/runner/`, `host/board/run_pmu_events.py` |
| 측정 시간: 모델당 업로드가 지배 (wav2letter 약 33분, 나머지 1–9분), RUN 자체는 6.6 s 이하 | x1 기록 |

## Stage 0 — 실보드 환경 및 PMU 검증

| 항목 | 판정 | 검토 |
| --- | --- | --- |
| 실행 사이클 `PMCCNTR` | **조건부** | 러너의 `PMCCNTR`은 PMU arm부터 seam 판독까지라 **CPU staging 복사(14.5 MB면 ~4.9 s)가 들어간다**. "NPU 하드웨어 사이클"로 쓰려면 창을 다시 정의해야 한다: (a) 지연은 `npu_active`로 보고(현행 규칙), (b) `PMCCNTR_CFG.CYCLE_CNT_CFG_START/STOP`을 `npu_active` 등 이벤트로 걸어 NPU 실행 구간만 세게 하기(TRM 기능, 러너 미구현 → 개발 필요), (c) 복사를 창 밖으로 옮기기(측정 경로 변경 → 재검증 필요). 미결 E4와 같은 과제. |
| NPU 활성 `NPU_ACTIVE` | **가능** | 이미 기준 지표. MLEK 대비 ±0.4 % 재현(Stage 0 기록). |
| 실행시간(외부·CPU 타이머) | **조건부** | NPU와 CPU 카운터가 같은 클럭이라 "NPU 사이클과 실제 시간 구분"은 **주파수 하나를 확인하는 문제**로 줄어든다. 선언값 50 MHz는 미검증 → SSE-320 system counter(`Drivers/syscounter_armv8_driver`, 독립 refclk)로 DWT 대비 비율을 한 번 측정하면 된다. 호스트 벽시계는 UART 지연 때문에 부적합. |
| 반복 편차 (Median, Min/Max, CV) | **가능** | `mlek_r10` = 측정 8회. CV는 n=8이라 0.1 % 단위 비교에는 약하다(Stage 1은 30회). |
| 계측 오버헤드 | **조건부** (의미 수정) | PMU 카운팅은 하드웨어라 NPU 실행에 비용이 없다. 오버헤드가 생기는 곳은 (1) PMU arm/판독을 위한 CPU 코드(창 밖), (2) **Stage 2의 그룹 분할(IRQ·stream 분할)**. 측정 가능한 형태: 러너 instrumentation `OFF` vs `EVENTS`의 CPU DWT 창 차이, 그리고 Stage 2에서 Σgroup vs 전체 실행. 이미 확보된 동등성 근거: MLEK 대비 `npu_active` ±0.4 %. |
| 그룹 계측 일관성 ΣGroup/Model | **개발 필요** | 러너는 명령 스트림 전체를 IRQ 1회로 실행한다. 그룹 계측 기능이 생겨야 측정할 수 있다(Stage 2 참조). FVP에서는 같은 검사가 통과했다(`U85_P1B_RESULTS.md` Coherence). |
| PMU 이벤트 유효성 (변화·Overflow·지원) | **가능** (재실시 권장) | Tier B는 TA untouched·작은 테스트 연산이라 실제 모델·TA profile 1에서는 미확인. 각 Pass 이벤트를 7개 모델에서 COUNTED_NONZERO/ZERO/INCONSISTENT로 다시 판정한다. Overflow는 RUN마다 기록된다. 32-bit 위험은 창 전체를 세는 이벤트(`*_enabled_cycles`, `cycle`)뿐: 50 MHz에서 2³² = 86 s, 포트 합산 시 43 s. |

**Stage 0에 더할 것**
- `npu_active` 외 창 기준 이벤트(`cycle` 17, `npu_idle` 32)로 창 구성을 확인: `npu_idle + npu_active ≈ PMCCNTR` 여부.
- 동등성 미결 E1–E5와 MLEK golden(vww4·yolo·wav2letter)은 Stage 0의 "기준 실행 환경" 정의에 들어간다(`evidence/runner_gap/open_equivalence_items.md`).

## Stage 1 — 전체 모델 실행 특성

| 지표 | 판정 | 검토 |
| --- | --- | --- |
| Total cycles (`PMCCNTR`) | **조건부** | Stage 0과 같은 창 문제. 지금 값은 모델 실행 시간이 아니다. |
| Active / Total | **부적합** (현재 정의) | 러너: 분모에 CPU 복사가 들어가 wav2letter 1.65 %, kws 3.5 % 같은 무의미한 값. MLEK: TOTAL ≈ ACTIVE라 FVP에서 98.9–99.98 %로 정보가 없다. 창을 NPU 구간으로 다시 정의한 뒤에도 "NPU 시작~끝 사이의 idle"만 남는다 → 별도 지표로 쓰려면 정의부터 다시 해야 한다. |
| MAC active / NPU active | **가능** | 현행 지표. 7개 모델 측정 완료. |
| DPU active / NPU active | **조건부** | TRM 정의는 "**적어도 하나의** DPU 활성"이라 이용률이 아니다. Stage 2A에서 `mac_dpu_active = mac_active`(비 1.000)였다 → 모델에서도 같다면 정보가 없다. Pass A에서 확인하고 같으면 보고에서 뺀다. |
| AO active / NPU active | **가능** | Stage 2A에서 측정됨. TRM: accumulation/chaining buffer의 block traversal — MAC과 다른 축. |
| WD active / NPU active | **가능** | Stage 2A에서 측정됨. WD는 4개; 이벤트가 4개를 합산하는지 단일인지 미확인 → 비율이 100 %를 넘는지로 확인. |
| 유효 처리량 MAC ops / NPU cycles | **가능** | 분모는 `npu_active`. MAC 수 출처를 하나로 고정: 현재 원본 tflite의 N_MAC(`workload_meta.py`); Vela `nn_macs`와 조금 다르다(wav2letter 3,491,098,000 vs 3,491,110,876). |
| Peak 대비 효율 | **가능** | 계획의 단서가 맞다: 회로 점유율이 아니다. DW·Elementwise·FC는 1024 MAC/cycle 구조에 맞지 않아 낮게 나오는 것이 정상이다. |

**Stage 1에 더할 것**
- **MAC active-cycle eff.** = N_MAC / (1024 × `mac_active`) — 이미 산출 중. MAC이 돌 때의 밀도.
- **Vela 추정 대비 실측**(모델 전체): Vela `cycles_npu` vs `npu_active`, Vela DRAM/SRAM bytes vs 측정 beat × 16 B. 예: wav2letter Vela `cycles_npu` 5,233,545 vs 측정 4,132,039. Stage 5를 기다리지 않고 Stage 1에서 바로 계산할 수 있다.

## Stage 2 — 연산 그룹 및 Pipeline 분석

| 항목 | 판정 | 검토 |
| --- | --- | --- |
| 그룹별 실행 비용·비중 | **개발 필요** | 보드에서 그룹 단위 값을 얻는 경로가 아직 없다. 후보: (1) 명령 스트림을 그룹 경계에서 나눠 따로 실행(경계마다 pipeline·캐시 상태가 바뀜), (2) 경계에 `NPU_OP_STOP`+IRQ를 넣고 IRQ마다 PMU 판독(FVP 기계 연구의 방식, tail 오버헤드 측정 필요), (3) `NPU_OP_PMU_MASK`로 한 그룹만 세게 하고 그룹 수만큼 반복(실행은 그대로, 단 TRM이 *debug feature*로 표기, 보드 미검증). (3)이 측정 교란이 가장 적다. 어느 쪽이든 Σgroup vs 전체로 검증한다. |
| MAC stall (`by_w`, `by_ib`, `w_or_acc`, `by_acc`) | **가능** (의미 추론) | 공개 TRM은 Reserved지만 보드에서 센다(Tier B, Stage 2A). 의미는 드라이버 status 비트 주석에서 추론(`evidence/stage2a/event_semantics_audit.md`). 검사: `mac_active + mac_stalled_by_ib ≤ npu_active`. |
| AO stall (67–72) | **가능** (의미 추론) | Reserved, Tier B에서 nonzero. 의미는 `AO_STATUS` 비트 주석 추론. |
| WD stall (`wd_stalled` 81, `wd_stalled_by_wd_buf` 83) | **가능** | 81은 TRM 문서화("weight 부족 또는 WD 버퍼 부족"), 83은 Reserved. |
| `CC_STALLED_ON_BLOCKDEP` | **조건부** | Reserved, **의미 문서 없음**, Tier B에서 0(작은 연산). 실제 모델에서 0이 아니면 서술용, 0이면 "미지원"으로 격상하지 않는다. |
| 그룹별 처리 효율 | **개발 필요** | 그룹 값이 있어야 한다. 그룹 MAC 수는 op별 N_MAC 합(`workload_meta.py`). |

**Stage 2에 더할 것**
- 그룹 계측이 생기기 전이라도 **모델 전체의 stall 구성**(Pass A·C)은 바로 얻을 수 있다.
- `PMCLUT` 복합 이벤트: 카운터 0이 최대 4개 이벤트의 논리 조합을 센다 → "MAC active AND EXT read stall" 같은 동시 발생을 한 RUN에서 직접 측정. 문서상 기능, 보드 미검증, 러너 미구현.
- FVP 그룹 결과(`U85_GROUP_DIFFERENTIAL.csv`, U85-256/512)와 같은 그룹 정의를 쓰면 FVP↔보드 비교가 된다.

## Stage 3 — 메모리 접근 특성

| 지표 | 판정 | 검토 |
| --- | --- | --- |
| Traffic (SRAM/EXT RD·WR beat) | **가능** | 측정 중. Bytes = beat × 16 B(128-bit 포트). 집계형은 포트 2개의 합이다 → 포트별 이벤트와 **더하지 않는다**. |
| Memory intensity Bytes/MAC | **가능** | 계획의 단서대로 재사용의 간접 지표. |
| Effective bandwidth Bytes/cycle | **조건부** | 분모는 `npu_active`(창 `PMCCNTR` 금지). 포트 2개 합산이므로 포트당 peak(16 B/cycle)와 비교하려면 2로 나누거나 포트별 이벤트를 쓴다. |
| Request stall ratio | **가능** | `*_rd_tran_req_stalled`(arvalid & ~arready), `*_wr_data_beat_stalled` — TRM 문서화. 포트 합산이므로 비율이 100 %를 넘을 수 있다 → 분모를 `npu_active × 포트 수`로 하거나 포트별로. |
| Outstanding pressure (`*_stall_limit`) | **조건부** | Tier B에서 전부 0. 실제 모델·TA profile 1에서 0이 아닐지 확인 필요. 0이면 "제한에 도달하지 않음"이지 "미지원"이 아니다. |
| Read latency tail ratio | **조건부** | `axi_latency_*`는 `PMCAXI_CHAN`으로 채널·포트 그룹 하나를 고른 뒤에만 의미가 있다(러너 knob word 16으로 설정 가능). 임계값은 배타적 bin이 아니고 분모는 `axi_latency_any`. Tier B에서 경계 불일치 3개. **핵심 해석 제약: 지연은 TA가 에뮬레이션한 값(SYS_DRAM_Mid)이 지배한다** → FPGA DRAM 자체의 지연이 아니다. |
| Port balance (SRAM0/1, EXT0/1) | **가능** (해석 주의) | 포트별 이벤트 존재(TRM 66개), `sram2/3_*`은 포트가 없어 0. 포트 배분은 주소 해시/striping(`CFG_SRAM_HASH*`)과 러너의 배치 주소에 좌우된다 → 워크로드 특성보다 배치의 결과일 수 있다(E5 scratch base와 연결). |

**Stage 3에 더할 것**
- **채널별 트래픽**: `PMCAXI_CHAN.BW_CH_SEL_EN=1` + `CH_SEL`(rd_cmd, rd_ifm, rd_weights, rd_scale_bias, wr_ofm 등)으로 beat를 채널별로 분리 → 가중치 vs IFM vs OFM 트래픽. 러너 knob(word 16)로 이미 쓸 수 있고, 채널당 RUN 1회.
- **평균 burst 길이** = data beat / trans accepted (RD). AXI 제한(MLEK `MAX_BEATS=2`)과 대조.
- **쓰기 완료** `*_wr_trans_completed_m/_s`(Reserved, Tier B nonzero).
- **Vela 예측 traffic 대비 실측**: Vela summary의 `sram_total_bytes`·`dram_total_bytes` vs beat × 16. 예: wav2letter Vela DRAM 33.4 MB vs 측정 EXT beat.
- **해석 범위 문장**: "TA profile 1(에뮬레이션 SYS_DRAM_Mid) 아래의 메모리 접근 특성". 물리 DRAM 특성으로 쓰지 않는다.

## Stage 4 — 연산자·텐서 형상 비교

| 항목 | 판정 | 검토 |
| --- | --- | --- |
| Operator·H×W·채널·Kernel | **가능** | `host/container/make_op_model.py`(단일 연산 INT8 tflite)와 Stage 1/2A의 합성 연산 경로가 있다. |
| Block alignment (OFM block·ublock) | **가능** | Vela `--verbose-schedule`로 연산별 block을 기록(FVP H13과 같은 방식). |
| Cycles per MAC, Shape cost variation | **가능** | 분모 `npu_active`. |
| 작은 연산의 상대 비용 | **조건부** | 작은 연산은 고정 비용이 지배한다. FVP에서 TOTAL이 1,000 사이클 격자에 모인 현상이 있었다(보드 `npu_active`에서도 해상도 확인 필요). |

**FVP H13의 교훈 반영**: 형상별로 양자화를 따로 calibration해서 "형상만 바꿨다"가 성립하지 않았다 → 기준 INT8 모델 하나에서 flatbuffer 수준으로 형상만 바꿔 파생(가중치·bias·양자화 바이트 동일)하도록 생성기를 고정한다.

## Stage 5 — 메모리 배치·컴파일 조건 비교

| 조건 | 판정 | 검토 |
| --- | --- | --- |
| Memory mode | **조건부** | Dedicated_Sram(현행, MLEK 기준) 외에 Shared_Sram은 러너 배치로 가능해 보이나 미검증. **Sram_Only는 모델 전체가 on-chip SRAM 4 MB(러너 이미지와 공유)에 들어가야 한다** → wav2letter(14.5 MB)는 불가, mobilenet(3.5 MB 가중치) 경계. 불가 셀은 `NOT_EXECUTABLE`로 기록. 모드가 바뀌면 Vela 산출물도 바뀐다(FVP P1-A: 모든 모드 쌍 DIFFERENT_ARTIFACT) → 메모리 효과와 컴파일 효과가 분리되지 않음을 전제로 보고. MLEK 기준값은 Dedicated_Sram에만 있다. |
| 데이터 접근 경로 | **가능** (부분) | 러너 knob(REGIONCFG/MEM_ATTR, fast base)로 region→포트 매핑을 바꿀 수 있다. 단 옛 브랜치 A/B는 TA untouched에서 "배치가 NPU 사이클을 거의 바꾸지 않음"이었다 → TA profile 1에서 다시 해야 한다. |
| SRAM cache 크기 | **가능** | Vela `--arena-cache-size` → fast scratch 크기. 실제 할당은 blob 헤더 `fast_size`로 확인. |
| Vela 최적화 전략 | **가능** | `--optimise Size` vs `Performance`. 프로파일과 다른 Vela 옵션은 조건 변경이므로 A/B 계약으로만. |
| Vela 추정 설명력 | **가능** | 모델 전체(cycles, bytes)는 지금 바로. 연산별 비중은 Stage 2 그룹 계측 후. Vela 문서대로 추정은 비용 모델이므로 비중·순위·방향 먼저 비교하는 계획이 맞다. |

## PMU Pass 구성 검토

| Pass | 판정 | 검토 |
| --- | --- | --- |
| A — Execution | **가능** | Stage 2A의 8개와 거의 같다(계획 `MAC_STALLED_BY_W` 53 vs Stage 2A `w_or_acc` 52). |
| B — Memory Traffic | **가능** | 8개 모두 TRM 문서화. |
| C — Memory Stall | **가능** | `*_stall_limit` 4개는 0일 가능성. `AO_STALLED_BY_OB`(69)·`WD_STALLED_BY_WD_BUF`(83)는 Reserved, 의미 추론. |
| D — Detailed | **조건부** | 포트별 이벤트는 가능. latency 이벤트는 `PMCAXI_CHAN` 설정이 RUN마다 하나라 채널·포트 그룹별로 Pass를 나눠야 한다. |

**구성에 대한 제안**
1. **모든 Pass에 `npu_active`(35)를 넣는다** — Pass 사이에 같은 실행이었는지 확인하는 앵커. Pass B·C는 8칸이 차 있으므로 하나를 뺀다(B: `*_rd_trans_accepted` 중 하나를 D로, C: `*_stall_limit` 중 한쪽).
   **현재 호스트로는 불가 (작은 개발 필요)**: `host/lib/pmu_events_parse.py` `event_sets()`가 id를 **오름차순 정렬·중복 제거한 뒤 8개씩** 자른다. 그래서 Pass 묶음을 계획대로 지정할 수 없고 같은 id를 여러 세트에 넣을 수도 없다. 세트를 명시하는 입력(예: 줄마다 8개)을 받도록 바꿔야 한다.
2. 한 부팅에 Pass A–D를 모두 넣으면 blob 업로드 1회로 끝난다(러너는 한 부팅에서 이벤트 세트를 여러 개 돈다). 7개 모델 × 1부팅 ≈ 업로드 합계 약 1시간(wav2letter 33분 포함).
3. Pass 간 비율(예: Pass B의 beat / Pass A의 `npu_active`)은 같은 RUN에서 나온 값이 아니다 — 계획의 단서대로 앵커(`npu_active`)의 RUN 간 편차를 먼저 보고한다.
4. 이름은 드라이버 `ETHOSU_PMU_*`가 아니라 **EV_TYPE 숫자**로 고정한다(세대마다 이름·번호가 다르다, CLAUDE.md Traps).

## 우선순위 제안

| 순서 | 내용 | 필요한 것 |
| --- | --- | --- |
| 1 | Stage 0 보강: 창 정의(PMCCNTR vs `npu_active`), 클럭 확인(system counter), Pass A–D 이벤트 유효성(7개 모델, TA profile 1) | 호스트 세트 지정 기능(작음) + system counter 판독 1회 |
| 2 | Stage 1 + Stage 3(모델 전체): Pass A–D 7개 모델, Vela 추정 대비 실측(전체) | 1과 같은 부팅에서 가능 |
| 3 | Stage 2 그룹 계측 기능 설계·검증(Σgroup vs 전체, 오버헤드) | 펌웨어/호스트 개발 + 계약 |
| 4 | Stage 4, Stage 5 | 합성 모델 생성기 고정, A/B 계약 |

병행 미결: MLEK golden(vww4·yolo·wav2letter), 동등성 E1–E5.

## 검증 수준

```
검증 수준: 문서·기존 데이터 대조 (새 측정 없음)
실제 실행한 것: PMU 레퍼런스·Stage 2A 감사·Tier B 기록·x1 원시 기록(boot 80, 93) 대조, PMCCNTR·enabled_cycles·DWT 창 비교
실행하지 않은 것: 어떤 Pass의 보드 측정도, system counter 판독, PMCCNTR_CFG·PMCLUT·NPU_OP_PMU_MASK의 보드 동작 확인
```
