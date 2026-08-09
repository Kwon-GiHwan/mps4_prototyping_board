# RUNNER_V1_PMU qualification H-PRINTF schema v8 설계

Date: 2026-08-09  
Status: Approved for design and implementation planning  
Scope: diagnostic/qualification only; Production END_ONLY remains frozen

## 1. 결정

첫 internal pre-release seam qualification candidate는 **H-PRINTF**로 구현한다.
공식 `Drivers/u85_driver/u85.c`를 수정하거나 복사하지 않고, `TEST_CPM=1` 빌드가
terminal release 직전에 실행하는 기존 `printf("Testing CPM signals\n")` callsite를
링커 `--wrap=printf` 경로에서 식별해 다음 순서를 실행한다.

```text
NPU command completion
  -> vendor CMD=0 stop
  -> unique vendor printf callsite
  -> internal PRE-RELEASE PMU snapshot
  -> PMU disable + readback
  -> vendor CMD=0xC terminal release (unchanged)
  -> test_u85() return
  -> after-return corroboration snapshot
```

H-PRINTF는 qualification 전용이다. 이 설계나 결과만으로
`firmware/Selftest_pmu/runner_pmu_main.c`, `firmware/Makefile.pmu`, 공식 vendor
driver 또는 Production END_ONLY를 수정하거나 qualification 완료로 승격하지 않는다.

## 2. 현재 증거와 해석

RUNNER_V1_PMU_DIAG schema v7의 S1/S2/S3는 모두 동일한 PRE 상태를 세웠다.

```text
PMCR.cnt_en = 1
PMCNTEN cycle bit = 1
PMCCNTR_CFG = 0x11
```

S1(reference release)과 S2(return 뒤 re-hold)는 POST PMU state를 잃었고,
S3(`TEST_CPM=0`)만 보존했다. 반환 뒤 re-hold는 이미 늦으므로 authoritative POST는
vendor terminal release보다 앞에 있어야 한다.

이 결과의 상태표는 다음과 같다.

```text
PMCCNTR_CFG wiring missing            CONFIRMED STATIC FACT
PMCCNTR_CFG required for progress     FALSE for tested FI101 path
PMCCNTR_CFG omission as zero-cause    FALSIFIED
NPU power-lifecycle integration       ROOT CAUSE CONFIRMED for DIAG path
Required measurement seam             INTERNAL PRE-RELEASE
Stability qualification               PENDING
Production END_ONLY                   FROZEN / NOT QUALIFIED
```

`PMCCNTR_CFG=0x11`은 v7 power-seam 비교의 통제 변수였으며 production fix가 아니다.
Schema v8 qualification candidate는 PMCCNTR_CFG에 쓰지 않는다. CFG timing semantics와
v6의 약 33% delta 차이는 별도 후속 연구 항목으로 남긴다.

외부 Linux Ethos-U perfmon patch는 FI101 실보드 증거를 대체하지 않는 corroboration이다.
최초 v1 게시일은 2026-03-06이고 v4는 2026-06-01이다.

- v1: https://www.spinics.net/lists/kernel/msg6082968.html
- v4: https://lkml.iu.edu/2606.0/01625.html

## 3. 후보 비교

### H-PRINTF — 채택

기존 reference driver와 `TEST_CPM=1`, `CMD=0xC` sequence를 그대로 링크한다.
Runner의 기존 printf wrapper만 target callsite에서 hook side effect를 수행한다.

장점:

- vendor source와 driver object provenance를 보존한다.
- terminal release의 원래 명령과 순서를 제거하지 않는다.
- DebugMonitor/DWT 예외를 추가하지 않는다.
- baseline과 candidate에서 동일한 vendor driver object를 비교할 수 있다.

위험:

- 문자열, printf lowering, linker wrapping, inlining/LTO 구성에 민감하다.
- 숨은 callsite 의존성이므로 source-string 검사만으로는 부족하다.

대응:

- 최종 ELF caller/callsite와 release-store 상대 순서를 fail-closed gate로 고정한다.
- 런타임 return address를 raw record에 싣고 build manifest의 expected callsite와 비교한다.
- builtin/puts/LTO 변형은 gate가 증명하지 못하면 빌드를 실패시킨다.

### H-COPY — 이번 candidate에서 사용하지 않음

Reference source의 controlled copy에 명시적 hook call 한 줄을 삽입하는 방식이다.
Callsite는 명확하지만 private driver provenance가 생기며, official/frozen 비교 원칙에
대한 예외가 필요하다.

### H-DWT — 기각

`CMD=0xC` write를 DWT watchpoint/DebugMonitor로 trap하는 방식이다. 예외 진입과 debug
unit 의존성이 측정 window를 교란하므로 qualification candidate에 사용하지 않는다.

## 4. 소스와 빌드 격리

Schema v8은 별도 qualification identity와 build directory를 사용한다. 구현은 기존
schema v7 진단 인프라를 재사용할 수 있지만 다음 경계가 보장되어야 한다.

- Production files, frozen linker scripts, frozen provenance directories: diff 0.
- Vendor `Drivers/u85_driver/u85.c`: source hash 불변.
- Baseline과 H-PRINTF candidate의 vendor `u85.o`: byte-identical.
- H-PRINTF 전용 build ID와 schema version 8.
- Baseline build는 같은 schema/runner 기능을 사용하되 target hook side effect를 비활성화한다.
- Baseline의 `hook_fired=0`은 성능 sample로는 의도적으로 invalid이다. 기능 동등성 비교에만 쓴다.
- Candidate의 `hook_fired=1`만 qualification 대상이다.

새 candidate의 산출물과 manifest는 v7 evidence/archive를 덮어쓰지 않는다.

## 5. 최종 ELF callsite 계약

현재 reference object에서 release tail은 다음 의미 순서를 가진다.

```text
str 0, [NPU_REG_CMD]            ; vendor STOP
bl  printf                      ; "Testing CPM signals\n"
mov  release_value, #12
str release_value, [NPU_REG_CMD]; vendor terminal release
```

절대 주소는 build마다 달라질 수 있으므로 계약은 주소 상수가 아니라 구조와 추출된
callsite identity로 정의한다.

Build gate는 최종 ELF와 link에 사용된 vendor object에서 아래를 모두 증명한다.

1. `TEST_CPM`은 1이다.
2. vendor source의 terminal `CMD=0xC` write는 정확히 1개다.
3. Final ELF에서 literal-pool load를 따라 첫 번째 인자를 복원했을 때 target 전체 문자열을
   전달하는 printf callsite는 measured path에 정확히 1개다. Raw string byte sequence의
   출현 횟수를 세는 게이트가 아니다.
4. vendor object에서 target call은 `printf` relocation이며 `puts`/builtin으로 변환되지 않았다.
5. 최종 ELF에서 해당 call은 `__wrap_printf`로 resolve된다.
6. Caller는 vendor `test_u85`의 inlined `test_commands` release tail이다.
7. Target `bl`이 반환한 지점부터 vendor `CMD=0xC` store까지의 **caller 명령
   스트림**에는 다른 NPU CMD store 또는 외부 call이 없다. Hook 내부의 선언된 PMU/NPU
   MMIO는 이 조항의 대상이 아니며 hook MMIO count로 별도 집계한다.
8. STOP -> target call -> immediate 12 -> release store 구조가 정확히 1회다.
9. Build flags는 `-fno-builtin-printf`를 포함하고 LTO를 활성화하지 않는다.
10. 어느 항목이든 증명할 수 없으면 ELF를 배포 가능 산출물로 만들지 않는다.

Gate는 expected normalized return address(Thumb bit 제거), caller symbol/range, release-store
address, relevant disassembly digest를 machine-readable build manifest에 기록한다.

## 6. Wrapper 활성화 계약

H-PRINTF hook은 문자열 일치만으로 유효해지지 않는다. Target format은 익명 rodata라
주소가 build마다 달라질 수 있으므로 pointer identity가 아니라 **전체 문자열 내용**으로
매칭한다. Runner matcher는 target 전체 문자열 literal의 두 번째 사본을 만들지 않고 개별
byte/character 비교를 사용한다. Wrapper는 최소한 다음 상태에서만 qualification hook을 실행한다.

```text
qualification build identity is H-PRINTF
AND measurement_active == 1
AND pre_release_hook_armed == 1
AND target full-format content matches
```

Wrapper와 hook은 `noinline`이며 최종 ELF에 심볼이 생존해야 한다. Gate는 wrapper가
인라인되거나 symbol/call boundary를 증명하지 못하면 실패한다.

Wrapper는 `__builtin_return_address(0)`의 normalized 값을 record에 저장한다. Firmware가
스스로 기대 주소를 하드코딩하지 않는다. Host는 bins manifest에서 추출한 expected return
address와 raw record의 observed address를 비교하며 불일치는 invalid-sample이다.

`pre_release_hook_armed`는 NPU submit 직전에 1로 설정하고 target 검출 시 원자적으로
소비한다. Record의 `hook_armed`는 submit 전 arm 설정 사실, `hook_arm_consumed`는 target
검출이 이를 소비한 사실을 뜻한다. Hook 재진입은 side effect를 실행하지 않고 count만
증가시킨다. 따라서 0회나 2회 이상 모두 실패로 남는다.

Q0 baseline도 target 전체 문자열과 LR을 검출해 `hook_detected_count=1`과 observed LR을
기록하지만 PMU snapshot/disable side effect는 실행하지 않고 `hook_fired_count=0`을 남긴다.
Q1만 동일 검출 경로 뒤에서 side effect를 실행한다. 이 분리는 Q0/Q1이 같은 target detection
path를 통과했음을 증명하면서 Q0를 performance sample로 오인하지 않게 한다.

Target 이외의 printf call은 H-PRINTF 도입 전 wrapper semantics를 그대로 따른다.

- clean profile: 기존처럼 suppression/counting을 수행한다.
- wrapped profile을 진단용으로 만들 경우: 기존처럼 real implementation으로 전달한다.

즉 target 검사 실패가 다른 printf의 출력·억제 동작을 바꾸지 않는다. Hook 내부에서는 printf,
puts, serial print, UART write 또는 다른 wrapped logging 함수를 호출하지 않는다.

## 7. Start boundary

Schema v7에서 실보드 검증된 start boundary를 유지한다.

```text
entry CMD read
-> CMD=0 hold
-> DSB/ISB
-> bounded power guard (65536)
-> CMD/STATUS validation
-> PMU disable
-> overflow/enable/interrupt clear
-> atomic PMCR reset launch
-> DSB/ISB
-> bounded reset guard (65536)
-> PMCR guard readback
-> exact PMCR global-enable write
-> no PMCCNTR_CFG write
-> cycle arm
-> arm/global readback
-> spaced stability reads
-> PRE snapshot
```

Reset self-clear bit의 즉시 readback을 completion proof로 재도입하지 않는다. Guard와 final
program stability가 precondition이다.

Schema v8의 CFG 계약은 v7과 다르며 다음으로 고정한다.

```text
cfg_write_performed == 0
PRE.PMCCNTR_CFG == 0
internal_pre_release.PMCCNTR_CFG == PRE.PMCCNTR_CFG == 0
```

v7의 `cfg_programmed`, `cfg_write_path_ok`, `cfg_programmed_pre`는 v8 validity에 상속하거나
재사용하지 않는다. 특히 `cfg_programmed_pre = (pre == cfg_write_value)`는 v8에서 `0 == 0`
항등이 되어 아무것도 증명하지 않으므로 금지한다.

## 8. Internal hook data flow

Hook은 release 전에 아래만 수행한다.

```text
record hook entry timestamp and observed return address
record NPU CMD before release (must be 0)
capture internal PRE-RELEASE snapshot, cycle first
disable PMU
DSB
read PMCR disable acknowledgement
capture internal post-disable snapshot/corroboration
record hook exit timestamp
```

그 후 wrapper는 기존 clean suppression/counting path로 돌아가며 vendor code가 기존
`CMD=0xC`를 실행한다. `test_u85()` 반환 뒤 runner는 NPU CMD와 PMU state를 다시 읽는다.
After-return state는 release가 실제로 일어났고 PMU bank를 wipe했다는 보조 증거일 뿐이며
성능 계산에 사용하지 않는다.

PMU disable write와 acknowledgement는 hook 안에서 정확히 한 번만 수행한다. 반환 후 runner는
PMU disable을 다시 쓰지 않고 read-only after-return corroboration만 수집한다. 이 규칙으로
measurement-window PMU MMIO count와 release 뒤 관측의 의미를 고정한다.

Authoritative delta:

```text
npu_pmu_window_cycles =
    internal_pre_release.cycle - pre.cycle  (48-bit modulo, only after validity)
```

Reset-to-zero modulo delta는 progress가 아니다. Internal snapshot이 armed/global/CFG contract를
잃었거나 cycle이 pre보다 0으로 reset된 모양이면 usable delta를 발행하지 않는다.

Schema v8의 authoritative state pair는 `(pre, internal_pre_release)`뿐이다. V7의
`(pre, post)` 기반 `armed`, `global_enable`, `raw_delta`, `progress_observed`,
`seam_post_held` 로직을 v8 validity에 상속하지 않는다. `after_return`의 PMCR/arm/CFG/cycle은
release 효과를 보여주는 corroboration이며, 값이 wipe되는 것이 정상이고 성능 validity에서
제외한다.

## 9. Schema v8 raw evidence

Schema v8 raw evidence field mapping:

기존 40-word prefix의 `npu_cmd_after_power_release` 슬롯은 schema v8에서
`npu_cmd_after_return` 의미로 사용한다. 따라서 아래 hook append 영역은 정확히 13 words다.
기존 seam 필드는 layout 호환을 위해 유지하며 `power_seam_id=4`,
`power_rehold_performed=0`, `rehold_guard_cycles=0`, `npu_cmd_after_seam`과
`npu_status_after_seam`은 after-return corroboration으로 정의한다.

```text
qualification_mode                 baseline | hprintf
hook_armed
hook_arm_consumed
hook_detected_count
hook_fired_count
hook_snapshot_valid
hook_callsite_lr_observed
hook_entry_timestamp
hook_exit_timestamp
npu_cmd_at_hook
pmcr_disable_readback_at_hook
hook_pmu_mmio_read_count
hook_pmu_mmio_write_count
internal_pre_release snapshot
internal_post_disable snapshot
after_return snapshot
npu_cmd_after_return                existing prefix slot mapping
```

기존 identity, start-boundary, exact golden window, output/result-region CRC, run status,
MMIO counts와 payload CRC/reread evidence는 유지한다. Parser는 schema v1-v7을 performance
sample로 재사용하지 않고 명시적으로 거부한다. Collection-time parser/source는 evidence에
복사해 보존한다.

성능 필드는 `npu_pmu_window_cycles` 하나만 제공한다. Raw counter와 diagnostic fields는
증거로 보존하지만 `T_npu`, latency 또는 performance baseline으로 이름 붙이지 않는다.

## 10. Fail-closed validity

아래 조건을 모두 만족해야만 `npu_pmu_window_cycles`가 유효하다.

```text
correct schema/build/profile identity
reference vendor driver hash/object identity valid
final ELF callsite manifest valid
hook_armed == 1
hook_arm_consumed == 1
hook_detected_count == 1
hook_fired_count == 1
hook_snapshot_valid == 1
observed callsite LR == manifest expected LR
npu_cmd_at_hook == 0
start boundary hold/reset/program/stability valid
cfg_write_performed == 0
PRE CFG == internal PRE-RELEASE CFG == 0
PRE armed/global/cycle-read stable/no-overflow
internal PRE-RELEASE armed/global/cycle-read stable/no-overflow
PMU disable acknowledgement valid
vendor release observed after return (CMD bits 3:2 == 0xC)
run_rc == 0 and required inference flags valid
exact golden window base/len/CRC == 0x90020CC0/0x100/0x27084C4C
output CRC consistency valid
positive non-reset delta
MMIO/logging contamination gates valid
```

하나라도 실패하면 sample은 `invalid-sample`이며 usable performance value는 `None`/미발행이다.
Raw evidence 자체는 원인 분석을 위해 그대로 archive한다.

## 11. Baseline 동등성

같은 toolchain, flags, linker inputs, reference driver object를 사용하는 두 이미지를 만든다.

- Q0: H-PRINTF hook disabled baseline. Performance invalid by design.
- Q1: H-PRINTF hook enabled qualification candidate.

비교 기준:

- vendor source hash와 vendor object hash 동일.
- DDR.BIN official hash 유지.
- NPU register programming/submission path가 target hook side effect 외 동일.
- Q0/Q1 모두 run success, exact golden window CRC, output CRC 동일.
- Q1 final ELF만 target wrapper hook side effect를 갖는다.
- Q0/Q1 모두 같은 logical vendor callsite를 정확히 1회 검출한다. 두 ELF의 numeric address는
  달라도 되며, 각 observed LR은 **자기 mode manifest의** expected LR과만 비교한다.
- Q0는 `hook_detected_count=1`, `hook_fired_count=0`; Q1은 둘 다 1이다.
- Q0/Q1 disassembly diff는 declared runner/wrapper/ABI paths로 제한한다.
- 다른 printf callsites의 wrapper behavior는 동일하다.

Q0의 after-return wipe는 예상되지만 performance zero로 해석하지 않는다.

## 12. Build and negative gates

필수 로컬/컨테이너 검증:

1. Python syntax/unit tests and legacy host suites.
2. ABI field count/payload CRC/parser truncation and old-schema rejection.
3. Final ELF unique caller/callsite/release-order gate.
4. Vendor source/object identity gate.
5. `TEST_CPM=1` and terminal release exactly-once gate.
6. No PMCCNTR_CFG write gate.
7. No LTO, `-fno-builtin-printf`, no puts folding gate.
8. Golden window linker-map gate.
9. Measurement-path logging/UART denylist gate.
10. Production/frozen/provenance diff 0.
11. Clean deterministic rebuild and complete hashes.
12. Shared source의 compile-time 격리를 증명하기 위해 schema-v7 S1/S2/S3 기록 해시를
    재현하고 A/B/C+NC4 build/check를 다시 통과한다.

Negative tests must prove rejection of:

- missing target string/callsite;
- duplicate target callsite;
- caller outside expected vendor function;
- callsite LR mismatch;
- printf -> puts/builtin conversion;
- LTO or inlining that erases/proves a different callsite;
- release before hook or extra NPU CMD store between hook and release;
- hook fired 0 or 2+ times;
- target detected 0 or 2+ times;
- hook recursion/logging use;
- wrong golden CRC/base/len;
- unstable read, overflow, arm/global loss, reset-to-zero, non-positive delta;
- Q0 sample being presented as performance-valid.

## 13. Board qualification gates

Local/container gates가 모두 통과하고 별도 deployment 승인을 받은 뒤에만 보드를 사용한다.

최소 qualification:

```text
independent full boot >= 3
  x consecutive runs per boot
```

모든 Q1 run에서 다음을 요구한다.

```text
PRE valid
internal PRE-RELEASE valid
hook exactly once and callsite match
disable acknowledgement valid
vendor release restored
cycle stable, no overflow, positive delta
golden window CRC 0x27084C4C
output CRC stable
measurement-window PMU MMIO count invariant
no UART/logging contamination
```

Root-cause mechanism은 confirmed 상태를 유지하되, 이 반복을 통과하기 전 stability와
production measurement는 qualified가 아니다. Schema v8의 값은 qualification evidence이며
30-run baseline이나 논문 성능 데이터가 아니다.

## 14. 역할과 검증 순서

1. Claude: 이 문서 기준으로 schema v8 qualification implementation을 수행한다.
2. Claude: local/container gates와 hashes를 보고하고 board는 건드리지 않는다.
3. Codex: 변경 파일을 독립 열람하고 final ELF disassembly, raw ABI/unit negatives,
   golden contract, Q0/Q1 equivalence, production/frozen diff를 재검증한다.
4. 설계 불일치가 있으면 Claude에 구체적인 수정 task를 다시 보낸다.
5. 모든 pre-board gate가 통과한 뒤에만 board deployment/run을 별도 단계로 진행한다.

## 15. Stop/go

Pre-board GO 조건:

- Final ELF의 유일한 release 직전 callsite가 machine-checkable하게 고정됨.
- Q1 hook ordering이 disassembly로 증명됨.
- Q0/Q1 기능/golden/NPU path 동등성 gate 통과.
- Fail-closed unit/negative tests 통과.
- Production/frozen/provenance diff 0.

그 전에는 board, Production END_ONLY, 30-run baseline, MLEK performance measurement로
이동하지 않는다.
