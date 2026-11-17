# Stage 6B-E2E-C 계약 — 잔여 EXT 경로 귀속 가능성과 파이프라인 특성 (보드 없음)

지시: Stage 6B-E2E-C 공식 지시(2026-11-18). 보드 측정은 하지 않는다. E2E-B 결과(`c7ddffe`/`b8fb580`/`650e79e`)와 그 이전 판정은 바꾸지 않는다.
이 계약, 분석 코드 `host/analysis/stage6be2ec.py`, 테스트, mutation은 결과 생성 전에 커밋한다.
E2E-B 원시 자료를 쓰는 분석은 모두 `POSTHOC_DIAGNOSTIC`이다.

## 계약 전 노출 (결과 전에 이미 본 것)

- **E2E-B 결과**: B0/B3의 NPU_ACTIVE, EXT/SRAM beat·트랜잭션.
- **E2D W0-P0/W0-P1 표**: W0-P1(가중치만 EXT, Conv 단독)의 지연 효과는 13,545이고 EXT read 트랜잭션은 788개다.
- **Stage 3 채널 측정**(`results/fi101_stage3_channels`, legacy runner, TA profile 1, AXI_SEL = 0)에서 본 것:
  - rd_weights/rd_ifm/rd_mem2mem의 read beat·트랜잭션이 SRAM·EXT 양쪽에서 필터됐고, npu_active는 변하지 않았다.
  - write 쪽은 해석할 수 없다.
  - rd_cmd, rd_scale_bias는 측정하지 않았다.
- **FI101 이벤트 감사**(`results/fi101_stage3/events_pass_B_to_G.csv`, driver_m7):
  - 387 `ext_rd_tran_req_stalled`는 측정됐다(COUNTED_NONZERO).
  - 398 `ext_rd_stall_limit`은 kws에서 INCONSISTENT였다.
  - 160–166 `axi_latency_*`와 385는 측정 기록이 없다.
- **driver runner**(`firmware/driver_runner`)에는 PMCAXI_CHAN 설정이 없다. legacy runner(`firmware/runner/pmwl.c`)는 header word 16으로 쓰고 되읽는다.
- **MLEK core-driver**(`dependencies/core-driver/src/ethosu_device_u85.c`, 수정 없음 = `.bak`와 동일):
  - `ethosu_address_remap(address, index)`가 weak 훅이다. QBASE(index −1, 147행)와 각 BASEP(index i, 158행)에 따로 호출된다.
  - `ethosu_config_select(remapped address, i)`는 REGIONCFG를 정한다.
  - runner `hooks.c`는 두 훅을 이미 덮어쓴다(remap은 항등이고 PMU arm에 쓴다).
- **Vela A2 연산별 값**(E2E-A facts):
  - L500: Add1 = DRAM 21,562, Conv = npu 24,290(DRAM 16,409), Add2 = SRAM 7,200.
  - L1000: Add1 = DRAM 43,124, Conv = DRAM 32,818(npu 25,540), Add2 = SRAM 7,200.

아래 규칙은 이 노출 뒤에 정했다.

## 0. 디스크·임시 파일 (지시 9)

- 시작 시 Mac 여유 3.2 GiB(df).
- 기존 E2D/E2E-A 테스트 누수(test.sh 1회 12.8 MB, 그중 11.9 MB가 test_stage6be2d)는 별도 유지보수 커밋 `df4aed0`로 정리했다. 1회 누수는 0.9 MB로 줄었고, 남은 것은 더 오래된 단계 테스트의 것이다(수정하지 않음).
- 같은 커밋에서 `6614ce8` 때문에 생긴 mutation 문제를 바로잡았다. NOT_APPLIED 3개(4K 2, 6B-B 1)의 패턴을 고쳤고, E2D SURVIVED 1개는 픽스처를 추가했다. 4K·6B-B·E2D의 `mutation.txt`는 커밋 때와 같다.
- E2E-C 코드와 테스트는 임시 디렉터리를 반드시 지운다. 테스트로 검사한다(실행 전후 임시 디렉터리 수가 같음).

## 1. Phase 0 — E2E-B 재현 (`recompute`)

E2E-B 판정을 원시 자료로 다시 실행해 다음을 모두 확인한다. 하나라도 틀리면 `INVALID`이다.

- summary가 커밋된 `stage6be2eb_summary.json`과 바이트 단위로 같다. 판정 6개도 같다.
- 필수값(정확히 일치):

| 값 | B0 | B3 |
|---|---|---|
| NPU_ACTIVE L500 | 99,044 | 60,320 |
| NPU_ACTIVE L1000 | 159,122.5 | 72,526.5 |
| LE | 60,078.5 | 12,206.5 |
| MAC_ACTIVE | 20,736 | 20,736 |
| EXT read beat / 트랜잭션 | 27,066 / 10,417 | 11,322 / 793 |

- 감소량: EXT read 15,744 beat, 9,624 트랜잭션(두 지연 모두).
- 보존: SRAM+EXT read beat 합, read 트랜잭션 합, write beat 합이 B0 = B3(두 지연 모두).
- AO_ACTIVE·WD_ACTIVE 불변: |B3 − B0| ≤ 1 % × B0(두 지연 모두).
- 출력: 4개 B 구성 모두 VALID(PASS_EXACT 포함).
- command stream: B0/B3 DRWL이 offset 28 한 바이트만 다르다.

## 2. Phase 1 — PMU 이벤트·채널 필터 조사 (`pmu_capability`, 정적)

이벤트 상태(closed set):
- `VERIFIED_ON_FI101`: TRM 110 목록에 있고, FI101 기존 원시 자료에서 COUNTED_NONZERO이며, 같은 감사에서 INCONSISTENT가 없음.
- `INCONSISTENT_ON_FI101`: FI101 감사에서 INCONSISTENT가 하나라도 있음.
- `TRM_ONLY_UNVERIFIED`: TRM에 있으나 FI101 측정 기록이 없음.
- `RESERVED`: TRM에 없음.

채널 상태(CH_SEL, closed set):
- `READ_FILTER_VERIFIED`: Stage 3에서 CHANNEL_FILTER_WORKS인 채널.
- `WRITE_NOT_INTERPRETABLE`: wr_ofm.
- `UNVERIFIED`: 그 밖(rd_cmd, rd_scale_bias, rd_ifm_stream, rd_mem2mem_idx, wr_mem2mem).

Runner 지원:
- driver runner의 PMCAXI_CHAN 설정·readback은 `NOT_IMPLEMENTED`이다(소스에 없음). 쓰려면 펌웨어 변경과 새 이미지가 필요하다.

검증 항목 1–9(지시 3)에 대해 근거 파일과 상태를 표로 낸다. 확인하지 못한 것은 UNVERIFIED로 둔다. Reserved 이벤트는 근거로 쓰지 않는다.

## 3. Phase 2 — EXT 읽기 요청 구조 (`transactions`, POSTHOC_DIAGNOSTIC)

- 구성: E2D W0-P0/W0-P1/W1-P0/W1-P1(boot 449–457), E2E-B B0/B3(boot 459–462). 모두 TA profile 1.
- 구성×지연마다 계산한다:
  - read beat, 트랜잭션, 평균 beat/트랜잭션
  - EXT read 트랜잭션 / 1,000 NPU_ACTIVE
  - 구성별 LE
  - MAC_ACTIVE
- 쌍(B0→B3, W0-P0→W0-P1)마다 계산한다:
  - 제거된 EXT read beat·트랜잭션과 그 평균 크기
  - ΔLE와 ΔLE / Δ트랜잭션
  - 남은 경로의 LE / 트랜잭션
- **이 비는 기술값이다.** 트랜잭션당 서비스 시간이나 대기시간이 아니다(outstanding, 포트 분산, 중첩 때문).
- 교차 비교(기술): 같은 Conv 가중치 경로만 EXT에 남은 두 구성 W0-P1과 B3의 EXT read 트랜잭션 수와 LE를 나란히 놓는다.
- Vela 5.0.0 모델 항목(E2A 소스 감사 재사용)을 표로 낸다: 읽기량, burst 반영, latency 반영, outstanding, 포트 BW, 작은 요청의 비용, 연산별 MAX. 요청 수가 중요해질 수 있는 조건을 정리한다.

## 4. Phase 3 — 잔여 EXT 경로 (`residual_channels`)

- 정적 채널 기대(B3, 16 B beat):
  - rd_weights 174,752 B
  - rd_scale_bias 5,760 B
  - rd_cmd 628 B(DRWL cms_len)
  - rd_ifm·mem2mem 0(region 표, DMA 0)
- 합 11,321.25 beat 대 보드 11,322 beat. 차이를 채널에 배분하지 않는다.
- `WEIGHT_AND_COMMAND_EXT_PATH_CONFIRMED`는 보존한다.
- 가설 H-R1(가중치·scale 공급), H-R2(command fetch), H-R3(파이프라인 의존성)에 대해, 방법별 예측과 가를 수 없는 부분을 표로 낸다.

## 5. Phase 4 — 후속 통제 실험 (`methods`, `gate`)

전제 항목 상태(closed set):
- `VERIFIED_SOURCE`: 소스·정적 자료로 확인.
- `VERIFIED_BOARD`: FI101 기존 원시 자료로 확인.
- `BOARD_CHECK_REQUIRED`: 원리상 가능하고, 후속 계약의 대조군·preflight에서 확인해야 함.
- `FAILS`: 불가능.

방법 판정:
- 전제에 `FAILS`가 하나라도 있으면 `UNAVAILABLE`.
- 아니면 `discriminating` = H-R1과 H-R2가 그 방법에서 서로 다른 관측 가능 결과를 예측함(예측표로 판단, 코드에 고정).

방법:
- **A — PMCAXI_CHAN 채널 필터(B3)**:
  - 전제: TRM 필드, FI101 read-side 필터 동작(VERIFIED_BOARD), rd_cmd/rd_scale_bias 동작(BOARD_CHECK_REQUIRED), driver runner 구현(BOARD_CHECK_REQUIRED: 펌웨어 변경), 8 카운터 제약(채널마다 pass 1개).
  - 예측: 채널 바이트는 두 가설 모두에서 정적 기대와 같다. 따라서 `discriminating = False`(트래픽 분할은 지연 귀속을 가르지 못함).
- **B — 가중치 배치 통제(B3w)**:
  - 구성: B3와 같은 DRWL(command stream 동일). runner 훅이 BASEP0(region 0 = 가중치·scale)만 on-chip SRAM 사본으로 remap하고, REGIONCFG region 0을 SRAM 포트로 바꾼다. QBASE(command stream)와 QCONFIG, graph IO, 중간 텐서는 B3와 같다.
  - 전제: 훅 존재(VERIFIED_SOURCE), region 0 내용 = WEIGHT·SCALE만(VERIFIED_SOURCE), command stream은 region 0 밖(VERIFIED_SOURCE), SRAM 용량(VERIFIED_SOURCE 계산), 새 이미지 동등성(BOARD_CHECK_REQUIRED: 대조군 B3가 E2E-B를 재현), 측정창 밖 복사·cache 처리(BOARD_CHECK_REQUIRED), 계측(EXT read beat, REGIONCFG readback: VERIFIED_BOARD).
  - 예측:
    - H-R1이면 LE(B3w) ≤ 0.25·LE(B3)이고 EXT read ≈ 39.25 beat(command stream만).
    - H-R2이면 LE(B3w) ≥ 0.75·LE(B3).
    - 그 사이면 `MIXED`. → `discriminating = True`. H-R3는 어느 쪽이든 매개될 수 있어 분리되지 않는다.

종료 Gate(지시 8, 방법마다 5개 모두 참이어야 함):
1. 통제 가능한 독립 변수가 있다.
2. 가설들이 서로 다른 예측을 낸다(`discriminating`).
3. 검증 가능한 계측 경로가 있다(계측 전제가 VERIFIED_SOURCE 또는 VERIFIED_BOARD).
4. 기존 자료 재분석만으로 풀리지 않는다.
5. 소규모 예산(≤ 5 boot / 50 RUN)으로 반증 가능하다.

## 6. 최종 판정 (위에서부터 처음 성립)

1. `INVALID`: Phase 0 재현 실패, 또는 입력 파일 오류.
2. `READY_FOR_TARGETED_BOARD_REVIEW`: Gate를 모두 통과한 방법이 하나 이상. 고를 방법은 하나다. 통과한 방법 중 BOARD_CHECK_REQUIRED 수가 적은 것, 같으면 B, A 순서.
3. `MECHANISM_NOT_IDENTIFIABLE`: `discriminating`인 방법이 없음.
4. `STATIC_CHARACTERIZATION_COMPLETE`: 그 밖(가를 수 있는 방법은 있으나 Gate를 통과하지 못함).

- READY여도 보드를 자동 실행하지 않는다. 최소 후속 계약 초안만 쓴다.
- READY가 아니면 Memory/Pipeline 범위를 종료하고 Stage 6C로 넘어가기를 권고한다.

## 7. Vela 연결 (Phase 5, 기술)

다음 두 현상을 따로 정리하고, 하나의 보정 계수로 묶지 않는다.
- **A2 SRAM 배치의 과소예측**: B0 board/Vela 1.87/1.91. graph IO 이전으로 LE가 80 % 감소했다. B3는 비교할 Vela 값이 없다.
- **Conv 단독 DRAM의 과대예측**: NHWC burst 효율 가정이 유력하다. C1 정오표를 보존하고, 사후 보정값은 검증 결과가 아니다.

Vela A2 Conv 연산의 DRAM 항(가중치) 지연 반응(16,409 → 32,818, 연산 비용 24,290 → 32,818)은 Vela가 가중치 경로를 어떻게 세는지 보여주는 사실로만 쓴다. B3의 예측값이나 오차로 쓰지 않는다.

## 8. 검증

- 테스트 `host/tests/test_stage6be2ec.py`, mutation 전부 KILLED, `test.sh` ALL PASS.
- 분석 2회 실행 바이트 동일, 기존 파일 불변, 임시 디렉터리 정리 확인.
- 로컬 커밋만 한다.
