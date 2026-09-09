# 측정 방법 점검 — 도구·옵션 고정 현황과 FVP 사용법 추가 study 결과

**작성 2026-09-09.** 서버 read-only 확인 + R1 재측정(진행 중) 기준.
모든 수치는 컨테이너에서 직접 실행해 확인한 값이며, 기억이나 문서 인용이 아니다.

---

## 요약

- 테스트 조건과 옵션을 고정하고 도구를 version fix 하여 사용하였으나, **도출 데이터에
  대한 추가 검증이 필요**하였다.
- **도출된 데이터 자체에는 문제가 없었다.** 재빌드 시 artifact 해시가 바이트 단위로
  재현되고, 사이클 값이 frozen 값과 완전히 일치한다 (§2).
- 동일 버전의 도구를 이용해 동일한 옵션으로 결과를 뽑았다 — **단, 플랫폼 단위로만
  그렇다.** Fast Models 버전은 플랫폼마다 다르다 (§3 F1).
- 다만 **FVP 사용법에 대한 추가 study 결과**, PMU 이벤트 이름 체계·이벤트 슬롯 구성·
  메모리 지연 파라미터·시뮬레이터 버전 선택에 대해 미흡하거나 고려하지 못한 점이
  확인되었고, 일부는 **추가 측정이 필요**하다 (§3, §4).

---

## 1. 고정한 것

### 1.1 도구 버전 (2026-09-09 컨테이너에서 직접 확인)

| 도구 | 버전 | 확인 방법 |
|---|---|---|
| Vela | `5.0.0` | `vela --version` |
| arm-none-eabi-gcc | `15.2.1 20251203` (Arm GNU Toolchain 15.2.Rel1, Build arm-15.86) | `arm-none-eabi-gcc --version` |
| CMake | `4.3.2` | `cmake --version` |
| Python | `3.10.12` | `python3 --version` |
| MLEK | `b2c0bb2884698b7328f65c41b7c8c51ca9bec386` | `git rev-parse HEAD` |

> 컴파일러 버전은 `REPORT.md` v1.2까지 `Not established`였다. 이번에 확정되었다.

### 1.2 빌드 옵션 (전 셀 공통)

| 항목 | 값 | 비고 |
|---|---|---|
| `SOURCE_DATE_EPOCH` | `1776763519` | 펌웨어가 `__DATE__`/`__TIME__`를 임베드하므로 고정 필수 |
| `inference_runner_ACTIVATION_BUF_SZ` | `0x00200000` (2 MiB) | 전 셀 동일 |
| `USE_CASE_BUILD` | `inference_runner` | stock, 무패치 |
| Vela 옵션 | `--optimise Performance`, `--config scripts/vela/default_vela.ini` | |
| toolchain | `bare-metal-gcc.cmake` | |
| `ETHOS_U_NPU_ENABLED` | `ON` | |
| `-DTA_CONFIG_FILE` | **넘기지 않음** | MLEK default 규칙이 적용됨 (§3 F4) |

### 1.3 플랫폼별 조건 표

| platform | NPU | MAC | FVP 바이너리 | Fast Models | system_config | memory_mode | TA | TA config file |
|---|---|---:|---|---|---|---|---|---|
| SSE-300 | u55 | 32/64/128/256 | `fvp_installed/.../SSE-300_Ethos-U55` | **11.22.35** | `Ethos_U55_High_End_Embedded` | Shared_Sram | ON | `ta_config_u55_high_end` |
| SSE-300 | u65 | 256/512 | `fvp_installed/.../SSE-300_Ethos-U65` | **11.22.35** | `Ethos_U65_High_End` | Dedicated_Sram | ON | `ta_config_u65_high_end` |
| SSE-310 | u55 | 32/64/128/256 | `fvp_installed_310/.../SSE-310` | **11.24.13** | `Ethos_U55_High_End_Embedded` | Shared_Sram | **OFF** | — |
| SSE-310 | u65 | 256/512 | `fvp_installed_310/.../SSE-310_Ethos-U65` | **11.24.13** | `Ethos_U65_High_End` | Dedicated_Sram | **OFF** | — |
| SSE-315 | u65 | 256/512 | `fvp_avh/bin/SSE-315` | **11.31.28** | `Ethos_U65_High_End` | Dedicated_Sram | **OFF** | — |
| SSE-320 | u85 | 128 | `fvp_installed_320/.../SSE-320` | **11.27.25** | `Ethos_U85_SYS_DRAM_Low` | Dedicated_Sram | ON | `..._low` |
| SSE-320 | u85 | 256 | 〃 | 11.27.25 | `Ethos_U85_SYS_DRAM_Low` | Dedicated_Sram | ON | `..._low` |
| SSE-320 | u85 | 512 | 〃 | 11.27.25 | `Ethos_U85_SYS_DRAM_Mid_512` | Dedicated_Sram | ON | `..._mid` |
| SSE-320 | u85 | 1024 | 〃 | 11.27.25 | `Ethos_U85_SYS_DRAM_Mid_1024` | Dedicated_Sram | ON | `..._mid` |
| SSE-320 | u85 | 2048 | 〃 | 11.27.25 | `Ethos_U85_SYS_DRAM_High_2048` | Dedicated_Sram | ON | `..._high` (mid와 바이트 동일) |

FVP 경로·버전은 frozen `cells.json`의 `fvp` 필드와 각 바이너리의 `--version` 출력으로
교차 확인했다.

### 1.4 사용한 FVP 실행 옵션 (전 셀 공통)

```
-C <board>.subsystem.ethosu.num_macs=<MAC>
-C <board>.visualisation.disable-visualisation=1
-C <board>.telnetterminal0.start_telnet=0
-C <board>.uart0.out_file=<path>
-C <board>.uart0.unbuffered_output=1
```

**설정한 것은 이 5개가 전부다.** SSE-320 FVP가 노출하는 파라미터는 총 **1,870개**다
(`--list-params`). 나머지는 전부 기본값으로 두었다 (§3 F5, F6).

---

## 2. 도출된 데이터에는 문제가 없었다

R1 재측정(§4 A2)이 이를 직접 증명하고 있다. 35셀 중 **12셀 완료 시점**의 결과:

| 검증 항목 | 결과 |
|---|---|
| Vela artifact SHA-256 재현 | 전수 일치 |
| 생성 `.cc` body SHA-256 재현 | 전수 일치 |
| 링크된 AXF SHA-256 재현 | 전수 일치 |
| 임베드 build stamp (`SOURCE_DATE_EPOCH`) | 전수 일치 |
| `TOTAL` 사이클 vs frozen `canonical_cycles` | 전수 일치 |
| `ACTIVE` 사이클 vs frozen | 전수 일치 |
| 반복 2회(R1/R2) 전 필드 동일 | 전수 일치 |

즉 **같은 소스·같은 옵션·같은 도구 버전으로 다시 빌드하면 바이트 단위로 같은
실행 파일이 나오고, 그 실행 파일은 같은 사이클 수를 낸다.** 기존 사이클 데이터는
유효하다.

> 최종 판정(G1–G5, 35/35)은 R1 완료 후 `remeasure/R1_GATE_REPORT.md`에 기록한다.
> 현재 상태: **IN_PROGRESS (12/35)**.

**문제가 있었던 것은 측정이 아니라 판독이었다** — §3 F2.

---

## 3. FVP 사용법 추가 study 결과 — 미흡했거나 고려하지 못한 점

### F1. Fast Models 버전이 플랫폼마다 다르다 — 그리고 통일할 수 있었다

| 사용한 것 | 버전 |
|---|---|
| SSE-300 | 11.22.35 (2023-08-18) |
| SSE-310 | 11.24.13 (2024-01-04) |
| SSE-320 | 11.27.25 (2024-09-24) |
| SSE-315 | 11.31.28 (2026-03-01) |

그런데 같은 컨테이너의 `/opt/arm/fvp_avh/bin/`에 **네 플랫폼 전부가 단일 버전
11.31.28로** 설치되어 있다:

```
fvp_avh/bin/FVP_Corstone_SSE-300  -> Fast Models [11.31.28]
fvp_avh/bin/FVP_Corstone_SSE-310  -> Fast Models [11.31.28]
fvp_avh/bin/FVP_Corstone_SSE-315  -> Fast Models [11.31.28]
fvp_avh/bin/FVP_Corstone_SSE-320  -> Fast Models [11.31.28]
```

SSE-315만 이 AVH 번들에서 실행했고 (frozen `cells.json`이 경로로 증명), 나머지 셋은
각각 독립 설치본을 썼다. **단일 버전으로 4개 플랫폼을 모두 돌릴 수 있었는데 그렇게
하지 않았다.**

- **영향:** 플랫폼 간 비교는 플랫폼 차이와 시뮬레이터 버전 차이가 교락되어 있다.
- **한정:** 이것이 실제로 수치를 바꾸는지는 **측정하지 않았다.** 바꾸지 않을 수도
  있다. 현재 상태는 "확인되지 않음"이지 "오염됨"이 아니다.
- → **추가 측정 A1**

### F2. PMU 이벤트 이름이 NPU 세대에 따라 다르다 (해결 진행 중)

stock profiler(`ethosu_profiler.c` L104-128)가 슬롯에 넣는 이벤트가 세대별로 다르다.

| 세대 | 슬롯 수 | 이벤트 이름 |
|---|---:|---|
| U55 / U65 | 4 | `AXI0_RD` / `AXI0_WR` / `AXI1_RD` |
| U85 | 5 | `SRAM_RD` / `SRAM_WR` / `EXT_RD` / `EXT_WR` |

`stage1.py`의 파서는 `AXI0_*`/`AXI1_*` 정규식만 가지고 있었다. U85 UART에는 그 라벨이
없으므로 세 필드 모두 `None`이 되었고, `EXT_WR`에 대응하는 필드는 스키마에 아예
없었다. **U85 35셀 전부에서 whole-model 메모리 카운터가 공란이 되었다.**

부수 피해: 결정론 검사 19개 필드 중 U85 메모리 3개가 35셀 전부에서
`None == None == None`으로 **무의미하게 통과**했다.

- **원인은 측정이 아니라 판독이다.** 값은 UART에 정상 출력되고 있었다.
- 원시 UART가 워크스페이스와 함께 삭제되어 재파싱으로는 복구 불가 → 재측정 필요.
- → **추가 측정 A2 (진행 중)**

### F3. U55/U65는 `AXI1_WR`을 애초에 수집하지 않았다

U55/U65 분기는 슬롯 0-3에 `AXI0_RD`, `AXI0_WR`, `AXI1_RD`만 넣는다. **`AXI1_WR`은
프로그램되지 않는다.** 따라서 U55/U65의 port1은 read-only이며, 지금까지의 port
share는 *수집된 부분집합에 대한* 비율이다.

R1 복구 후 U85는 네 카운터가 모두 있으므로 **완전집합**에 대한 비율이 된다.
**두 비율은 서로 비교할 수 없다.** 표에 그렇게 명시했다.

- 슬롯 구성을 바꾸려면 펌웨어 수정이 필요하다 → 프로젝트 제약과 충돌 (§4 참조).

### F4. Timing Adapter는 build-time이며, MAC에 따라 조용히 바뀐다

- TA 파일은 `ETHOS_U_NPU_CONFIG_ID`(=MAC)로 **CMake가 자동 선택**한다.
  우리는 `-DTA_CONFIG_FILE`을 넘기지 않았으므로 default 규칙이 적용되었다.
- U85 사다리에서 TA 설정은 **정확히 한 번, 256→512에서 바뀐다**
  (SRAM latency 16→32, `EXT_MAXR` 24→64, `EXT_RLATENCY` 250→500, `EXT_BWCAP` 2344→3750).
- 따라서 **`TA=ON`이 전 MAC에서 동일 조건을 뜻하지 않는다.**
- SSE-310/315는 TA가 **OFF**이며, 이는 플래그가 아니라 *컴파일 대상 소스 파일의 부재*로
  나타난다. 해당 56셀은 실행가능성 증거이지 성능 데이터가 아니다.

### F5. FVP의 메모리 지연 파라미터는 전부 기본값 0이다

```
mps4_board.ddr.read_latency = 0        (ps/byte)
mps4_board.ddr.write_latency = 0
mps4_board.sram.read_latency = 0
mps4_board.sram.write_latency = 0
mps4_board.qspi_sram.read_latency = 0
```

즉 **FVP 자체의 메모리 지연 모델은 꺼져 있고, 메모리 타이밍은 전적으로 Timing
Adapter에서 온다.** 이것은 F4와 합쳐져 중요한 결론을 준다 — **TA가 OFF인 구성은
메모리 지연이 0인 환경**이며, SSE-310/315를 성능 비교에서 제외한 것이 사후 판단이
아니라 구조적으로 옳았음을 뒷받침한다.

한편 MPS4 FVP는 TA를 **런타임 `-C`로 노출하지 않는다** (`stub_timing_adapter`뿐).
따라서 TA를 바꾸려면 반드시 재빌드해야 한다. — FVP 옵션으로 TA를 조정할 수 있었는지에
대한 의문은 이것으로 닫힌다.

### F6. CPU 캐시는 상태 모델링이 꺼져 있다

```
mps4_board.subsystem.cpu0.dcache-state_modelled = 0
mps4_board.subsystem.cpu0.icache-state_modelled = 0
mps4_board.subsystem.cpu0.DCACHESZ = 15   (64KB, 포함)
mps4_board.subsystem.cpu0.ICACHESZ = 15   (64KB, 포함)
```

캐시는 *존재하지만 상태가 모델링되지 않는다.* NPU PMU 사이클 자체에는 영향이 제한적일
것으로 보이나, **확인하지 않았다.** CPU 측 시간을 논거로 쓸 경우 반드시 짚어야 한다.

### F7. 쓰지 않은 NPU 옵션

SSE-320 FVP가 노출하는 `ethosu.*` 파라미터는 3개뿐이며, 우리는 그중 하나만 썼다.

| 파라미터 | 기본값 | 우리 설정 | 비고 |
|---|---|---|---|
| `ethosu.num_macs` | 256 | **설정함** | 범위 `[0x80:0x800]` = 128–2048, 우리 사다리와 정확히 일치 |
| `ethosu.diagnostics` | 0 | 미사용 | 범위 `[0x0:0x4]` — 진단 메시지 레벨 |
| `ethosu.extra_args` | `""` | 미사용 | Arm 기술지원 지시 시에만 사용 권장 |

`num_macs`의 허용 범위가 128–2048이라는 것은 **U85 사다리가 시뮬레이터가 허용하는
전 범위를 덮고 있음**을 뜻한다. 이는 긍정적 확인 사항이다.

### F8. counter overflow 경고를 파서가 수집하지 않는다

`ethosu_profiler.c`의 `counter_overflow()`가 `warn("Counter overflow detected for %s.")`를
출력하고, 주석은 *"The idle counter is 32 bit while the total cycle count is 64 bit"*라고
적고 있다. **현재까지의 파서는 이 경고를 수집하지 않았다.** 경고가 실제로 발생했는지
여부 자체가 확인되지 않은 상태다.

R1은 원시 UART를 보존하므로 **사후 확인이 가능해졌다.** (R1 완료 후 확인 예정)

### F9. IDLE은 독립 카운터가 아니다 (기확인, 참고)

`IDLE = TOTAL − ACTIVE`인 소프트웨어 파생값이다. 따라서 `TOTAL == ACTIVE + IDLE`
74/74는 **산술 항등식이며 독립적인 PMU 일관성 검증이 아니다.** 측정 창은 드라이버의
`inference_begin` ~ `inference_end` 구간이다.

---

## 4. 추가 측정이 필요한 항목

| # | 항목 | 근거 | 펌웨어 수정 필요 | 상태 |
|---|---|---|---|---|
| **A1** | 4개 플랫폼을 **단일 Fast Models 11.31.28**(AVH 번들)로 재측정 | F1 | 불필요 | **미착수 — 관리자 판단 필요** |
| **A2** | U85 whole-model 메모리 카운터 재측정 (35셀 × 2반복) | F2 | 불필요 | **진행 중 (12/35)** |
| **A3** | U55/U65 `AXI1_WR` 수집 | F3 | **필요** | **보류 — 제약 충돌** |
| **A4** | counter overflow 경고 수집·확인 | F8 | 불필요 (파서만) | R1 UART로 사후 확인 예정 |
| **A5** | 캐시 상태 모델링 ON에서의 영향 확인 | F6 | 불필요 (`-C`) | 미착수 — 필요성 낮음 |

### A1이 가장 값어치 있다

펌웨어를 건드리지 않고, 기존 빌드 절차를 그대로 쓰며, 이미 설치된 바이너리만 바꾸면
된다. 결과가 기존과 일치하면 **F1의 교락 우려가 데이터로 해소**되고, 다르면 그 자체가
중요한 발견이다. 어느 쪽이든 결론이 강해진다.

### A3은 프로젝트 제약과 충돌한다

`AXI1_WR`을 얻으려면 PMU 이벤트 슬롯 구성을 바꿔야 하고, 이는 `inference_runner`
경로의 수정을 의미한다. 프로젝트 표준 제약은 다음과 같다:

> *"Never patch `inference_runner` to obtain a metric. If the stock path cannot
> produce an observation, that is the finding."*

따라서 **A3은 임의로 진행하지 않는다.** 현재의 올바른 처리는 U55/U65 port share를
*수집된 부분집합에 대한 비율*로 명시하고 U85와 비교하지 않는 것이며, 이미 그렇게
처리했다. 제약을 풀 것인지는 관리자 판단 사항이다.

---

## 검증 수준

```
검증 수준: 통합 (서버 실행 + 재빌드 + FVP 실행)
```

**실제 실행한 것**
- 컨테이너에서 도구 버전 5종 직접 실행 확인
- FVP 바이너리 7개의 `--version` 직접 확인 (표준 설치본 3 + AVH 번들 4)
- SSE-320 FVP `--list-params` 1,870개 열거 및 카테고리별 확인
- frozen `cells.json` 133셀의 FVP 경로 확인
- R1 재측정 12/35 셀 (재빌드 + 해시 게이트 + FVP 실행 + 재파싱), 각 2회 반복

**실행하지 않은 것**
- A1 (단일 버전 재측정) — 미착수
- A3, A5 — 미착수
- R1 나머지 23셀 및 G1–G5 최종 판정 — 진행 중
- 캐시/지연 파라미터를 바꾼 대조 실행 — 없음. F5·F6은 **파라미터 기본값 확인**이지
  영향 측정이 아니다.
