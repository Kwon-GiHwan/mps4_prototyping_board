# Stage 6E-X3 Preflight (2026-11-18, 보드 실행 전) — **FAIL: PMU_MASK가 승인된 이미지에서 동작하지 않음**

지시: `docs/plan/stage6ex3_directive_chatgpt.txt` §3·§6("Preflight 실패 시 보드 실행을 중단하고 실패 원인만 보고").
보드 실행, 이미지 빌드, DRWL 생성은 하지 않았다. 계약 동결 전 단계에서 중단한다.

## 실패 원인 (정적, 기존 원시 자료로 확인)

| 근거 | 내용 |
|---|---|
| 하드웨어 조건 | NPU_OP_PMU_MASK는 PMCR.mask_en(bit 3, `0x8`, `firmware/common/npu_pmu_regs.h:46-47`)이 1일 때만 계수를 막는다(`host/lib/cms.py` 머리말; legacy runner는 `firmware/runner/pmwl.c:134`에서 knob으로 설정) |
| driver runner 코드 | `firmware/driver_runner/use_case/pmu_runner/src/pmu_session.c` `pmu_session_arm`: PMCR = (읽은 값 & ~reset) \| CNT_EN \| reset. mask_en을 설정하는 경로가 없다 |
| 기록된 값 | Stage 6C raw(이미지 `14077be`) 135/135 RUN의 `pmcr_at_arm` = 16,385 = `0x4001` → mask_en = 0. NPU soft reset 뒤 값이며 arm은 이를 유지한다 |
| 결론 | 이미지 `14077be`에서는 PMU_MASK 명령이 계수에 영향을 주지 않는다. B2–B4 그룹 창은 B1과 같은 전체 계수를 낸다 → 그룹 귀속 불가 |

## 6E-0 판단 오류 (정정 기록: `evidence/stage6e0/erratum_mask_en.md`)

6E-0 구현 표의 "runner 펌웨어(변경 불필요) EXISTS"와 "driver runner에서 PMU_MASK 동작 NEEDS_BOARD_PRECHECK"는 틀렸다.
PMU_MASK가 동작하지 않는다는 것은 보드 없이 코드와 기록값으로 확정할 수 있었다. 확인하지 않은 것이 원인이다.

## 정적으로 확인된 나머지 (참고, 판정 아님)

| 항목 | 결과 |
|---|---|
| KERNEL_WAIT 인코딩 | yolo 원본 스트림(`evidence/qread_pilot/workloads/…cms.bin`)의 KERNEL_WAIT 11개 = `0x00010012`(cmd0 opcode 18, n=1 at bits 31:16) → n=0은 `0x00000012`. 2B-3 표의 수(yolo 11)와 일치 |
| KERNEL_WAIT 의미(TRM 102685, 2B-3 인용) | "Wait for n or fewer kernel operations to be remaining before starting the next command"; n=0은 이전 커널 전부 완료 대기. mem2mem DMA는 기다리지 않음(DMA_WAIT 별도) |
| 직렬화만(B0·B1) | PMU_MASK 없이 KERNEL_WAIT만 쓰면 이미지 `14077be`에서도 가능(펌웨어는 명령 스트림을 검사하지 않음). 단 이번 지시의 B0–B4 구성 전체는 아님 |

## 판정

`PREFLIGHT_FAIL`(PMU_MASK 경계 검증 불가: 승인 이미지에서 mask_en = 0). 보드 실행 시작 안 함.
