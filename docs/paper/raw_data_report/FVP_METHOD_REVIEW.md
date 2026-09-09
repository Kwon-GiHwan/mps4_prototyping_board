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

R1 재측정(§4 A2)이 이를 직접 증명했다. **35/35 완료**, 각 2회 반복(총 70회 실행):

| 검증 항목 | 결과 |
|---|---|
| Vela artifact SHA-256 재현 | 전수 일치 |
| 생성 `.cc` body SHA-256 재현 | 전수 일치 |
| 링크된 AXF SHA-256 재현 | 전수 일치 |
| 임베드 build stamp (`SOURCE_DATE_EPOCH`) | 전수 일치 |
| `TOTAL` 사이클 vs frozen `canonical_cycles` | 전수 일치 |
| `ACTIVE` 사이클 vs frozen | 전수 일치 |
| 반복 2회(R1/R2) 전 필드 동일 | 전수 일치 |

게이트 판정:

```
R1_GATES: PASS
  G1_artifact_reproduction        35/35
  G2_total_cycles_match_frozen    35/35
  G3_active_cycles_match_frozen   35/35
  G4_repetition_identical         35/35
  G5_memory_counters_present      35/35
```

뮤테이션 테스트 9건 통과 — 각 게이트를 데이터에서 무력화해 FAIL 발화를 확인했다.

즉 **같은 소스·같은 옵션·같은 도구 버전으로 다시 빌드하면 바이트 단위로 같은
실행 파일이 나오고, 그 실행 파일은 같은 사이클 수를 낸다.** 기존 사이클 데이터는
유효하다.

> 상세: `remeasure/R1_GATE_REPORT.md`, `remeasure/R1_RESULTS.json`.

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

#### 정정 — 이 항목은 이미 기록되어 있었고, 부분적으로 답이 나와 있다

초판에서 이것을 새 발견처럼 쓰고 A1을 "가장 값어치 있다"고 했다. **둘 다 틀렸다.**
기존 frozen 기록을 확인한 결과:

1. **이미 기록되어 있다.** X0 산출물
   `platform_sensitivity/FVP_COMPARABILITY_MATRIX.md`가 FVP별 Fast Models 버전을
   컬럼으로 갖고 있으며, 비교 등급(CLASS A/B/X)까지 부여해 동결해 두었다.
2. **교락도 명시되어 있다.** `X1_LIMITATIONS.md` #1 — *"every CLASS B comparison
   changes subsystem, Fast Models version and TA state together. Attribution to
   any single factor is `NOT_SEPARATED`."* `X3_LIMITATIONS.md` #2도 같다.
3. **부분적으로 실측 답이 있다.** CLASS A는 **SSE-310(FM 11.24.13) ↔
   SSE-315(FM 11.31.28)** 쌍이다. 즉 *서로 다른 Fast Models 버전*을 나머지 조건을
   맞춘 채 비교한 것이며, 결과는 **14/14 셀 canonical cycle 완전 일치**였다
   (근사가 아니라 exact).

따라서 "버전이 다르니 수치가 오염됐을 수 있다"는 우려는, **직접 비교가 가능했던
유일한 조건에서 반증되었다.**

- **남는 한정:** CLASS A는 `TA_OFF`·U65·14셀뿐이다. `TA_ON`이나 U85/SSE-320으로의
  전이는 `NOT_EVALUABLE`이다. 우려가 완전히 닫힌 것은 아니고 **훨씬 좁아졌다.**
- **계획서와의 관계:** `docs/FUTURE_EXPERIMENT_PLAN.md` §10은
  *"immediate FM reinstall/version-unification"*을 **not currently recommended**로
  명시한다. 버전 통일(Stage X5)은 실행 순서 **10번째**이며, *"only if absolute
  cross-platform performance becomes a paper goal"* 조건부다. 현재 논문은 절대
  교차 플랫폼 비교를 하지 않으므로 조건이 성립하지 않는다.
- → **A1은 권고에서 철회한다.** 아래 §4 참조.

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

R1이 원시 UART를 보존하므로 확인했다 — **보존된 71개 UART 전수에서 overflow 경고
0건.** U85 35셀 × 2반복 범위에서 이 우려는 실증적으로 닫혔다.

### F10. 클럭 주파수는 설정값이 아니라 fallback 가정값이다

보존된 UART 전 실행에서 다음이 출력된다:

```
INFO - WARN - MPS4_SCC->CFG_ACLK reads 0. Assuming default clock of 32000000
```

FVP가 SCC 클럭 레지스터를 제공하지 않아 펌웨어가 **32 MHz를 가정**한다. NPU 사이클
카운트 자체에는 영향이 없다(사이클은 클럭과 무관하게 세어진다). 다만 **사이클을
시간(ms, FPS)으로 환산하는 순간 그 32 MHz는 우리가 설정한 값이 아니라 읽기 실패에
따른 fallback**이 된다.

본 보고서와 논문은 시간 환산을 하지 않으므로 현재 영향은 없다. 향후 시간 단위 주장을
할 경우 반드시 짚어야 한다.

### F9. IDLE은 독립 카운터가 아니다 (기확인, 참고)

`IDLE = TOTAL − ACTIVE`인 소프트웨어 파생값이다. 따라서 `TOTAL == ACTIVE + IDLE`
74/74는 **산술 항등식이며 독립적인 PMU 일관성 검증이 아니다.** 측정 창은 드라이버의
`inference_begin` ~ `inference_end` 구간이다.

---

## 4. 추가 측정이 필요한 항목

| # | 항목 | 근거 | 펌웨어 수정 필요 | 상태 |
|---|---|---|---|---|
| ~~**A1**~~ | ~~4개 플랫폼을 단일 Fast Models로 재측정~~ | F1 | 불필요 | **철회.** 이미 X5로 계획돼 있고, 계획서가 현재 비권고로 분류. CLASS A가 부분 반증 |
| **A2** | U85 whole-model 메모리 카운터 재측정 (35셀 × 2반복) | F2 | 불필요 | **완료 — G1–G5 전부 PASS 35/35** |
| **A3** | U55/U65 `AXI1_WR` 수집 | F3 | **필요** | **보류 — 제약 충돌** |
| **A4** | counter overflow 경고 수집·확인 | F8 | 불필요 (파서만) | **완료 — 71개 UART 전수 0건** |
| **A5** | 캐시 상태 모델링 ON에서의 영향 확인 | F6 | 불필요 (`-C`) | 미착수 — 필요성 낮음 |

### A1을 철회한 이유

초판에서 A1을 최우선으로 권고했으나, frozen 기록을 확인한 뒤 철회한다.

- 이것은 이미 **Stage X5**로 계획되어 있다 (`FUTURE_EXPERIMENT_PLAN.md`).
- 계획서 §10이 *"immediate FM reinstall/version-unification"*을 **not currently
  recommended**로 분류했고, X5는 실행 순서 10번째의 조건부 단계다.
- 그리고 CLASS A(FM 11.24.13 ↔ 11.31.28, 14/14 exact 일치)가 이미 부분적인
  실측 답을 준다.

**새 측정을 제안하기 전에 기존 계획과 기존 데이터를 먼저 확인했어야 했다.**
계획서 §11이 요구하는 절차가 정확히 그것이다 — 새 실험을 제안하기 전에
FUTURE_EXPERIMENT_PLAN과 frozen evidence를 먼저 읽을 것.

### A3은 프로젝트 제약과 충돌한다

`AXI1_WR`을 얻으려면 PMU 이벤트 슬롯 구성을 바꿔야 하고, 이는 `inference_runner`
경로의 수정을 의미한다. 프로젝트 표준 제약은 다음과 같다:

> *"Never patch `inference_runner` to obtain a metric. If the stock path cannot
> produce an observation, that is the finding."*

따라서 **A3은 임의로 진행하지 않는다.** 현재의 올바른 처리는 U55/U65 port share를
*수집된 부분집합에 대한 비율*로 명시하고 U85와 비교하지 않는 것이며, 이미 그렇게
처리했다. 제약을 풀 것인지는 관리자 판단 사항이다.

---

## 5. 측정 하네스 — 파이썬 스크립트의 역할

### 5.1 FVP는 손으로 실행된 적이 없다

§1.4의 5개 `-C` 옵션은 **파이썬 스크립트가 argv 리스트로 구성한 것**이다. 전체 명령은
이것이 전부다:

```python
cmd = [cell["fvp"], "-a", axf,
       "-C", "%s=%d" % (mac_param, cell["mac_config"]),
       "-C", "%s.visualisation.disable-visualisation=1" % board,
       "-C", "%s.telnetterminal0.start_telnet=0" % board,
       "-C", "%s.uart0.out_file=%s" % (board, uart),
       "-C", "%s.uart0.unbuffered_output=1" % board]
```

`subprocess.Popen(cmd, ...)`으로 실행되며 셸을 거치지 않는다.

측정을 수행하는 스크립트는 4개(`execq.py`, `stage1.py`, `stage2.py`, `stage3.py`)이고,
**네 파일 모두 `-C`가 정확히 5개씩**이다. `--stat`, `--cyclelimit`, `-Q`, `--quantum`,
`--plugin`, `-f`(config 파일) 등 다른 FVP 플래그는 **전 스크립트에서 0건**이다.

> 따라서 "그 외 파라미터 기본값 사용"은 **명시적으로 기본값을 지정한 것이 아니라,
> 지정하지 않아서 기본값이 적용된 것**이다. 1,870개 파라미터를 검토한 뒤 기본값을
> 선택한 것이 아니다. 이 구분이 §3 F5·F6이 뒤늦게 나온 이유다.

MAC 값과 보드 이름만 셀에 따라 달라지고(`mps4_board` / `mps3_board`,
`mps4_board.subsystem.ethosu.num_macs` / `ethosu.num_macs`), 나머지 네 개는 리터럴이다.

### 5.2 스크립트별 역할

| 스크립트 | 줄 수 | 역할 |
|---|---:|---|
| `ccident.py` | 61 | 생성된 모델 `.cc`의 **정규 신원**. 생성기가 찍는 wall-clock 헤더 필드 **하나만** 제거하고 body를 해시한다. "첫 줄 버리기" 같은 일반 규칙이 아니라 pinned 템플릿 문법을 단언하며, 위반 시 fail-closed |
| `execq.py` | 319 | **실행가능성 자격검증** (133셀). 셀마다 워크스페이스 생성 → vela → 빌드 → 실행 → 증거 수집 → 워크스페이스 삭제 → 공간 회수 확인. `FORMAL_FVP_SAMPLES = 0`, 즉 **여기서 나온 사이클 값은 자격검증 증거일 뿐 논문 성능 샘플이 아니다** |
| `formal_baseline.py` | 217 | 74개 primary 셀의 **재현 가능한 AXF 기준선** 수립. 신원 = pinned 소스 클로저 + pinned 툴체인 + pinned `SOURCE_DATE_EPOCH` + pinned 빌드 경로 + pinned 빌드 인자. 이것이 anchor 해시가 된다 |
| `stage1.py` | 255 | **정식 측정 1회차 (M1)**, 74셀. 셀마다 재빌드하여 anchor 해시를 바이트 재현해야 **비로소 실행이 허용**된다 |
| `stage2.py` | 295 | **2회차 (M2)**. 동일 anchor·동일 순서·동일 게이트에 더해 **결정론 검사** — 19개 동등성 필드가 M1과 완전 일치해야 한다 |
| `stage3.py` | 302 | **3회차 (M3)**, `M1 == M2 == M3` 확정. M3는 **앞의 두 회차 모두와** 같아야 한다 |
| `requal.py` | 55 | **하네스 자격검증**. 양성 1건 + **음성 1건**(arena를 일부러 작게 잡아 fatal 경로를 강제 발화). 둘 다 잔존 FVP 프로세스 0이어야 한다 |
| `summarize.py` | 108 | 실행가능성 집계 — 2계층 카운트, 실패 구조, provenance |
| `fpga_build.py` | 126 | FPGA용 U85@1024 빌드 7건. **provenance 전용, 보드 실행 없음.** FVP 바이너리와 FPGA 바이너리는 MLEK 계약상 서로 다르므로 아무것도 전용(轉用)하지 않는다 |
| `pmuparse.py` | 65 | 세대 비의존 PMU 파서. 이벤트 이름을 가정하지 않고 **발견**한다 |
| `remeasure_u85.py` | 137 | **R1 재측정** (신규). `stage1`을 재구현하지 않고 **import**한다 |
| `gates.py` / `test_gates.py` | 108 / 84 | R1 게이트 G1–G5 판정 + **뮤테이션 테스트** (신규) |

### 5.3 설계에서 잘 잡힌 것

이 하네스가 §2의 "데이터에 문제 없음"을 가능하게 한 구조적 이유다.

1. **빌드 게이트가 실행 앞에 있다.** 나중에 비교하는 것이 아니라, anchor 해시를 바이트
   재현하지 못하면 **애초에 FVP를 실행하지 않는다.**
2. **하드 스톱, 재시도 없음.** 어떤 정지 조건이든 스테이지 전체를 멈춘다. top-up도,
   재량 재시도도 없다.
3. **결정론은 다수결이 아니다.** `stage3.py`가 명시한다 — *"no 2/3 majority, no M3
   retry, no median, no average, no tie-break from the qualification value."*
   불일치는 `DETERMINISM_FAILURE`이지 평균 낼 대상이 아니다.
4. **자격검증에 음성 시험이 있다.** `requal.py`의 주석 그대로 — *"Positive alone is a
   silent gate."* 실패 경로를 실제로 발화시켜 확인한다.
5. **역할이 분리되어 있다.** 측정 스크립트는 분석하지 않는다 (`stage1.py`: *"No analysis
   is performed here"*). 자격검증 사이클과 정식 샘플이 코드 수준에서 구분된다.
6. **프로세스 누수 검사.** 실행 전후로 FVP 프로세스 목록을 비교해 잔존 프로세스를
   증거로 남긴다.

### 5.4 설계에서 약했던 것 — F2의 구조적 원인

**파서가 측정 스크립트 안에 인라인 정규식으로 박혀 있었다.**

```python
# stage1.py L176-178
"axi0_rd_beats": g(r"AXI0_RD_DATA_BEAT_RECEIVED:\s*(\d+)"),
```

이 설계에는 세 가지 결과가 따라왔다.

- **파서에 테스트가 없었다.** 빌드·해시·결정론·프로세스 누수에는 게이트가 있었지만,
  *판독*에는 없었다. 라벨이 안 맞으면 예외가 아니라 `None`이 되었다.
- **`None`이 성공처럼 통과했다.** 결정론 검사에서 U85 메모리 3필드가 35셀 전부
  `None == None == None`으로 **무의미하게 일치**했다. 검사가 아무것도 검사하지 않는
  전형적인 형태다.
- **원시 UART가 즉시 삭제되었다.** 워크스페이스 즉시 삭제(§5.3의 디스크 회수 설계)가
  여기서는 역효과였다. 파싱된 JSON만 남아 **재파싱으로 복구할 수 없었다.**

`pmuparse.py`는 이 문제를 고치려고 작성되어 있었으나 — **어떤 모듈도 import하지 않는다**
(이번 세션 확인). 작성만 되고 배선되지 않았다. R1이 첫 사용이다.

### 5.5 R1에서 바꾼 것

| 항목 | 기존 | R1 |
|---|---|---|
| 빌드·게이트·FVP 실행 | `stage1.py` | **동일 코드** (`import stage1`) — 재구현 아님 |
| 파서 | 인라인 정규식, 이름 가정 | `pmuparse.parse_profile` — 이름 **발견**, 실패 시 예외 |
| 원시 UART | 워크스페이스와 함께 삭제 | **워크스페이스 밖에 보존** |
| 판정 | — | `gates.py` G1–G5, 35/35에서만 PASS |
| 판정의 검증 | — | `test_gates.py` — 각 게이트를 **데이터에서** 무력화해 FAIL 발화 확인 |

재구현이 아니라 import인 이유는, "stage1과 같은 방식으로 빌드했다"가 아니라
**"stage1과 같은 코드로 빌드했다"**를 성립시키기 위해서다.

---

## 검증 수준

```
검증 수준: 통합 (서버 실행 + 재빌드 + FVP 실행)
```

**실제 실행한 것**
- 컨테이너에서 도구 버전 5종 직접 실행 확인
- 측정 스크립트 11개의 docstring·함수 목록·`-C` 옵션 구성 직접 확인
  (`execq`/`stage1`/`stage2`/`stage3` 각 `-C` 5개, 다른 FVP 플래그 0건)
- FVP 바이너리 7개의 `--version` 직접 확인 (표준 설치본 3 + AVH 번들 4)
- SSE-320 FVP `--list-params` 1,870개 열거 및 카테고리별 확인
- frozen `cells.json` 133셀의 FVP 경로 확인
- R1 재측정 **35/35 셀** (재빌드 + 해시 게이트 + FVP 실행 + 재파싱), 각 2회 반복 = 70회
- R1 게이트 G1–G5 판정 + 뮤테이션 테스트 9건
- 보존 UART 71개 전수 overflow 경고 검사
- 감사 검사 10건 재실행 (전부 PASS) + 검사 5·10 뮤테이션 3건

**실행하지 않은 것**
- A1 (단일 Fast Models 버전 재측정) — **미착수, 관리자 판단 필요**
- A3 (`AXI1_WR` 수집) — 펌웨어 수정이 필요해 제약과 충돌, **보류**
- A5 (캐시 상태 모델링 영향) — 미착수
- 캐시/지연 파라미터를 바꾼 대조 실행 — 없음. F5·F6은 **파라미터 기본값 확인**이지
  영향 측정이 아니다.
- U55/U65 재측정 — 하지 않았다. R1은 U85 35셀만 대상이다.
