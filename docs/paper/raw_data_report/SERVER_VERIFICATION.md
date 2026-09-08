# Server verification — measurement semantics (read-only)

**2026-09-09.** `REPORT.md`의 미해결 항목 3건을 서버에서 read-only로 확인.
새 측정·FVP 실행·빌드 없음. 기존 evidence 수정 없음. **manuscript와 비교하지 않음.**

**환경:** `ssh gihwan` → `docker exec benchmark-runner`
**MLEK:** `/opt/arm/ml-embedded-evaluation-kit`, git `b2c0bb2884698b7328f65c41b7c8c51ca9bec386`

---

## V1. U85 timing-adapter configuration

### 결론

> **`TA=ON`은 U85 전 MAC에서 동일한 memory-service 조건을 뜻하지 않는다.
> TA 설정은 사다리에서 정확히 한 번, 256→512에서 바뀐다.**

### 증명 체인

**① 선택 로직** — `scripts/cmake/configuration_options/npu_opts.cmake:91-113`

```cmake
if (ETHOS_U_NPU_TIMING_ADAPTER_ENABLED)
    ...
    elseif (${ETHOS_U_NPU_ID} STREQUAL "U85")
        set(U85_TA_LOW  "Z128" "Z256")
        set(U85_TA_MID  "Z512" "Z1024")
        set(U85_TA_HIGH "Z2048")
        if(${ETHOS_U_NPU_CONFIG_ID} IN_LIST U85_TA_LOW)
            set(DEFAULT_TA_CONFIG_FILE  "ta_config_u85_sys_dram_low")
        elseif (${ETHOS_U_NPU_CONFIG_ID} IN_LIST U85_TA_MID)
            set(DEFAULT_TA_CONFIG_FILE  "ta_config_u85_sys_dram_mid")
        elseif (${ETHOS_U_NPU_CONFIG_ID} IN_LIST U85_TA_HIGH)
            set(DEFAULT_TA_CONFIG_FILE  "ta_config_u85_sys_dram_high")
```

즉 TA 파일은 **`ETHOS_U_NPU_CONFIG_ID`(= MAC)로 선택**된다.

**② 파일 내용** — `scripts/cmake/timing_adapter/`

```
1ae235035d77046c3ae41a8735570d040189ddf1431c6fc7de3b3f3e00ee4765  ta_config_u85_sys_dram_low.cmake
176cb1d08c6ef68822eb4e2967126682919877a25f8336dcad2a9217fd4d6c09  ta_config_u85_sys_dram_mid.cmake
176cb1d08c6ef68822eb4e2967126682919877a25f8336dcad2a9217fd4d6c09  ta_config_u85_sys_dram_high.cmake
```

**`mid`와 `high`는 바이트 동일하다.** `low`만 다르며, 차이는 정확히 다음 6개 값이다
(`diff low mid`):

| 설정 | low | mid = high |
|---|---:|---:|
| `SRAM_RLATENCY` | 16 | 32 |
| `SRAM_WLATENCY` | 16 | 32 |
| `EXT_MAXR` | 24 | 64 |
| `EXT_MAXW` | 12 | 32 |
| `EXT_RLATENCY` | 250 | 500 |
| `EXT_WLATENCY` | 125 | 250 |
| `EXT_BWCAP` | 2344 | 3750 |

**③ 생성 헤더에서 실측** — 보존된 U85 빌드의 `CMakeCache.txt` + `generated/ta/timing_adapter_settings.h`

| build | `ETHOS_U_NPU_CONFIG_ID` | `TA_CONFIG_FILE` | SRAM_RLAT | EXT_MAXR | EXT_RLAT | EXT_BWCAP |
|---|---|---|---:|---:|---:|---:|
| `build-prof-u85-128` | Z128 | `ta_config_u85_sys_dram_low` | 16 | 24 | 250 | 2344 |
| `build-prof-u85-256-new` | Z256 | `ta_config_u85_sys_dram_low` | 16 | 24 | 250 | 2344 |
| `build-prof-u85-512` | Z512 | `ta_config_u85_sys_dram_mid` | 32 | 64 | 500 | 3750 |

CMake 소스 → `TA_CONFIG_FILE` → 생성 헤더 → 컴파일 상수까지 실물로 이어진다.

### 요구 표

| MAC | system_config (Vela) | TA enabled | TA_CONFIG_FILE | generated TA (SRAM_RLAT / EXT_MAXR / EXT_RLAT / EXT_BWCAP) | same_as_previous_MAC | evidence |
|---:|---|---|---|---|---|---|
| 128 | `Ethos_U85_SYS_DRAM_Low` | ON | `..._low` | 16 / 24 / 250 / 2344 | — | `build-prof-u85-128` |
| 256 | `Ethos_U85_SYS_DRAM_Low` | ON | `..._low` | 16 / 24 / 250 / 2344 | **YES** | `build-prof-u85-256-new` |
| 512 | `Ethos_U85_SYS_DRAM_Mid_512` | ON | `..._mid` | 32 / 64 / 500 / 3750 | **NO — 유일한 변경점** | `build-prof-u85-512` |
| 1024 | `Ethos_U85_SYS_DRAM_Mid_1024` | ON | `..._mid` | 32 / 64 / 500 / 3750 | **YES** | CMake 규칙 (Z1024 ∈ U85_TA_MID) |
| 2048 | `Ethos_U85_SYS_DRAM_High_2048` | ON | `..._high` | 32 / 64 / 500 / 3750 | **YES (파일 바이트 동일)** | SHA-256 일치 |

### 한정

- 실측 헤더는 **mechanism-study 빌드**의 것이다. formal 74셀 스윕의 빌드 트리는
  보존되지 않았다(V3 참조). 다만 `stage1.py`는 `-DTA_CONFIG_FILE`을 **넘기지 않으므로**
  (파일 내 언급 0회) 위 default 규칙이 그대로 적용된다. 1024는 생성 헤더 실측이 아니라
  CMake 규칙에서 도출한 값이다.
- TA 레지스터에 실제로 쓰인 런타임 값은 확인하지 않았다(정적 빌드 상수까지만).

---

## V2. NPU IDLE의 정의

### 결론

> **IDLE은 독립 PMU 하드웨어 카운터가 아니라 `TOTAL − ACTIVE` 소프트웨어 파생값이다.
> 따라서 `TOTAL == ACTIVE + IDLE`은 산술 항등식이며 독립적인 PMU 일관성 검증이 아니다.**

### 소스 체인

파일: `source/hal/source/components/npu/ethosu_profiler.c`

```c
// L131  선언
counters->npu_derived_counters[0].name = "NPU IDLE";
counters->npu_derived_counters[0].unit = unit_cycles;

// L181  전체 사이클
counters->npu_total_ccnt = ETHOSU_PMU_Get_CCNTR(&ethosu_drv);

// L185-189  파생 계산
if (counters->npu_evt_counters[0].event_type == ETHOSU_PMU_NPU_ACTIVE) {
    /* Compute the idle count */
    counters->npu_derived_counters[0].counter_value =
        counters->npu_total_ccnt - counters->npu_evt_counters[0].counter_value;
}
```

- `TOTAL` = `ETHOSU_PMU_Get_CCNTR` (전용 cycle counter)
- `ACTIVE` = event slot 0 = `ETHOSU_PMU_NPU_ACTIVE` (`ETHOSU_PMU_Get_EVCNTR(drv, 0)`)
- `IDLE` = **derived**, 위 두 값의 차

### 부수 확인 — 측정 창

```c
void ethosu_inference_begin(struct ethosu_driver* drv, void* userArg) {
    ethosu_clear_cache_states();
    ETHOSU_PMU_CNTR_Disable(drv, get_event_mask());
    ETHOSU_PMU_CNTR_Enable(drv, get_event_mask());
}
void ethosu_inference_end(struct ethosu_driver* drv, void* userArg) {
    ETHOSU_PMU_CNTR_Disable(drv, get_event_mask());
}
```

카운터는 드라이버의 `inference_begin` 콜백에서 enable, `inference_end`에서 disable된다.
`ethosu_pmu_reset_counters()`는 별도 함수이며 `ethosu_pmu_init` 경로(L150)에서 호출된다.
즉 측정 경계는 **드라이버의 추론 호출 구간**이지 "첫 NPU 명령 → 마지막 NPU 사이클"이 아니다.

### 부수 확인 — overflow

`counter_overflow()` (L65-71)가 `ETHOSU_PMU_Get_CNTR_OVS`로 오버플로를 검사하고
`warn("Counter overflow detected for %s.")`를 출력한다. 주석: *"The idle counter is
32 bit while the total cycle count is 64 bit."* 현재 파서는 이 경고를 수집하지 않는다.

---

## V3. U85 whole-model memory-counter parser loss

### 결론

```
PARSER_LOSS_BUT_RAW_UART_NOT_RETAINED
```

### 1단계 — stock profiler가 이벤트를 설정하는가: **YES**

`ethosu_profiler.c` L104-128, `#elif defined(ETHOSU85)` 분기:

| slot | event | UART에 출력되는 이름 |
|---|---|---|
| 0 | `ETHOSU_PMU_NPU_ACTIVE` | `NPU ACTIVE` |
| 1 | `ETHOSU_PMU_SRAM_RD_DATA_BEAT_RECEIVED` | `NPU ETHOSU_PMU_SRAM_RD_DATA_BEAT_RECEIVED` |
| 2 | `ETHOSU_PMU_SRAM_WR_DATA_BEAT_WRITTEN` | `NPU ETHOSU_PMU_SRAM_WR_DATA_BEAT_WRITTEN` |
| 3 | `ETHOSU_PMU_EXT_RD_DATA_BEAT_RECEIVED` | `NPU ETHOSU_PMU_EXT_RD_DATA_BEAT_RECEIVED` |
| 4 | `ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN` | `NPU ETHOSU_PMU_EXT_WR_DATA_BEAT_WRITTEN` |

U55/U65 분기는 slot 0-3에 `AXI0_RD` / `AXI0_WR` / `AXI1_RD`를 쓴다.
**U85는 5개, U55/U65는 4개**이며 이름 체계가 완전히 다르다.

### 2단계 — 파서가 라벨을 인식하는가: **NO**

`stage1.py` L176-178:

```python
"axi0_rd_beats": g(r"AXI0_RD_DATA_BEAT_RECEIVED:\s*(\d+)"),
"axi0_wr_beats": g(r"AXI0_WR_DATA_BEAT_WRITTEN:\s*(\d+)"),
"axi1_rd_beats": g(r"AXI1_RD_DATA_BEAT_RECEIVED:\s*(\d+)"),
```

U85 UART에는 `AXI0_*`/`AXI1_*` 라벨이 없으므로 세 정규식 모두 `None`을 반환한다.
`EXT_WR`에 대응하는 필드는 레코드 스키마에 **아예 없다**.

### 3단계 — 원시 UART가 보존되어 있는가: **NO**

| 위치 | 상태 |
|---|---|
| `container:/tmp/xq` (stage1 `ROOT`, 셀 워크스페이스) | **비어 있음** (셀마다 `shutil.rmtree`) |
| `container:/tmp/xqstage1..3`, `/tmp/xqformal`, `/tmp/xqout` | 존재하나 **파싱된 JSON만** (74개씩) |
| `/tmp/xqstage1/_stage1.log` | 6,832 B, PMU 라인 **0건** |
| 저장소 `stage{1,2,3}_m{1,2,3}_evidence.tar.gz` | **74 json만**, UART 없음 |
| 서버 frozen evidence 루트 (`EVIDENCE.sha256` 보유) | U85_MECH_P0C0/P0C/P0D/P0D2/P1A/P1B, X1, PMU_CFG, U65_BRIDGE — **formal FVP 스윕 루트 없음** |

보존된 JSON의 `measurement` 스키마에는 `uart_tail` 키 자체가 없다
(`DETERMINISTIC_METRIC_VECTOR.md`는 비-동등성 항목으로 언급하나 stage1 레코드에는 부재).

### 4단계 — 보존 UART에서 이벤트 라인 확인: **불가**

3단계에 따라 확인 대상이 존재하지 않는다.

### 파생 결과

- **재파싱으로 복구 불가.** 복구하려면 재측정이 필요하며, 이는 이번 작업 범위 밖이다.
- 새 derived artifact를 만들지 않았다(만들 원본이 없음).
- **결정론 검사에 미친 영향:** 19개 동등성 필드 중 U85 메모리 3개는 35셀 전부에서
  `None == None == None`으로 vacuous 통과했다. 이는 소스에서 확인된 사실이며 추정이 아니다.
- 같은 이벤트군이 **mechanism dataset에는 수집되어 있다**
  (`U85_ATTRIBUTION_UNITS.csv`의 `evt_sram_rd` / `evt_sram_wr` / `evt_ext_rd` / `evt_ext_wr`).
  단, 다른 바이너리·다른 계측 경로이므로 whole-model 값의 대체물이 아니다.

---

## 확인하지 않은 것

- FVP·빌드·측정 재실행 없음
- 기존 frozen evidence 무수정 (읽기만)
- TA 레지스터의 런타임 실제 기록값 (정적 빌드 상수까지만 추적)
- formal 스윕 빌드의 `CMakeCache.txt` (미보존; 규칙과 `stage1.py`의 override 부재로 도출)
- U85 1024 MAC의 생성 헤더 실측 (CMake 규칙에서 도출)
