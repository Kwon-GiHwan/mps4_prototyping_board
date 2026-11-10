# 기준 계측 환경: Driver Runner (owner 결정 2026-11-10)

공식 Ethos-U core driver 기반 Driver Runner(`firmware/driver_runner`, MLEK `b2c0bb2` 플랫폼 + out-of-tree use case
`pmu_runner`)를 FI101 연구의 **기준 계측 환경**으로 채택한다. 근거: 7개 모델 D1–D6 통과, MLEK 동등성(아래). 기존 자체
runner(`firmware/runner`, 이미지 `d0cd4775` 등)는 보존하고, 신규 PMU 실험은 Driver Runner로 한다. 모든 수치는 **TA profile
1**(MLEK `sys_dram_mid`), FI101 Ethos-U85 1024 MAC. 기본 실행 조건: `config/driver_r5.json`(세트당 5 RUN = warm-up 1 +
측정 4, 추가 5 RUN은 계약에 미리 고정한 조건에서만, 편차 안의 성능 차이는 `UNRESOLVED`).

## 1. 동등성 — 확인된 범위

| 항목 | 결과 | 범위 (이 밖으로 일반화하지 않음) | 근거 |
| --- | --- | --- | --- |
| 출력 | 7개 모델 모두 MLEK FI101 OFM과 바이트 단위로 같음 (80/80 RUN) | MLEK 입력, Vela 5.0.0 MLEK 옵션 | `results/driver_m7` M1, D2 |
| beat 4종 (SRAM/EXT RD/WR) | 7개 모두 MLEK와 정확히 같음 | 같은 입력 | M2 |
| NPU_ACTIVE | 7개 모두 M3 규칙 안, 중앙값 차 −0.33…+0.47 % | 같은 입력, 단일 부팅(vww4 3부팅) | M3, `results/var_w2l_vww4` V |
| MAC_ACTIVE / MAC_DPU_ACTIVE / AO_ACTIVE | 6개 EQUIVALENT | wav2letter 제외(아래 예외 1) | M4 |
| 플랫폼 설정 | TA 두 개 = sys_dram_mid(TA_EXT MAXR 0으로 읽힘), AXI·MEM_ATTR·POWER_CTRL = MLEK | 이 이미지 | D1, 실험 A |
| 기존 runner와의 재현 | 7개 모두 결정적 카운터 동일, NPU_ACTIVE 허용오차 안 | 같은 입력 | D5 |
| PMU 설정 영향 | 세트 BASE/A/B 사이 NPU_ACTIVE·실행 창·호스트 시간 차이 없음(허용오차 ≥ 1 %) | 세트 A·B | D6 |
| 측정 창 (P1) | NPU_EXECUTION = NPU_ACTIVE + 534–666 cycles, RUN마다 거의 일정; CPU 복사 없음 | 이 이미지 | `results/driver_m7/descriptive.txt` |
| 실행 경로 (P2) | 작업마다 soft reset 없음(power 참조 수 2), WFE 대기, cache on — MLEK와 같은 코드 | 이 이미지 | D1, power_requests |

## 2. 남은 예외와 제한

1. **wav2letter M4 = `UNPROVEN`** (동등성 C, 3+3 부팅, 고정 판정 — 소급 변경하지 않음). 별도 기록: 교차 8부팅(W)에서 계측
   빌드 차이가 재현되지 않음(`NO_SHIFT`), 같은 규칙에 전체 부팅을 넣으면 M4 EQUIVALENT(보충, `results/var_w2l_vww4`).
   두 결과를 합쳐 하나의 판정으로 쓰지 않는다.
2. **입력**: MLEK 입력 하나뿐. 다른 입력으로 일반화하지 않는다.
3. **카운터**: 위에 적은 것만 MLEK와 직접 비교했다. 세트 C–G의 stall·포트 이벤트는 MLEK가 세지 않아 MLEK 비교가 없다.
4. **EXT 포트 0/1 분배**: 경로에 따라 달라진다(총량은 정확히 같음). 원인은 DDR 배치 주소 차이로 추정(`INFERRED`).
5. **기존 runner vs Driver**: vww4 약 0.6 % 차(허용오차 안, 원인 미분리). WFE/busy·cache·배치 등 Phase 5 변수는 측정하지 않음.
6. **IDLE/TOTAL**: MLEK profiler 창과 Driver 창이 달라 비교하지 않음.
7. **이미지 기록 칸 `qsize`**: P3·m7 이미지에서는 PROT(0x24)를 담는다(`afceaa8`에서 수정, 판정 미사용).

## 3. 기존 Stage 1·2A·3 지표의 사용 규칙 (`results/driver_m7/reval/reval.csv`)

| 표시 | 사용 |
| --- | --- |
| `REVALIDATED` | 그대로 사용 (Stage 1 측정값 대부분, SRAM·EXT 총 바이트, 대역폭, MAC 효율 등) |
| `RETAINED` | 값 유지, 조건과 함께 표기 (컴파일 상수, 입력·경로가 섞인 비교에서 일치한 C–G 지표, 채널 비율) |
| `CONDITION_SPECIFIC` | **별도 표시**: 기존 runner 경로의 값. 기존 runner 자체 창(`infer_cycles`, `active_over_infer`), EXT read burst, EXT 포트별 바이트·불균형(mobilenet 같은 입력에서 확인), vww4 WD active |
| `REMEASURE_REQUIRED` | MLEK 경로 주장에 쓰기 전 Driver Runner로 같은 입력 재측정 (포트별 EXT·일부 stall, seed-1 모델) |
| `INVALID` | 사용하지 않음: CPU 복사가 포함된 기존 PMCCNTR 창(`runner_window`) |

Stage 2B 그룹별 H1/H2: 계속 무효. 2B-3 3a 창 위치 기술은 귀속이 아니다.

## 4. 다음 연구 목표

실제 연속 실행에서 **연산별 활동 · 실행 완료 시점 · PMU 이벤트를 얼마나 정확하게 연결할 수 있는가.** 방법은 원본 실행을
바꾸지 않는 것(QREAD 폴링, PMU 주기 샘플링, PMCCNTR_CFG 창, IRQ 시점 판독)과 바꾸는 것(PMU Mask, STOP prefix,
KERNEL_WAIT 장벽, 중간 IRQ, 연산 단독 실행)으로 나눠 비교한다. 설계와 판정 상한: `docs/plan/driver_profiling_design.md`.
연산별 시작·종료 시각이나 정확한 PMU 귀속은 근거 없이 주장하지 않는다.
