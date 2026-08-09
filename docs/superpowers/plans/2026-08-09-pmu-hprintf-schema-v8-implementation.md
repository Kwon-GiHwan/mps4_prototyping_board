# PMU H-PRINTF Schema v8 Qualification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and pre-board qualify a schema-v8 H-PRINTF image that captures and disables the Ethos-U85 PMU at the unique reference-driver callsite immediately before vendor `CMD=0xC`, without modifying Production END_ONLY or the vendor driver.

**Architecture:** Extend the diagnostic runner behind a schema-v8 compile-time boundary, but give the qualification milestone its own Q0/Q1 Makefile, build identities, ELF gate, manifest, host parser, collector, analyzer, tests, and procedure. Q0 and Q1 link the same byte-identical `TEST_CPM=1` vendor object; both detect and attest the target callsite, while only Q1 snapshots/disables the PMU. Final-ELF structure plus runtime LR/raw state form a two-layer fail-closed proof.

**Tech Stack:** C11/CMSIS on Cortex-M85, GNU Arm Embedded toolchain, GNU ld `--wrap`, Python 3 standard library, existing UART runner protocol, Docker container `benchmark-runner`, Orca-supervised Claude implementation and Codex verification.

---

Implementation must stay in the current worktree because the schema-v7 firmware/host foundation is presently uncommitted and is not available from `HEAD` in a fresh worktree. Claude owns implementation edits; Codex owns independent verification. No board/SD/reboot and no Production/frozen/provenance modification in this plan. Implementation commits are deferred until Codex verifies the complete pre-board candidate so the existing dirty v7 work is not accidentally captured in partial commits.

Design authority: `docs/superpowers/specs/2026-08-09-pmu-hprintf-schema-v8-design.md`.

## File map

**Create**

- `firmware/Makefile.pmu_qual` — isolated Q0/Q1 build graph and identities.
- `firmware/Selftest_pmu_diag/check_pmu_qual.py` — final-ELF/object/source/map gate and manifest generator.
- `firmware/Selftest_pmu_diag/test_check_pmu_qual.py` — positive/negative unit fixtures for the gate.
- `firmware/Selftest_pmu_diag/PMU_QUAL_FROZEN_BASELINE.sha256` — pre-task frozen/vendor/provenance hash roots.
- `firmware/Selftest_pmu_diag/PMU_QUAL_PROCEDURE.md` — build, pre-board, deployment, and stop/go procedure.
- `host/run_pmu_qual.py` — schema-v8 collector with bins-manifest attestation and reread.
- `host/analyze_pmu_qual.py` — Q0/Q1 evidence report and qualification verdict.
- `host/tests/test_pmu_qual_unit.py` — schema-v8 ABI/classification/analyzer/manifest negative tests.

**Modify**

- `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c` — compile-time-isolated schema-v8 record, H-PRINTF detector/hook, authoritative snapshots, serialization.
- `host/runner_proto.py` — schema-v8 dataclass/parser/classifier; retain schema-v7 APIs for archived evidence.
- `firmware/Selftest_pmu_diag/PMU_DIAG_PROCEDURE.md` — one pointer stating v7 root-cause mission is complete and v8 qualification has a separate procedure.
- `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md` — update only after verified pre-board results.
- `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md` — append only after verified pre-board results.

**Must remain byte/diff identical**

- `firmware/Selftest_pmu/runner_pmu_main.c`
- `firmware/Makefile.pmu`
- `firmware/LinkScripts/lnk.ld.S`
- `firmware/LinkScripts/lnk.measure.overlay.ld`
- `provenance/**`
- server/container `Drivers/u85_driver/u85.c`

## Chunk 1: Host contract first

### Task 0: Capture the immutable baseline before implementation

**Files:**

- Create: `firmware/Selftest_pmu_diag/PMU_QUAL_FROZEN_BASELINE.sha256`
- Read only: Production/frozen files, `provenance/**`, server/container vendor driver

- [ ] **Step 1: Mark the baseline record before writing**

```bash
codex-mark-used firmware/Selftest_pmu_diag/PMU_QUAL_FROZEN_BASELINE.sha256
```

- [ ] **Step 2: Read current local immutable hashes**

```bash
sha256sum firmware/Selftest_pmu/runner_pmu_main.c \
  firmware/Makefile.pmu \
  firmware/LinkScripts/lnk.ld.S \
  firmware/LinkScripts/lnk.measure.overlay.ld
find provenance -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
```

Expected: five full digest lines; no writes.

- [ ] **Step 3: Read vendor source hashes from both authoritative copies**

```bash
ssh gihwan 'sha256sum /home/gihwan/mps4/runner/selftest/Drivers/u85_driver/u85.c; \
  docker exec benchmark-runner sha256sum /work/selftest/Drivers/u85_driver/u85.c'
```

Expected: both equal
`bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf`.

- [ ] **Step 4: Create the baseline record with the observed full values**

Use `apply_patch`; do not shell-redirect. Record path, full SHA-256, capture timestamp,
and the provenance tree-root command. This file is Task 5's comparison input.

- [ ] **Step 5: Verify the baseline record**

```bash
git diff --check -- firmware/Selftest_pmu_diag/PMU_QUAL_FROZEN_BASELINE.sha256
```

Expected: clean.

### Task 1: Pin schema-v8 ABI and fail-closed classification with failing tests

**Files:**

- Create: `host/tests/test_pmu_qual_unit.py`
- Modify: `host/runner_proto.py:612-1160`
- Reference: `docs/superpowers/specs/2026-08-09-pmu-hprintf-schema-v8-design.md:266-329`

- [ ] **Step 1: Mark both files before the first write**

Run:

```bash
codex-mark-used host/tests/test_pmu_qual_unit.py
codex-mark-used host/runner_proto.py
```

Expected: both commands exit 0.

- [ ] **Step 2: Write the schema-v8 parsing tests before implementation**

The test must construct a complete 93-word/372-byte payload with:

```python
PMU_QUAL_SCHEMA_VERSION = 8
PMU_QUAL_HEADER_WORDS = 8
PMU_QUAL_BASE_FIELDS = 40
PMU_QUAL_HOOK_FIELDS = 13
PMU_QUAL_SNAPSHOT_WORDS = 8
PMU_QUAL_SNAPSHOT_COUNT = 4
PMU_QUAL_KNOWN_FIELDS = 40 + 13 + 4 * 8  # 85
PMU_QUAL_TOTAL_WORDS = 8 + 85             # 93
PMU_QUAL_PAYLOAD_SIZE = 93 * 4            # 372
```

The 13 appended hook words are fixed in this exact firmware/wire/host order:

```text
1  qualification_mode
2  hook_armed
3  hook_arm_consumed
4  hook_detected_count
5  hook_fired_count
6  hook_snapshot_valid
7  hook_callsite_lr_observed
8  hook_entry_timestamp
9  hook_exit_timestamp
10 npu_cmd_at_hook
11 pmcr_disable_readback_at_hook
12 hook_pmu_mmio_read_count
13 hook_pmu_mmio_write_count
```

`npu_cmd_after_return` is not a 14th appended word. It uses the existing 40-word prefix
slot named `npu_cmd_after_power_release` in v7. Retained seam-prefix meanings are fixed:
`power_seam_id=4`, `power_rehold_performed=0`, `rehold_guard_cycles=0`, and
`npu_cmd_after_seam`/`npu_status_after_seam` are after-return corroboration.

The four snapshots are exactly, after the 13 words:

```text
pre
internal_pre_release
internal_post_disable
after_return
```

Tests must cover parse success, bad magic/schema/length/CRC, body/header schema disagreement, and trailing-word accounting.

- [ ] **Step 3: Run the new test and observe the expected import/constant failure**

Run:

```bash
python3 host/tests/test_pmu_qual_unit.py
```

Expected: non-zero exit because schema-v8 types/functions do not exist yet.

- [ ] **Step 4: Add explicit schema-v8 types without changing schema-v7 APIs**

Add to `host/runner_proto.py`:

```python
PMU_QUAL_SCHEMA_VERSION = 8
PMU_QUAL_MODES = {"Q0": 0, "Q1": 1}
PMU_QUAL_BUILD_IDS = {"Q0": 0x30425150, "Q1": 0x31485150}  # PQB0/PQH1

@dataclass(frozen=True)
class PmuQualResult:
    # Preserve the exact 40-field prefix with the v8 mapping above.
    # Append the numbered 13-word list, then four snapshots.
    ...
```

Implement a new `parse_pmu_qual_payload()` rather than changing
`parse_pmu_diag_payload()`. The v7 parser and its 159-test behavior remain available for archived evidence.

- [ ] **Step 5: Add the authoritative v8 classifier**

Implement a separate `classify_pmu_qual(res, expected_manifest)` that computes only from
`pre` and `internal_pre_release`:

```python
raw_delta = ((internal.cycle - pre.cycle) & ((1 << 48) - 1))
reset_to_zero = pre.cycle != 0 and internal.cycle == 0
positive_delta = raw_delta > 0 and not reset_to_zero
cfg_contract = (
    res.cfg_write_performed == 0
    and pre.pmccntr_cfg == 0
    and internal.pmccntr_cfg == 0
)
hook_identity = (
    res.hook_armed == 1
    and res.hook_arm_consumed == 1
    and res.hook_detected_count == 1
    and res.hook_fired_count == 1
    and res.hook_callsite_lr_observed
        == expected_manifest["expected_return_address"]
)
```

Do not call or reuse v7 `cfg_programmed`, `cfg_write_path_ok`,
`cfg_programmed_pre`, `progress_observed`, or `pmu_diag_seam_post_held`.
Return `npu_pmu_window_cycles=None` unless every design validity term passes.

- [ ] **Step 6: Add focused negative tests**

Tests must independently invalidate:

```text
Q0 presented as valid
hook armed/consumed missing
detected count 0 or 2
fired count 0 or 2
observed LR mismatch
CFG write performed
PRE CFG non-zero
internal CFG drift/non-zero
PRE/internal arm loss
PRE/internal global loss
unstable cycle read
overflow
reset-to-zero modulo artifact
zero/non-positive delta
disable acknowledgement missing
vendor CMD=0xC not observed after return
wrong exact golden base/len/CRC
run_rc/valid_flags failure
```

Add a positive test proving after-return PMU wipe does not invalidate an otherwise valid Q1 sample.

- [ ] **Step 7: Run host tests**

Run:

```bash
python3 host/tests/test_pmu_qual_unit.py
python3 host/tests/test_pmu_diag_unit.py
(cd host/tests && PYTHONPATH=.. python3 test_abi_unit.py)
(cd host/tests && PYTHONPATH=.. python3 test_proto_unit.py)
(cd host/tests && PYTHONPATH=.. python3 test_pmu_abi_unit.py)
```

Expected: new suite 0 failures; existing suites remain 159/159, 18/18, 9/9, 16/16.

- [ ] **Step 8: Record a checkpoint without committing**

Run:

```bash
git diff --check -- host/runner_proto.py host/tests/test_pmu_qual_unit.py
```

Expected: no output and exit 0.

## Chunk 2: Firmware hook and exact ABI

### Task 2: Implement compile-time-isolated schema-v8 firmware behavior

**Files:**

- Modify: `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c:866-1000`
- Modify: `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c:2460-2610`
- Modify: `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c:2610-2960`
- Modify: `firmware/Selftest_pmu_diag/runner_pmu_diag_main.c:3540-3665`
- Test: `host/tests/test_pmu_qual_unit.py`

- [ ] **Step 1: Mark the firmware source before writing**

Run:

```bash
codex-mark-used firmware/Selftest_pmu_diag/runner_pmu_diag_main.c
```

- [ ] **Step 2: Add compile-time identities and mutual-exclusion assertions**

Under `PMU_QUAL_SCHEMA_V8`, require exactly one of:

```c
PMU_QUAL_MODE_Q0
PMU_QUAL_MODE_Q1
```

Both modes must require the reference driver and case-A/no-CFG path. Refuse all S2/S3/private-driver and negative-control macros with `#error`.

- [ ] **Step 3: Add the exact schema-v8 record**

Preserve the current 40-word prefix with Task 1's explicit semantic mapping, append the
numbered 13 hook words in exactly that order, then serialize four snapshots. The numbered
wire list is authoritative; both dataclass and serializer are tested against it. Add
`_Static_assert`s for snapshot words, field count 85, total words 93, and payload size 372.

- [ ] **Step 4: Add non-recursive target matching and arm state**

Implement a local comparator that does not call libc/wrapped functions and does not emit a
second full target literal. Use explicit indexed character constants:

```c
static int pmu_qual_is_target_format(const char *fmt)
{
    return fmt[0] == 'T' && fmt[1] == 'e' /* every remaining byte explicitly */
        && fmt[19] == '\n' && fmt[20] == '\0';
}
```

The gate never counts raw target byte-sequence occurrences. It follows the vendor caller's
literal-pool load and proves the first argument of the unique printf callsite resolves to the
full target bytes; matcher implementation bytes are outside that callsite count.

Add volatile arm/detected/fired state. Arm immediately before `run_fixed_inference()` only in v8. On target detection, record and clear the arm exactly once; repeated matches increment detected count without side effects.

- [ ] **Step 5: Implement the noinline hook**

The noinline hook must not log and must execute:

```text
timestamp + normalized caller LR already captured by wrapper
NPU CMD read (expect 0)
internal_pre_release capture, cycle first
PMU disable exactly once
DSB
PMCR disable readback
internal_post_disable capture
timestamp
hook-local PMU read/write deltas
hook_snapshot_valid latch only at the end
```

The total measured-window PMU counters include hook PMU accesses. The hook-local counters are a reported subset; unit/static checks must require:

```text
total_window_reads >= hook_reads
total_window_writes >= hook_writes
```

- [ ] **Step 6: Modify only the clean `__wrap_printf` qualification branch**

Mark `__wrap_printf` noinline. In Q0/Q1, when measurement is active, armed, and the full target string matches:

```c
observed_lr = ((uint32_t)(uintptr_t)__builtin_return_address(0)) & ~1U;
hook_detected_count++;
hook_arm_consumed = 1U;
pre_release_hook_armed = 0U;
#if defined(PMU_QUAL_MODE_Q1)
    hook_fired_count++;
    pmu_qual_pre_release_hook();
#endif
```

Then execute the same clean suppression/counting behavior as before. Non-target calls must take the exact pre-existing path. Q0 records detection/LR but performs no snapshot/disable.

- [ ] **Step 7: Change v8 post-return handling to reads only**

For Q1, remove the v7 post-return `npu_pmu_disable()` write from the compiled v8 path. After return, read NPU CMD and capture `after_return` PMU state only. V7 behavior under its compile-time branch must remain unchanged.

- [ ] **Step 8: Enforce no PMCCNTR_CFG write in v8**

Compile v8 through the case-A branch and set `cfg_write_performed=0`. Do not add a write of 0 or 0x11. PRE and internal snapshots must still read CFG for the non-vacuous zero/stability contract.

- [ ] **Step 9: Serialize and latch validity only after all evidence exists**

Q1 may mark a result fresh only after hook snapshot, after-return corroboration, exact golden CRC, output CRC, payload length, and record field count are complete. Q0 may return raw evidence but must identify itself as performance-invalid.

- [ ] **Step 10: Preprocess both modes and inspect write counts**

Run in the build container after Task 3 creates the Makefile:

```bash
make -f Makefile.pmu_qual QUAL=Q0 preprocess
make -f Makefile.pmu_qual QUAL=Q1 preprocess
```

Expected: both preprocessed TUs contain zero `PMCCNTR_CFG` writes; Q0 contains no hook PMU disable side effect; Q1 contains exactly one.

## Chunk 3: Build graph, ELF attestation, and negative gates

### Task 3: Create the Q0/Q1 build and manifest gate

**Files:**

- Create: `firmware/Makefile.pmu_qual`
- Create: `firmware/Selftest_pmu_diag/check_pmu_qual.py`
- Create: `firmware/Selftest_pmu_diag/test_check_pmu_qual.py`
- Reference: `firmware/Makefile.pmu_diag`
- Reference: `firmware/Selftest_pmu_diag/check_diag_case.py`

- [ ] **Step 1: Mark new files before writing**

```bash
codex-mark-used firmware/Makefile.pmu_qual
codex-mark-used firmware/Selftest_pmu_diag/check_pmu_qual.py
codex-mark-used firmware/Selftest_pmu_diag/test_check_pmu_qual.py
```

- [ ] **Step 2: Write gate unit fixtures first**

Create synthetic disassembly/object-relocation fixtures for:

```text
one valid STOP -> target bl -> mov #12 -> release store
missing target
duplicate target
wrong caller
target resolves to puts
target resolves to real printf rather than __wrap_printf
extra call between target return and release
extra NPU CMD store between target return and release
release before target
missing noinline wrapper/hook symbol
```

- [ ] **Step 3: Run gate tests and observe failure**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_qual.py
```

Expected: fail because `check_pmu_qual.py` does not exist.

- [ ] **Step 4: Implement Q0/Q1 build identities and isolation**

`Makefile.pmu_qual` must build:

```text
QUAL=Q0 -> build_pmu_qual_q0, BUILD_ID 0x30425150 (PQB0)
QUAL=Q1 -> build_pmu_qual_q1, BUILD_ID 0x31485150 (PQH1)
```

Both use:

```text
reference Drivers/u85_driver/u85.c
TEST_CPM=1
clean wrapper profile
-fno-builtin-printf
no -flto
PMU_DIAG_CASE_A/no CFG write
existing measure + diag golden linker overlays
separate build directories
```

Add targets: `preprocess`, `bins`, `check`, `manifest`, `hashes`, `clean`.

- [ ] **Step 5: Implement source/object/final-ELF gate**

`check_pmu_qual.py` must accept explicit source, object, ELF, map, objdump, nm, and readelf paths. It must fail closed unless it proves all ten design callsite terms and outputs a JSON manifest containing:

The unique-target gate follows `test_u85`'s literal-pool load to reconstruct the first
argument of each printf callsite. It counts callsites whose first argument is the complete
target string, not raw string occurrences in ELF sections. `printf_relocations` is recorded
for provenance but is not required to equal 12; only the target relocation/lowering contract
is a pass/fail term.

```json
{
  "schema_version": 8,
  "qualification_mode": "Q1",
  "build_id": "0x31485150",
  "vendor_source_sha256": "...",
  "vendor_object_sha256": "...",
  "caller_symbol": "test_u85",
  "expected_return_address": 0,
  "release_store_address": 0,
  "callsite_disassembly_sha256": "...",
  "test_cpm": 1,
  "printf_relocations": 12,
  "puts_relocations": 0
}
```

Addresses are extracted after the final link; firmware never imports them.

- [ ] **Step 6: Add compiler-configuration gates**

The Makefile/checker must prove `-fno-builtin-printf` and absence of `-flto`. A negative invocation that removes the flag or injects LTO must fail before producing a deployable manifest. It is acceptable to fail unsupported optimization configurations; silently accepting a moved callsite is not.

- [ ] **Step 7: Run unit fixtures**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_qual.py
```

Expected: all positive and negative fixtures pass.

- [ ] **Step 8: Build Q0 and Q1 in the authoritative container**

Run through SSH because the local mirror is not the authoritative build tree:

```bash
ssh gihwan 'docker exec benchmark-runner bash -lc "cd /work/selftest && \
  make -f Makefile.pmu_qual QUAL=Q0 clean bins check manifest hashes && \
  make -f Makefile.pmu_qual QUAL=Q1 clean bins check manifest hashes"'
```

Expected: both compile/link/check; Q0/Q1 manifests exist; every fail-closed gate passes.

- [ ] **Step 9: Verify baseline/candidate vendor object identity**

```bash
ssh gihwan 'docker exec benchmark-runner sha256sum \
  /work/selftest/build_pmu_qual_q0/Drivers/u85_driver/u85.o \
  /work/selftest/build_pmu_qual_q1/Drivers/u85_driver/u85.o'
```

Expected: identical full hashes.

- [ ] **Step 10: Verify deterministic rebuild and official DDR**

Clean-build Q0/Q1 a second time and compare all BIN/ELF/map/manifest hashes. Expected: deterministic within each mode and DDR.BIN remains `81d37a21...` official full hash recorded in the existing procedure/evidence.

- [ ] **Step 11: Record a checkpoint without committing**

```bash
git diff --check -- firmware/Makefile.pmu_qual \
  firmware/Selftest_pmu_diag/runner_pmu_diag_main.c \
  firmware/Selftest_pmu_diag/check_pmu_qual.py \
  firmware/Selftest_pmu_diag/test_check_pmu_qual.py
```

Expected: clean.

## Chunk 4: Collector and analyzer

### Task 4: Bind raw evidence to the ELF manifest

**Files:**

- Create: `host/run_pmu_qual.py`
- Create: `host/analyze_pmu_qual.py`
- Modify: `host/tests/test_pmu_qual_unit.py`
- Reference: `host/run_pmu_diag.py`
- Reference: `host/analyze_pmu_diag.py`

- [ ] **Step 1: Mark files before writing**

```bash
codex-mark-used host/run_pmu_qual.py
codex-mark-used host/analyze_pmu_qual.py
codex-mark-used host/tests/test_pmu_qual_unit.py
```

- [ ] **Step 2: Add failing manifest and archive tests**

Test rejection of wrong Q0/Q1 build ID, APP/VECTORS/DDR hashes, missing manifest, manifest schema/mode mismatch, observed LR mismatch, absent reread, and stale COMPLETE reuse.

- [ ] **Step 3: Implement `run_pmu_qual.py`**

The collector must require:

```text
--mode Q0|Q1
--bins-dir
--manifest
--host-boot-index
--out
```

Before opening the serial port, verify manifest identity, local BIN hashes, and Q0/Q1 build
ID. Each mode's observed LR is compared only with that same mode manifest's expected LR.
Q0 and Q1 may link at different numeric addresses, so `Q0.LR == Q1.LR` is never a gate.
Collect unsolicited COMPLETE plus an independent GET reread; preserve both raw payload hex
values and require equality. Archive manifest and full hashes with the JSON.

- [ ] **Step 4: Implement `analyze_pmu_qual.py`**

Output:

```text
identity and callsite attestation
start-boundary raw state
PRE / internal PRE-RELEASE / internal post-disable / after-return table
hook counts, LR, NPU CMD, timestamps, MMIO counts
exact golden/output CRCs
npu_pmu_window_cycles or INVALID with failing checks
Q0/Q1 functional equivalence when both files are supplied; same logical caller/release shape,
but no numeric cross-mode LR equality requirement
```

Never print `T_npu` or promote Q0/DIAG values as performance.

- [ ] **Step 5: Run all host tests**

Use the exact commands from Task 1 Step 7 plus:

```bash
python3 -m py_compile host/run_pmu_qual.py host/analyze_pmu_qual.py
```

Expected: all pass.

## Chunk 5: Complete pre-board verification and documentation

### Task 5: Prove no production drift and publish a bounded procedure

**Files:**

- Create: `firmware/Selftest_pmu_diag/PMU_QUAL_PROCEDURE.md`
- Modify: `firmware/Selftest_pmu_diag/PMU_DIAG_PROCEDURE.md`
- Modify after verification: `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md`
- Modify after verification: `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md`

- [ ] **Step 1: Mark documentation before writing**

```bash
codex-mark-used firmware/Selftest_pmu_diag/PMU_QUAL_PROCEDURE.md
codex-mark-used firmware/Selftest_pmu_diag/PMU_DIAG_PROCEDURE.md
```

- [ ] **Step 2: Write the qualification procedure**

Include exact Q0/Q1 commands, full artifact/manifest hashes, callsite addresses and disassembly digest, required raw fields, Q0/Q1 equivalence gates, independent boot/repeat matrix, stop/go criteria, restore procedure, and explicit labels:

```text
QUALIFICATION ONLY
NO PRODUCTION GO
NO PERFORMANCE BASELINE
NO BOARD RUN YET
```

- [ ] **Step 3: Add one historical pointer to the v7 procedure**

Do not rewrite v7 evidence. Add only a short note pointing to `PMU_QUAL_PROCEDURE.md` and stating v7 root-cause isolation is complete.

- [ ] **Step 4: Verify frozen/production/provenance diff**

Re-run Task 0's exact commands and compare full output against
`PMU_QUAL_FROZEN_BASELINE.sha256`, including both out-of-git vendor copies and the
`provenance/**` tree root. Expected: every value identical.

- [ ] **Step 5: Run the complete pre-board matrix**

Run and observe:

```text
Python compile checks
new host schema-v8 suite
existing v7/legacy host suites
gate positive/negative fixture suite
Q0/Q1 preprocess/write-count gates
Q0/Q1 container compile/link/map/ELF gates
Q0/Q1 clean rebuild determinism
schema-v7 S1/S2/S3 clean rebuild exact hash reproduction
schema-v7 A/B/C+NC4 build/check regression
vendor source/object identity
DDR official hash
golden map contract
denylist/logging gates
git diff --check
production/frozen/provenance diff 0
```

The shared runner's compile-time isolation is a required gate, not an inference. Rebuild v7
S1/S2/S3 and require these exact full hashes:

```text
S1 APP     7570133e68c803b3268c9a9bf75ace8996f3ba26ede3713362226bb8bbe84375
S1 VECTORS 83eb2eb167a5aa82477545650e37c51e55e14d9ebfd92fe6b306e3709f97ea9f
S2 APP     880080bab94aed99dd494c4659c5c2a8bc3543f800cab7b85974c333541c368f
S2 VECTORS 5f15c108b580b8aa6e93f88669a5f618418c623c0668451c966dce0b8044598c
S3 APP     b04ef92151efa50ff9fe062d07ce33b214342439da7f2c9713b0348827d65a1d
S3 VECTORS 8c6fe7d00be152964c518731c3ed425f0ebf53b7059432c67445da9c7b0afb26
all DDR    81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98
```

Also rebuild/check schema-v7 A/B/C plus NC1-NC4. Their APP hashes are not reused as v8
identity; their build/check success proves the shared source did not break legacy matrices.

- [ ] **Step 6: Update Obsidian only with observed results**

Record the approved design, actual test counts/hashes, callsite proof, remaining board qualification, and the corrected external patch dates. Do not claim board success or production qualification.

- [ ] **Step 7: Stop before board deployment**

Report the pre-board result to the user. Board/SD/reboot requires a separate execution decision after Codex independent verification.

## Chunk 6: Independent verification

### Task 6: Codex audits Claude's implementation

**Files:** all files listed above, read-only unless a concrete defect requires a separately attributed fix.

- [ ] **Step 1: Inspect every changed file and `git diff --check`**

- [ ] **Step 2: Re-run host tests independently**

- [ ] **Step 3: Re-run gate fixture tests independently**

- [ ] **Step 4: Rebuild Q0/Q1 independently in the authoritative container**

- [ ] **Step 5: Independently disassemble the final ELF**

Verify the target caller, resolved `__wrap_printf`, expected LR, no caller-side access between
return and release, Q0/Q1 logical callsite identity, and manifest digest. Compare each
observed LR only to its own manifest; do not require the two modes' numeric addresses to match.
Do not rely only on the checker output.

- [ ] **Step 6: Verify Q0/Q1 driver object hashes and NPU-path equivalence**

- [ ] **Step 7: Verify ABI raw fixtures and every fail-closed negative**

- [ ] **Step 8: Verify production/frozen/provenance diff 0**

- [ ] **Step 9: Return defects to Claude as a scoped follow-up task**

Repeat implementation/review only for observed defects; do not broaden scope.

- [ ] **Step 10: Report pre-board GO/NO-GO**

GO means only “safe to begin separate board qualification.” It never means Production END_ONLY or performance baseline approval.
