# R1 재측정 계약 — U85 whole-model 메모리 카운터 복구

**동결 시각:** 2026-09-09, **데이터 취득 이전**. 이 문서는 결과를 본 뒤 수정하지 않는다.

## 목적

`SERVER_VERIFICATION.md` V3이 확정한 파서 손실을 복구한다. formal 74셀 중 **U85 35셀**의
`SRAM_RD / SRAM_WR / EXT_RD / EXT_WR` beat가 파싱 단계에서 유실됐고 원시 UART가
보존되지 않아 재파싱으로 복구할 수 없다. 따라서 **동일 실행물을 다시 돌려** 해당
카운터만 회수한다.

## 절대 조건

- 기존 frozen evidence를 **덮어쓰지 않는다.** 결과는 별도 artifact로만 남긴다.
- 사이클 값을 "개선"하거나 재해석하지 않는다. 목적은 **누락 필드 회수 하나뿐**이다.
- 새 지표·새 임계값을 만들지 않는다.

## 대상

SSE-320 / ethos-u85, MAC {128, 256, 512, 1024, 2048} × 7 workload = **35 cells**.
`Dedicated_Sram`, TA ON. 빌드 절차·Vela 인자·cmake 플래그·`SOURCE_DATE_EPOCH`는
`stage1.py`와 동일하게 유지한다.

## 반복

셀당 **2회** (R1, R2). 기존 캠페인이 이미 3회로 결정론을 확립했으므로 반복 수를
줄이되, 회수 대상인 메모리 카운터 자체의 결정론은 이 2회로 확인한다.

## 사전 등록 게이트 — 데이터를 보기 전에 고정

| id | 조건 | 실패 시 |
|---|---|---|
| **G1** | 35셀 전부 `vela_sha256` / `generated_cc_body_sha256` / `axf_sha256`가 frozen anchor와 일치 | 중단. 다른 실행물이므로 어떤 값도 frozen 셀에 붙일 수 없다 |
| **G2** | `npu_total_cycles`가 frozen `canonical_cycles`와 **35/35 정확히 일치** | 중단. 재현 실패 |
| **G3** | `npu_active_cycles`가 frozen 값과 **35/35 정확히 일치** | 중단 |
| **G4** | R1 == R2 (사이클 + 메모리 카운터 전 필드) | 중단. 결정론 미충족 |
| **G5** | 메모리 카운터 4종이 35/35 셀에서 non-null | 부분 성공으로 기록, 원인 별도 조사 |

G1–G4 중 하나라도 실패하면 **회수값을 frozen 셀에 연결하지 않는다.** 실패 사실만 기록한다.

G1–G3이 통과하면, 이 실행은 frozen 셀과 **동일한 바이너리·동일한 결과**를 낸 것이므로
회수된 메모리 카운터를 해당 셀의 값으로 붙일 수 있다.

## 파서

`stage1.py`는 `AXI0_*`/`AXI1_*`만 인식했다. 신규 파서는 U85 stock profiler가 실제로
출력하는 라벨을 인식한다 (`ethosu_profiler.c` L104-128에서 확인):

```
NPU ACTIVE
NPU ETHOSU_PMU_SRAM_RD_DATA_BEAT_RECEIVED
NPU ETHOSU_PMU_SRAM_WR_DATA_BEAT_WRITTEN
NPU ETHOSU_PMU_EXT_RD_DATA_BEAT_RECEIVED
NPU ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN
```

**원시 UART를 이번에는 보존한다.** 같은 손실이 재발하지 않도록 파싱 결과와 함께
UART 원문을 artifact에 포함한다.

## 산출물

```
remeasure/
  REMEASURE_CONTRACT.md      이 문서 (동결)
  remeasure_u85.py           실행 하네스
  R1_RESULTS.json            셀별 결과 + 게이트 판정
  R1_MEMORY_COUNTERS.csv     회수된 카운터 (셀 × 4종)
  R1_GATE_REPORT.md          G1-G5 판정
  uart/                      원시 UART 보존
```

## 기록 위치

게이트 통과 시 `REPORT.md`의 U85 메모리 상태를 `PARSER_LOSS` →
`RECOVERED_BY_REMEASUREMENT_R1`로 갱신하고, `3_1_measurement_availability.csv`와
`3_2_whole_model_pmu.csv`에 회수값을 **출처 컬럼과 함께** 반영한다. 기존 frozen
`canonical_cells.csv`는 건드리지 않는다.
