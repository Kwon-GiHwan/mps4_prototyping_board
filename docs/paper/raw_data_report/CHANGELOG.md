# 변경 이력

수정·재계산이 발생하면 새 버전을 추가한다. 이전 기술은 지우지 않는다.

## v1.0 — 2026-09-09

최초 생성. 기존 frozen evidence 무수정 집계. 표 15 · 그림 15(PNG+SVG) · provenance 4.
검증 10/10 통과.

### 작업 중 발생한 재계산 (v1.0 내부)

| # | 사항 | 조치 | 근거 |
|---|---|---|---|
| R1 | 3.3 점 데이터 출처를 `analysis/scaling.csv` → `analysis/canonical_cells.csv`로 변경 | 재계산 | `scaling.csv`가 측정된 셀 `SSE-300/u55/wav2letter@256`을 사다리 baseline 결측을 이유로 점 행에서 누락. 측정 데이터를 버리지 않기 위함 |
| R2 | `scaling.csv`가 점 행(73)과 전이 행(56) 혼합 파일임을 확인 | 파서 분리 | `mac` 컬럼에 `32->64` 형태가 섞여 있음 |

두 조치 모두 **기존 파일을 수정하지 않았고**, 재계산 결과는 frozen 집계와 일치한다
(53 evaluable transition, legacy `<0.50` 규칙 2건 = manuscript의 `WEAK_OR_SATURATED | 2`).

### 검사기 결함 정정 (v1.0 내부, 데이터 아님)

| # | 검사 | 결함 | 조치 |
|---|---|---|---|
| C1 | #1 evidence 불변 | `.omc/state/...` 플러그인 세션 파일을 evidence로 오인 | 검사 범위에서 `/.omc/` 제외. **실제 evidence는 무수정 확인** |
| C2 | #1 evidence 불변 | baseline은 상대경로, 검사는 절대경로 → 전량 불일치로 오판 | repo 루트 기준 경로 정규화 |
| C3 | #9 figure 추적 | 파일명이 동적 생성이라 소스에 리터럴 부재 | 파일명 대신 SVG에 삽입된 `source: tables/*.csv` 스탬프로 검증 |
| C4 | #9 figure 추적 | 태그 제거 정규식이 스탬프(주석 내부)를 함께 삭제 | 원문에서 검색 |

C1은 결과적으로 **frozen evidence가 실제로 무수정임을 확인**한 것이다.

## v1.1 — 2026-09-09

서버 read-only 검증(`SERVER_VERIFICATION.md`, MLEK `b2c0bb2`) 결과 반영.
**새 측정 없음. frozen evidence 무수정.**

### 상태 변경 NOT_VERIFIED → VERIFIED

| 항목 | 결과 |
|---|---|
| TA_CONFIG_FILE | MAC별로 달라짐. `Z128/Z256→low`, `Z512/Z1024→mid`, `Z2048→high`. **mid와 high는 바이트 동일**하므로 파라미터는 256→512에서만 변경 |
| profiler IDLE | `TOTAL − ACTIVE` 소프트웨어 파생 (`ethosu_profiler.c:187-189`) |
| U85 메모리 공란 | `PARSER_LOSS_BUT_RAW_UART_NOT_RETAINED` |
| PMU 측정 창 | `inference_begin`/`inference_end` enable-disable 구간 |
| MLEK commit | `b2c0bb2884698b7328f65c41b7c8c51ca9bec386` |

### 표 스키마 변경

`ta_config` 플레이스홀더(`NOT_VERIFIED_LOCALLY`)를 실측값으로 교체하고,
`ta_config_changed` 단일 컬럼을 두 개로 분리했다:

- `ta_config_file_changed` — 파일 **이름**이 바뀌었는가
- `ta_parameters_changed` — 실효 **파라미터**가 바뀌었는가 (mid≡high 반영)

영향 표: `3_1_platform_matrix.csv`(+`ta_parameter_set`), `3_3_cycles_by_mac.csv`,
`3_3_scaling_transitions.csv`, `3_4_u85_256_512_combined.csv`,
`4_2_transition_prediction.csv`.

### 무효화된 해석

REPORT.md "검증으로 무효화된 해석" 절에 I1–I6으로 기록. 핵심은 두 가지다 —
**256→512 역전을 MAC 단독 효과로 읽을 수 없고**, **두 역전을 같은 원인으로 묶을
근거가 없다**(후자는 TA 파라미터 불변).

## v1.2 — 2026-09-09

`source_data/` 추가. 각 REPORT 섹션이 사용하는 **원본 frozen evidence를 가공 없이
복사**해 섹션별로 모았다. 사본 37개 / 원본 26개 / 1.19 MB, 전부 원본과 SHA-256 동일
(`source_data/MANIFEST.csv`가 검증 결과 보유).

- 여러 섹션이 쓰는 파일은 중복 복사했고 `also_in_sections` 컬럼에 기록.
- 재생성: `scripts/collect_source_data.py` (폴더를 지우고 다시 복사, 복사 후 해시 대조).
- **원본은 read-only.** 검사 1(evidence 536파일 해시)이 작업 후에도 drift 0.

## v1.3 — 2026-09-09

**U85 whole-model 메모리 카운터를 재측정(R1)으로 회수했다.** v1.2까지 35/35 셀에서
공란이던 네 필드가 전부 채워졌다.

### 무엇이 문제였나

측정이 아니라 **판독**이 문제였다. `stage1.py`의 파서는 `AXI0_*`/`AXI1_*` 정규식만
가지고 있었는데, U85 stock profiler는 `SRAM_*`/`EXT_*`를 방출한다. 값은 UART에 정상
출력되고 있었으나 읽히지 않았고, 워크스페이스 즉시 삭제로 원시 UART까지 사라져
재파싱이 불가능했다.

### 무엇을 했나

`remeasure/` 신설. 데이터 취득 **전에** 계약과 게이트를 동결했다
(`REMEASURE_CONTRACT.md`, sha256 `88d9eb65…`).

- `remeasure_u85.py` — `stage1`을 **import**한다. 재구현이 아니므로 빌드·해시 게이트·
  FVP 호출이 *같은 방식*이 아니라 **같은 코드**다. 파서만 `pmuparse`로 교체하고,
  원시 UART를 워크스페이스 밖에 보존한다.
- 35셀 × 2반복 = 70회 실행.

### 게이트 결과

```
R1_GATES: PASS
  G1_artifact_reproduction        35/35   frozen anchor 해시 바이트 재현
  G2_total_cycles_match_frozen    35/35   TOTAL == frozen canonical_cycles
  G3_active_cycles_match_frozen   35/35   ACTIVE == frozen
  G4_repetition_identical         35/35   R1 == R2 전 필드
  G5_memory_counters_present      35/35   SRAM/EXT 4종 존재
```

G1–G3이 통과했다는 것이 **회수값을 기존 셀에 붙일 수 있는 근거**다. 같은 실행 파일이
같은 사이클을 냈으므로, 같은 실행에서 나온 메모리 값도 그 셀의 것이다.

뮤테이션 테스트 9건 통과 (`test_gates.py`) — 각 게이트를 데이터에서 무력화해 FAIL
발화를 확인했다. 원래의 실패 형태(U85 메모리 4종 삭제) 재현 포함.

### 영향 표

| 파일 | 변경 |
|---|---|
| `3_1_measurement_availability.csv` | U85 SRAM/EXT 4종 `AVAILABLE_PARTIAL` → **`AVAILABLE`**. AXI 4종 `PARSER_LOSS`/`NOT_COLLECTED` → **`NOT_EVALUABLE`** |
| `3_2_whole_model_pmu.csv` | U85 35행의 `rd/wr_beats_0/1` 채움, `status` → `RECOVERED_BY_REMEASUREMENT_R1`, `source`에 출처 명시 |
| `3_2_memory_traffic.csv` | U85 35행 `NOT_EVALUABLE` → `OK_RECOVERED_R1`, 포트 비중 산출 |

`REPORT.md`: 가용성 표, Appendix A, Appendix B, D4, D5 갱신.

**frozen `analysis/canonical_cells.csv`는 건드리지 않았다.** 회수값은 별도 출처
(`remeasure/R1_MEMORY_COUNTERS.csv`)로 유지하며, 파생 표에서 출처 컬럼으로 결합한다.

### 용어 정정

U85의 `AXI0_*`/`AXI1_*`를 `PARSER_LOSS`로 표기한 것은 틀렸다. **"읽지 못했다"와
"거기 없다"를 혼동한 것**이다. U85는 AXI 이름을 애초에 방출하지 않으므로 올바른 값은
`NOT_EVALUABLE`이다. 손실이었던 것은 SRAM/EXT 쪽이며, 그쪽이 이번에 회수되었다.

### 부수 확인

- **counter overflow 경고 0건** — 보존된 UART 71개 전수 검사. `ethosu_profiler.c`가
  경고할 수 있는 조건(IDLE 32bit / TOTAL 64bit)이 U85 35셀 × 2반복에서 발생하지 않았다.
  기존 파서가 수집하지 않던 항목이며, 이제 실증적으로 닫혔다.
- **`MPS4_SCC->CFG_ACLK reads 0. Assuming default clock of 32000000`** — 전 실행에서
  출력된다. FVP가 SCC 클럭 레지스터를 제공하지 않아 펌웨어가 32 MHz를 가정한다.
  NPU 사이클 카운트에는 영향이 없으나, **사이클을 시간으로 환산하면 그 32 MHz는
  설정값이 아니라 fallback 가정값**이다. 본 보고서는 시간 환산을 하지 않는다.
