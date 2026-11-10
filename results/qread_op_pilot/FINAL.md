# Stage 2B operator-aware QREAD 파일럿 — 최종 정리 (2026-11-10, 종료)

대상: yolo-fastest_192_face_v4 Op 99(Conv2D)·Op 100(Resize), FI101/MPS4 Ethos-U85 1024 MAC, 공식 Driver Runner,
**TA profile 1**(MLEK sys_dram_mid), 원본 command stream, 조건·세트당 warm-up 1 + 측정 4 RUN. Boots 328–329.
계약 `evidence/qread_op_pilot/contract.md`(동결 `987b3e9`), 판정·수치 `results/qread_op_pilot/README.md`, 원시 데이터
`evidence/qread_op_pilot/raw_p12`, `raw_p3`. Owner 결정(2026-11-10): **이 파일럿으로 QREAD 실험 종료. 추가 측정·새 계측 방식 없음.**

**최종 요약: QREAD 기반 명령 완료 진행 관측은 부분적으로 가능했으나, 연산별 PMU 귀속과 지연 원인 분석에는 도달하지 못했다.**

## 1. TRACE_INVALID → TRACE_RECOVERED: 개선된 것과 남은 원인

| | 이전 QREAD 파일럿 (boots 325–326) | 이번 (boot 328) |
| --- | --- | --- |
| 판정 | trace 조건 전부 `TRACE_INVALID` | P1 `TRACE_RECOVERED` (측정 12 RUN 전부) |
| 첫 샘플 = 이전 RUN 끝 | 40/40 RUN | 원인 확인: `ethosu_reserve_driver()`의 semaphore take에서 trace가 돈 **계측 코드 오류**. 샘플에 job 플래그를 붙여 측정 창 밖으로 분리(삭제하지 않음) |
| 0xFFFF0001 등 비정상 값 | yolo 고속 폴링 RUN 대부분, 검출 안 되는 경우 존재 | 각 판독 앞에 ID 판독(센티넬)을 두어 **모두 검출**, 최대 2회 재판독. 77건 전부 재판독으로 수용, 복구 실패 0, 최초 값·재판독 값·순서·횟수 원시 보존 |

- 개선은 "오류를 검출하고 다시 읽는 방법"이지 오류 제거가 아니다. 이상 판독은 이번에도 **모든 RUN**에서 3–12건 발생했다
  (QREAD 66, STATUS 11; boot 329에서는 카운터 포함 27건). 따라서 `TRACE_RECOVERED`는 판독 신뢰성이 완전히 검증된 상태가 아니다.
- 확인된 것: 이상 판독은 전부 "바로 앞 판독(ID)의 데이터"가 다시 나온 것이며, CPU가 판독 직후 검출했고 샘플 checksum·구조
  오류는 0건 → 버퍼 기록·전송 경로가 아니라 **판독 경로 자체**에서 생긴다. 새 이미지의 기계어는 레지스터당 한 번, 프로그램 순서의 판독.
- **미해결(UNVERIFIED):** 판독 경로의 어느 부품(CPU 버스 인터페이스, 인터커넥트, NPU 레지스터 슬레이브)에서 생기는지, 왜 yolo
  실행 중에 나타나고 rnnoise에서는 이전 파일럿에서 보이지 않았는지. 같은 현상이 IRQ 시점 판독(기존 기록 필드)에 영향을 주는지도 미확인.

## 2. 관측된 간격은 연산 실행시간이 아니다

boot 328 q06(QREAD만, 2^6 폴링)의 사후 기술값(`POST_HOC_DESCRIPTIVE`, CPU cycles):

- QREAD가 18,820(Op 98 kernel 명령 바로 뒤)에 머문 구간: 약 2.5–3.4k cycles, 그 뒤 Op 99 통과가 보인다.
- Op 99 통과 → Op 100 통과: 약 **1.82–1.84k** cycles(12 RUN 중 11, 한 RUN 2.25k).
  (owner 메시지의 "약 1.18k"는 측정값과 다르다. 원시 데이터 기준 값은 1.82–1.84k이다.)

이 값들은 **QREAD 완료 진행이 관측된 시점 사이의 간격**이다. QREAD는 완료 위치만 알려 주고 시작 시각이 없으며, 멈춘
위치("kernel 명령 바로 뒤")가 그 연산의 완료인지 다음 명령 대기인지 구분되지 않는다. 앞 명령이 늦게 끝나면 뒤 연산의
완료 표시도 늦어지고, 연산들은 겹쳐 실행될 수 있다. 따라서 Op 98·99·100 각각의 실행시간으로 해석하지 않는다.
각 경계 통과 시점의 불확실 폭은 폴링 1–2회(약 300 또는 약 725 cycles)다.

## 3. PMU 결합: 판독 비용 증가로 사전 기준 초과

- boot 329 p06(QREAD + 이벤트 35·48·81·387): 샘플당 판독 비용 중앙값 **297 → 642 cycles**.
- 그 결과 Op 99 경계 bracket 폭 중앙값 637.5 cycles > 사전 기준(QREAD만일 때 296.5의 2배 = 593) → P3 `NOT_ASSOCIATED`.
  (Op 100은 1,039.5 ≤ 2 × 512.5로 기준 이내였지만 판정은 두 연산 모두를 요구한다.)
- 다른 항목은 통과: NPU_ACTIVE −0.02 %(기준 1 %), 4/4 RUN `TRACE_RECOVERED`, 두 경계 관측·분리.
- 규칙대로 경계 주변 구간별 PMU 값은 사용·보고하지 않았다. QREAD와 PMU 판독이 동시에 이루어지지 않는 시간 불확실성도 남는다.

## 4. 결론

- 유지한 것: 원본 command stream(STOP·KERNEL_WAIT·중간 IRQ·명령 삽입 없음), 모델 실행과 출력(모든 RUN golden 일치),
  NPU_ACTIVE(±0.4 % 이내), 메모리 트래픽 카운터(1 % 이내).
- 입증하지 못한 것: 개별 연산의 시작·종료 시점, 연산별 실행시간, PMU 이벤트의 연산 귀속, MAC·WD·외부 읽기 정체 중 지연 원인 후보.
- 판정 수준: P1 `TRACE_RECOVERED`, P2 `BOUNDARY_OBSERVED`, P3 `NOT_ASSOCIATED`. `BOUNDARY_OBSERVED`는 명령 완료 진행이
  두 경계를 지난 시점의 시간 범위를 관측했다는 뜻이며, 연산 귀속의 증명이 아니다.

## 5. 기존 Stage 2B PMU Mask 결과와 구분

| | Stage 2B PMU Mask (2B-3 pilot, boots 244–273) | 이번 QREAD 파일럿 (boots 328–329) |
| --- | --- | --- |
| 방법 | command stream에 PMU_MASK 명령을 넣어 연산 창별로 카운트 (**원본 변경**) | 원본 그대로, CPU가 QREAD·STATUS(·PMU)를 폴링 (**원본 유지**) |
| 묻는 것 | 창의 카운트가 기준 연산의 것인가 | 연산 경계의 완료 진행을 시간 범위로 볼 수 있는가, 그 구간 PMU를 읽을 수 있는가 |
| yolo Op 99/100 결과 | `WINDOW_AMBIGUOUS` (MAC 활동이 W(A−1) 1,512 / W(A+1) 648로 갈림) | P2 `BOUNDARY_OBSERVED`, P3 `NOT_ASSOCIATED` |
| 실패 이유 | 창과 실제 실행이 어긋남(발행·완료 지연, 겹친 실행) — 창의 카운트를 연산에 귀속할 수 없음 | PMU 판독 비용 때문에 경계 해상도가 기준을 넘음; 판독 오류는 재판독에 의존 |

두 결과는 서로 다른 질문·방법의 결과이며 합치지 않는다. 이번 결과로 Stage 2B H1/H2를 재판정하지 않으며(H1/H2는 계속 무효),
Stage 1·2A·3 결과와 `REVALIDATED`/`CONDITION_SPECIFIC` 구분도 변경하지 않는다.

## 보존

계약·이미지 해시·세션 로그·원시 trace·판정 요약을 커밋(`717ba5b`, `987b3e9`, `302feaa`, `e7d09fc`, `b883845` 및 이 문서).
보드 host의 `~/evsweep_qread_op`, `~/evsweep_qread_op_run`, `~/evsweep_qread_op_p3_run`은 그대로 둔다(정리하지 않음).
