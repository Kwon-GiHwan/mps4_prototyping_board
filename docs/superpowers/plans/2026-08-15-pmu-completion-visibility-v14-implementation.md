# PMU_COMPLETION_VISIBILITY_DIAG_V14 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and qualify three schema-14 diagnostic images (Q, QS, SQ) that compare QREAD completion-cursor visibility with STATUS command-end visibility while preserving one common fail-closed convergence and cleanup path.

**Architecture:** Generate all three variants from the same frozen V13 raw runner/vendor inputs. Keep variant-specific primary poll loops small, then join one shared convergence helper and the frozen V12/V13 IRQ-hard-bypass cleanup. Bind source, actual ARM CFG/dataflow, exact 127-word wire ABI, host classification, and board artifacts through independent fail-closed gates before any deployment.

**Tech Stack:** Python 3 standard library, generated C for Cortex-M85, GNU Arm Embedded toolchain in the existing `benchmark-runner` container, `objdump`/`nm`/DWARF/map evidence, existing PMU V8-V13 protocol modules, UART collector, JSON/SHA-256 evidence.

**Approved spec:** `docs/superpowers/specs/2026-08-15-pmu-completion-visibility-v14-design.md` at design anchor `d840ed2`.

---

## File structure

New files have one responsibility each:

- `firmware/patches/patch_pmu_completion_visibility_v14.py` — generate Q/QS/SQ source from exact frozen inputs.
- `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py` — source, fixture, manifest, and actual-ELF contract gates.
- `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py` — positive and deliberate-negative firmware/checker tests.
- `firmware/Makefile.pmu_completion_visibility_v14` — isolated three-variant ARM graph and evidence manifest.
- `firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py` — graph and executable CLI smoke tests.
- `firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md` — frozen generated/ELF addresses, hashes, qualification boundary.
- `host/runner_proto_pmu_completion_visibility_v14.py` — exact schema-14 parser/classifier only.
- `host/tests/test_pmu_completion_visibility_v14.py` — protocol, manifest, sentinel, and validity tests.
- `host/compare_declared_builds.py` — deterministic logical-artifact comparison.
- `host/tests/test_compare_declared_builds.py` — artifact-set mutation tests.
- `host/collect_pmu_completion_visibility_v14.py` — preflight, raw/reread, failure quarantine, and cell-attempt collection.
- `host/tests/test_collect_pmu_completion_visibility_v14.py` — collector fail-closed tests.
- `host/analyze_pmu_completion_visibility_v14.py` — categorical ordering and within-variant structure analysis.
- `host/tests/test_analyze_pmu_completion_visibility_v14.py` — exact 90-sample and conditional-S5 analysis tests.
- `docs/superpowers/plans/2026-08-15-pmu-completion-visibility-v14-board.md` — generated only after pre-board qualification; operator commands and restore gates.

Existing V8-V13 source, generated artifacts, evidence, and Production files are read-only inputs/regressions. Do not modify them.

## Frozen execution constants

Every command in this plan uses these exact identities:

```text
local worktree
  /Users/kwongihwan/.config/superpowers/worktrees/mps4_testing/pmu-completion-poll-count-v13

SSH host                 gihwan
host selftest tree       /home/gihwan/mps4/runner/selftest
container                benchmark-runner
container selftest tree  /work/selftest
pre-board evidence root  /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE

raw runner
  Selftest_pmu_diag/runner_pmu_diag_main.c
  sha256 69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b

raw vendor
  Drivers/u85_driver/u85.c
  sha256 bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf

generated runner
  generated/Selftest_pmu_diag/runner_pmu_diag_main.c

generated vendor
  generated/Drivers/u85_driver/u85.c
```

The implementation freezes these C symbols and numeric return contract:

```text
mailbox storage       pmu_completion_visibility_v14_mailbox
mailbox reset API     v14_mailbox_reset
primary Q helper      v14_primary_q
primary QS helper     v14_primary_qs
primary SQ helper     v14_primary_sq
common tail helper    v14_converge

vendor return:
  0 SUCCESS
  1 PRE_PROGRAM_FAILURE
  2 PRE_SUBMIT_FAILURE
  3 PRIMARY_TIMEOUT
  4 RESET_IN_PROGRESS
  5 HARDWARE_FAULT
  6 CONVERGENCE_TIMEOUT
  7 CLEANUP_INVARIANT
```

The generator uses exact-one anchors already defined in
`patch_pmu_completion_poll_v12.py`: runner anchors
`_RUNNER_SCHEMA_STOCK`, `_RUNNER_EXTERN_STOCK`, `_RUNNER_RECORD_STOCK`,
`_RUNNER_FIELD_COUNT_STOCK`, `_RUNNER_ASSERTS_STOCK`,
`_RUNNER_PRIVATE_DRIVER_SEAM_STOCK`, `_RUNNER_PRIVATE_DRIVER_V8_STOCK`,
`_RUNNER_CLEAR_STOCK`, `_RUNNER_SERIALIZE_STOCK`, `_RUNNER_COPY_STOCK`; and
vendor anchors `_VENDOR_DEFS_ANCHOR`, `_VENDOR_HELPER_ANCHOR`,
`_VENDOR_LOCALS_STOCK`, `_VENDOR_ENABLE_STOCK`, `_VENDOR_COMMAND_STOCK`.
Every reported replacement count must be exactly one.

The firmware test entrypoint must end with `passed=N failed=0`, where `N` is a
constant asserted inside the test file and updated only when named fixtures are
added. RED runs must exit nonzero with the stable rejection reason named in the
step. GREEN runs exit zero. This avoids plans that depend on an unfrozen count.

---

## Chunk 1: Firmware RED contract and frozen-source generator

### Task 1: Freeze schema constants and source fixtures

**Files:**
- Create: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`
- Reference: `docs/superpowers/specs/2026-08-15-pmu-completion-visibility-v14-design.md`
- Reference: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Add failing identity tests**

Before the first edit, record the exact Chunk-1 base:

```bash
v14_base_file="$(git rev-parse --git-path v14_chunk1_base)"
git rev-parse HEAD > "$v14_base_file"
test -z "$(git status --porcelain)"
```

Define exact constants in the test fixture:

```python
SCHEMA = 14
BUILD_ID = 0x34314950
BASE_WORDS = 85
APPENDIX_WORDS = 34
BODY_WORDS = 119
TOTAL_WORDS = 127
PAYLOAD_BYTES = 508
QSIZE_EXPECTED = 0x110
MAILBOX_VALID = 0x5631344D
U32_INVALID = 0xFFFFFFFF
VARIANTS = {"Q": 1, "QS": 2, "SQ": 3}
```

Assert the future checker exports the same values and rejects any different
schema, build ID, QSIZE, appendix count, or mailbox magic.

- [ ] **Step 2: Run the targeted test and observe RED**

Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: FAIL because `check_pmu_completion_visibility_v14` does not exist.

- [ ] **Step 3: Create the checker constants and minimal CLI**

Create `check_pmu_completion_visibility_v14.py` with `argparse`, `main()`, and
the exact fixture CLI used by Task 5: `--allow-fixture`, `--variant {Q,QS,SQ}`,
`--runner-generated PATH`, `--vendor-generated PATH`, and
`--fixture-manifest-out PATH`; all are required in fixture mode. Default mode
rejects synthetic evidence. Add CLI RED/GREEN subprocess tests for `--help`,
missing `--allow-fixture`, invalid variant, missing inputs, and a controlled
manifest output.

- [ ] **Step 4: Run syntax and identity tests**

Run:

```bash
python3 -m py_compile firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: identity tests PASS; later RED tests may still fail.

- [ ] **Step 5: Commit the identity gate**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): define firmware identity contract"
```

### Task 2: TDD the pre-run QSIZE and stale-state contract

**Files:**
- Modify: `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Add deliberate failing fixtures**

Add mutations for:

```text
pre-program STATUS gate missing or after QBASE/QSIZE
state transition between gate and programming
QSIZE snapshot before final QSIZE write
QSIZE snapshot not equal to manifest 0x110
second QSIZE read
QSIZE read reachable after submit
post-program stale irq/cmd_end/reset/fault gate missing
pre-run failure falling through to submit
```

- [ ] **Step 2: Run and confirm every mutation is currently accepted or unimplemented**

Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: nonzero; each named mutation reports its stable expected reason
(`QSIZE access not dominated by stopped gate`, `running QSIZE reachable`,
`qsize_expected is not manifest 0x110`, or `pre-run failure reaches submit`).

- [ ] **Step 3: Implement exact source/CFG fixture validation**

Require the two distinct STATUS reads, exact masks `0x001`, `0x002`, `0x008`,
`0x020`, `0x314`, and one QSIZE load between final programming and submit.
Bind the QSIZE compare to `0x110` and manifest identity.

- [ ] **Step 4: Run the fixture suite**

Run the same command. Expected: exit zero and final line
`passed=N failed=0`; canonical fixture PASS and every mutation is counted only
when rejected for its declared stable reason.

- [ ] **Step 5: Commit the pre-run gate**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): enforce stopped-state queue setup"
```

### Task 3: TDD Q/QS/SQ primary loop semantics

**Files:**
- Modify: `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Add canonical Q, QS, and SQ fixture functions**

Use explicit volatile addresses for `QREAD=base+0x18`, `STATUS=base+0x04`, and
no QSIZE pointer in any primary helper. QS/SQ must assign both raw values before
testing reset/fault and `q_done || s_done`.

- [ ] **Step 2: Add primary-loop negative mutations**

Cover Q adding STATUS, QS/SQ dropping the second read, short-circuit exit,
identical QS/SQ order, bit1 used instead of bit5, success reread, per-iteration
store/call/timestamp, missing reset/fault priority, and fault mislabeled as
timeout.

Also mutate the retained hard-bypass contract: runtime vector away from exact
stock `u85_irq_handler`; missing/reordered Disable/Clear/GetEnable/GetPending/
GetActive; reachable `NVIC_EnableIRQ`; direct ISER enable write; and reachable
`irq_triggered=true` publication/store. Each must fail for a stable reason.

- [ ] **Step 3: Add mandatory positive boundaries**

Add Q success, QS/SQ `Q_FIRST`, `S5_FIRST`, and `SAME_ITERATION`; success on
iteration 1 and 10000; each independent fault bit `0x004`, `0x010`, `0x100`,
`0x200`; reset `0x008`; stale pre-run bit5; primary timeout; and Q-complete
before IRQ visibility. Each fixture asserts its exact enum, tuple, and sentinel
state.

- [ ] **Step 4: Add Q timeout-only diagnostic STATUS fixture**

Require exactly one STATUS read after the Q loop exhausts; prove it cannot
reach P1, convergence, or success cleanup.

- [ ] **Step 5: Run the new tests and observe RED**

Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: nonzero with named read-order,
fault-priority, or timeout-diagnostic rejection reasons.

- [ ] **Step 6: Implement normalized fixture CFG/dataflow checks**

The checker must identify semantic MMIO loads and branch-driving values rather
than compare source strings or fixed registers. Add source/fixture gates for
the exact stock vector target, initial Disable/Clear/GetEnable/GetPending/
GetActive order, absence of reachable `NVIC_EnableIRQ` or ISER enable writes,
and `irq_triggered` remaining false.

- [ ] **Step 7: Run GREEN**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: exit zero, `passed=N failed=0`.

- [ ] **Step 8: Commit the primary-loop gate**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): lock primary observation loops"
```

Expected: all three canonical loops PASS; every deliberate mutation FAIL.

### Task 4: TDD common convergence, failure mailbox, and cleanup

**Files:**
- Modify: `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Add the canonical convergence helper fixture**

Use the exact symbol `v14_converge` and result struct consumed by all three
primary helpers. Express one 10000-iteration loop with fixed QREAD-then-STATUS order, immediate
`reset_status`/`0x314` failure, and one same-tuple predicate:

```c
qread == qsize_expected &&
(status & 0x20U) != 0U &&
(status & 0x02U) != 0U &&
(status & 0x01U) == 0U
```

- [ ] **Step 2: Add convergence negative mutations**

Reject cross-iteration accumulation, omitted predicate term, delayed fault,
different per-variant helper/bound/order, per-loop evidence store, QSIZE read,
and timeout/fault edges merged into normal cleanup.

Add positive success on tail iteration 1 and 10000, each fault bit, reset,
convergence timeout, and Q completion before later cmd-end/IRQ convergence.
Compute a normalized common-helper source digest after whitespace/newline
normalization and require it to be identical for Q/QS/SQ. Reject any reachable
variant-specific function/block between primary freeze and `v14_converge`, or
between its success return and the one common cleanup block.

- [ ] **Step 3: Add the exact 34-word mailbox fixture**

Bind appendix offsets 0..33 to the exact spec table, all enum/sentinel rules,
and every phase-validity matrix row. Require reset-to-invalid,
`mailbox_valid=0`, final magic
`0x5631344D`, DSB, vendor ownership, runner magic check, copy, and exact
127-word serialization.

- [ ] **Step 4: Add mailbox and cleanup mutations**

Reject missing/early/duplicate/stale magic, field store after magic, runner copy
before magic check, failure-path NPU clear, history STATUS reread, and drift from
success `CMD2 -> QREAD -> CMD2 -> verify -> NVIC -> CMD0 -> H-PRINTF -> CMD0xC`.

Also reject Q first-STATUS fields synthesized from convergence, simultaneous
success/failure tuple validity, discarded convergence-failure T2/P0/P1/first
tuple, invalid raw fields promoted to a verdict/distribution, failure reaching
H-PRINTF, and missing/duplicate Q-timeout diagnostic STATUS.

- [ ] **Step 5: Run the new tests and observe RED**

Run the firmware test entrypoint. Expected: nonzero with the named convergence,
mailbox, phase-matrix, or cleanup rejection reason.

- [ ] **Step 6: Implement checker gates**

Implement only the gates demanded by Steps 1-4.

- [ ] **Step 7: Run GREEN**

Run the same command. Expected: exit zero and `passed=N failed=0`.

- [ ] **Step 8: Commit the convergence/mailbox gate**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): gate convergence and failure evidence"
```

### Task 5: Implement the frozen-source generator

**Files:**
- Create: `firmware/patches/patch_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Add generator RED tests**

Require exact SHA-256 pins for raw runner/vendor, exact-one source anchors,
`--variant Q|QS|SQ`, no patching of V13 generated output, and deterministic
output for repeated inputs.

- [ ] **Step 2: Run RED**

Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: nonzero with
`generator module not found`.

- [ ] **Step 3: Implement the minimal generator**

Import the exact anchor constants listed under Frozen execution constants and
use `sub_once()` for each; reject any replacement count other than one. Accept
only `--variant`, `--runner-in`, `--vendor-in`, `--runner-out`, and
`--vendor-out`. Emit the frozen symbols `v14_primary_q/qs/sq`,
`v14_converge`, `pmu_completion_visibility_v14_mailbox`, and
`v14_mailbox_reset`; use the exact return mapping in the plan header. The
inactive primary helper symbols must not be reachable in a variant. Preserve
the stock vector/NVIC/CMD/QREAD/H-PRINTF anchors and report every replacement
count in canonical JSON on stdout.

- [ ] **Step 4: Generate all variants into temporary directories**

```bash
v14_tmp="$(mktemp -d)"
scp gihwan:/home/gihwan/mps4/runner/selftest/Selftest_pmu_diag/runner_pmu_diag_main.c "$v14_tmp/runner.c"
scp gihwan:/home/gihwan/mps4/runner/selftest/Drivers/u85_driver/u85.c "$v14_tmp/u85.c"
printf '%s  %s\n' \
  69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b "$v14_tmp/runner.c" \
  bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf "$v14_tmp/u85.c" \
  | shasum -a 256 -c -
for v14_case in Q QS SQ; do
  mkdir -p "$v14_tmp/$v14_case/generated/Selftest_pmu_diag" \
           "$v14_tmp/$v14_case/generated/Drivers/u85_driver"
  python3 firmware/patches/patch_pmu_completion_visibility_v14.py \
    --variant "$v14_case" \
    --runner-in "$v14_tmp/runner.c" \
    --vendor-in "$v14_tmp/u85.c" \
    --runner-out "$v14_tmp/$v14_case/generated/Selftest_pmu_diag/runner_pmu_diag_main.c" \
    --vendor-out "$v14_tmp/$v14_case/generated/Drivers/u85_driver/u85.c"
done
```

Expected: hash check exit zero; three generated pairs; stdout replacement
counts all equal one. Perform the exact independent repeat/comparison:

```bash
for v14_case in Q QS SQ; do
  mkdir -p "$v14_tmp/repeat/$v14_case/generated/Selftest_pmu_diag" \
           "$v14_tmp/repeat/$v14_case/generated/Drivers/u85_driver"
  python3 firmware/patches/patch_pmu_completion_visibility_v14.py \
    --variant "$v14_case" --runner-in "$v14_tmp/runner.c" --vendor-in "$v14_tmp/u85.c" \
    --runner-out "$v14_tmp/repeat/$v14_case/generated/Selftest_pmu_diag/runner_pmu_diag_main.c" \
    --vendor-out "$v14_tmp/repeat/$v14_case/generated/Drivers/u85_driver/u85.c"
  diff -rq "$v14_tmp/$v14_case/generated" "$v14_tmp/repeat/$v14_case/generated"
done
```

- [ ] **Step 5: Run the source/fixture checker on generated output**

Run for each case:

```bash
for v14_case in Q QS SQ; do
  python3 firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
    --allow-fixture \
    --variant "$v14_case" \
    --runner-generated "$v14_tmp/$v14_case/generated/Selftest_pmu_diag/runner_pmu_diag_main.c" \
    --vendor-generated "$v14_tmp/$v14_case/generated/Drivers/u85_driver/u85.c" \
    --fixture-manifest-out "$v14_tmp/$v14_case/fixture-manifest.json"
done
```

Expected: three exit-zero results. Recompute the manifest-declared
`common_convergence_source_sha256` with:

```bash
python3 - "$v14_tmp" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
values = []
for case in ("Q", "QS", "SQ"):
    p = root / case / "fixture-manifest.json"
    doc = json.loads(p.read_text())
    source = root / case / "generated/Drivers/u85_driver/u85.c"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == doc["generated_vendor_sha256"]
    values.append(doc["common_convergence_source_sha256"])
assert len(set(values)) == 1, values
PY
```

- [ ] **Step 6: Run frozen regressions**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py
```

Expected: all existing suites retain their prior PASS counts.

Exact expected final lines are V13 `passed=372 failed=0`, V12
`passed=110 failed=0`, and V11-A `passed=38 failed=0`.

- [ ] **Step 7: Verify isolation and formatting**

```bash
git diff --check
base="$(cat "$(git rev-parse --git-path v14_chunk1_base)")"
git add firmware/patches/patch_pmu_completion_visibility_v14.py \
  firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git diff --cached --check "$base"
git diff --cached --name-only "$base" | sort > /tmp/v14_chunk1_actual.txt
printf '%s\n' \
 firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py \
 firmware/patches/patch_pmu_completion_visibility_v14.py | sort \
 > /tmp/v14_chunk1_allowed.txt
diff -u /tmp/v14_chunk1_allowed.txt /tmp/v14_chunk1_actual.txt
test -z "$(git diff --name-only)"
test -z "$(git ls-files --others --exclude-standard)"
```

Expected: all commands exit zero; no tracked path outside the three-file
Chunk-1 allowlist changed across the full commit range.

- [ ] **Step 8: Commit Chunk 1**

```bash
git add firmware/patches/patch_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "feat(pmu-v14): generate completion visibility variants"
```

Chunk 1 may claim only firmware contract/generator UNIT-QUALIFIED. It may not
claim real ARM, host, pre-board, or board qualification.

---

## Chunk 2: Isolated ARM builds and final-ELF qualification

### Task 6: Add the isolated three-variant build graph

**Files:**
- Create: `firmware/Makefile.pmu_completion_visibility_v14`
- Create: `firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py`
- Create: `host/compare_declared_builds.py`
- Create: `host/tests/test_compare_declared_builds.py`

- [ ] **Step 1: Write RED graph tests**

Assert three disjoint build roots, exact frozen inputs, explicit variant
argument, no writable shared generated source, real checker CLI invocation,
manifest `test -s`, and declared evidence outputs.

- [ ] **Step 2: Run RED**

Expected: missing Makefile.

- [ ] **Step 3: Implement the graph**

Provide `clean`, `all`, `manifest`, and `check` targets parameterized by
`V14_VARIANT` and overridable absolute `BUILD`. Reject other variant strings.
Every manifest depends on actual ELF/map/nm/objdump/DWARF,
generated source, source/fixture proof, mailbox/wire proof, retained base-PMU
proof, and frozen-input digests.

- [ ] **Step 4: Execute CLI smoke tests**

The Makefile test must actually invoke checker `--help` and a controlled
`--manifest-out` fixture path; substring inspection alone is insufficient.
TDD the comparison CLI with exact options `--left`, `--right`, `--variants`,
`--manifest-name`, and `--report`; reject missing, extra, substituted, or
byte-different declared artifacts and path/timestamp leakage.

- [ ] **Step 5: Run graph tests and commit**

```bash
python3 firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py
python3 -m unittest host.tests.test_compare_declared_builds -v
```

Expected: exit zero and the test's frozen `passed=N failed=0` line.

- [ ] **Step 6: Commit the build graph**

```bash
git add firmware/Makefile.pmu_completion_visibility_v14 \
        firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py \
        host/compare_declared_builds.py host/tests/test_compare_declared_builds.py
git commit -m "build(pmu-v14): add isolated variant graph"
```

### Task 7: Build Q/QS/SQ twice with the real ARM toolchain

**Files:** no tracked edit in this task; evidence goes to the fixed remote root
which must be absent before one-time initialization.

- [ ] **Step 1: Verify SSH/container/toolchain and frozen inputs read-only**

Run:

```bash
ssh gihwan 'set -eu
  root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE
  test ! -e "$root"
  mkdir "$root"
  {
    test "$(docker inspect -f "{{.State.Running}}" benchmark-runner)" = true
    docker exec -w /work/selftest benchmark-runner \
      /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-gcc --version | head -1
    docker exec -w /work/selftest benchmark-runner sha256sum \
      Selftest_pmu_diag/runner_pmu_diag_main.c Drivers/u85_driver/u85.c
    printf "%s  %s\n%s  %s\n" \
      69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b Selftest_pmu_diag/runner_pmu_diag_main.c \
      bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf Drivers/u85_driver/u85.c \
      | docker exec -i -w /work/selftest benchmark-runner sha256sum -c -
    df -h /home/gihwan/mps4
    docker inspect -f "{{.Id}}" benchmark-runner
  } > "$root/PREFLIGHT.txt" 2>&1
  cat "$root/PREFLIGHT.txt"'
```

Expected runner/vendor digests are the two frozen values above; mismatch,
stopped container, existing root, or insufficient stage space is STOP.

- [ ] **Step 2: Stage only the tracked V14 build files into the container**

```bash
ssh gihwan 'mkdir /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE'
scp firmware/Makefile.pmu_completion_visibility_v14 \
    firmware/patches/patch_pmu_completion_visibility_v14.py \
    firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
    host/compare_declared_builds.py \
    gihwan:/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/
ssh gihwan 'set -eu
  docker cp /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/Makefile.pmu_completion_visibility_v14 benchmark-runner:/work/selftest/Makefile.pmu_completion_visibility_v14
  docker cp /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/patch_pmu_completion_visibility_v14.py benchmark-runner:/work/selftest/patches/patch_pmu_completion_visibility_v14.py
  docker cp /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/check_pmu_completion_visibility_v14.py benchmark-runner:/work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py'
```

Expected: exit zero. Re-hash staged files on local/host/container and require
three-way identity with this exact local command:

```bash
check_three() {
  local local_path="$1" host_path="$2" container_path="$3"
  local l h c
  l="$(shasum -a 256 "$local_path" | awk '{print $1}')"
  h="$(ssh gihwan "sha256sum '$host_path'" | awk '{print $1}')"
  c="$(ssh gihwan "docker exec benchmark-runner sha256sum '$container_path'" | awk '{print $1}')"
  test "$l" = "$h" && test "$l" = "$c"
}
root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE
check_three firmware/Makefile.pmu_completion_visibility_v14 \
  "$root/Makefile.pmu_completion_visibility_v14" /work/selftest/Makefile.pmu_completion_visibility_v14
check_three firmware/patches/patch_pmu_completion_visibility_v14.py \
  "$root/patch_pmu_completion_visibility_v14.py" /work/selftest/patches/patch_pmu_completion_visibility_v14.py
check_three firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
  "$root/check_pmu_completion_visibility_v14.py" /work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py
```

- [ ] **Step 3: Run clean Build A for each variant**

```bash
ssh gihwan 'set -eu
  rm -rf /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A
  for c in Q QS SQ; do
    docker exec -w /work/selftest benchmark-runner make \
      -f Makefile.pmu_completion_visibility_v14 \
      V14_VARIANT="$c" BUILD="/work/v14/BUILD_A/$c" clean all manifest
    mkdir -p "/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A/$c"
    docker cp "benchmark-runner:/work/v14/BUILD_A/$c/." \
      "/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A/$c/"
  done'
```

Expected: three make exits zero; each copied tree contains nonempty
APP/VECTORS/DDR/ELF/map/manifest and declared evidence.

- [ ] **Step 4: Run clean Build B for each variant**

Repeat the exact command with both `BUILD_A` occurrences changed to `BUILD_B`.
Do not copy any A file into B. Expected: three exits zero.

- [ ] **Step 5: Compare declared artifacts**

Require byte identity for APP/VECTORS/DDR/ELF/map/generated/preprocessed source,
nm/objdump/DWARF, manifest, and every evidence JSON. Manifests/evidence must
serialize stable logical artifact keys and digests, never absolute A/B paths or
timestamps. Run on `gihwan`:

```bash
python3 /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/compare_declared_builds.py \
  --left /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A \
  --right /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_B \
  --variants Q,QS,SQ \
  --manifest-name pmu_completion_visibility_v14_manifest.json \
  --report /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_DETERMINISM.json
```

Expected report: `mismatches=[]`, every declared artifact present, and exit
zero. This must use the tracked, unit-tested Task-6 script.

- [ ] **Step 6: STOP on any nondeterminism**

Do not normalize or bless a mismatch; identify the generating input first.

### Task 8: Bind real ARM primary-loop and QSIZE proofs

**Files:**
- Modify: `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Add real-disassembly RED tests**

Mutate actual instruction traces for running QSIZE, swapped/missing reads,
short-circuit exit, wrong bit mask, extra per-iteration effects, and wrong
branch-driving values.

Also mutate each required pre-run fact: pre-program STATUS no longer dominates
QBASE/QSIZE, running transition inserted, QSIZE load moved before final write,
second/running QSIZE load, compare changed from manifest `0x110`, post-program
STATUS reused from the pre-program load, stale/reset/fault check omitted, and
failure allowed to reach submit.

Run immediately:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected RED: nonzero with the named mutated-trace reason for every new case.

- [ ] **Step 2: Implement normalized ARM CFG/dataflow extraction**

Resolve literal/MOVW/MOVT addresses, Thumb targets, call reachability, load/store
effects, and same-load use. Do not hardcode general behavior to one register
allocation; bind the actual build in the manifest.

For Q prove one QREAD/zero STATUS loads per iteration and exactly one
post-timeout STATUS read. For QS/SQ prove both loads execute, reset/fault
dominates completion, bit1 is not an exit predicate, branch-driving loads feed
the frozen tuple, and primary loops contain no QSIZE, timestamp, log, call, or
per-iteration store.

- [ ] **Step 3: Prove QS/SQ equivalence except read order**

Compare normalized CFG, loop bounds, predicate dataflow, fault priority, and
effect multisets. Permit address relocation/register renaming only.

- [ ] **Step 4: Run actual-ELF checker on all six builds**

First run local GREEN:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

Expected: `passed=N failed=0`. Commit the checker/test now, then restage it:

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): prove ARM observation loops"
scp firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/
local_sha="$(shasum -a 256 firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py | awk '{print $1}')"
remote_sha="$(ssh gihwan 'sha256sum /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/check_pmu_completion_visibility_v14.py' | awk '{print $1}')"
test "$local_sha" = "$remote_sha"
ssh gihwan 'docker cp /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/check_pmu_completion_visibility_v14.py benchmark-runner:/work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py'
container_sha="$(ssh gihwan 'docker exec benchmark-runner sha256sum /work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py' | awk '{print $1}')"
test "$local_sha" = "$container_sha"
```

Run:

```bash
ssh gihwan 'set -eu
  root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE
  for b in BUILD_A BUILD_B; do for c in Q QS SQ; do
    docker exec -w /work/selftest benchmark-runner make -B \
      -f Makefile.pmu_completion_visibility_v14 V14_VARIANT="$c" \
      BUILD="/work/v14/$b/$c" check manifest
    rm -rf "$root/$b/$c" && mkdir -p "$root/$b/$c"
    docker cp "benchmark-runner:/work/v14/$b/$c/." "$root/$b/$c/"
    python3 "$root/SOURCE/check_pmu_completion_visibility_v14.py" \
      --variant "$c" --real-elf \
      --build-root "$root/$b/$c" \
      --manifest "$root/$b/$c/pmu_completion_visibility_v14_manifest.json"
  done; done'
```

Expected: six exit-zero `REAL_ELF PASS` results using the SHA-identical final
Task-8 checker.

### Task 9: Bind common tail, mailbox, and retained V12/V13 semantics

**Files:**
- Modify: `firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py`
- Create: `firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md`

- [ ] **Step 1: Prove one common tail symbol/object and normalized CFG**

Require the same helper object SHA, QREAD/STATUS order, 10000 bound, exact
predicate, fault/reset exits, and zero per-iteration stores/QSIZE/calls.

Require convergence evidence stores only after loop exit, exact same-load
dataflow from `convergence_final_status` to history, no STATUS reread, and no
variant-specific reachable block from primary freeze through terminal release.

- [ ] **Step 2: Prove actual mailbox and runner-wire dataflow**

Use DWARF plus disassembly to bind all 34 appendix offsets, magic-last store,
DSB, reset API, runner magic check, copy, 127-word/508-byte serialization, and
failure return before any NPU clear.

Add actual-trace negative fixtures for failure-to-cleanup reachability,
variant-specific cleanup, cleanup-invariant mislabeled as convergence failure,
and magic/copy/serialization reordering.

TDD the checker subcommand `verify-preboard` used in Task 17. Fixture tests
must reject a contract/runbook/review/artifact mismatch and on success write a
canonical file at the required `--approval-index-out` path. Its exact arguments
are shown in Task 17; `--help` must document them.

Run the firmware test now and require RED for each new mutation, implement only
the demanded gates, then rerun to `passed=N failed=0`:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
```

- [ ] **Step 3: Re-run retained executable gates**

Parameterize, do not weaken, the V12/V13 stock vector, NVIC hard-bypass,
history, success CMD2x2/QREAD, base PMU, H-PRINTF, golden-window, CMD0, and
terminal CMD0xC verifiers.

- [ ] **Step 4: Emit per-variant real evidence manifests**

Each manifest binds artifact hashes, exact semantic addresses, QSIZE value,
mailbox symbol/size/magic, common-tail hash, proof limitations, and
non-performance labels.

Commit the final checker/test, then restage and requalify exactly:

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
        firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
git commit -m "test(pmu-v14): bind executable mailbox and cleanup"
scp firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/
local_sha="$(shasum -a 256 firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py | awk '{print $1}')"
remote_sha="$(ssh gihwan 'sha256sum /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/check_pmu_completion_visibility_v14.py' | awk '{print $1}')"
test "$local_sha" = "$remote_sha"
ssh gihwan 'docker cp /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/check_pmu_completion_visibility_v14.py benchmark-runner:/work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py'
container_sha="$(ssh gihwan 'docker exec benchmark-runner sha256sum /work/selftest/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py' | awk '{print $1}')"
test "$local_sha" = "$container_sha"
```

Then run:

```bash
ssh gihwan 'set -eu
  root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE
  for b in BUILD_A BUILD_B; do for c in Q QS SQ; do
    docker exec -w /work/selftest benchmark-runner make -B \
      -f Makefile.pmu_completion_visibility_v14 V14_VARIANT="$c" \
      BUILD="/work/v14/$b/$c" check manifest
    rm -rf "$root/$b/$c"
    mkdir -p "$root/$b/$c"
    docker cp "benchmark-runner:/work/v14/$b/$c/." "$root/$b/$c/"
    python3 "$root/SOURCE/check_pmu_completion_visibility_v14.py" \
      --variant "$c" --real-elf --build-root "$root/$b/$c" \
      --manifest "$root/$b/$c/pmu_completion_visibility_v14_manifest.json"
  done; done
  python3 "$root/SOURCE/compare_declared_builds.py" \
    --left "$root/BUILD_A" --right "$root/BUILD_B" --variants Q,QS,SQ \
    --manifest-name pmu_completion_visibility_v14_manifest.json \
    --report "$root/BUILD_DETERMINISM_FINAL.json"
  (cd "$root" && find BUILD_A BUILD_B -type f -print0 | sort -z | \
    xargs -0 sha256sum) > "$root/FINAL_EVIDENCE.sha256"'
```

Expected: six `REAL_ELF PASS`, comparison `mismatches=[]`, and nonempty final
hash index, all after final-checker SHA identity.

- [ ] **Step 5: Record the canonical evidence root**

In the contract record the exact host root, container/toolchain identity, the
six manifest hashes, and SHA-256 of every map/nm/objdump/DWARF/evidence JSON.
The contract must state that paths are provenance labels; manifest determinism
is based on logical keys and content hashes.

- [ ] **Step 6: Verify and commit ARM qualification**

Create `PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md`, record all hashes/PASS
counts, then run:

```bash
git diff --check
git add firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md
git commit -m "test(pmu-v14): qualify ARM visibility images"
git tag -a pmu-completion-visibility-v14-arm-qualified \
  -m "V14 ARM executable qualified"
git status --short
```

Expected: diff check and commit succeed; final status is clean; annotated tag
resolves to the new commit.

Chunk 2 may claim firmware/ARM executable QUALIFIED only. Host and board remain
unqualified/not started.

---

## Chunk 3: Exact host ABI and classifier

### Task 10: TDD the schema-14 parser

**Files:**
- Create: `host/runner_proto_pmu_completion_visibility_v14.py`
- Create: `host/tests/test_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Write exact frame RED tests**

Freeze this literal appendix order independently in the tests:

```text
0 variant_id, 1 qsize_expected, 2 pre_program_status, 3 pre_submit_status,
4 t_submit_after_cmd, 5 t_primary_entry, 6 t_first_observation,
7 primary_result, 8 primary_iterations, 9 first_qread, 10 first_status,
11 first_q_done, 12 first_cmd_end_reached, 13 first_irq_raised, 14 first_state,
15 convergence_result, 16 convergence_iterations, 17 convergence_final_qread,
18 convergence_final_status, 19 convergence_timeout, 20 failure_phase,
21 failure_reason, 22 failure_qread, 23 failure_status, 24 installed_vector,
25 nvic_enabled_before_submit, 26 nvic_pending_after_initial_clear,
27 nvic_active_before_submit, 28 irq_triggered_before_submit,
29 nvic_pending_before_final_clear, 30 nvic_pending_after_final_clear,
31 nvic_active_after_cleanup, 32 irq_triggered_after_cleanup, 33 mailbox_valid
```

The parser may not import this test literal. Assert little-endian `uint32_t`,
header=8, base=85, appendix=34, body=119, total=127, bytes=508, schema `14`,
build `0x34314950`, and appendix[33] magic `0x5631344D` (absolute frame word
126/body word 118). Reject every offset swap,
truncation, extension, wrong CRC/schema/build/magic, and length mismatch.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest host.tests.test_pmu_completion_visibility_v14.ParserRedTests -v
```

Expected: nonzero because the parser/module is missing; preserve RED output.

- [ ] **Step 3: Implement dataclass/parser without compatibility coercion**

Parse every field explicitly. Earlier parsers keep rejecting schema14; do not
forge older IDs. An older prefix view is allowed only after complete V14 frame
validation and an independently checked immutable 85-word prefix.

- [ ] **Step 4: Run parser GREEN**

Run the Step-2 command again. Expected: canonical Q/QS/SQ PASS and every
malformed frame is rejected for its named reason.

- [ ] **Step 5: Commit parser**

```bash
git add host/runner_proto_pmu_completion_visibility_v14.py \
        host/tests/test_pmu_completion_visibility_v14.py
git commit -m "host: parse PMU completion visibility V14"
```

### Task 11: TDD the phase-validity classifier

**Files:** same parser/test files.

- [ ] **Step 1: Add the complete path-sensitive matrix and run RED**

Use separate fixtures for success; each pre-program/pre-submit reason; primary
timeout, reset, fault; convergence timeout, reset, fault; cleanup invariant;
and missing/early/stale/wrong mailbox magic. Encode these exact publications:

- success: T2/P0/P1 valid; Q has Q-only first tuple/STATUS sentinels, QS/SQ a
  full tuple; convergence valid; failure tuple invalid;
- pre-run failure: T2/P0/P1 and first/convergence invalid, STATUS-only failure
  tuple and invalid QREAD;
- primary timeout/reset/fault: T2/P0 valid, P1 and first/convergence invalid;
  Q timeout retains final QREAD plus its single diagnostic STATUS;
- convergence timeout/reset/fault: T2/P0/P1 and first tuple retained,
  convergence invalid, final/offending failure tuple retained;
- cleanup invariant: first and convergence retained plus cleanup readbacks, but
  sample invalid;
- transport failure: never a sample.

Each iteration field is `1..10000` iff its own stage succeeded
(`primary_result=OBSERVED`, `convergence_result=SUCCESS`) and zero iff that
stage is TIMEOUT/RESET/FAULT/NOT_RUN. Convergence failure retains the successful
primary count; cleanup failure retains both successful counts.
`convergence_timeout==1` iff result is TIMEOUT. Every invalid phase suppresses
category, distribution, PMU metric, and performance-like output. Q never emits
a category; QS/SQ do so only after full success.

```bash
python3 -m unittest host.tests.test_pmu_completion_visibility_v14.ClassifierRedTests -v
```

Expected: nonzero due to missing classifier rules.

- [ ] **Step 2: Implement exact validation and output shape**

Validate enums/sentinels, qsize `0x110`, stale/reset/fault masks, mailbox magic,
stock-vector Thumb identity, NVIC hard-bypass, golden/release semantics, tuple
exclusivity, and same-load fields. Valid diagnostics must expose all three
truths: `perturbed_by_convergence_tail=true`, `not_comparable_to_v13=true`,
`not_performance_metric=true`. QS/SQ success categories are exactly `Q_FIRST`,
`S5_FIRST`, or `SAME_ITERATION`.

- [ ] **Step 3: Run GREEN and commit**

```bash
python3 -m unittest host.tests.test_pmu_completion_visibility_v14 -v
git add host/runner_proto_pmu_completion_visibility_v14.py \
        host/tests/test_pmu_completion_visibility_v14.py
git commit -m "host: classify V14 observation phases"
```

Expected: zero exit and every matrix fixture behaves exactly as declared.

### Task 12: Bind manifests and artifacts

**Files:** same parser/test files.

- [ ] **Step 1: Add mutation RED tests**

From the three actual Build-A manifests, mutate variant/schema/build/QSIZE,
vector/mailbox/common-tail identity, nested proof inputs/hashes, artifact bundle
hash, manifest self-hash, and each classification truth. Reject missing, extra,
renamed, substituted, or digest-mismatched artifacts with stable reasons.

```bash
python3 -m unittest host.tests.test_pmu_completion_visibility_v14.ManifestRedTests -v
```

Expected: nonzero until verification exists.

- [ ] **Step 2: Implement canonical manifest verification**

Use canonical UTF-8 JSON (`sort_keys=true`, separators `(',', ':')`, no NaN,
trailing LF), named `v14-canonical-json-v1`. The manifest self-hash preimage is
the complete manifest with the top-level `manifest_self_hash` key omitted;
hash the canonical bytes once and store lowercase SHA-256 hex in that key.
Generator and host mutation fixtures use this identical rule. Recompute nested
evidence hashes and the logical-key artifact bundle hash; never trust stored
booleans, timestamps, or absolute paths.

- [ ] **Step 3: Replay exact Build-A manifests**

```bash
scp host/runner_proto_pmu_completion_visibility_v14.py \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/
local_parser_sha="$(shasum -a 256 host/runner_proto_pmu_completion_visibility_v14.py | awk '{print $1}')"
remote_parser_sha="$(ssh gihwan 'sha256sum /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/runner_proto_pmu_completion_visibility_v14.py' | awk '{print $1}')"
test "$local_parser_sha" = "$remote_parser_sha"
ssh gihwan 'set -eu
  for c in Q QS SQ; do
    python3 /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/runner_proto_pmu_completion_visibility_v14.py verify-manifest \
      --manifest "/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A/$c/pmu_completion_visibility_v14_manifest.json" \
      --artifact-root "/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/BUILD_A/$c"
  done'
```

Expected: SHA identity plus three `MANIFEST PASS` results.

- [ ] **Step 4: Run GREEN and exact older-schema regressions**

```bash
python3 -m unittest host.tests.test_pmu_completion_visibility_v14 -v
python3 -m unittest host.tests.test_pmu_qual_unit -v
python3 -m unittest host.tests.test_pmu_interval_v9_unit -v
python3 -m unittest host.tests.test_pmu_interval_v10_unit -v
python3 -m unittest host.tests.test_pmu_interval_v11a_unit -v
python3 -m unittest host.tests.test_pmu_completion_poll_v12_unit -v
python3 -m unittest host.tests.test_pmu_completion_poll_count_v13_unit -v
```

Expected: zero exits; older parsers accept their own schema and reject 14.
Record the actual counts rather than predicting them.

- [ ] **Step 5: Commit atomically**

```bash
git diff --check
git add host/runner_proto_pmu_completion_visibility_v14.py \
        host/tests/test_pmu_completion_visibility_v14.py
git commit -m "host: bind V14 manifests and artifacts"
git status --short
```

Expected: clean status. Host is UNIT-QUALIFIED only.

---

## Chunk 4: Fail-closed collector and categorical analyzer

### Task 13: TDD the collector state machine

**Files:**
- Create: `host/collect_pmu_completion_visibility_v14.py`
- Create: `host/tests/test_collect_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Write collector RED tests and run them**

Require exact artifact/manifest/variant identity, IDLE/PING, UART-holder gate,
run-sequence restart, raw/reread/CRC/SHA identity, mailbox magic, schema, and
phase matrix. Each cell must retain one unchanged boot ID and exactly contiguous
run IDs 1..10; inject a mid-cell boot-ID change, gap, restart, run 0, run 11,
and early/late completion as RED fixtures. Refuse collection before all gates.
Use the unique root
`<campaign>/cells/<round>-<position>-<variant>/attempt-<n>/`.

Inject failure after runs 1 and 9. The collector must move raw/reread/target/
derived/manifest/SHA and every preceding run from that attempt to
`quarantine/`, write STOP/disposition, block later cells, and leave none in
formal `samples/`. It may retry only after explicit disposition + board restore,
from run 1 on a fresh boot/new attempt. Earlier completed cells remain eligible
only if source/image/classifier/manifest/contract are byte-identical; changing
one restarts the whole campaign.

```bash
python3 -m unittest host.tests.test_collect_pmu_completion_visibility_v14 -v
```

Expected RED: nonzero because collector/state transitions are absent.

- [ ] **Step 2: Implement and run GREEN**

Import only `host.run_pmu_qual.PmuQualLink` and the framing constants/
`build_frame` from `host.runner_proto`, following the read/sequence transport
shape in `host/run_pmu_completion_poll_count_v13.py`; never import its V13
classifier verdict. Do not auto-retry or auto-increment attempts. Run the
Step-1 command; expect zero exit including
mid-cell quarantine/retry, later-cell blocking, and whole-campaign invalidation.

- [ ] **Step 3: Commit collector**

```bash
git add host/collect_pmu_completion_visibility_v14.py \
        host/tests/test_collect_pmu_completion_visibility_v14.py
git commit -m "host: collect V14 fail closed"
```

### Task 14: TDD the analyzer

**Files:**
- Create: `host/analyze_pmu_completion_visibility_v14.py`
- Create: `host/tests/test_analyze_pmu_completion_visibility_v14.py`

- [ ] **Step 1: Create decision/campaign RED fixtures and run them**

Cover all five rows: order reversal, Q-first both, same both, S5-first both,
mixed/unstable. Each has exact 9 cells x 10 with round/position/boot/attempt/run
and immutable artifact identity. Reject missing/extra/duplicate runs, partial
or prior failed attempts, unbalanced order, quarantine inclusion, later cells
collected before a retry, identity drift, multiple boot IDs in a cell, or any
cell whose run IDs are not exactly 1..10 under that single boot.

```bash
python3 -m unittest host.tests.test_analyze_pmu_completion_visibility_v14 -v
```

Expected RED: nonzero because analyzer is absent.

- [ ] **Step 2: Implement exact non-performance analysis**

Reject cross-variant cycle subtraction, latency/`T_npu`, outer PMU comparison,
and physical-simultaneity claims. Q uses `q_observation_cycles=u32(P1-P0)`.
A floor is reproduced only when the same global minimum occurs in all three Q
boots; excursion structure requires values above it in at least two boots.
Otherwise report `NOT_REPRODUCED`; pooled evidence alone is insufficient.

Read-order reversal may conclude bias dominance; same/same says only no gap was
resolved. Q-first/Q-first or S5-first/S5-first emits
`CONTROL_REQUIRED_NO_FINAL_ORDERING`: a fresh V14 bit5-only S5 control is
mandatory before any visibility-order claim. Historical V13 bit1 never
satisfies it. The same control-required verdict is mandatory when Q reports
`REPRODUCED` floor/excursion but either dual variant does not, or Q reports
`NOT_REPRODUCED` while either dual variant does; this deterministic qualitative
classification disagreement is the dual-read-perturbation trigger. Add a RED
fixture for both directions. Mixed remains unresolved. Report per-boot category
counts, raw tuples, and convergence-tail diagnostics without promotion.

- [ ] **Step 3: Run GREEN and commit separately**

```bash
python3 -m unittest host.tests.test_analyze_pmu_completion_visibility_v14 -v
git diff --check
git add host/analyze_pmu_completion_visibility_v14.py \
        host/tests/test_analyze_pmu_completion_visibility_v14.py
git commit -m "host: analyze V14 visibility ordering"
```

Expected: zero exit for all five rows and nonzero verdicts for malformed sets.
Finally run collector and analyzer suites together and require both zero.

---

## Chunk 5: Full pre-board qualification

### Task 15: Run the complete local and ARM regression matrix

**Files:** no functional edits unless a scoped regression defect is found.

- [ ] **Step 1: Run syntax and every V14 suite**

```bash
python3 -m py_compile firmware/patches/patch_pmu_completion_visibility_v14.py \
  firmware/Selftest_pmu_diag/check_pmu_completion_visibility_v14.py \
  host/runner_proto_pmu_completion_visibility_v14.py \
  host/collect_pmu_completion_visibility_v14.py \
  host/analyze_pmu_completion_visibility_v14.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_visibility_v14.py
python3 firmware/Selftest_pmu_diag/test_makefile_pmu_completion_visibility_v14.py
python3 -m unittest host.tests.test_compare_declared_builds -v
python3 -m unittest host.tests.test_pmu_completion_visibility_v14 -v
python3 -m unittest host.tests.test_collect_pmu_completion_visibility_v14 -v
python3 -m unittest host.tests.test_analyze_pmu_completion_visibility_v14 -v
```

Expected: all zero exit; capture exact counts/output.

- [ ] **Step 2: Run exact V8-V13/CFG/DIAG regressions**

```bash
for t in \
 firmware/Selftest_pmu_diag/test_check_pmu_qual.py \
 firmware/Selftest_pmu_diag/test_check_pmu_interval_v9.py \
 firmware/Selftest_pmu_diag/test_check_pmu_interval_v10.py \
 firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py \
 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py \
 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py \
 firmware/Selftest_pmu_diag/test_check_pmu_cfg.py; do python3 "$t"; done
python3 -m unittest host.tests.test_pmu_qual_unit -v
python3 -m unittest host.tests.test_pmu_interval_v9_unit -v
python3 -m unittest host.tests.test_pmu_interval_v10_unit -v
python3 -m unittest host.tests.test_pmu_interval_v11a_unit -v
python3 -m unittest host.tests.test_pmu_completion_poll_v12_unit -v
python3 -m unittest host.tests.test_pmu_completion_poll_count_v13_unit -v
python3 -m unittest host.tests.test_pmu_cfg_unit \
  host.tests.test_pmu_cfg_analyzer_unit host.tests.test_pmu_diag_unit -v
```

Expected: all zero exit; record each actual PASS count.

- [ ] **Step 3: Rebuild and compare exact canonical roots**

Run the final SHA-matched staged toolchain:

```bash
ssh gihwan 'set -eu
  root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE
  rm -rf "$root/BUILD_FINAL_A" "$root/BUILD_FINAL_B"
  for b in BUILD_FINAL_A BUILD_FINAL_B; do for c in Q QS SQ; do
    docker exec -w /work/selftest benchmark-runner make \
      -f Makefile.pmu_completion_visibility_v14 V14_VARIANT="$c" \
      BUILD="/work/v14/$b/$c" clean all check manifest
    mkdir -p "$root/$b/$c"
    docker cp "benchmark-runner:/work/v14/$b/$c/." "$root/$b/$c/"
  done; done
  python3 "$root/SOURCE/compare_declared_builds.py" \
    --left "$root/BUILD_FINAL_A" --right "$root/BUILD_FINAL_B" \
    --variants Q,QS,SQ --manifest-name pmu_completion_visibility_v14_manifest.json \
    --report "$root/BUILD_FINAL_A_VS_B.json"
  python3 "$root/SOURCE/compare_declared_builds.py" \
    --left "$root/BUILD_FINAL_A" --right "$root/BUILD_A" \
    --variants Q,QS,SQ --manifest-name pmu_completion_visibility_v14_manifest.json \
    --report "$root/BUILD_FINAL_A_VS_CANONICAL_A.json"'
```

Expected: both reports `mismatches=[]`; any mismatch is STOP, not normalized.

- [ ] **Step 4: Enforce freeze and defect workflow**

```bash
git diff --check
git diff --exit-code d840ed2 -- firmware/Selftest_pmu firmware/Selftest_pmu_diag/runner_pmu_diag_main.c \
  firmware/Drivers host/runner_proto_pmu_completion_poll_v12.py \
  host/runner_proto_pmu_completion_poll_count_v13.py
```

Expected: zero. Any regression defect STOPs qualification; add a named RED
test, make one scoped fix/commit, rebuild both roots, rerun the whole matrix,
and repeat both reviews. Never bless an unexplained failure.

- [ ] **Step 5: Freeze and commit the exact pre-board candidate before review**

Create `docs/superpowers/plans/2026-08-15-pmu-completion-visibility-v14-board.md`
from the existing qualification procedure with exact read-only preflight,
backup, deploy, per-cell boot/run, STOP/quarantine, finally-style restore,
PING/IDLE/errors, USB_OFF, mount, and root-inclusive UART commands. No
credentials, `sudo -S`, placeholders, or alternative command paths. From this
point any runbook byte change invalidates security approval. Update
`PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md` with canonical Q/QS/SQ APP,
VECTORS, DDR, ELF, manifest, generated, common-tail, mailbox, runner-wire, final
comparison, and runbook hashes. Then freeze the review target:

```bash
git diff --check
git add firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md \
  docs/superpowers/plans/2026-08-15-pmu-completion-visibility-v14-board.md
git commit -m "docs(pmu-v14): prepare preboard candidate"
test -z "$(git status --porcelain)"
```

### Task 16: Independent correctness and security review

**Files:** review the full implementation plus the exact board runbook, then
make only scoped fixes if required.

- [ ] **Step 1: Request correctness review**

Focus on QSIZE access legality, read-order dataflow, same-tuple convergence,
failure egress, mailbox publication, phase matrix, and campaign classifier.
Save `PREBOARD_STAGE/REVIEWS/correctness.json` containing reviewer/task ID,
reviewed commit, artifact-bundle hashes, verdict `APPROVED|REJECTED`, severity,
and findings.

- [ ] **Step 2: Request security/safety review**

Focus on UART/parser bounds, manifest trust, path traversal, unsafe shell/
credential use, stale mailbox, and destructive board-operation boundaries.
Save the same fields in `REVIEWS/security.json`; medium+ finding rejects.
It must include the reviewed board-runbook SHA-256 and explicitly approve its
destructive-operation/restore boundaries.

- [ ] **Step 3: Fix only verified findings with new regression tests**

Re-run the affected chunk and full matrix after every change.

- [ ] **Step 4: Repeat reviews until approved**

Do not create a pre-board anchor with an open correctness or medium+ security
finding. Verify both JSONs name the exact final commit, artifact bundles, and
runbook SHA; any subsequent change triggers both reviews again. The final
approval index hashes both JSONs without modifying the reviewed tree.

### Task 17: Verify and tag the reviewed pre-board anchor

**Files:** no tracked edits after approval.

- [ ] **Step 1: Recheck the frozen contract**

Do not edit it. Verify the Task-15 commit already binds all Q/QS/SQ evidence and
is exactly the commit named by both reviews.

- [ ] **Step 2: Freeze the reviewed board runbook**

Do not change the reviewed bytes. Verify its SHA-256 matches the contract and
both approval JSONs; it is the sole Chunk-6 command authority.

- [ ] **Step 3: Run exact final document/hash verification**

```bash
scp firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md \
  docs/superpowers/plans/2026-08-15-pmu-completion-visibility-v14-board.md \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/SOURCE/
ssh gihwan 'set -eu
  root=/home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE
  python3 "$root/SOURCE/check_pmu_completion_visibility_v14.py" verify-preboard \
    --contract "$root/SOURCE/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md" \
    --artifact-root "$root/BUILD_FINAL_A" \
    --runbook "$root/SOURCE/2026-08-15-pmu-completion-visibility-v14-board.md" \
    --correctness-review "$root/REVIEWS/correctness.json" \
    --security-review "$root/REVIEWS/security.json" \
    --approval-index-out "$root/PREBOARD_APPROVAL_INDEX.json"'
```

Expected: `PREBOARD DOCUMENT PASS`; every Q/QS/SQ hash resolves, runbook/review
hashes match, and no placeholder remains. The verifier writes canonical remote
`PREBOARD_APPROVAL_INDEX.json` binding commit, artifacts, runbook, and reviews.

- [ ] **Step 4: Prove provenance and tag the unchanged reviewed commit**

```bash
test "$(git branch --show-current)" = pmu-completion-visibility-v14-impl
git merge-base --is-ancestor d49fa5f HEAD
git merge-base --is-ancestor 3a32b17 HEAD
git merge-base --is-ancestor d840ed2 HEAD
ARM_ANCHOR="$(git rev-list -n1 pmu-completion-visibility-v14-arm-qualified)"
git merge-base --is-ancestor "$ARM_ANCHOR" HEAD
test -z "$(git status --porcelain)"
! git rev-parse -q --verify refs/tags/pmu-completion-visibility-v14-preboard
approval_sha="$(ssh gihwan 'sha256sum /home/gihwan/mps4/PMU_COMPLETION_VISIBILITY_V14_PREBOARD_STAGE/PREBOARD_APPROVAL_INDEX.json' | awk '{print $1}')"
printf 'V14 pre-board qualified\napproval-index-sha256: %s\n' "$approval_sha" > /tmp/v14_preboard_tag_message.txt
git tag -a pmu-completion-visibility-v14-preboard -F /tmp/v14_preboard_tag_message.txt
test "$(git rev-parse pmu-completion-visibility-v14-preboard^{commit})" = "$(git rev-parse HEAD)"
test -z "$(git status --porcelain)"
```

Only now may status become `PREBOARD QUALIFIED`. Board deployment still needs
an explicit GO.

---

## Chunk 6: Board campaign after explicit GO

The sole board-command authority is
`docs/superpowers/plans/2026-08-15-pmu-completion-visibility-v14-board.md` at
the SHA frozen in the pre-board contract. Before board access, create and hash
`BOARD_GO.json` binding explicit operator GO, pre-board commit/tag, runbook SHA,
SSH host identity, Q/QS/SQ artifact bundles, and collector/analyzer hashes. Any
post-GO mutation is STOP and requires a new GO record.

### Task 18: Restore known-good liveness and deploy one fixed cell

**Files:** no tracked changes; write timestamped evidence only on the authorized
host.

- [ ] **Step 1: Execute the frozen preflight and backup runbook**

Require mount zero, block write holders zero, a byte-exact recoverable original
backup, DDR PASS, CPUWAIT clear, PING 3/3, IDLE, and protocol errors zero. A
root-inclusive UART-holder check is a TOCTOU boundary: transition/capture must
follow immediately with no serial tool or unrelated command in between.

- [ ] **Step 2: Execute one complete fixed-cell state machine**

For this and every later cell, use the identical runbook path: verify fixed
source hashes -> mount/write gate -> deploy -> destination APP/VECTORS/DDR
hashes -> unmount -> USB_OFF and `/dev/sdb` absent -> immediate root-inclusive
UART gate -> fresh full boot -> DDR/CPUWAIT -> protocol identity/IDLE/errors ->
ten sequential runs. Record every gate. A cell missing any gate is ineligible.

- [ ] **Step 3: Fail closed on any invalid result**

Quarantine the whole attempt before reboot and block later acquisition. Enter
the finally-style restore path on invalid sample, interruption, command error,
operator abandonment, or ordinary success; never leave a diagnostic image as
an implicit terminal state.

### Task 19: Complete the balanced nine-cell matrix

**Files:** evidence only.

- [ ] **Step 1: Follow Q->QS->SQ, QS->SQ->Q, SQ->Q->QS**

Each position is one fresh boot and exactly ten uninterrupted valid runs using
the identical Task-18 state machine and fixed GO identities.

- [ ] **Step 2: Verify every raw/reread/archive immediately**

For success require mailbox/phase terms, golden CRC, PMU validity, overflow
zero, variant identity, and terminal release. For an invalid sample require its
exact phase-matrix/mailbox evidence, absence of forbidden cleanup (including no
`CMD=0xC` on pre-cleanup failure), quarantine, and zero dataset promotion;
retained PMU/release fields may be invalid by contract. Always preserve raw.

- [ ] **Step 3: Dispose and retry only a failed cell**

Before reboot, quarantine all runs from the failed attempt. Restore the known-
good image/liveness, record disposition, then restart at run 1 with a new
attempt/fresh boot. Later cells remain blocked. Any code/image/host/manifest/
contract/runbook change restarts the entire campaign and requires new GO.

- [ ] **Step 4: Run the frozen analyzer**

Expected: exactly 90 eligible samples and one predeclared interpretation branch
or explicit unresolved/control-required output.

### Task 20: Restore and freeze board evidence

**Files:**
- Modify after evidence exists: `firmware/Selftest_pmu_diag/PMU_COMPLETION_VISIBILITY_DIAG_V14_CONTRACT.md`

- [ ] **Step 1: Always execute final restore**

Restore original APP/VECTORS/DDR byte-exact, then require DDR/CPUWAIT, PING 3/3
IDLE/errors zero, USB_OFF, `/dev/sdb` absent, mount zero, and immediate final
root-inclusive UART-holder zero. This runs for success and every early exit.

- [ ] **Step 2: Build and verify the evidence index**

Index GO, preflight, backup/destination hashes, every USB/mount/UART transition,
per-cell boot gates, raw/reread/derived/manifests, STOP/disposition/quarantine,
analysis, restore, and final holder checks. Recompute every listed SHA and then
hash the index itself.

- [ ] **Step 3: Commit/tag diagnostic evidence only**

Use annotated tag `pmu-completion-visibility-v14-board-evidence`. Keep
Production END_ONLY frozen and MLEK blocked regardless of result.

---

## Completion labels

```text
after Chunk 1  firmware source contract / generator UNIT-QUALIFIED
after Chunk 2  ARM executable QUALIFIED; host NOT QUALIFIED
after Chunk 4  host UNIT-QUALIFIED; board NOT STARTED
after Chunk 5  PREBOARD QUALIFIED
after Chunk 6  BOARD EVIDENCE COMPLETE for diagnostic scope only

Production END_ONLY  FROZEN throughout
MLEK                 BLOCKED throughout
```
