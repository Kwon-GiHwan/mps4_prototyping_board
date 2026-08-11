# PMU Completion Poll V12 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic-only schema-12 image that keeps the stock U85 vector and peripheral completion semantics, hard-disables NPU0 IRQ delivery, observes completion with one minimal STATUS polling helper, and determines whether the V11-A floor/excursion structure survives without IRQ/NVIC/exception servicing.

**Architecture:** Generate a private V12 runner/vendor copy from the same frozen raw inputs as V11-A. Replace the frozen `NVIC_EnableIRQ` site with a disable/clear/verify precondition and replace the one `wait_for_irq()` callsite with a named non-inlined polling helper plus proof-friendly success/timeout blocks. A new final-ELF gate proves the successful STATUS dataflow, path-specific two-versus-one `CMD=2` semantics, stock vector installation, NVIC hard-bypass, V11 isolation, and every retained PMU/golden/release contract.

**Tech Stack:** Cortex-M85 Thumb-2 C firmware, Arm GNU Toolchain, CMSIS NVIC API, Python 3 standard library, existing MPS4 UART/PMU qualification harness, objdump/nm/map final-ELF analysis.

---

## File structure

Create V12-specific files only:

- `firmware/Makefile.pmu_completion_poll_v12` — isolated generated-source build graph.
- `firmware/patches/patch_pmu_completion_poll_v12.py` — hash-pinned runner/vendor generator.
- `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md` — frozen implementation and interpretation contract.
- `firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py` — source, CFG, final-ELF, artifact, and manifest gate.
- `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py` — positive and deliberate-mutation firmware tests.
- `host/runner_proto_pmu_completion_poll_v12.py` — schema-12 ABI, decode, and validity classifier.
- `host/run_pmu_completion_poll_v12.py` — fail-closed one-sample collector.
- `host/analyze_pmu_completion_poll_v12.py` — one-sample and 3x10 distribution analyzer.
- `host/tests/test_pmu_completion_poll_v12_unit.py` — host parser/collector/analyzer tests.

Modify documentation only after the implementation is verified:

- `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md` — freeze real build evidence.
- `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md` — project state and next actions.
- `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md` — supervisory decision/evidence record.

Do not modify V11-A, V10, V9, V8, CFG, DIAG, Production END_ONLY, their build files, or their frozen artifacts. Do not add an assembly veneer.

Reference the approved design throughout implementation:

- `docs/superpowers/specs/2026-08-11-pmu-completion-poll-v12-design.md`
- final reviewed design commit `27cf1a2`
- V11-A post-board fork point `f1948bcda5232c89f3468585a4099bc2f94ae300`

---

## Chunk 1: Firmware RED contract and generator

### Task 1: Establish the failing V12 firmware contract

**Files:**
- Create: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py`
- Test absent: `firmware/patches/patch_pmu_completion_poll_v12.py`
- Test absent: `firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py`

- [ ] **Step 1: Mark the RED test file before writing**

Run:

```bash
codex-mark-used firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
```

Expected: exit zero.

- [ ] **Step 2: Write generator fixtures from the frozen vendor shape**

Include minimal source fixtures containing:

```c
NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
NVIC_EnableIRQ(NPU0_IRQn);

read_val = read_reg(NPU_REG_CMD);
write_reg(NPU_REG_CMD, read_val | 0x00000001);
wait_for_irq();
read_val = read_reg(NPU_REG_QREAD);
write_reg(NPU_REG_CMD, 0x00000002);
```

Assert the future generator must consume each enable and wait callsite exactly once, retain the stock ISR body, reject an input-hash mismatch, and never accept V11 generated input.

- [ ] **Step 3: Add positive semantic fixtures**

Model a proof-friendly final path with:

```text
stock vector install
Disable -> initial ClearPending -> readback verify
submit -> T2 -> direct helper call -> direct result branch
success: history <- successful status; CMD2; QREAD; CMD2; verify
timeout: sticky timeout; extra STATUS/report; QREAD; CMD2; verify
common final pending cleanup -> verify pending=0/active=0/irq=false
-> CMD0 -> H-PRINTF -> CMD0xC
```

Include one separate non-inlined helper symbol with P0/P1/P2, one static STATUS load site, mask `0x02`, and no helper side effect beyond the approved list.

- [ ] **Step 4: Add the full deliberate-mutation matrix**

Create negative fixtures for all 27 cases in the design, including:

- missing/moved/extra success CMD2;
- missing/duplicate timeout CMD2;
- helper CMD write;
- retained `NVIC_EnableIRQ` followed by a later Disable;
- direct ISER set;
- V11 veneer vector or reachable J0/I0/T3;
- success STATUS reread or wrong history-mask provenance;
- P1 loop-back or timeout fall-through;
- wrong completion mask;
- transient reachable `irq_triggered=true`;
- helper inlining/cloning/tail-call/indirect call;
- early success/timeout merge, indirect branch, or IT-predicated CMD store;
- extra helper MMIO, nested call, barrier, or per-iteration store.

- [ ] **Step 5: Run the RED test**

Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
```

Expected: fail with `ModuleNotFoundError` for the V12 patcher/checker, not a fixture syntax error.

- [ ] **Step 6: Commit the RED contract**

```bash
git add firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
git commit -m "test: define PMU completion poll V12 firmware contract"
```

### Task 2: Implement the frozen-input generator and contract

**Files:**
- Create: `firmware/patches/patch_pmu_completion_poll_v12.py`
- Create: `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py`

- [ ] **Step 1: Mark the new files before writing**

```bash
codex-mark-used firmware/patches/patch_pmu_completion_poll_v12.py
codex-mark-used firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md
```

- [ ] **Step 2: Add the hash-pinned generator shell**

Copy the V11-A generator structure without copying V11-generated code. Freeze:

```python
RUNNER_SHA256 = "69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b"
VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
SCHEMA_VERSION = 12
BUILD_ID = 0x32314950
```

Every source substitution uses an exact-one helper and returns named patch counts in the producer manifest.

- [ ] **Step 3: Replace the frozen enable site, not merely supplement it**

Generate this logical shape at the original `NVIC_EnableIRQ(NPU0_IRQn)` site:

```c
irq_triggered = false;
NVIC_DisableIRQ(NPU0_IRQn);
NVIC_ClearPendingIRQ(NPU0_IRQn);
v12_installed_vector = NVIC_GetVector(NPU0_IRQn);
v12_nvic_enabled_before_submit = NVIC_GetEnableIRQ(NPU0_IRQn);
v12_nvic_pending_after_initial_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
v12_nvic_active_before_submit = NVIC_GetActive(NPU0_IRQn);
v12_irq_triggered_before_submit = irq_triggered ? 1U : 0U;
```

Derive a function-local `preflight_ok` from these already approved wire fields.
If it is false, return nonzero before NPU submit. Do not add a sixteenth V12
wire field and do not leave the stock enable call reachable; the host derives
the preflight failure from the existing 15 raw fields.

- [ ] **Step 4: Implement the named non-inlined poll helper**

Use a direct volatile STATUS pointer so the loop cannot contain a `read_reg()` call:

```c
__attribute__((noinline))
static uint32_t v12_poll_completion(void)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);

    pmu_completion_poll_v12_t_poll_entry = DWT->CYCCNT;
    for (uint32_t i = 0U; i < 10000U; ++i) {
        uint32_t status = *status_reg;
        if ((status & 0x02U) != 0U) {
            pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
            pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
            return status;
        }
    }
    return 0U;
}
```

P2 is the final timestamp before return. If the compiler emits any call, extra loop MMIO/store, clone, inlining, tail-call substitution, or unprovable dataflow, fix the code shape rather than weakening the gate.

- [ ] **Step 5: Generate explicit, non-merging success and timeout regions**

Replace the one `wait_for_irq()` callsite with code equivalent to:

```c
uint32_t v12_status = v12_poll_completion();

/* SUCCESS=1, TIMEOUT=2: compute explicitly without a control-flow branch. */
v12_poll_result = V12_POLL_TIMEOUT - ((v12_status & 0x02U) >> 1);

if (v12_poll_result == V12_POLL_SUCCESS) {
    v12_status_at_success = v12_status;
    irq_history_mask = (uint16_t)(v12_status >> 16);
    write_reg(NPU_REG_CMD, 0x00000002);       /* ISR-equivalent #1 */
    read_val = read_reg(NPU_REG_QREAD);
    write_reg(NPU_REG_CMD, 0x00000002);       /* stock caller #2 */
    /* unchanged QREAD verification */
    goto v12_common_cleanup;
}

v12_poll_result = V12_POLL_TIMEOUT;
irq_never_triggered = true;
printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n",
       read_reg(NPU_REG_STATUS));
read_val = read_reg(NPU_REG_QREAD);
write_reg(NPU_REG_CMD, 0x00000002);           /* stock caller only */
/* unchanged QREAD verification */
goto v12_common_cleanup;
```

The real generated blocks may use local labels rather than literal `goto`, but final ELF must retain one direct result branch, distinct path blocks through QREAD verification, and one later common cleanup. Do not set `irq_triggered=true` anywhere reachable.

Declare the serialized `v12_poll_result` storage volatile so optimization
cannot bypass the explicit stored result and branch directly on
`v12_status`. The final-ELF gate must prove the caller's one success/timeout
edge is controlled by the loaded explicit result field, while the helper's
returned status independently retains the approved STATUS provenance.

- [ ] **Step 6: Add final NVIC cleanup before the retained terminal path**

At the common block after path-specific QREAD verification:

```c
v12_nvic_pending_before_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
NVIC_ClearPendingIRQ(NPU0_IRQn);
v12_nvic_pending_after_final_clear = NVIC_GetPendingIRQ(NPU0_IRQn);
v12_nvic_active_after_cleanup = NVIC_GetActive(NPU0_IRQn);
v12_irq_triggered_after_cleanup = irq_triggered ? 1U : 0U;
```

Then retain `CMD=0`, the H-PRINTF pre-release hook, authoritative PMU snapshot/disable, and vendor `CMD=0xC` ordering.

- [ ] **Step 7: Extend runner schema and serialization**

Add schema 12/build ID `0x32314950`, the 15 approved V12 fields, retained PMU/golden fields, and explicit invalid emission when `poll_result != SUCCESS`. Zero P1/P2 at run reset and leave them zero on timeout.

- [ ] **Step 8: Write the implementation contract**

Copy the approved semantics from `docs/superpowers/specs/2026-08-11-pmu-completion-poll-v12-design.md` without weakening language. Include diagnostic-only labels, path-specific CMD counts, exact STATUS provenance, poll-limit caveat, sticky-timeout fresh-boot rule, and frozen exclusions.

- [ ] **Step 9: Run generator tests and syntax checks**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
python3 -m py_compile \
  firmware/patches/patch_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
```

Expected: generator tests progress to checker-related RED failures; `py_compile` passes.

- [ ] **Step 10: Commit the generator**

```bash
git add firmware/patches/patch_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
git commit -m "feat: add PMU completion poll V12 generator"
```

### Task 3: Implement the final-ELF and manifest attack gate

**Files:**
- Create: `firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py`

- [ ] **Step 1: Mark the checker before writing**

```bash
codex-mark-used firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py
```

- [ ] **Step 2: Add a bounded Thumb basic-block parser**

Reuse instruction/literal/register helpers from the existing checkers, but add
only the minimal direct-branch graph required by V12. Lock these interfaces in
unit tests before implementing them:

- `split_basic_blocks(insns) -> dict[int, BasicBlock]`: create starts at the
  function entry, every resolved direct-branch target, and every conditional
  fallthrough; reject a target outside the named function.
- `build_direct_edges(blocks) -> dict[int, tuple[int, ...]]`: emit only direct
  unconditional, direct conditional, and fallthrough edges; reject indirect
  control flow and IT-predicated CMD stores.
- `reachable_blocks(entry, edges) -> set[int]`: perform a worklist traversal
  bounded by the number of blocks; reject every cycle except the one admitted
  poll-loop back edge inside the named helper.
- `enumerate_result_paths(callsite, result_branch, merge)`: require exactly
  one direct caller branch, one success successor, one timeout successor, and
  a first common block only after both path-local QREAD-verification blocks.

Reject indirect branches, IT-predicated CMD stores, unrecognized terminators, helper clones, early merges, and cycles outside the one polling back-edge. Do not attempt a general interprocedural CFG engine.

- [ ] **Step 3: Prove the helper boundary and loop semantics**

Require one named non-inlined helper symbol, one direct callsite, one P0/P1/P2 store site, exact DWT provenance, one loop STATUS load at resolved address `0x50004004`, mask `0x02`, a register-local bounded counter, no loop memory store, and no nested call or forbidden MMIO.

- [ ] **Step 4: Prove successful STATUS dataflow**

Trace the branch-driving STATUS load through:

```text
STATUS load -> bit 0x02 test -> helper return register
-> caller status_at_success serialization
-> shift by 16 -> irq_history_mask store
```

Reject any reread, constant substitution, stale value, overwrite, timeout STATUS, or unrelated reaching definition.

- [ ] **Step 5: Prove path-specific peripheral sequencing**

Resolve every store of value two to exact NPU CMD. On the success path require exactly:

```text
P2 < return < history store < CMD2 #1 < QREAD < CMD2 #2 < QREAD verify
```

On the timeout path require exactly:

```text
timeout STATUS/report < QREAD < CMD2 < QREAD verify
```

Both paths merge only afterward into final pending cleanup, CMD0, H-PRINTF, PMU disable, and CMD0xC.

- [ ] **Step 6: Prove the hard-bypass and side-effect boundary**

Prove exact stock vector Thumb value, replacement of the frozen Enable site, zero reachable NPU0 ISER-set write, exact Disable/initial Clear/final Clear NVIC accesses, no reachable V11 veneer/J0/I0/T3, and only one reachable `irq_triggered` store whose value is false at run start.

- [ ] **Step 7: Freeze the producer manifest shape**

Include frozen input hashes, schema/build identity, generated file hashes,
callsite/helper addresses, STATUS/CMD/QREAD addresses, branch/block identities,
vector target, NVIC access addresses/masks, both path CMD store addresses,
P0/P1/P2 stores, H-PRINTF LR/window, vendor release, PMU/golden identity, and
all gate booleans. Critical named booleans must include at least
`helper_one_direct_callsite`, `status_success_dataflow_exact`,
`history_mask_from_success_status`, `success_cmd2_count_2`,
`timeout_cmd2_count_1`, `nvic_enable_replaced`, and
`irq_triggered_true_reachable_false`.

- [ ] **Step 8: Make every deliberate mutation fail**

Run all positive and 27 negative fixtures. Every mutation must fail for its intended reason, not an earlier fixture parse error.

- [ ] **Step 9: Run firmware checks**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
python3 -m py_compile \
  firmware/patches/patch_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
git diff --check
```

Expected: all V12 firmware tests pass, `py_compile` exits zero, and `git diff --check` prints nothing.

- [ ] **Step 10: Commit the firmware gate**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
git commit -m "test: gate PMU completion poll V12 ELF paths"
```

---

## Chunk 2: Isolated build and host schema

### Task 4: Add the isolated ARM build graph

**Files:**
- Create: `firmware/Makefile.pmu_completion_poll_v12`

- [ ] **Step 1: Mark and create the Makefile**

```bash
codex-mark-used firmware/Makefile.pmu_completion_poll_v12
```

Clone the V11-A graph structure but remove the assembly object and use only V12 names, generated C sources, build directory `build_pmu_completion_poll_v12/`, schema define `PMU_COMPLETION_POLL_DIAG_V12`, and the V12 checker.

- [ ] **Step 2: Verify local graph text without pretending to build**

The local repository lacks the full FI101 source tree. Check targets/dependencies by inspection and unit tests only; do not report a local ARM build.

```bash
rg -n "v11a|pmu_interval|entry\.S" firmware/Makefile.pmu_completion_poll_v12
rg -n "^BUILD  := build_pmu_completion_poll_v12$|^PATCHER := patches/patch_pmu_completion_poll_v12.py$|^GATE    := Selftest_pmu_diag/check_pmu_completion_poll_v12.py$|PMU_COMPLETION_POLL_DIAG_V12" \
  firmware/Makefile.pmu_completion_poll_v12
```

Expected: the first command has no output; the second finds the exact V12
build directory, patcher, checker, and profile define.

- [ ] **Step 3: Commit the build graph**

```bash
git add firmware/Makefile.pmu_completion_poll_v12
git commit -m "build: add PMU completion poll V12 image"
```

### Task 5: Establish failing host contract tests

**Files:**
- Create: `host/tests/test_pmu_completion_poll_v12_unit.py`
- Test absent: `host/runner_proto_pmu_completion_poll_v12.py`
- Test absent: `host/run_pmu_completion_poll_v12.py`
- Test absent: `host/analyze_pmu_completion_poll_v12.py`

- [ ] **Step 1: Mark and write the RED host test**

```bash
codex-mark-used host/tests/test_pmu_completion_poll_v12_unit.py
```

Cover exact schema length/build ID, V8-V11 rejection, all 15 new fields,
retained PMU/golden fields, modulo wrap, both identities, timeout invalidation,
pending-before diagnostic-only behavior, vector/NVIC/flag validity, no invalid
archive write, manifest producer-consumer round-trip, and exact 3x10
cardinality. Add transport negatives for truncation, extra bytes, record CRC,
header/body disagreement, schema/build mismatch, command/sequence mismatch,
and raw-reread disagreement.

- [ ] **Step 2: Add campaign-stop tests**

Simulate a timeout at boot/run `(2, 4)` and require:

- sample not written as valid;
- no derived diagnostic field emitted;
- collector returns a distinct timeout/abort outcome;
- orchestrator refuses runs `(2, 5..10)`;
- a new full boot is required before collection resumes.

- [ ] **Step 3: Run RED**

```bash
python3 host/tests/test_pmu_completion_poll_v12_unit.py
```

Expected: `ModuleNotFoundError` for the absent V12 host module.

- [ ] **Step 4: Commit the RED host contract**

```bash
git add host/tests/test_pmu_completion_poll_v12_unit.py
git commit -m "test: define PMU completion poll V12 host contract"
```

### Task 6: Implement parser, collector, and analyzer

**Files:**
- Create: `host/runner_proto_pmu_completion_poll_v12.py`
- Create: `host/run_pmu_completion_poll_v12.py`
- Create: `host/analyze_pmu_completion_poll_v12.py`
- Modify: `host/tests/test_pmu_completion_poll_v12_unit.py`

- [ ] **Step 1: Mark implementation files**

```bash
codex-mark-used host/runner_proto_pmu_completion_poll_v12.py
codex-mark-used host/run_pmu_completion_poll_v12.py
codex-mark-used host/analyze_pmu_completion_poll_v12.py
```

- [ ] **Step 2: Implement schema-12 decode and classifier**

Use schema `12`, build ID `0x32314950`, exact body length, CRC/header-body agreement, retained V11/V8 gates, and these derivations:

```python
d0 = (p0 - t2) & 0xFFFFFFFF
d1 = (p1 - p0) & 0xFFFFFFFF
d2 = (p2 - p1) & 0xFFFFFFFF
submit_to_observed = (p1 - t2) & 0xFFFFFFFF
p2_from_submit = (p2 - t2) & 0xFFFFFFFF
```

Require positive half-range deltas and:

```python
((d0 + d1) & 0xFFFFFFFF) == submit_to_observed
((d0 + d1 + d2) & 0xFFFFFFFF) == p2_from_submit
```

- [ ] **Step 3: Encode fail-closed validity**

Require poll success, successful status bit `0x02`, exact stock vector, all
start/final NVIC/flag gates, frozen manifest/callsite/artifacts, PMU validity,
no overflow, stable reads, golden CRC, H-PRINTF/release, MMIO counts, and raw
reread identity. On success P0/P1/P2 must all be nonzero and pass half-range
ordering plus both modular identities. `pending_before_final_clear` accepts
either 0 or 1. Timeout must leave P1/P2 zero/invalid and emits no
`submit_to_status_completion_observed_cycles`; P0 must still be nonzero because
the helper entered before exhausting its bounded poll loop.

- [ ] **Step 4: Implement one-sample collection without invalid writes**

Parse and classify before opening the destination path. On timeout, write no
sample or forensic archive file, return the distinct campaign-abort outcome,
and never append to the valid sample file. UART/console diagnostics may be
reported to the operator in memory/stdout but are not persisted by the V12
collector.

- [ ] **Step 5: Implement the 3x10 analyzer**

Require three distinct boot IDs, sequences `1..10` within each boot, 30 valid samples, and fixed manifest/artifact identity. Report min/max/median/MAD/IQR/CV, per-boot median, within-boot CV, between-boot spread, exact modes/frequencies, hard-floor count, and excursion count.

Output only `submit_to_status_completion_observed_cycles` and explicit interpretation labels:

```text
DIAGNOSTIC ONLY
NOT NUMERICALLY COMPARABLE TO V11-A
NOT LATENCY / NOT T_npu / NOT PRODUCTION / NOT MLEK
```

- [ ] **Step 6: Make the host suite GREEN**

```bash
python3 host/tests/test_pmu_completion_poll_v12_unit.py
python3 -m py_compile \
  host/runner_proto_pmu_completion_poll_v12.py \
  host/run_pmu_completion_poll_v12.py \
  host/analyze_pmu_completion_poll_v12.py \
  host/tests/test_pmu_completion_poll_v12_unit.py
```

Expected: every test passes and `py_compile` exits zero.

- [ ] **Step 7: Commit the host path**

```bash
git add host/runner_proto_pmu_completion_poll_v12.py \
  host/run_pmu_completion_poll_v12.py \
  host/analyze_pmu_completion_poll_v12.py \
  host/tests/test_pmu_completion_poll_v12_unit.py
git commit -m "feat: add PMU completion poll V12 host path"
```

---

## Chunk 3: Real ARM proof, regression, and pre-board freeze

### Task 7: Build twice in the pinned remote ARM environment

**Files:**
- Modify V12 frozen manifest/hash constants only after observing real outputs.
- Modify `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md` with reproducibility evidence.

- [ ] **Step 1: Run read-only remote preflight**

Verify the running container, both frozen raw inputs inside the authoritative
container, host disk space, and direct-container execution boundary. The host
runner source is known to differ and must not be used as the generator input.
Do not touch board, SD, USB, UART, or MCC.

```bash
ssh gihwan 'set -eu
test "$(docker inspect -f "{{.State.Running}}" benchmark-runner)" = true
docker exec -w /work/selftest benchmark-runner sha256sum \
  Selftest_pmu_diag/runner_pmu_diag_main.c \
  Drivers/u85_driver/u85.c
docker exec -w /work/selftest benchmark-runner test -d Device_SSE-320
docker exec -w /work/selftest benchmark-runner test -d LinkScripts
df -Pk /home/gihwan/mps4
docker inspect -f "{{json .Mounts}}" benchmark-runner'
```

Expected container hashes, in order:

```text
69cab8c48a2248d0cc0b883a2bc651efa8eb8867c86369051ebc99cc5ee5a88b  Selftest_pmu_diag/runner_pmu_diag_main.c
bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf  Drivers/u85_driver/u85.c
```

The build is STOP if either differs. The direct path is local checkout -> SSH
host staging -> `docker cp` -> `docker exec make`; GitHub Actions is not part
of this path.

- [ ] **Step 2: Stage only V12 files through a host directory**

Use a new explicit host-persistent staging directory. Fail if it already
exists; do not delete or reuse an old directory.

```bash
ssh gihwan 'set -eu
test ! -e /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE
mkdir -p /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/patches
mkdir -p /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/Selftest_pmu_diag'

scp firmware/Makefile.pmu_completion_poll_v12 \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/
scp firmware/patches/patch_pmu_completion_poll_v12.py \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/patches/
scp firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/Selftest_pmu_diag/

ssh gihwan 'set -eu
docker cp /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware/. \
  benchmark-runner:/work/selftest/
cd /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/firmware
sha256sum \
  Makefile.pmu_completion_poll_v12 \
  patches/patch_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md \
  > ../V12_SOURCE_HOST.sha256
docker exec -w /work/selftest benchmark-runner sha256sum \
  Makefile.pmu_completion_poll_v12 \
  patches/patch_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py \
  Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md \
  > ../V12_SOURCE_CONTAINER.sha256
diff -u ../V12_SOURCE_HOST.sha256 ../V12_SOURCE_CONTAINER.sha256
docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_completion_poll_v12 -n clean all manifest \
  > ../V12_MAKE_DRYRUN.txt
if grep -Eiq "github|actions/|(^|[[:space:]])gh[[:space:]]" ../V12_MAKE_DRYRUN.txt; then exit 1; fi'
```

Expected: source diff has no output, dry-run exits zero, contains only direct
toolchain/Python/make commands, and contains no CI/GitHub invocation.

- [ ] **Step 3: Run the first clean build**

```bash
ssh gihwan 'set -eu
docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_completion_poll_v12 clean all manifest \
  > /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_A.log 2>&1
mkdir /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_A
docker cp benchmark-runner:/work/selftest/build_pmu_completion_poll_v12/. \
  /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_A/'
```

Expected: generator hash gates, compile/link, final-ELF attack gate, and
manifest gate all pass; BUILD_A is host-persistent even if the container is
later removed.

- [ ] **Step 4: Fix only evidence-driven code-shape failures**

If ARM optimization inlines the helper, merges paths early, creates IT-predicated CMD stores, changes STATUS provenance, or obscures NVIC accesses, adjust generated C/compiler attributes and rerun. Never weaken the design gate to admit an unprovable path.

- [ ] **Step 5: Freeze real addresses and hashes**

Capture exactly the ten frozen artifacts plus disassembly/symbol evidence:

```bash
ssh gihwan 'set -eu
cd /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_A
sha256sum \
  APP.BIN VECTORS.BIN DDR.BIN \
  runner_pmu_completion_poll_v12.elf \
  runner_pmu_completion_poll_v12.map \
  generated/Selftest_pmu_diag/runner_pmu_diag_main.c \
  generated/Drivers/u85_driver/u85.c \
  generated/Drivers/u85_driver/u85.o \
  runner_pmu_completion_poll_v12_main.i \
  pmu_completion_poll_v12_manifest.json \
  > ../REPRO_BUILD_A.sha256
python3 -m json.tool pmu_completion_poll_v12_manifest.json \
  > ../BUILD_A.manifest.pretty.json
docker exec benchmark-runner test ! -e /tmp/pmu_v12_build_a_evidence.elf
docker cp runner_pmu_completion_poll_v12.elf \
  benchmark-runner:/tmp/pmu_v12_build_a_evidence.elf
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump -drwC \
  /tmp/pmu_v12_build_a_evidence.elf \
  > ../BUILD_A.objdump.txt
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm -n \
  /tmp/pmu_v12_build_a_evidence.elf \
  > ../BUILD_A.nm.txt
test -s ../REPRO_BUILD_A.sha256
test -s ../BUILD_A.objdump.txt
test -s ../BUILD_A.nm.txt
test -s ../BUILD_A.manifest.pretty.json'
```

Expected: ten hash lines. The pretty manifest and objdump must contain the
helper/callsite, P0/P1/P2, STATUS/CMD/QREAD, stock vector, NVIC accesses,
two success CMD stores, one timeout CMD store, H-PRINTF LR/window, and terminal
release evidence required by the checker.

- [ ] **Step 6: Run an independent second clean build**

Repeat the exact clean build, copy it to a distinct host directory, hash the
same explicit ten-file list, and require an empty diff:

```bash
ssh gihwan 'set -eu
docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_completion_poll_v12 clean all manifest \
  > /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_B.log 2>&1
mkdir /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_B
docker cp benchmark-runner:/work/selftest/build_pmu_completion_poll_v12/. \
  /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_B/
cd /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/BUILD_B
sha256sum \
  APP.BIN VECTORS.BIN DDR.BIN \
  runner_pmu_completion_poll_v12.elf \
  runner_pmu_completion_poll_v12.map \
  generated/Selftest_pmu_diag/runner_pmu_diag_main.c \
  generated/Drivers/u85_driver/u85.c \
  generated/Drivers/u85_driver/u85.o \
  runner_pmu_completion_poll_v12_main.i \
  pmu_completion_poll_v12_manifest.json \
  > ../REPRO_BUILD_B.sha256
cd ..
diff -u REPRO_BUILD_A.sha256 REPRO_BUILD_B.sha256 > REPRO_BUILD_DIFF.txt || true
test ! -s REPRO_BUILD_DIFF.txt
cmp -s REPRO_BUILD_A.sha256 REPRO_BUILD_B.sha256'
```

Expected: `REPRO_BUILD_DIFF.txt` exists and is zero bytes; `cmp` exits zero.

- [ ] **Step 7: Commit the frozen candidate**

Run local V12 tests again, update only observed constants/evidence, then:

```bash
git add firmware/Makefile.pmu_completion_poll_v12 \
  firmware/patches/patch_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md \
  firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py \
  host/runner_proto_pmu_completion_poll_v12.py \
  host/run_pmu_completion_poll_v12.py \
  host/analyze_pmu_completion_poll_v12.py \
  host/tests/test_pmu_completion_poll_v12_unit.py
git commit -m "build: freeze PMU completion poll V12 candidate"
```

### Task 8: Run full regression and independent reviews

**Files:**
- No planned changes unless a review finds a concrete defect.

- [ ] **Step 1: Run exact local regression commands**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py
python3 host/tests/test_pmu_completion_poll_v12_unit.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py
python3 host/tests/test_pmu_interval_v11a_unit.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v10.py
python3 host/tests/test_pmu_interval_v10_unit.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v9.py
python3 host/tests/test_pmu_interval_v9_unit.py
python3 host/tests/test_pmu_qual_unit.py
python3 host/tests/test_pmu_cfg_unit.py
python3 host/tests/test_pmu_diag_unit.py
git diff --check
```

Expected: every suite exits zero with printed failure count zero; `git diff --check` has no output.

- [ ] **Step 2: Prove frozen baselines unchanged**

Fail if any repository change since the V11-A fork is outside the explicit V12
and planning-document allowlist:

```bash
git diff --name-only f1948bcda5232c89f3468585a4099bc2f94ae300..HEAD |
while IFS= read -r path; do
  case "$path" in
    docs/superpowers/specs/2026-08-11-pmu-completion-poll-v12-design.md|\
    docs/superpowers/plans/2026-08-11-pmu-completion-poll-v12-implementation.md|\
    firmware/Makefile.pmu_completion_poll_v12|\
    firmware/patches/patch_pmu_completion_poll_v12.py|\
    firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_DIAG_V12_CONTRACT.md|\
    firmware/Selftest_pmu_diag/check_pmu_completion_poll_v12.py|\
    firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_v12.py|\
    host/runner_proto_pmu_completion_poll_v12.py|\
    host/run_pmu_completion_poll_v12.py|\
    host/analyze_pmu_completion_poll_v12.py|\
    host/tests/test_pmu_completion_poll_v12_unit.py) ;;
    *) printf 'unexpected modified path: %s\n' "$path" >&2; exit 1 ;;
  esac
done
```

Also prove the frozen V11-A remote artifact set still matches its post-board
evidence list:

```bash
ssh gihwan 'set -eu
docker exec -w /work/selftest benchmark-runner sha256sum \
  build_pmu_interval_v11a/APP.BIN \
  build_pmu_interval_v11a/VECTORS.BIN \
  build_pmu_interval_v11a/DDR.BIN \
  build_pmu_interval_v11a/runner_pmu_interval_v11a.elf \
  build_pmu_interval_v11a/runner_pmu_interval_v11a.map \
  build_pmu_interval_v11a/generated/Selftest_pmu_diag/runner_pmu_diag_main.c \
  build_pmu_interval_v11a/generated/Drivers/u85_driver/u85.c \
  build_pmu_interval_v11a/generated/Drivers/u85_driver/u85.o \
  build_pmu_interval_v11a/runner_pmu_interval_v11a_main.i \
  build_pmu_interval_v11a/pmu_interval_v11a_manifest.json \
  > /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/V11_CURRENT.sha256
diff -u \
  /home/gihwan/mps4/PMU_INTERVAL_V11A_20260810T140216Z/REPRO_BUILD_B.sha256 \
  /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_PREBOARD_STAGE/V11_CURRENT.sha256'
```

Expected: both commands produce no diff/failure. The existing V10/V9/V8/CFG/
DIAG regression suites remain the authoritative gates for their respective
frozen contracts; do not accept a source-only comparison.

- [ ] **Step 3: Dispatch code and security reviews**

Use fresh `code-reviewer` and `security-reviewer` agents. Require explicit review of successful STATUS provenance, path-sensitive two-versus-one CMD semantics, no transient IRQ flag, stock vector/ISER hard-bypass, timeout abort behavior, manifest trust, archive bounds, unsafe command/path use, and missing negative tests.

Pass criterion: no unresolved correctness blocker and no unresolved critical/high/medium security finding. Fix each finding, rerun affected and full tests, and redispatch the same reviewer until approved.

- [ ] **Step 4: Independently verify all review fixes**

Read every changed file, rerun the exact local regression block and remote manifest/final-ELF gate, and run `git diff --check`. Reviewer summaries alone are insufficient evidence.

- [ ] **Step 5: Create the pre-board anchor**

```bash
test -z "$(git status --porcelain)"
test -z "$(git tag -l pmu-completion-poll-v12-preboard)"
git tag -a pmu-completion-poll-v12-preboard \
  -m "PMU completion poll V12 pre-board qualification"
```

Expected: clean working tree. Keep the branch unmerged and unpushed unless the user separately requests push.

### Task 9: Record the pre-board handoff

**Files:**
- Modify: `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md`
- Modify: `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md`

- [ ] **Step 1: Read documentation instructions before editing**

Read `/Users/kwongihwan/Documents/Obsidian/CLAUDE.md` completely and follow its project-note schema.

- [ ] **Step 2: Mark both notes before material writes**

```bash
codex-mark-used /Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md
codex-mark-used "/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md"
```

- [ ] **Step 3: Record the qualified boundary**

Record design commit `27cf1a2`, implementation/pre-board commit and tag, frozen hashes, final-ELF evidence, exact test counts, independent review decisions, and:

```text
V11-A                         FROZEN / BOARD EVIDENCE COMPLETE
V12                           PREBOARD QUALIFIED / BOARD NOT STARTED
Production END_ONLY           FROZEN
MLEK performance              BLOCKED
```

Do not claim board qualification or a performance result.

- [ ] **Step 4: Reindex and verify the notes**

```bash
qmd update
qmd embed
git -C /Users/kwongihwan/Documents/Obsidian diff --check
```

Expected: indexing succeeds and note diff has no whitespace errors.

- [ ] **Step 5: Report the pre-board handoff**

Report commit/tag, clean status, frozen hashes, exact local/remote verification, review decisions, explicit board-not-started state, and the next approval boundary. Do not deploy, mount, write SD, reboot, open UART, or interact with MCC in this plan.
