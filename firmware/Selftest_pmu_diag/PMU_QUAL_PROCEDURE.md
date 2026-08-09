# RUNNER_V1_PMU_QUAL — H-PRINTF schema v8 실보드 자격심사(qualification) 절차

> **이 문서의 지위**: 실보드 실행 **전(pre-board)** 절차서다. 여기 실린 모든
> 해시·주소·게이트 결과는 **컨테이너 정적 증거**이며, 보드에서 아무것도
> 실행하지 않은 상태에서 확정된 값이다. serial/board/SD/reboot는 **수행하지
> 않았다**.

---

## 0. 스코프 라벨 (먼저 읽을 것)

이 절차는 세 가지 라벨을 동시에 달고 있다. 하나라도 잊으면 결과가 오독된다.

| 라벨 | 의미 |
|---|---|
| **QUALIFICATION ONLY** | H-PRINTF seam이 "관측 가능하고 비간섭적인가"만 묻는다. |
| **NOT PRODUCTION** | Q0/Q1 이미지는 production 후보가 **아니다**. Production `END_ONLY`는 **동결(frozen) 상태 그대로**이며 이 절차는 그것을 건드리지 않는다. |
| **NOT A PERFORMANCE BASELINE** | 여기서 나오는 숫자는 성능 기준선이 아니다. 비교·회귀판정·리포팅에 쓰면 안 된다. |

`analyze_pmu_qual.py`는 실행 끝에 다음 줄을 무조건 출력한다. 이 줄이 없으면
그 출력은 이 절차의 산출물이 아니다:

```
QUALIFICATION ONLY -- no production go, no performance baseline.
```

### 배출 가능한 수치는 단 하나다

- **`npu_pmu_window_cycles`만** 외부로 내보낼 수 있다.
- 이것은 **counter window**다. **`T_npu`가 아니고, latency도 아니다.**
  `T_npu`라는 이름으로 환산·표기·전달하는 것을 금지한다.
- validity term이 **하나라도 실패하면 이 필드는 `None`이다** (`runner_proto`가
  `valid` 전체 AND에만 값을 채운다). `None`을 0이나 결측 처리로 대체하지 않는다.
- `raw_delta_diagnostic`은 **진단용**이다. validity와 무관하게 항상 채워지므로
  이 값을 성능 수치로 인용하면 안 된다.

### 권위 있는(authoritative) POST는 어디인가

- 권위 있는 측정 경계는 **`pre` → `internal_pre_release`** 두 스냅샷이다.
  `npu_pmu_window_cycles`는 이 쌍에서만 유도된다.
- **`after_return`은 corroboration(방증) 전용**이다. 벤더 드라이버의 terminal
  release가 PMU bank를 지워버리므로 **설계상 0으로 읽힌다**. gate로 쓰지 않는다.
- **golden window는 corroboration이 아니다.** `golden_window_base` /
  `golden_window_len` / `golden_window_crc`가 기대값과 **정확히** 일치하는지는
  `golden_window_ok`라는 **권위 있는 기능 validity gate**이며, `valid`의 AND에
  그대로 들어간다. 추론이 실제로 옳게 수행되었는지를 판정하는 항목이므로
  여기서 실패하면 그 표본은 무효다.
- corroboration인 것은 **둘뿐이다**: `result_region_crc`(표시 전용, v7과 동일하게
  어떤 term에도 들어가지 않는다)와 위의 **`after_return` PMU wipe**.
- 즉 **권위 있는 POST는 hook 내부(pre-release) 캡처**이고, 반환 후 PMU 관측은
  "벤더가 자기 release를 정상 발행했다"는 사실만 뒷받침한다. 반면 golden window는
  반환 후에 읽히더라도 **방증이 아니라 gate**다.

---

## 1. Q0 / Q1 계약

두 이미지는 **동일한 검출 경로**를 갖고 **부작용의 유무만** 다르다.

| | **Q0** (`PQB0`, `0x30425150`) | **Q1** (`PQH1`, `0x31485150`) |
|---|---|---|
| H-PRINTF hook | **DISABLED** | **ENABLED** |
| callsite 검출 | 수행 (관측 LR 기록) | 수행 (관측 LR 기록) |
| PMU snapshot / disable | **없음** | pre-release 캡처 + 단일 disable |
| `hook_fired_count` | **0** (설계상) | **정확히 1** |
| 성능 표본으로서 | **설계상 무효** — 기능/NPU 경로 등가성 확인 전용 | 자격심사 후보 |
| 벤더 드라이버 | 참조 `Drivers/u85_driver/u85.c`, `TEST_CPM=1` | 동일 (**byte-identical**) |
| terminal `CMD=0xC` | 벤더 드라이버가 발행 | 벤더 드라이버가 발행 (runner는 read만) |

계약의 핵심:

1. **벤더 object가 두 모드에서 byte-identical**이다
   (`cf0e816e161186f6d25750d340867afb1a268f2ef949b97212c3c8b7964fead2`).
   따라서 terminal release는 두 모드 모두 **수정되지 않은
   벤더 드라이버 자신**이 소유한다.
2. **Case A 강제**: schema v8은 **PMCCNTR_CFG를 어떤 값으로도 쓰지 않는다.**
   소스가 `PMU_QUAL_SCHEMA_V8` 하에서 다른 조합을 `#error`로 거부한다.
3. **Seam S1 강제**: 참조 드라이버를 링크하면서 runner-side release를 발행하지
   않는 유일한 v7 seam. S2/S3·private driver·모든 negative control은 v8에서
   컴파일 거부된다.
4. Q0는 "Q1이 유효한지"를 판정하지 않는다. Q0의 역할은 **hook을 끈 같은 빌드
   그래프가 동일한 NPU 경로를 통과한다**는 등가성 증거뿐이다.

### `PMCCNTR_CFG = 0x11`은 fix가 아니다

- v7의 A/B/C 실험에서 `PMCCNTR_CFG=0x11`(case B, START=CYCLE)은 **비교를 위한
  통제 변수**였다. **production fix가 아니다.**
- schema v8은 **CFG write 0건**이 계약이며, 이는 record가 아니라
  **전처리된 TU에 대한 정적 게이트**(`check_diag_case.py`)로 강제된다.
- 따라서 "0x11을 넣으면 되지 않느냐"는 이 절차의 유효한 결론이 될 수 없다.
  0x11을 재도입한 이미지는 **다른 이미지**이며, 여기 실린 어떤 gate도 그것을
  판정하지 않는다.

---

## 2. 빌드 및 정적 게이트 (benchmark-runner 컨테이너, `/work/selftest`)

```sh
make -f Makefile.pmu_qual QUAL=Q0 clean bins check manifest hashes
make -f Makefile.pmu_qual QUAL=Q1 clean bins check manifest hashes
```

- `QUAL`은 `Q0` 또는 `Q1`이어야 한다. 비우면 Makefile이 `$(error)`로 멈춘다.
- 출력 디렉터리는 각각 `build_pmu_qual_q0` / `build_pmu_qual_q1`이며 **서로
  독립**이다. v7 diag 빌드 그래프(`Makefile.pmu_diag`)와도 완전히 분리되어
  있어 **v7 산출물을 이동시키거나 무효화할 수 없다**.
- `-fno-builtin-printf`가 있고 `-flto`가 **없다**. 둘 다 취향이 아니라
  **게이트 조건**이다.

`check` 타깃이 돌리는 것:

```sh
python3 Selftest_measure/check_measure_symbols.py \
    --elf build_pmu_qual_<tag>/runner_pmu_qual.elf \
    --map build_pmu_qual_<tag>/runner_pmu_qual.map \
    --objdump /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump \
    --nm      /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm \
    --profile clean
python3 Selftest_pmu_diag/check_diag_case.py \
    --map build_pmu_qual_<tag>/runner_pmu_qual.map --map-only
```

`manifest` 타깃이 돌리는 것 (ELF 게이트 본체 + 머신리더블 manifest 생성):

```sh
python3 Selftest_pmu_diag/check_pmu_qual.py \
    --mode <Q0|Q1> \
    --build-id <0x30425150|0x31485150> \
    --vendor-source     Drivers/u85_driver/u85.c \
    --interface-header  Drivers/u85_driver/interface.h \
    --vendor-object     build_pmu_qual_<tag>/Drivers/u85_driver/u85.o \
    --regs-header       Selftest_pmu/npu_pmu_regs.h \
    --preprocessed      build_pmu_qual_<tag>/runner_pmu_qual_main.i \
    --elf               build_pmu_qual_<tag>/runner_pmu_qual.elf \
    --map               build_pmu_qual_<tag>/runner_pmu_qual.map \
    --app-bin           build_pmu_qual_<tag>/APP.BIN \
    --vectors-bin       build_pmu_qual_<tag>/VECTORS.BIN \
    --ddr-bin           build_pmu_qual_<tag>/DDR.BIN \
    --objdump /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump \
    --nm      /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm \
    --readelf /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-readelf \
    --cflags  "<CFLAGS>" \
    --manifest-out build_pmu_qual_<tag>/pmu_qual_manifest.json
```

`hashes` 타깃:

```sh
sha256sum build_pmu_qual_<tag>/APP.BIN \
          build_pmu_qual_<tag>/DDR.BIN \
          build_pmu_qual_<tag>/VECTORS.BIN \
          build_pmu_qual_<tag>/runner_pmu_qual.elf \
          build_pmu_qual_<tag>/runner_pmu_qual.map \
          build_pmu_qual_<tag>/Drivers/u85_driver/u85.o \
          build_pmu_qual_<tag>/pmu_qual_manifest.json
```

### 소스 동일성(source identity) 확인 명령

배포 전에 **벤더 소스가 동결값 그대로인지** 호스트와 컨테이너 양쪽에서 읽는다.
읽기 전용이며 아무것도 쓰지 않는다.

```sh
ssh -o BatchMode=yes gihwan \
  'sha256sum /home/gihwan/mps4/runner/selftest/Drivers/u85_driver/u85.c;
   docker exec benchmark-runner \
     sha256sum /work/selftest/Drivers/u85_driver/u85.c'
```

기대값 (두 경로 모두 동일해야 한다):

```
bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf
```

동결 baseline 전체 기록은 `PMU_QUAL_FROZEN_BASELINE.sha256`에 있다. 그 파일의
어떤 digest와도 어긋나면 **그 digest에 의존한 자격심사 실행은 무효**다.

---

## 3. 현재 산출물 해시 (2026-08-09 컨테이너 clean build)

동결 provenance가 아니라 **재현 기대값**이다. 배포 전 컨테이너에서 재빌드해
일치를 확인하고, 결과 JSON에는 **실제 배포한 BIN의 해시**를 host가 붙인다.
**이미지 식별은 APP.BIN 해시로 한다.**

**Q0/Q1 모두 clean build를 2회 수행했고, 각 모드 안에서 byte-identical했다.**

### Q0 — `build_pmu_qual_q0`, `build_id = 0x30425150` ("PQB0")

| 파일 | SHA-256 |
|---|---|
| `APP.BIN` | `727563fd252f574e19145b6d2beac388e4eed5205cf5f7cd92ff94f88a8e111d` |
| `VECTORS.BIN` | `eff245cd435a34c50c5ac2cd834a89c9e9114cef0131fcc5a7fb0b0ebc562309` |
| `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| `runner_pmu_qual.elf` | `a52f929b81d9c0661f0ede179a6fb8a9176435ab6709d453a577582268701288` |
| `runner_pmu_qual.map` | `ee9fba81e9cbd78e7309f5f9fae01fc5a3c0f1c9ff074181f28686a5e40dc556` |
| `pmu_qual_manifest.json` | `6d98025153fef18cd96e4962da5acc54848ccef6d08c497952fb78e58e5b4687` |

### Q1 — `build_pmu_qual_q1`, `build_id = 0x31485150` ("PQH1")

| 파일 | SHA-256 |
|---|---|
| `APP.BIN` | `dc66915a26f95e983b28b160d9acdec48e3091d989f02636b8399c97865754cb` |
| `VECTORS.BIN` | `5d2a20761c9b38ef9b2ef6b35ed94953c50a1ad00494b5128568066ea923d5e9` |
| `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` |
| `runner_pmu_qual.elf` | `2eba134593d5481141b651d5867c19554100c7357051aa2a87544f35b5875eb6` |
| `runner_pmu_qual.map` | `8449fb6278f33c749a3614d98e145e49425a9e50dfe5a92ff7c7a4015423e7f2` |
| `pmu_qual_manifest.json` | `e2c1ebe0c140bb144032351dd81ddfd031e527ec37ad859663cef05cdad72f33` |

### 두 모드 공통 (등가성 증거)

| 항목 | SHA-256 | 의미 |
|---|---|---|
| `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` | NPU command stream 불변 |
| vendor object `u85.o` | `cf0e816e161186f6d25750d340867afb1a268f2ef949b97212c3c8b7964fead2` | 벤더 드라이버 **byte-identical** |
| vendor source `u85.c` | `bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf` | 동결값과 일치 |
| callsite disassembly | `b3afd9963258a899ee3ee318f608cb86782c141d20a4197262fc4d58fffd06e3` | callsite 코드 **동일** |

---

## 4. Callsite / relocation / release 증거

두 manifest 모두 아래 값을 **동일하게** 기록한다.

| manifest 필드 | 값 | 16진 |
|---|---|---|
| `caller_symbol` | `test_u85` | — |
| `object_section` | `.text.test_u85` | — |
| `stop_store_address` | 822085508 | `0x31000784` |
| `target_call_address` | 822085512 | `0x31000788` |
| `expected_return_address` | 822085516 | `0x3100078C` |
| `release_store_address` | 822085518 | `0x3100078E` |
| `release_immediate_address` | 822085516 | `0x3100078C` |
| `release_immediate_value` | 12 (`0xC`) | — |
| `object_target_call_offset` | 400 | — |
| `object_target_literal_offset` | 584 | — |
| `object_target_string_offset` | 396 | — |
| `object_target_string_section` | `.rodata.test_u85.str1.4` | — |
| `object_target_relocation_symbol` | `printf` | — |
| `object_target_relocation_type` | `R_ARM_THM_CALL` | — |
| `printf_relocations` | 12 | — |
| `puts_relocations` | **0** | — |
| `test_cpm` | 1 | — |
| `schema_version` | 8 | — |

읽는 법:

- terminal release는 `release_immediate_value = 12`(`0xC`)를 `release_store_address`에
  저장하는 **벤더 코드 자신**이다. runner는 그 자리를 읽기만 한다.
- `puts_relocations = 0`이 중요하다. `-fno-builtin-printf`가 살아 있어
  컴파일러가 `printf`를 `puts`로 치환하지 않았다는 뜻이고, 이것이 곧
  `R_ARM_THM_CALL against printf`가 **실제 후킹 대상**임을 보증한다.
- `expected_return_address`가 Q0/Q1에서 **같다**(`0x3100078C`). 이는 두 이미지의
  callsite가 같은 자리에 있다는 사실 진술일 뿐이다.
  **동일성 자체는 절대 gate가 아니다** — gate는 언제나
  "record의 관측 LR == **자기 모드의** manifest 값"이다
  (`hook_callsite_lr_matches_manifest`). collector는 요청 모드의 manifest를
  **필수 인자**로 받으므로 호출자가 자기 표본을 자기 승인할 수 없다.

### 순서가 있는(ordered) hook 증거 — Q1 manifest 전용

`hook_order_sha256 = 0539a5b438ba7c824bb2a49b3c7af8822e94216f0c251abb22469c8c06babb75`

**이 digest는 숫자 주소를 해시하지 않는다.** 해시 입력은 두 부분이다:

1. **순서가 확정된 attested term 이름들** (`wrapper_call`,
   `internal_pre_release_cycle_read`, 각 `pre_release_*_address`,
   `pmu_disable`, `dsb`, `pmcr_readback`,
   `internal_post_disable_capture`, `snapshot_valid_latch`,
   `latch_is_final`, `return`) — 이름만 순서대로,
2. 구분자 `--` 다음에 오는 **주소 정규화된(address-normalized) hook 명령어
   슬라이스** — hook 진입부터 **validity latch까지 포함**한 구간.

이름만 해시하면 서로 다른 명령어 스트림이 같은 term을 만족한다는 이유로 같은
digest를 낼 수 있다. 그래서 명령어 본문이 함께 들어간다. 반대로 주소를
정규화하기 때문에 **같은 소스를 다시 링크해도 digest는 안정적**이다.

아래 표의 **숫자 주소는 digest의 입력이 아니다.** 게이트가 순서가 확정된
주소 필드로 **따로 방출(emit)하고 따로 검증**하는 값이며, manifest에 그대로
실린다. 반환 문법/주소(`return`) 역시 digest가 아니라 **별도의 gate term**
(`check_latch_is_last` / `check_hook_call_sequence`)이 판정한다.

Q0 manifest에는 hook 주소도 `hook_order_sha256`도 **존재하지 않는다**
(hook 자체가 없다).

| # | manifest 필드 | 값 | 16진 |
|---|---|---|---|
| 1 | `hook_address` | 822087732 | `0x31001034` |
| 2 | `hook_internal_pre_release_cycle_read_address` | 822087762 | `0x31001052` |
| 3 | `hook_pre_release_pmcr_address` | 822087778 | `0x31001062` |
| 4 | `hook_pre_release_pmcntenset_address` | 822087790 | `0x3100106E` |
| 5 | `hook_pre_release_pmccntr_cfg_address` | 822087802 | `0x3100107A` |
| 6 | `hook_pre_release_pmovsset_address` | 822087814 | `0x31001086` |
| 7 | `hook_pmu_disable_address` | 822087820 | `0x3100108C` |
| 8 | `hook_dsb_address` | 822087824 | `0x31001090` |
| 9 | `hook_pmcr_readback_address` | 822087832 | `0x31001098` |
| 10 | `hook_internal_post_disable_capture_address` | 822087842 | `0x310010A2` |
| 11 | `hook_snapshot_valid_latch_address` | 822087878 | `0x310010C6` |
| 12 | `hook_return_address` | 822087880 | `0x310010C8` |
| — | `hook_wrapper_call_address` | 822092046 | `0x3100210E` |

읽는 법:

- 5번 `hook_pre_release_pmccntr_cfg_address`는 **CFG를 읽는** 자리다.
  **쓰기가 아니다.** CFG write 0건은 `check_diag_case.py`가 전처리 TU에서
  강제하고, record 쪽에서는 `cfg_write_performed == 0` /
  `pre.pmccntr_cfg == 0` / `internal.pmccntr_cfg == 0` 세 term이 다시 확인한다.
- disable(7) → `DSB`(8) → readback(9) 순서가 봉인되어 있으므로, "disable을
  했다"는 주장은 **readback으로만** 증명된다
  (`pmu_disable_acknowledged`: `PMCR.cnt_en`이 0으로 읽힘).
- 권위 있는 캡처는 2번(`internal_pre_release`)이다. 10번
  (`internal_post_disable_capture`)과 반환 후 관측은 방증이다.

---

## 5. 수집 / 분석 명령

### 수집 (collector)

```sh
python3 run_pmu_qual.py \
    --mode <Q0|Q1> \
    --bins-dir <실제 배포에 쓴 build dir> \
    --manifest <그 모드의 pmu_qual_manifest.json> \
    --host-boot-index <N> \
    --out results/pmu_qual_<mode>_boot<N>.json \
    [--port <serial port>]
```

`run_pmu_qual.py`가 하는 일 (순서 고정):

1. **포트를 열기 전에** manifest를 읽고 모드 일치를 확인한다.
2. **포트를 열기 전에** `--bins-dir`의 `APP/VECTORS/DDR.BIN`을 manifest
   `artifact_sha256`와 대조한다. 잘못된 이미지를 나중에 구제할 방법은 없으므로
   전부 여기서 끝낸다.
3. ping → prime(dummy model/input으로 상태기계 진입) → PMU_QUAL 실행 →
   record 수신 → **재독(re-read)으로 latch 일치 확인**.
4. `verify_record_identity()` — record ↔ manifest ↔ 모드 불일치 시
   **JSON을 쓰지 않고 실패**한다.
5. 통과한 경우에만 `--out` JSON을 기록한다.

`--host-boot-index`는 **모든 REBOOT마다 1씩 단조 증가**시킨다. 모드와 무관하다.

### 분석 (analyzer)

```sh
python3 analyze_pmu_qual.py \
    --q0 results/pmu_qual_Q0_boot<N>.json \
    --q1 results/pmu_qual_Q1_boot<M>.json
```

- `--q0`, `--q1` 중 **최소 하나**는 필수. 둘 다 주면 등가성 리포트
  (`report_equivalence`)가 추가로 나온다.
- 출력 섹션: identity/callsite attestation → start boundary → raw PMU snapshots
  → hook evidence → inference outputs → (양쪽 제공 시) equivalence.
- 마지막 줄에 `QUALIFICATION ONLY -- no production go, no performance baseline.`
  문구가 반드시 있어야 한다.

### raw record가 반드시 담아야 하는 것

schema v8 record: magic + `schema_version = 8`, `header_words = 8`,
base 40 워드(v7 prefix, slot-for-slot 보존) + hook 13 워드 +
snapshot 4개 × 8워드 = 총 93워드 / 372바이트. payload CRC 필수.

4개 snapshot은 순서대로 `pre`, `internal_pre_release`,
`internal_post_disable`, `after_return`이다.

수집 JSON에 반드시 들어가야 하는 필드:

- **identity**: `qualification_mode`, `build_id`, `run_sequence`, `run_rc`,
  `valid_flags`, `nc_control_id`, `diag_case`
- **manifest 결속**: `manifest_path`, `manifest_sha256`,
  `expected_return_address`, `callsite_disassembly_sha256`,
  `vendor_source_sha256`, `vendor_object_sha256`,
  (Q1) `hook_order_sha256`
- **배포 산출물**: 실제 배포한 `APP/VECTORS/DDR.BIN`의 `artifact_sha256`
- **start boundary**: `start_sequence_id`, `power_guard_cycles`,
  `reset_guard_cycles`, `npu_cmd_after_power_request`,
  `npu_status_after_power_request`, `pmcr_after_program`,
  `armed_after_program`, `program_stable`, `program_stability_reads`
- **CFG 계약**: `cfg_write_performed`, 각 snapshot의 `pmccntr_cfg`
- **hook 증거**: `hook_armed`, `hook_arm_consumed`, `hook_detected_count`,
  `hook_fired_count`, `hook_snapshot_valid`, `hook_callsite_lr_observed`,
  `npu_cmd_at_hook`, `hook_entry_timestamp`, `hook_exit_timestamp`,
  `hook_pmu_mmio_read_count`, `hook_pmu_mmio_write_count`,
  `pmcr_disable_readback_at_hook`
- **비간섭 증거**: `pmu_mmio_read_count_delta`, `pmu_mmio_write_count_delta`
- **release 방증**: `npu_cmd_after_return`
- **추론 산출물**: `golden_window_base/len/crc`
- **derived**: `terms`, `invalid_reasons`, `raw_delta_diagnostic`,
  `reset_to_zero`, `valid`, `npu_pmu_window_cycles`

---

## 6. 실행 계획 — 독립 boot ≥ 3, boot 내 반복

**독립 full REBOOT 최소 3회**를 각 모드에 대해 확보한다. 같은 boot에서 모드를
바꿔 돌린 표본은 서로 독립이 아니다.

```
Q1 → boot N     : build_pmu_qual_q1 배포 → REBOOT → run_pmu_qual.py --mode Q1
Q1 → boot N+1   : (재배포 불필요, 같은 이미지) REBOOT → run_pmu_qual.py --mode Q1
Q1 → boot N+2   : REBOOT → run_pmu_qual.py --mode Q1
Q0 → boot N+3   : build_pmu_qual_q0 배포 → REBOOT → run_pmu_qual.py --mode Q0
Q0 → boot N+4   : REBOOT → run_pmu_qual.py --mode Q0
Q0 → boot N+5   : REBOOT → run_pmu_qual.py --mode Q0
```

- **boot 간 반복(≥3)**: power/reset 경로에 따른 재현성을 본다.
- **boot 내 반복**: 각 boot에서 collector를 **연속 3회 이상** 실행해
  같은 boot 안에서의 안정성을 본다. `--out` 파일명에 반복 인덱스를 넣고,
  `--host-boot-index`는 **바꾸지 않는다** (REBOOT가 없었으므로).
- `hook_fired_count`는 boot 내 반복에서도 **매 record마다 정확히 1**이어야 한다.
  누적되면 arm/consume 회계가 깨진 것이다.
- boot 내 반복 사이에 `npu_pmu_window_cycles`가 크게 흔들리면 그것 자체가
  결론이다. **분산을 평균으로 덮지 않는다.**

---

## 7. Fail-closed 판정 — STOP / GO

`runner_proto.classify_pmu_qual(res, expected_manifest)`의 term 전체 AND가
`valid`다.
**하나라도 거짓이면 `npu_pmu_window_cycles`는 `None`이고, 그 표본은 STOP이다.**
실패한 이름은 `invalid_reasons`에 정렬되어 남는다.

### identity

| term | 통과 조건 |
|---|---|
| `manifest_schema_matches` | manifest `schema_version == 8` |
| `manifest_mode_matches` | record 모드 == manifest 모드 |
| `manifest_build_id_matches` | record `build_id` == manifest build id |
| `mode_is_hprintf` | 모드가 **Q1** |
| `build_id_is_hprintf` | `build_id == 0x31485150` |
| `is_normal_build` | `nc_control_id == 0` (negative control 아님) |
| `is_case_a` | `diag_case == 1` |

> `mode_is_hprintf` / `build_id_is_hprintf` 때문에 **Q0 record는 구조적으로
> `valid`가 될 수 없다.** 이는 결함이 아니라 §1의 계약이다 — Q0는 성능 표본이
> 아니다. Q0는 등가성 리포트에서만 의미를 갖는다.

### hook

| term | 통과 조건 |
|---|---|
| `hook_armed` | `== 1` |
| `hook_arm_consumed` | `== 1` |
| `hook_detected_once` | `hook_detected_count == 1` |
| `hook_fired_once` | `hook_fired_count == 1` (0회도 2회도 실패) |
| `hook_snapshot_valid` | `== 1` |
| `hook_callsite_lr_matches_manifest` | 관측 LR == **자기 모드** manifest `expected_return_address` |
| `npu_power_held_at_hook` | `npu_cmd_at_hook == 0` — **정확히 0**. release 비트만 없는 게 아니라 어떤 비트도 서 있으면 안 된다 |

### 비간섭 (contamination)

| term | 통과 조건 |
|---|---|
| `hook_mmio_reads_within_window` | `pmu_mmio_read_count_delta >= hook_pmu_mmio_read_count` |
| `hook_mmio_writes_within_window` | `pmu_mmio_write_count_delta >= hook_pmu_mmio_write_count` |

hook의 PMU 접근은 측정 창 **내부**에서 일어나므로 hook-local 카운트는 전체
델타의 **부분집합**이고, 등호가 정당한 경계다(창 안의 유일한 PMU 트래픽이
hook 자신이었던 경우). 전체가 부분집합보다 작으면 두 카운터가 같은 접근을
세고 있지 않았다는 뜻이라 오염 증거 자체가 무의미해진다.

### start boundary

`start_sequence_ok`, `power_hold_ok`, `reset_guard_complete`,
`armed_after_program`, `global_after_program`, `program_stable`.

### CFG 무기록 계약

`cfg_no_write`, `cfg_pre_zero`, `cfg_internal_zero`.

### snapshot

`pre_armed`, `pre_global_enable`, `pre_read_stable`,
`internal_armed`, `internal_global_enable`, `internal_read_stable`,
`no_overflow`, `positive_delta`.

`positive_delta`는 `raw_delta > 0` **이면서** `reset_to_zero`가 아닐 것을 요구한다.
전원/리셋 경로가 카운터를 지우면 `(0 - pre) mod 2^48`이 거대한 양수로 읽히므로,
쌍의 **모양**으로만 진짜 진행과 구별된다.

### disable / release

`pmu_disable_acknowledged` (`PMCR.cnt_en` readback이 0),
`vendor_release_after_return` (`npu_cmd_after_return & 0xC == 0xC`).

### 추론

`golden_window_ok`, `run_rc_ok`, `required_flags_ok`.

### STOP / GO 규칙

- **GO**: 계획된 모든 독립 boot(≥3)와 boot 내 반복에서 **Q1 record가 전부
  `valid == True`**이고, `hook_fired_count`가 매번 정확히 1이며,
  **Q0/Q1 functional equivalence 리포트가 전체 `PASS`**여야 한다.
  → 여기서 요구되는 것은 `both_released_after_return` 하나가 아니라
  **`functional_equivalence`의 모든 term**이다 (`equivalence: PASS`).
  그 term 집합이 덮는 범위:
  - **각자 자기 manifest 기준 LR** — `q0_lr_matches_own_manifest`,
    `q1_lr_matches_own_manifest`. 두 모드는 별개 링크이므로 숫자 주소가
    달라도 되고, **어떤 term도 두 숫자를 서로 비교하지 않는다.**
  - **동일 vendor source/object** — `same_vendor_source`,
    `same_vendor_object`, `same_caller_symbol`, `same_test_cpm`
  - **주소 정규화된 callsite shape 동일** —
    `same_normalized_callsite_shape`, `same_release_immediate`,
    `q0_release_follows_return`, `q1_release_follows_return`
  - **기능/golden/출력 결과** — `same_golden_window`,
    `golden_window_is_the_pinned_one`, `same_output_crc`, `both_run_rc_ok`
  - **required flags** — `both_required_flags_ok`
  - **hook detect/fire 계약** — `both_detected_once`,
    `both_armed_and_consumed`, `q0_never_fired`, `q1_fired_once`
  - **이미지 계열 동일성** — `both_case_a`, `both_normal_build`,
    `both_no_cfg_write`, `both_start_boundary`
  - **벤더 release 방증** — `both_released_after_return`
  - **독립 boot** — `independent_boots` (Q0와 Q1의 `host_boot_index`가 달라야
    한다. 같은 boot에서 모은 쌍은 등가성 근거가 될 수 없다.)
  → 그래도 이것은 **자격심사 통과**일 뿐이다. production go가 아니다.
- **STOP**: 위 중 **하나라도** 어긋나면 즉시 중단한다. 재실행으로 덮지 않고,
  `invalid_reasons`를 그대로 보고한다.
- 표본을 버리거나 "재시도해서 좋은 것만 채택"하는 행위를 금지한다.

#### 두 종류의 실패를 혼동하지 말 것

collector는 **표본을 받아들이기 전에 거부하는 실패**와 **타깃이 만들어낸
well-formed 무효 표본**을 다르게 취급한다. 전자는 아카이브할 표본 자체가 없고,
후자는 반드시 아카이브된다.

**(a) 하드 admission 실패 — JSON이 아예 기록되지 않는다**

`run_pmu_qual.py`는 아래를 **JSON을 쓰기 전에** 거부한다. 따라서 "무효 표본"이
남지 않고, 애초에 **표본이 존재하지 않는다**:

- manifest ↔ record의 **모드 / `build_id` / schema 불일치**
- 관측 callsite LR이 그 모드 manifest의 `expected_return_address`와 불일치
- **negative-control 이미지**(`nc_control_id != 0`)로 수집 시도
- `--bins-dir`의 배포 BIN 해시가 manifest `artifact_sha256`와 불일치
  (포트를 열기도 전에 실패)
- **transport 계층 실패**: payload CRC 불일치, magic/schema/header 워드 이상,
  재독(re-read) latch 불일치

이것들은 "무효 표본"이 아니라 **잘못된 이미지·잘못된 인자·전송 고장**이다.
원인을 고쳐 다시 수집해야 하며, 실행 로그에 실패 사실과 사유를 남긴다.
이 경우 아카이브할 수집 JSON은 **존재하지 않는다** — 없는 파일을 찾지 말 것.

**(b) 타깃이 만들어낸 well-formed 무효 표본 — 반드시 아카이브한다**

record 자체는 정상적으로 수신·검증되었고 identity도 일치하지만 validity term이
실패한 경우다. 예: `golden_window_ok` 불일치, `no_overflow` 실패,
`positive_delta` 실패(0 이하이거나 `reset_to_zero`), `hook_fired_once` 실패,
`pmu_disable_acknowledged` 실패, `npu_power_held_at_hook` 실패.

- 이 표본은 **JSON으로 기록된다**. `valid == False`, `npu_pmu_window_cycles`는
  `None`, `invalid_reasons`에 실패한 term 이름이 남는다.
- **버리지 않는다.** 아카이브하고 **INVALID로 보고한다.** 재시도로 덮어쓰거나
  유효 표본만 골라 남기는 것을 금지한다.
- 이런 표본은 그 자체가 결과다 — 타깃이 계약을 만족하지 못했다는 증거다.

---

## 8. 백업 / 배포 / 복구 절차 (**전 사이클 1회 완주 — 2026-08-09**)

> **현재 진행 상태 (2026-08-09): 0~10단계 전부 실제로 수행되었다.**
> 백업 → Q1 배포 → 독립 boot 3회 × boot 내 3회 수집 → Q0 배포 → 동일 수집 →
> Q0/Q1 등가성 판정 → 원본 복구 → USB_OFF까지 한 사이클을 완주했다.
> 마운트는 `udisksctl`이 Polkit/remote-TTY로 거부된 뒤 operator의 명시적 승인
> 아래 **2-EXC** 경로로 획득했다.
>
> **이 완주가 판정한 것과 판정하지 않은 것을 혼동하지 말 것:**
> H-PRINTF schema v8은 **관측 가능성(observability)과 기능적 비간섭
> (functional non-interference)** 을 통과했다. **안정성(stability)과 성능
> baseline은 자격심사되지 않았다** — §9의 cycle 산포를 볼 것.
> 이 절차는 여전히 **qualification 전용**이며 production go가 아니다.
> Production `END_ONLY`는 **계속 동결**이고 schema v8은 반영되지 않았다.
>
> **evidence root:** `/home/gihwan/mps4/PMU_QUAL_V8_20260809T114306Z`
>
> **배포 무결성 (source ≡ destination, 각 목록의 SHA-256):**
>
> | 이미지 | 목록 SHA-256 | APP.BIN |
> |---|---|---|
> | Q1 | `4671073b4ecc9fc508576ec0384c90b8d8f9cf62678b19624e706bc39e2cfb1e` | `dc66915a…754cb` |
> | Q0 | `25887564637bc54bba57d48e5ee59ceb2bcc6270e4bc3ff91076b4e4937dab51` | `727563fd…e111d` |
>
> **백업 = 복구의 유일한 기준값** (`<EV>/board-backup/current`):
>
> | 파일 | SHA-256 | 크기 |
> |---|---|---|
> | `APP.BIN` | `ffa3e5bd0363f791d61f9673074c625865f1e6a8f24e53ee303372c64ef3597d` | 16496 |
> | `VECTORS.BIN` | `45e943c577e3744104d53cf57c7d0afb369ff68a99e5e6906971d71503f06c92` | 592 |
> | `DDR.BIN` | `81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98` | 47344 |
>
> `backup.sha256`은 맨 파일명 형식이며 백업 디렉터리 안에서 `sha256sum -c`가
> rc=0으로 통과한다. `APP`/`VECTORS`는 Q0·Q1 이미지와 **다르고**(= 진짜 이전
> 보드 상태), `DDR`은 Q0·Q1과 **같다**(NPU command stream 불변).
>
> **복구 완료 증거:** `RESTORE_DESTINATION.sha256`의 세 digest가 위 백업 값과
> **정확히 일치**하며 목록 SHA-256은
> `0d1fe942f9ea2c64e4c5752ed544767e0aeb4c71a5e2f818ea3d64f6c5f3f790`이다.
> 복구 후 REBOOT는 DDR self-test PASSED=True · CPUWAIT cleared=True,
> PING은 `state=1`(IDLE)에 **에러 카운터 7종 전부 0**
> (`rx_overrun`/`bad_magic`/`bad_version`/`bad_crc`/`length_error`/
> `sequence_error`/`parser_resync`), 마지막으로 MCC `USB_OFF`를 발행해
> `/dev/sdb` 없음 · findmnt 비어 있음 · 임시 마운트 지점 없음 · UART 4포트 free
> 상태로 종료했다.
>
> 전체 기록: 같은 evidence root의 `PREBOARD_STAGING.txt`,
> `BOARD_BACKUP_V2.txt`, `Q1_RUNTIME_QUAL.txt`, `Q0_RUNTIME_QUAL.txt`,
> `logs/equivalence_*`(요약 SHA-256
> `4722fb61c68754812ef691b894416c70a39dc4927ac50a607541405323ebae4b`).
> **자격증명은 이 문서에도 증거 트리에도 기록하지 않는다** — 승인 사실만 남긴다.

SD 접근은 **경계가 정해진(bounded) 순서**를 따른다. 범용
`sudo mount /dev/sdb1 /mnt`를 쓰지 않는다 — 마운트 지점을 가정하지 않고,
루트 권한을 요구하지 않으며, 실패 시 보드를 매달린 상태로 두지 않기 위해서다.

```
FAILCLEAN (실패 시 정리 순서 — 어떤 단계에서 실패하든 반드시 이 순서)

   f1. sync                              # 안전한 경우에만. 쓰기 자체가 실패해
                                         #   마운트가 이미 불건전하면 건너뛴다.
   f2. unmount — **반드시 USB_OFF보다 먼저.**
       **어떤 경로로 마운트했는지에 따라 갈린다. 두 경로를 절대 섞지 않는다.**

         (A) 2단계 `udisksctl mount`로 획득한 경우:
               udisksctl unmount -b /dev/sdb1

         (B) 2-EXC bounded sudo mount로 획득한 경우:
               sync                                    # = f1
               sudo umount "$MP"                       # 기록해 둔 **정확한**
                                                       #   mktemp 마운트 지점
               findmnt | grep -E "sdb|$MP"             # 비어 있어야 한다
               rmdir "$MP"                             # 임시 지점 제거

         교차 사용 금지: `udisksctl`로 마운트한 것을 `sudo umount`하거나,
         `sudo mount`한 것을 `udisksctl unmount`로 내리려 하지 않는다. 전자는
         udisks2의 기록과 실제 상태를 어긋나게 하고, 후자는 udisks2가 모르는
         마운트라 실패하거나 엉뚱한 대상을 건드린다. 마운트를 획득한 순간
         **어느 경로였는지와 마운트 지점을 반드시 기록**해 두고, 해제할 때
         그 기록만 따른다.

         - 성공  → f3으로 간다.
         - 실패(마운트된 상태로 남음) → **USB_OFF를 발행하지 않는다.**
           거기서 멈추고 보고한다. 이후는 **operator 복구 영역**이다.
           (B)에서 `rmdir`만 실패한 경우는 마운트가 이미 해제된 것이므로
           unmount 실패가 아니다 — 빈 디렉터리 잔여물로 보고하고 f3은 허용된다.
   f3. MCC USB_OFF
         **허용 조건은 둘뿐이다**: (i) f2 unmount가 **성공**했거나,
         (ii) 애초에 **마운트에 성공한 적이 없다**(마운트 실패 등).
         그 외에는 USB_OFF를 치지 않는다.
   f4. 중단하고 보고한다.

   **마운트된 상태에서 USB_OFF로 바로 가지 않는다.** 호스트가 아직 파일시스템을
   잡고 있는데 보드가 USB를 내려버리면 미기록 데이터와 SD 상태를 잃는다.
   실패 경로에서 f2를 건너뛰는 지름길은 존재하지 않는다.
   (마운트에 성공한 적이 없다면 f1·f2는 해당 없음 — f3만 수행한다.)

   요약하면 **USB_OFF는 "마운트되어 있지 않음"이 확인된 뒤에만** 허용된다.
   unmount가 실패했는데 USB_OFF를 치는 것은 이 절차에서 가장 위험한 동작이다.

0. 소유권 확인   UART/SD를 지금 이 세션이 단독으로 잡고 있는지 확인한다.
                 다른 세션·프로세스가 포트나 블록 디바이스를 쥐고 있으면
                 중단한다. 소유권이 불명확한 상태에서 USB_ON 금지.

1. USB_ON        MCC 콘솔로 USB_ON. 호스트에 블록 디바이스가 올라오는지 확인.

2. 마운트        udisksctl mount -b /dev/sdb1
                 - 사용자 마운트를 **우선**한다. sudo가 아니다.
                 - udisksctl이 출력한 **실제 마운트 지점을 그대로 사용**한다
                   (예: /media/<user>/<label>). /mnt로 가정하지 않는다.
                 - 이후 모든 경로는 이 반환된 MOUNT를 기준으로 쓴다.

2-EXC. 예외 경로 — bounded sudo mount (**자격심사 한정, 기본 경로 아님**)

     이 예외는 **udisksctl을 대체하지 않는다.** 2단계가 여전히 기본이며,
     아래 두 조건이 **모두 실제로 관측·기록**된 경우에만 예외가 열린다:

       (E1) `udisksctl mount -b /dev/sdb1`을 실제로 시도해
            **Polkit/remote-TTY 실패를 관측**했다. 예:
              GDBus.Error:org.freedesktop.UDisks2.Error.NotAuthorizedCanObtain
              Error creating textual authentication agent ... /dev/tty
            (원격 SSH 세션은 loginctl Remote=yes이고 controlling TTY가 없어
             udisks2의 allow_active 무암호 경로가 적용되지 않는다.)
       (E2) **operator의 명시적 승인**이 있고, 그 승인 사실을 증거 파일에
            기록했다.

     추측으로 예외를 여는 것을 금지한다. E1을 **시도해 보지도 않고** 예외로
     건너뛰면 안 된다.

     예외가 열렸을 때의 규칙 (하나라도 못 지키면 중단):

       a. **고유한 mktemp 마운트 지점**을 만든다. `/mnt`도, 고정 경로도,
          기존 디렉터리 재사용도 **금지**:
            MP=$(mktemp -d /tmp/pmu_qual_sd.XXXXXXXX)
          비어 있는 새 디렉터리여야 한다.

       b. 마운트 **직전에 /dev/sdb1의 정체를 검증**한다. 장치 이름만 믿지
          않는다 — 모델/라벨/FSTYPE/크기가 기대와 일치해야 한다:
            lsblk -n -o NAME,SIZE,FSTYPE,LABEL,MODEL,TRAN /dev/sdb
          기대: MPS4 mass storage, vfat, LABEL=M1SDP, ~7.4G, TRAN=usb.
          하나라도 어긋나면 **마운트하지 않는다**(다른 디스크일 수 있다).

       c. 소유권 옵션을 주어 정확히 그 장치만 마운트한다:
            sudo mount -t vfat /dev/sdb1 "$MP" \
                -o uid=$(id -u),gid=$(id -g),umask=022
          장치·마운트 지점 모두 **변수 없이 실제 값으로 확인**한 뒤 실행한다.

       d. **비밀번호를 절대 출력·기록·저장하지 않는다.** 로그, 증거 파일,
          커밋, 히스토리, 환경변수, 파일 어디에도 남기지 않는다. 승인 사실만
          기록하고 자격증명 자체는 기록하지 않는다. 자격증명을 코드/문서/
          설정에서 **탐색하지도 않는다.**

       e. 작업이 끝나면 **정확히 그 마운트 지점을** 해제한다:
            sync
            sudo umount "$MP"
            findmnt | grep -E "sdb|$MP"   # 비어 있어야 한다
            rmdir "$MP"
          **umount이 실패하면 USB_OFF를 발행하지 않는다.** FAILCLEAN f2/f3
          경계가 그대로 적용된다 — 멈추고 operator 복구를 요청한다.

     이 예외는 마운트 획득 방법만 바꾼다. 백업·해시·검증·배포·복구의
     **fail-closed 규칙은 하나도 완화되지 않는다.**

3. 증거 디렉터리 첫 덮어쓰기 **이전에** 타임스탬프가 붙은 호스트 백업/증거
                 디렉터리를 만든다:
                   BK=board-backup/$(date -u +%Y%m%dT%H%M%SZ)
                   mkdir -p "$BK"
                 **이번 실행에서는 이미 완료되었다.** 타임스탬프는 evidence
                 root 이름이 갖고 있고 백업은 그 아래 고정 이름으로 있다:
                   BK=/home/gihwan/mps4/PMU_QUAL_V8_20260809T114306Z/board-backup/current
                 이후 §8의 "$BK"는 **이 경로**를 가리킨다. 새로 만들지 않는다.

4. 백업 + 해시   cp "$MOUNT"/SOFTWARE/{APP,VECTORS,DDR}.BIN "$BK"/
                 ( cd "$BK" && sha256sum APP.BIN VECTORS.BIN DDR.BIN \
                       > backup.sha256 )
                 cat "$BK"/backup.sha256
                 **반드시 "$BK" 안에서 생성한다.** backup.sha256은 경로 없이
                 **맨 파일명**(APP.BIN / VECTORS.BIN / DDR.BIN)만 기록해야
                 하며, 그래야 나중에 "$BK"에서 `sha256sum -c`가 그대로
                 통한다. `sha256sum "$BK"/...`로 만들면 경로가 박혀서
                 복구 시 검증이 실패한다.
                 이 값이 복구 검증의 유일한 기준값이다.

5. 배포          cp build_pmu_qual_<q0|q1>/{APP,VECTORS,DDR}.BIN "$MOUNT"/SOFTWARE/
                 sha256sum build_pmu_qual_<q0|q1>/{APP,VECTORS,DDR}.BIN   # source
                 sha256sum "$MOUNT"/SOFTWARE/{APP,VECTORS,DDR}.BIN        # destination
                 source·destination·§3 표 **세 값이 모두 정확히 일치**해야 한다.
                 하나라도 어긋나면 배포를 계속하지 말고 **FAILCLEAN**을 수행한다
                 (f1 sync → **f2 unmount는 2단계/2-EXC 중 실제 획득 경로에 맞는
                 쪽으로** → unmount 성공 시에만 USB_OFF → 보고.
                 unmount가 실패하면 USB_OFF 없이 멈추고 operator 복구 요청).
                 **7단계로 건너뛰지 않는다** — 그것은 마운트된 채 USB_OFF를
                 치는 것이고, 여기서 금지된 동작이다.

6. sync → unmount  sync
                   그 다음은 **2단계에서 어느 경로로 마운트했는지에 따라
                   갈린다. 섞지 않는다** (FAILCLEAN f2와 동일한 분기):

                     (A) 2단계 `udisksctl mount`였다면:
                           udisksctl unmount -b /dev/sdb1

                     (B) 2-EXC bounded sudo mount였다면:
                           sudo umount "$MP"            # 기록된 정확한 지점
                           findmnt | grep -E "sdb|$MP"  # 비어 있어야 한다
                           rmdir "$MP"

                   unmount가 **실패하면 7단계로 가지 않는다** — 멈추고 보고하며
                   operator 복구를 요청한다.

7. cleanup       MCC USB_OFF. 앞 단계들의 성공·실패와 무관하게 **반드시**
                 도달해야 하는 단계지만, **6단계 unmount가 성공한 뒤에만**
                 (또는 마운트에 성공한 적이 없을 때만) 발행한다.
                 마운트된 채로는 USB_OFF를 치지 않는다.

8. MCC REBOOT    (DDR self-test PASS · CPUWAIT 해제 확인)

9. 수집          python3 run_pmu_qual.py --mode <Q0|Q1> --bins-dir <배포 dir> \
                     --manifest <그 모드 manifest> --host-boot-index <N> \
                     --out results/pmu_qual_<mode>_boot<N>.json
                 host_boot_index += 1

10. 복구         **새 백업을 만들지 않는다.** 0~4단계를 반복하지 말 것 —
                 기준값은 이미 "$BK"/backup.sha256이다. 아래 순서를 그대로 밟는다:

                 10.1  MCC USB_ON
                 10.2  마운트 — 2단계와 **같은 우선순위·같은 규칙**을 따른다.
                       (A) 기본: udisksctl mount -b /dev/sdb1
                           → 이번에 반환된 MOUNT를 사용한다 (이전 값 재사용 금지)
                       (B) 예외: 이번에도 `udisksctl mount`가 **Polkit/remote-TTY
                           실패로 실제 거부되고**, 이미 기록된 operator 승인이
                           유효하면 **2-EXC**를 쓸 수 있다. 승인은 재사용 가능해도
                           **E1(실제 관측된 실패)은 이번 시도에서 다시 성립해야
                           한다** — 지난번에 실패했으니 이번에도 그럴 것이라고
                           가정하고 곧바로 sudo로 가지 않는다.
                           2-EXC의 규칙은 하나도 완화되지 않는다: 고유 mktemp
                           지점(/mnt 금지), 마운트 직전 /dev/sdb1 정체 검증
                           (model/label/FSTYPE/size/TRAN), uid/gid/umask 옵션,
                           그리고 **자격증명 탐색·출력·저장 금지**.
                       어느 경로를 썼는지와 마운트 지점을 **기록**한다 —
                       10.6이 그 기록에 따라 갈린다.
                 10.3  cp "$BK"/{APP,VECTORS,DDR}.BIN "$MOUNT"/SOFTWARE/
                 10.4  검증 — 두 단계로 나눠서 한다.

                       (a) 백업본 자신이 온전한지 먼저 확인한다. backup.sha256이
                           맨 파일명만 담고 있으므로 "$BK" 안에서 실행한다.
                           **`|| echo`로 끝내지 않는다** — 그러면 명령 자체는
                           성공(0)으로 끝나서 실패가 사라진다:
                             verify_backup() {
                                 if ( cd "$BK" && sha256sum -c backup.sha256 ); then
                                     return 0
                                 fi
                                 echo "BACKUP CORRUPT"
                                 return 1
                             }

                             verify_backup
                             rc=$?
                           여기서 실패하면(`rc != 0`) 기준값 자체를 믿을 수 없다.
                           **복구를 계속하지 말고 FAILCLEAN**을 수행한다
                           (sync(안전할 때만) → unmount → [unmount 성공 시에만]
                           USB_OFF → 보고). 10.7로 건너뛰면 마운트된 채 USB_OFF가
                           되므로 금지한다.

                       (b) 목적지 SOFTWARE의 각 파일 digest를 backup.sha256의
                           대응 기대값과 하나씩 비교한다. **echo만 하고 끝내지
                           않는다 — 스니펫 자체가 0이 아닌 상태로 끝난다:**
                             verify_dest() {
                                 rc=0
                                 for f in APP.BIN VECTORS.BIN DDR.BIN; do
                                     exp=$(awk -v f="$f" '$2==f {print $1}' \
                                             "$BK"/backup.sha256)
                                     got=$(sha256sum "$MOUNT"/SOFTWARE/"$f" \
                                             | cut -d' ' -f1)
                                     if [ -z "$exp" ]; then
                                         echo "NO-EXPECTED-HASH $f"; rc=1
                                     elif [ -z "$got" ]; then
                                         echo "UNREADABLE $f"; rc=1
                                     elif [ "$exp" != "$got" ]; then
                                         echo "MISMATCH $f exp=$exp got=$got"
                                         rc=1
                                     fi
                                 done
                                 [ "$rc" -eq 0 ] || echo "RESTORE VERIFY FAILED"
                                 return "$rc"
                             }

                             verify_dest
                             rc=$?
                           `return "$rc"`가 핵심이다. `[ "$rc" -eq 0 ] || echo`로
                           끝내면 스니펫이 **성공으로 끝나서** 실패가 호출자에게
                           전달되지 않는다.
                           파일명·크기·타임스탬프가 아니라 **내용**으로
                           판정한다. 기대 digest가 **없는 경우**(`NO-EXPECTED-HASH`)도
                           읽을 수 없는 경우도 **불일치와 똑같이 실패**다 —
                           fail-closed다.

                       **`rc != 0`이면 10.5~10.8로 진행하지 말고 FAILCLEAN을
                       수행한다**: sync(안전할 때만) → **f2 unmount를 10.2에서
                       기록한 획득 경로에 맞춰**(A: `udisksctl unmount -b
                       /dev/sdb1` / B: `sudo umount "$MP"` → findmnt 확인 →
                       `rmdir "$MP"`) → **unmount가 성공한 경우에만** MCC
                       USB_OFF → 중단하고 보고. unmount가 실패하면 USB_OFF 없이
                       멈추고 operator 복구를 요청한다.
                       검증이 실패해도 cleanup 자체는 **반드시** 수행하며,
                       **순서를 지킨다.** 단 USB_OFF는 unmount 성공 이후에만이다.
                       보드를 마운트된 채로 두지 않는다.
                 10.5  sync
                 10.6  unmount — **10.2에서 기록한 획득 경로에 따라 갈린다.
                       섞지 않는다** (FAILCLEAN f2 / 6단계와 동일한 분기):
                         (A) 10.2가 udisksctl mount였다면:
                               udisksctl unmount -b /dev/sdb1
                         (B) 10.2가 2-EXC sudo mount였다면:
                               sudo umount "$MP"            # 기록된 정확한 지점
                               findmnt | grep -E "sdb|$MP"  # 비어 있어야 한다
                               rmdir "$MP"
                       **unmount 실패 시 10.7로 가지 않는다** — USB_OFF 없이
                       멈추고 operator 복구를 요청한다.
                 10.7  MCC USB_OFF — **10.6 unmount가 성공한 뒤에만**
                       (또는 10.2에서 마운트에 성공한 적이 없을 때만).
                 10.8  MCC REBOOT — 원상 복귀를 확인한다.
```

**권한 실패 시 규칙**: `udisksctl`이 권한/Polkit 오류로 실패하면 **거기서
멈춘다.** 자격증명을 탐색하거나, 임의로 sudo로 우회하거나, polkit 규칙을
수정하거나, 다른 마운트 경로를 시도하지 **않는다.**

멈춘 뒤 열릴 수 있는 경로는 **2-EXC(bounded sudo mount) 하나뿐**이며, 그것도
**operator의 명시적 승인이 선행**되어야 한다. 승인이 없으면 이 문단의 금지가
그대로 유효하다 — 승인은 worker가 스스로 부여할 수 없다. 승인이 있더라도
자격증명 **탐색 금지**는 해제되지 않는다: 자격증명은 operator가 그 시점에
직접 제공하는 것이지, worker가 찾아내는 것이 아니다.

그 다음 동작은 **어느 쪽이 실패했는지에 따라 갈린다** — 무조건 USB_OFF가
아니다:

- **`udisksctl mount`가 실패한 경우** (마운트된 적 없음): 파일시스템을 잡고
  있는 것이 없으므로 **USB_OFF로 되돌리고** 보고한다. FAILCLEAN의 (ii) 조건.
- **unmount가 실패한 경우** (`udisksctl unmount`든 2-EXC의 `sudo umount`든,
  마운트된 채로 남음):
  **USB_OFF를 발행하지 않는다.** 그대로 멈추고 보고하며, **operator 복구가
  필요하다.** 마운트된 상태에서 USB를 내리면 미기록 데이터와 SD 상태를 잃는다.
  권한 오류라는 이유로 이 경계를 넘지 않는다.

복구는 선택이 아니다. 자격심사 이미지는 production 이미지가 아니므로 보드를
그 상태로 두면 안 된다.

---

## 9. 현재까지의 검증 상태

### 검증 수준: 구문 + 단위 + 정적(ELF/객체/전처리 TU) 게이트
### + **실보드 통합 1회 완주** + **Q1 고정 이미지 30표본 특성화**

**실제 실행한 것 — 실보드 투입 전 컨테이너/호스트 검증**:

- Q0/Q1 **clean build 각 2회** — 모드 내 **byte-identical** 확인.
- `check_pmu_qual.py` ELF 게이트: **123/123 통과**.
- host 단위 테스트 v8 (실제 산출물 사용): **283/283 통과**.
- host 단위 테스트 v7: **159/159 통과**.
- legacy 스위트: **18 / 9 / 16 / 17 통과**.
- v7 S1/S2/S3 및 A/B/C + NC 매트릭스 **재현 확인**.
- 동결 production 값과 provenance **정확히 재현** — Production `END_ONLY`는
  **동결 상태 유지**.

**실제 실행한 것 — 실보드 (2026-08-09, 전 사이클 완주)**:

- Q0/Q1 산출물 staging: mode당 119파일 경로+내용 **byte-identical**
  (Q0 rollup `8ebfdfe2…`, Q1 rollup `7bdfb58d…`).
- 덮어쓰기 이전 read-only 백업 + `sha256sum -c` rc=0 (§8 표).
- **독립 full REBOOT 6회** (boot 13·14·15 = Q1, boot 16·17·18 = Q0).
  6회 전부 DDR self-test PASSED=True · CPUWAIT cleared=True.
  boot마다 `run_sequence`가 1부터 재시작 → 실제 fresh boot임이 독립 확인됨.
- **Q1 9/9 유효** (boot당 3회 반복). 38개 term 전부 true, `derived.valid=True`,
  `invalid_reasons` 없음. LR `0x3100078C`가 자기 manifest와 일치,
  `npu_cmd_at_hook=0x0`, CFG write 0, disable readback `0x00004000`,
  `npu_cmd_after_return=0x0000000C`, raw reread identity true.
- **Q0 9/9 detect-only 계약 충족**: 30 term true + **정확히 8개**의 예상된 false
  (`mode_is_hprintf`, `build_id_is_hprintf`, `hook_fired_once`,
  `hook_snapshot_valid`, `internal_armed`, `internal_global_enable`,
  `internal_read_stable`, `positive_delta`).
  `hook_detected_count=1`, `hook_fired_count=0`, `hook_snapshot_valid=0`,
  **`npu_pmu_window_cycles` 미발행(None)**.
  Q0 record가 `derived.valid=False`인 것은 **계약이지 실패가 아니다** —
  `classify_pmu_qual`은 `mode_is_hprintf`를 요구하므로 Q0는 구조적으로
  valid가 될 수 없다.
- **Q0/Q1 functional equivalence: 공식 analyzer로 9쌍 전부 PASS (rc=0)**,
  검사 항목 **225/225 ok**, FAIL 0건. 요약 SHA-256
  `4722fb61c68754812ef691b894416c70a39dc4927ac50a607541405323ebae4b`.
- **복구 완료**: `RESTORE_DESTINATION.sha256` 3개 digest가 백업과 정확히 일치
  (목록 SHA-256 `0d1fe942…f790`), 복구 REBOOT DDR/CPUWAIT True,
  PING `state=1`(IDLE) + 에러 카운터 7종 전부 0, 최종 MCC `USB_OFF`.
- 종료 상태: `/dev/sdb` 없음, findmnt 비어 있음, 임시 마운트 지점 없음,
  UART 4포트 모두 free.

**`npu_pmu_window_cycles` (counter window — `T_npu` 아님, 성능 baseline 아님)**:

```
boot13  3207, 5034, 3207
boot14  3207, 3288, 5388
boot15  8241, 4848, 5511
전체    min 3207   max 8241   max/min = 2.57배
```

**이 산포가 결론의 경계다.** 9/9가 유효하다는 것은 seam이 **관측 가능하고
기능적으로 비간섭적**이라는 뜻이지, cycle 값이 안정적이라는 뜻이 **아니다**.
평균 내지 말고, `T_npu`나 latency로 부르지 말고, 성능 baseline으로 쓰지 말 것.

**Gate 1 — Q1 고정 이미지 stability characterization 완료**
(`PMU_STABILITY_V8_20260809T130131Z`):

- byte-exact Q1을 바꾸지 않고 boot 19·20·21에서 각 10회, 총 **30/30 유효**.
  매 표본 38 term 전부 true, raw reread identity와 artifact/manifest identity 유지.
- 전체 `min=3207`, `max=7885`, `median=3300`, `MAD=93`, inclusive
  `Q1=3207`, `Q3=5603.25`, `IQR=2396.25`, sample `CV=0.378709`.
  boot median은 `3207 / 3811.5 / 4047.5`, `3207`이 정확히 `15/30`이다.
- `pre_cycle48=10592`가 30회 전부 동일하고 internal cycle만 16개 값으로 변했다.
  기존 timestamp를 독립 재계산하면
  `cycles = u32(hook_entry_timestamp - t_call_enter) + 514`가 **30/30 정확히
  성립**한다. hook body span은 41, post-hook tail span은 47이므로 산포는
  `call-enter → internal pre-release hook` 구간에 국소화된다.
- 이는 **어디에서 변동이 유입되는지**를 좁힌 결과다. 원인 메커니즘이나 NPU
  arithmetic 성능을 규명한 것이 아니며 stable cycle figure도 만들지 않는다.
- 수집 뒤 원본 BIN 3개를 목록 SHA `0d1fe942…f790`로 복구했고, 복구 reboot
  DDR/CPUWAIT True, PING IDLE + 오류 7종 0, 최종 unmounted·USB_OFF·UART free.

따라서 Gate 1은 **완료**지만 `stability qualification`과 performance baseline은
여전히 **NOT QUALIFIED**다. H-PRINTF는 observability mechanism으로 qualified일
뿐 production mechanism으로 결정되지 않았다.

**여전히 실행하지 않은 것 / 판정되지 않은 것**:

- **안정성·성능 baseline 미자격**: 30표본 characterization은 완료했지만
  `3207` hard floor + singleton excursion 구조와 call-enter→hook 산포의 원인·
  state dependency는 아직 설명되지 않았다.
- **Production `END_ONLY` 미자격 · 동결 유지** — schema v8은 반영하지 않았다.
- `PMCCNTR_CFG` 누락의 **zero-cause 가설은 A/B/C 보드 증거로 반증(falsified)**
  되었으나, **timing semantics는 여전히 미해결**이다. 이전에 관측된 **약 33%
  CFG semantic delta**는 설명되지 않은 채 남아 있다.
- **S3 seam은 diagnostic 전용**이다 — private driver provenance를 만들므로
  production 후보가 아니다.
- 성능 수치 인용 일체 금지 — 이 문서의 cycle 값은 자격심사 산출물이다.

### 남은 작업

1. Gate 1의 hard floor/excursion 구조를 설명할 상태·경계 가설을 세우되 현재
   30표본을 성능 baseline으로 승격하지 않는다.
2. v8 pre-release seam, `TEST_CPM=1`, driver, workload, PMU ordering을 고정하고
   **CFG만 단일 변수**로 바꾸는 A/B/C 실험을 새로 수행한다
   (A=no-write, B=generated START=CYCLE/STOP=NO_EVENT, C=explicit zero).
3. 결과가 설명된 뒤 최종 seam을 결정하고, 그 뒤에만 Production `END_ONLY`
   승격 여부를 **별도로** 판단한다.

1회 완주는 seam이 **작동하고 방해하지 않는다**는 것까지만 보증한다.
