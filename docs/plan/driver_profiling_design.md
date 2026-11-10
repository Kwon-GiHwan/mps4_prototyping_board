# Driver Runner의 QREAD·PMU Sampling 통합과 연산별 계측 방법 비교 (설계, 2026-11-10, 보드 실행 없음)

Owner 요청 2026-11-10 (항목 4): 공식 Ethos-U driver 기반 Runner에 QREAD·PMU sampling을 넣을 수 있는지, 연산별 실제
시작·완료 시각을 얻을 방법이 있는지, PMU Mask와 다른 방법의 비교 설계. **QREAD의 완료 진행 위치를 개별 연산의 종료
시각으로 해석하지 않는다.** 주장 표기: `DOCUMENTED`(TRM·드라이버 문서) / `CODE_VERIFIED` / `BOARD_MEASURED` / `INFERRED` /
`UNVERIFIED`. TA profile 1(이 문서의 모든 실험). STOP·KERNEL_WAIT·NPU_OP_IRQ 삽입 실험은 설계만 하고 실행하지 않는다
(별도 승인 항목, 지시 9.5).

## 0. 결론

| 질문 | 답 | 근거 |
| --- | --- | --- |
| Driver Runner에 QREAD sampler를 넣을 수 있나 | **가능.** 드라이버가 완료를 기다리는 곳이 우리 `ethosu_semaphore_take`(weak override)라서, 그 안의 대기 전략에 "QREAD·PMU를 읽으며 기다리기"를 세 번째 모드로 두면 된다. vendor 패치(`patch_u85_trace.py`)가 필요 없다 | `CODE_VERIFIED`: `hooks.c`, `include/probe.h` WAIT_WFE/WAIT_BUSY, 드라이버 `ethosu_wait` → `ethosu_semaphore_take` |
| PMU sampling | 같은 루프에서 PMEVCNTR·PMCCNTR를 함께 읽는다. PMU 소유는 `pmu_session` 하나(J3)라 판독만 추가 | `CODE_VERIFIED` |
| 기존 QREAD 코드 재사용 | 호스트 `qread_trace.py`(샘플·정합성)와 `qread_timeline.py`(`CommandMap`, 완료 구간, 판정)는 그대로 쓸 수 있다. 펌웨어는 샘플 형식만 같게 새로 쓴다(기존 runner 소스는 고정) | `CODE_VERIFIED`: `feat/stage2b4-qread` `65d3f8b`(미병합, 보드 미실행) |
| 연산별 **실제 시작·완료 시각** | **원래 command stream으로는 직접 관측할 수 없다.** QREAD는 "그 앞 명령이 모두 완료됐다"는 위치라서, 커널 k의 완료 시각은 "QREAD가 k를 지난 것이 관측된 구간"으로 위에서만 묶이고(상한), 시작 시각은 정의되지 않는다. 커널은 비차단이고 최대 2개가 겹쳐 남을 수 있다 | `DOCUMENTED`(TRM QREAD, Command completion) + `INFERRED` |
| 시작·종료에 가까운 값을 얻는 방법 | stream을 바꾸는 방법(STOP prefix, KERNEL_WAIT 장벽, 연산 단독 실행)뿐이다. 이들은 실행을 직렬화해 "파이프라인 안 시각"이 아니라 "격리된 비용"을 준다(`ISOLATED_ONLY`) | `INFERRED`, 2B-3 3b 설계 |

따라서 목표를 "연산별 시작·종료 시각"이 아니라 **(1) 완료 진행의 상·하한 타임라인, (2) 시간 창별 PMU 증가량, (3) 격리
비용**의 세 층으로 나누고, 각 층이 무엇을 말하지 못하는지를 판정 규칙에 넣는다.

## 1. 이미 확인된 사실 (이 설계의 전제)

| 사실 | 수준 | 출처 |
| --- | --- | --- |
| QREAD = 완료 위치(QBASE+QREAD 앞 명령 완료). 같은 TRM 페이지의 비트 설명은 "current command under execution" — 긴장 | `DOCUMENTED` | `feat/stage2b4-qread:docs/plan/stage2b4_qread_plan.md` §1 |
| 커널 명령 비차단, KERNEL_WAIT·DMA_WAIT·PMU_MASK·STOP 차단, 커널 최대 2개 미완료 | `DOCUMENTED` | 같은 문서 §1, `results/fi101_stage2b3/README.md` |
| IRQ 시점 QREAD = command stream 길이(ad 2,480 = `cms_len` 2,480) | `BOARD_MEASURED` | `evidence/driver_p3/raw` (boot 299) |
| PMU Mask: 실행은 교란하지 않으나 창 합이 전체와 맞지 않음(7개 중 3개만), 경계마다 12–1,980 cycles 손실 | `BOARD_MEASURED` | `results/fi101_stage2_mask` (2B-0b) |
| 그룹 귀속 오류: ad CONV MAC 효율 2.85(합은 보존) → H1/H2 무효 | `BOARD_MEASURED` | `results/fi101_stage2_groups` |
| 마스크 창 경계는 앞 연산의 **완료**에 묶이고 발행·완료 어느 쪽과도 일정한 지연으로 맞지 않음(고정 lag 없음) | `INFERRED`(TRM) + `BOARD_MEASURED`(2B-3 3a: 모델마다 다른 결과) | `results/fi101_stage2b3/` |
| PMCLUT: unit의 stall과 active는 같은 cycle에 겹치지 않음 | `BOARD_MEASURED` | `results/fi101_stage2_probe` |
| PMCCNTR_CFG start/stop 이벤트 창 | `UNVERIFIED`(필드만 문서화, 보드 기록은 모두 0) | `docs/reference/ETHOS_U85_PMU_REFERENCE.md:296` |
| **Driver Runner 기록의 `qsize`는 QSIZE가 아니다**: `hooks.c`가 0x24(드라이버 헤더상 `NPU_REG_PROT`)를 읽는다. QSIZE는 0x20 | `CODE_VERIFIED` (`ethosu85_interface.h:77–78`) | 판정에 쓰이지 않는 진단 칸. 측정 중인 m7 이미지는 그대로 두고, 다음 이미지에서 고친다 |

## 2. 통합 구조 (Driver Runner, 재사용 우선)

```
host                                                    firmware (pmu_runner, MLEK platform)
 set_run_options(wait_mode, pmccntr_cfg, trace cfg) ──▶ runner.c  (상태 기계, 그대로)
 RUN ───────────────────────────────────────────────▶   RunInference → driver → ethosu_semaphore_take (hooks.c)
                                                           └ wait.c: WAIT_WFE | WAIT_BUSY | WAIT_TRACE
                                                                 WAIT_TRACE: 간격마다 trace_sample():
                                                                   DWT t0, QREAD, STATUS, PMEVCNTR[0..n), PMCCNTR, QREAD, DWT t1
 GET_TRACE (새 명령, RESULT_READY에서만) ◀───────────── trace.c  (고정 버퍼, 넘침 표시, IRQ 진입에서 최종 샘플)
 qread_trace.py / qread_timeline.py (재사용)
   CommandMap ← DRWL의 Vela tflite에서 command stream 추출 (host/lib/cms.py 재사용)
```

| 결정 | 이유 | 버린 대안 |
| --- | --- | --- |
| sampler는 대기 전략 모듈(`wait.c`, 계획 J5)의 한 모드 | WFE / busy / trace를 **같은 이미지**에서 RUN 설정 하나로 바꿈 → 교란을 한 변수로 측정 | 별도 이미지: 이미지 차이가 섞임 |
| 비교 기준은 **WAIT_BUSY** (같은 이미지) | trace 루프는 본질적으로 busy-poll이다. trace의 교란 = (BUSY 대비 차이), BUSY의 차이 = (WFE 대비 차이, Phase 5 B1)로 두 단계로 나눈다 | WFE와 바로 비교: 두 원인이 섞임 |
| 버퍼는 NPU가 쓰지 않는 메모리(DTCM 또는 BRAM .bss), D-cache 영향은 BUSY와 같게 | NPU 트래픽(SRAM 0x31000000 fast scratch, DDR)과 경쟁하지 않게 | SRAM: fast scratch와 같은 메모리 |
| 샘플 형식은 기존 `qread_trace.py`와 같게 | 호스트 정합성 검사·판정·테스트·변이 시험을 그대로 씀 | 새 형식 |
| IRQ 진입(hooks.c)에서 최종 샘플 강제 | 마지막 커널 완료 관측(리뷰 지적 1) | — |
| 이벤트는 IRQ 판독과 같은 slot 배치 | 샘플 Δ의 합 = IRQ 판독값 검사 가능(정합성) | — |

필요한 변경(추정 규모): 펌웨어 `wait.c`·`trace.c` 신규(약 150줄), `hooks.c` 1곳, 프로토콜 명령 1개, 기록 v2 필드 몇 개(`trace_samples`,
`trace_dropped`, `trace_mode`), 호스트 `driver_link.get_trace`, `run_driver_events.py` 저장, `qread_trace.py`·`qread_timeline.py`를
`feat/stage2b4-qread`에서 가져옴(브랜치 병합 결정이 필요: §6). 시뮬레이터(`host_sim.c`)에 가짜 QREAD 진행을 넣어 끝까지 테스트.

## 3. 방법별 비교 — 무엇을 줄 수 있고 무엇을 못 주는가

| 방법 | stream 변경 | 얻는 것 | 얻지 못하는 것 | 교란 위험 | 판정 상한 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 PMU Mask (`NPU_OP_PMU_MASK`) | 마스크 명령 삽입 | 창별 이벤트 합 | 창 경계 = 연산 경계가 아님(완료에 묶임, 모델마다 lag 다름), 경계 손실 | 낮음(2B-0b 비교란) | `COARSE_ATTRIBUTION`(창) / `NOT_IDENTIFIABLE`(ad) | 보드 측정됨(기존 runner) |
| M2 QREAD + DWT 폴링 | 없음 | 커널별 "완료가 관측된 시간 구간"(상한), 정체 구간 | 시작 시각, 정확한 완료 시각, 겹친 두 커널의 분리 | 폴링 MMIO 판독·busy 대기 | 타임라인 `TRACE_VALID`까지; 귀속 판정 아님 | 코드만(기존 runner) |
| M3 QREAD + PMU 샘플 | 없음 | 샘플 간격별 Δevent와 그 구간의 완료 진행 | Δevent의 연산 귀속(두 커널 겹침, 처리부가 앞 커널을 계속 처리) | M2 + PMU 판독 | `COARSE_ATTRIBUTION` 상한 | 코드만 |
| M4 PMCCNTR_CFG start/stop | 없음 | 특정 이벤트 사이 cycle 수(하드웨어 창) | 이벤트가 연산을 식별하지 않음 | 없음(설정만) | 진단 | `UNVERIFIED` — 먼저 의미 확인(kws에서 start=stop=0 vs 특정 이벤트) |
| M5 STOP prefix (0..k까지만 실행) | 끝을 STOP로 자름 | Δ(prefix k − prefix k−1) = 커널 k를 붙였을 때 늘어난 총 시간·이벤트 | 파이프라인 겹침 속 시각; prefix 끝의 drain이 비용에 섞임 | 실행 구조 변경 | `ISOLATED_ONLY` | 설계(2B-3 3b), **미승인** |
| M6 KERNEL_WAIT 0 장벽 | 커널마다 장벽 | 직렬 실행에서 커널별 시작·종료가 QREAD로 분리됨 | 원래 실행의 겹침(장벽이 없앰) | 실행 직렬화 | `ISOLATED_ONLY` | 설계, **미승인** |
| M7 `NPU_OP_IRQ`/중간 IRQ | IRQ 명령 삽입 | 지정 위치 도달 시각 | 공식 드라이버의 IRQ 처리기는 IRQ를 작업 완료로 처리(semaphore give) → 중간 IRQ를 완료로 착각할 위험 | 높음 | — | TRM 확인 전 **실행 안 함**(지시 Phase 6) |
| M8 연산 단독 모델(Stage 4) | 모델 자체 | 형상별 단독 비용 | 실제 모델 문맥(앞뒤 겹침, 캐시·버퍼 상태) | 없음 | `ISOLATED_ONLY` | 도구 있음(`make_op_model.py`) |

**어느 방법도 원래 실행에서 연산별 시작·종료 시각을 직접 주지 않는다**(`INFERRED`, 위 근거). 정확한 귀속(`EXACT_ATTRIBUTION`)에
가장 가까운 것은 M2/M3에서 "커널 k의 완료 관측 구간이 이웃과 겹치지 않고, 그 구간의 Δevent가 k의 격리 비용(M5/M6/M8)과
일치"하는 경우뿐이며, 그것도 서로 다른 실행 조건을 잇는 추론이다. 그래서 판정 상한을 방법별로 미리 고정한다.

## 4. 비교 실험 설계 (계약 초안 — 보드 전에 수치를 고정해 별도 승인)

대상: 7개 모델, MLEK 입력, TA profile 1, Driver Runner 한 이미지. 단계:

| 단계 | 조건 (같은 이미지, RUN 설정만 다름) | 질문 | 사전 판정 |
| --- | --- | --- | --- |
| P0 | QSIZE 오프셋 수정 이미지에서 BASE·A·B 재검증 (D1–D6 그대로) | 수정이 측정을 바꾸지 않는가 | D1–D6 |
| P1 | WAIT_WFE vs WAIT_BUSY | busy 대기가 NPU를 바꾸는가 (Phase 5 B1) | `INERT`/`EFFECTIVE` (D6 허용오차) |
| P2 | WAIT_BUSY vs WAIT_TRACE(QREAD만, 간격 2^6/2^10/2^14) | 폴링이 교란하는가, 해상도는 | `TRACE_INVALID/PERTURBED/UNOBSERVABLE/COARSE/VALID` (기존 §8 규칙, 수치는 계약에서) |
| P3 | WAIT_TRACE(QREAD+PMU, 세트 A) | Δevent와 완료 진행의 관계 | 샘플 Δ 합 = IRQ 판독값(정합성), 귀속 상한 `COARSE` |
| P4 | PMCCNTR_CFG 몇 가지 (start/stop 이벤트) | 하드웨어 창의 의미 | 진단(`UNVERIFIED` → 관측 기술) |
| P5 | PMU Mask variant (J6 direct 모드, 같은 base address) | 같은 이미지에서 Mask 창과 QREAD 타임라인을 겹쳐 보기 | 창 경계 명령의 완료 관측 구간 안에 이벤트 증가가 몰리는가(기술), Mask 결과를 보정하지 않음 |
| (P6) | STOP prefix / KERNEL_WAIT 장벽 | 격리 비용 | `ISOLATED_ONLY` — **별도 승인 전 실행 안 함** |

교차 검사(모든 단계): 출력 = MLEK golden, Σ창 = 전체(허용오차), MAC 효율 ≤ 1·depthwise 상한(128 MAC/cycle) 위반은 귀속 오류로
판정, 완료 순서가 command stream 순서와 모순되면 `TRACE_INVALID`. 판정 집합(지시 Phase 6): `EXACT_ATTRIBUTION` /
`COARSE_ATTRIBUTION` / `ISOLATED_ONLY` / `NOT_IDENTIFIABLE` / `UNPROVEN`. "MAC 효율 ≤ 1"이나 "합 일치"만으로 EXACT를 주지 않는다.

예상 비용: P0–P5 = 7개 모델 × 단계별 1부팅 정도(P2는 간격 3개를 한 부팅 안 세트로) — 대규모 측정에 해당하므로 계약과 함께
별도 승인.

## 5. 2B 그룹 Profiling 현황 (변경 없음)

Stage 2B 그룹별 H1/H2 판정은 계속 무효다. 2B-3 3a 결과(창 위치 기술)는 귀속이 아니다. 이 설계의 어느 단계도 기존 2B 데이터를
고치거나 다시 판정하지 않는다.

## 6. 결정이 필요한 것

1. `feat/stage2b4-qread`의 호스트 모듈을 Driver Runner로 가져오는 방법: (a) 그 브랜치를 병합(기존 runner의 기본 이미지가
   바뀜 — 리뷰 지적 3), (b) **호스트 모듈 2개와 테스트만 `feat/driver-runner`로 옮기고 기존 runner 펌웨어 쪽은 병합하지 않음(추천)**.
2. P0–P5 계약 작성과 보드 실행 승인(대규모 측정).
3. M5/M6(STOP·KERNEL_WAIT) 실행 여부 — 지금은 설계만.

## 7. 진행 상태 (2026-11-10, owner 결정 반영)

- Owner 결정: QREAD 분석은 Driver Runner로 통합, QREAD 브랜치에서는 호스트 모듈만 검토·재사용(펌웨어·실행 경로 전체 병합 안 함),
  정적 검증·비보드 테스트 먼저, 그다음 최소 파일럿. §6-1은 (b)로 결정됨.
- 구현(`c1b9b79`, `4361e42`): 펌웨어 `trace.c`(WAIT_TRACE, 마지막 샘플은 IRQ 뒤 일반 흐름에서), GET_TRACE, 기록 칸; 호스트
  `qread_trace.py`·`qread_timeline.py`(브랜치 `65d3f8b`에서 이식, 판정 로직 그대로), 한 부팅 여러 조건(`--conditions`),
  `qread_pilot.py`(P1–P3). 브랜치에는 시각화 모듈이 없어 가져올 것이 없었다(분석은 CSV 출력).
- 검증: 시뮬레이터(펌웨어 C를 호스트로 빌드)로 끝까지, C↔Python 계약 테스트, 변이 27개 RED, 대상 빌드 rc 0·GATE OK.
  보드 실행 없음.
- 파일럿 계약 초안: `evidence/qread_pilot/contract_draft.md`(승인 대기).
- 방법 구분(§3 표의 "stream 변경" 열): 원본 실행을 바꾸지 않는 것 — M2 QREAD 폴링, M3 QREAD+PMU 샘플, M4 PMCCNTR_CFG, IRQ 시점
  판독; 바꾸는 것 — M1 PMU Mask, M5 STOP prefix, M6 KERNEL_WAIT 장벽, M7 중간 IRQ, M8 단독 실행. 파일럿은 앞쪽만 쓴다.
