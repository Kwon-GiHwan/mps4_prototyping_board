# Stage 6E-0 정오표 — driver runner의 PMU_MASK (2026-11-18, X3 preflight에서 발견)

6E-0 결과(`16f8127`)와 계약(`034ef0e`)은 바꾸지 않는다. 다음 두 구현 항목의 상태가 틀렸다.

| 항목 | 6E-0 상태 | 정정 |
|---|---|---|
| runner 펌웨어 | EXISTS(명령 스트림 검증 없음, 변경 불필요) | 명령 스트림 검증이 없다는 사실은 맞다. 그러나 그룹 창에는 PMCR.mask_en 설정이 필요하고, driver runner에는 그 경로가 없다 → NEW_BOUNDED(펌웨어 변경, 새 이미지) |
| driver runner에서 PMU_MASK | NEEDS_BOARD_PRECHECK | 정적으로 확정: 동작하지 않음(`pmu_session_arm`, 6C 135 RUN의 `pmcr_at_arm` = 0x4001) |

계약 §5 규칙을 정정된 상태에 적용하면 UNKNOWN_FEASIBILITY는 없으므로 `READY_FOR_BOARD_REVIEW`는 형식상 유지된다. 그러나 승인된 이미지(`14077be`) 조건에서는 실행할 수 없다. 이미지 변경은 측정 조건의 변경이므로 별도 승인이 필요하다.
