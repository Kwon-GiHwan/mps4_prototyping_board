# PMU Interval V11-A Entry Veneer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic-only schema-11 variant that installs a standalone Thumb entry veneer at runtime, records one first-veneer-probe J0 timestamp, tail-branches to the unchanged stock U85 IRQ handler, and splits V10 E0 into A0/A1 without modifying any frozen V10 file.

**Architecture:** Generate a private V11-A runner/vendor copy from the same frozen inputs as V10, compile one standalone `.S` veneer, and link it only into the V11-A image. A final-ELF gate proves the active `VTOR + NPU0 slot` write installs the veneer Thumb entry, the veneer has the exact permitted semantics, and the retained I0/T3/release path is intact. A separate schema-11 host path adds J0 and derives A0/A1/A2 fail-closed.

**Tech Stack:** Cortex-M85 Thumb-2 assembly, Arm GNU Toolchain, C11 firmware, Python 3 standard library, existing MPS4 UART/PMU qualification harness.

---

## File structure

Create only V11-A-specific files:

- `firmware/Makefile.pmu_interval_v11a` — isolated generated-source and assembly build graph.
- `firmware/patches/patch_pmu_interval_v11a.py` — hash-pinned runner/vendor generator.
- `firmware/Selftest_pmu_diag/pmu_interval_v11a_entry.S` — standalone J0 veneer only.
- `firmware/Selftest_pmu_diag/PMU_INTERVAL_ENTRY_DIAG_V11A_CONTRACT.md` — implementation contract.
- `firmware/Selftest_pmu_diag/check_pmu_interval_v11a.py` — source/object/final-ELF/manifest gate.
- `firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py` — positive and negative firmware tests.
- `host/runner_proto_pmu_interval_v11a.py` — schema-11 ABI and classifier.
- `host/run_pmu_interval_v11a.py` — one-sample collector.
- `host/analyze_pmu_interval_v11a.py` — one-sample and 3x10 analyzer.
- `host/tests/test_pmu_interval_v11a_unit.py` — host contract tests.

Do not modify V9, V10, V8, CFG, Production, or shared protocol files.

---

## Chunk 1: Firmware RED contract and generator

### Task 1: Establish failing V11-A firmware tests

**Files:**
- Create: `firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py`
- Test absent: `firmware/patches/patch_pmu_interval_v11a.py`
- Test absent: `firmware/Selftest_pmu_diag/check_pmu_interval_v11a.py`

- [ ] Mark the new test file with `codex-mark-used`.
- [ ] Add imports for the absent patcher/checker and fixtures representing `VTOR slot -> veneer Thumb value -> J0 -> stock handler -> I0 -> STATUS -> T3`.
- [ ] Add negative fixtures for a stock/even/later-overwritten vector target, wrong DWT/J0 address, extra stack/call/branch/load/store, LR write, interrupt-mask change, barrier, thunk, and wrong tail target.
- [ ] Run `python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py`.
- [ ] Verify RED is `ModuleNotFoundError`, then commit with `test: define PMU interval V11-A firmware contract`.

### Task 2: Implement the generator, veneer, and contract

**Files:**
- Create: `firmware/patches/patch_pmu_interval_v11a.py`
- Create: `firmware/Selftest_pmu_diag/pmu_interval_v11a_entry.S`
- Create: `firmware/Selftest_pmu_diag/PMU_INTERVAL_ENTRY_DIAG_V11A_CONTRACT.md`

- [ ] Mark all three files before writing.
- [ ] Implement a hash-pinned generator based on the V10 pattern with V11-A names and one J0 word.
- [ ] Preserve the original stock handler body and replace exactly one active vendor install with `NVIC_SetVector(NPU0_IRQn, (uint32_t)&v11a_u85_irq_entry_veneer)`.
- [ ] Declare the veneer and V11-A timestamp globals without adding another runtime vector install.
- [ ] Implement the Thumb assembly semantic sequence:

```asm
ldr r0, =0xE0001004
ldr r1, [r0]
ldr r0, =pmu_interval_v11a_t_vector_probe
str r1, [r0]
b u85_irq_handler
```

- [ ] Add no counter, prologue, stack access, call, return, barrier, conditional branch, or interrupt-state instruction.
- [ ] Freeze variant `PMU_INTERVAL_ENTRY_DIAG_V11A`, schema `11`, build ID `0x41314950`, J0 terminology, A0/A1/A2 identity, and diagnostic-only scope.
- [ ] Run the firmware test: imports should progress while absent final-gate tests remain RED.
- [ ] Commit with `feat: add PMU interval V11-A entry veneer`.

### Task 3: Implement final-ELF and manifest gates

**Files:**
- Create: `firmware/Selftest_pmu_diag/check_pmu_interval_v11a.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py`

- [ ] Mark the checker before writing.
- [ ] Reuse read-only helpers from `check_pmu_qual.py` and the V10 checker only where semantics are unchanged.
- [ ] Resolve the inlined `NVIC_SetVector` effect in final `test_u85`: active VTOR load, NPU0 slot write, stored value `veneer | 1`, masked value exact veneer, and no later overwrite before submit.
- [ ] Resolve literal or `movw`/`movt` materialization; admit at most two read-only literal-pool loads whose values are exactly DWT CYCCNT or J0.
- [ ] Prove one DWT read, one reaching J0 store, no other data effect, no stack/LR/call/conditional/barrier/interrupt-state instruction, and one direct unconditional transfer to exact stock handler with no thunk.
- [ ] Prove retained execution order: `T1 -> submit -> T2`, `vector -> veneer -> J0 -> stock handler`, `I0 -> STATUS -> T3 -> flag -> CMD2`, `H-PRINTF -> CMD=0xC`.
- [ ] Add every negative test listed in Task 1.
- [ ] Run:

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py
python3 -m py_compile firmware/patches/patch_pmu_interval_v11a.py \
  firmware/Selftest_pmu_diag/check_pmu_interval_v11a.py \
  firmware/Selftest_pmu_diag/test_check_pmu_interval_v11a.py
```

- [ ] Verify GREEN and commit with `test: gate PMU interval V11-A ELF path`.

---

## Chunk 2: Isolated build and host schema

### Task 4: Add the isolated ARM build graph

**Files:**
- Create: `firmware/Makefile.pmu_interval_v11a`

- [ ] Mark the Makefile before writing.
- [ ] Clone only the V10 graph; use `build_pmu_interval_v11a/`, generated V11-A sources, and a dedicated assembly object.
- [ ] Compile the `.S` file for Cortex-M85 Thumb, link it only into V11-A, and invoke only the V11-A checker.
- [ ] Do not run the graph from the local repo snapshot: it intentionally lacks `Device_SSE-320`, `Drivers`, `Tests`, and the other full FI101 sources. Locally, inspect the Makefile target/dependency text and rely on the patcher/checker unit tests. Run every actual or dry-run make command only in the pinned remote container build root `/work/selftest` as specified in Task 7.
- [ ] Commit with `build: add PMU interval V11-A image`.

### Task 5: Establish failing host tests

**Files:**
- Create: `host/tests/test_pmu_interval_v11a_unit.py`
- Test absent: `host/runner_proto_pmu_interval_v11a.py`
- Test absent: `host/run_pmu_interval_v11a.py`
- Test absent: `host/analyze_pmu_interval_v11a.py`

- [ ] Mark and write RED tests covering schema length, V8/V9/V10 rejection, J0 decode, A0/A1/A2 identity, retained V10 gates, reread/manifest identity, collector failure, and 3x10 localization.
- [ ] Run `python3 host/tests/test_pmu_interval_v11a_unit.py` and verify `ModuleNotFoundError`.
- [ ] Commit with `test: define PMU interval V11-A host contract`.

### Task 6: Implement host parser, collector, and analyzer

**Files:**
- Create: `host/runner_proto_pmu_interval_v11a.py`
- Create: `host/run_pmu_interval_v11a.py`
- Create: `host/analyze_pmu_interval_v11a.py`
- Modify: `host/tests/test_pmu_interval_v11a_unit.py`

- [ ] Mark the three implementation files.
- [ ] Extend the V10 body by one J0 word and use build ID `0x41314950`.
- [ ] Derive `A0=(J0-T2)`, `A1=(I0-J0)`, `A2=(T3-I0)`, and `D23=(T3-T2)` modulo u32.
- [ ] Require positive half-range intervals, J0 nonzero, I0/T3 exactly once, A0+A1+A2 identity, and every retained V10 term.
- [ ] Export only `v11a_perturbed_window_cycles`; state non-comparability to V8/V9/V10.
- [ ] Implement fail-closed collector and analyzer for one sample or exactly 3 boots x 10, localizing across A0/A1/A2.
- [ ] Run host tests and `py_compile`; verify GREEN.
- [ ] Commit with `feat: add PMU interval V11-A host path`.

---

## Chunk 3: Real ARM proof and freeze

### Task 7: Build in the pinned remote ARM environment

**Files:**
- Modify only V11-A frozen hash constants after observing real outputs.

- [ ] Create a host staging directory below `/home/gihwan/mps4/`, copy only V11-A files into it, and then `docker cp` those files into the existing `benchmark-runner` container. Verify the frozen runner/vendor inputs in `/work/selftest` before copying.
- [ ] Use exactly this build context and command form for dry-run and real builds:

```bash
ssh gihwan 'docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_interval_v11a -n all'
ssh gihwan 'docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_interval_v11a clean all manifest'
```

Do not run make from the local partial repo or the host staging directory. Do not perform any SD, USB, reboot, or UART action.
- [ ] Fix only evidence-driven assembler/compiler/gate mismatches; never relax active-vector, no-thunk, or exact-effect contracts.
- [ ] Freeze APP/VECTORS/DDR/ELF/map/generated/preprocessed/manifest hashes, expected LR, VTOR slot/value, veneer/J0, and stock handler addresses.
- [ ] Run a second clean build and prove byte identity for every frozen artifact.
- [ ] Verify the host manifest loader accepts the real manifest and bins.
- [ ] Commit with `build: freeze PMU interval V11-A candidate`.

### Task 8: Run regressions and independent reviews

**Files:**
- No planned changes unless review finds a concrete defect.

- [ ] Run the exact local regression commands:

```bash
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

Pass criterion: every suite exits zero with its printed failed count equal to zero, and `git diff --check` has no output.
- [ ] Run `git diff --check` and prove frozen V10/V9/Production files unchanged.
- [ ] Use `collaboration.spawn_agent` with a `code-reviewer` agent for the V11-A file set. Require explicit review of runtime VTOR/vector proof, Thumb bit, veneer grammar, LR/stack safety, thunk rejection, host fail-closed path, and missing tests. Pass criterion: no unresolved correctness blocker; fix every blocker and redispatch the same review.
- [ ] Use `collaboration.spawn_agent` with a `security-reviewer` agent for the same file set. Require secret scanning plus unsafe command/path, manifest trust, parser input, and firmware interrupt-state review. Pass criterion: no unresolved critical/high/medium finding; fix and redispatch until met.
- [ ] After fixes, rerun the exact regression block above and the real remote manifest gate. Do not accept a reviewer summary without independently reading changed files and observing the commands.
- [ ] Create local tag `pmu-interval-v11a-preboard`; keep branch unmerged and unpushed.

### Task 9: Record the pre-board handoff

**Files:**
- Modify: `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md`
- Modify: `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md`

- [ ] Record design, build hashes, ELF evidence, tests, review status, and `V11-A PREBOARD READY / BOARD NOT STARTED`.
- [ ] Preserve V10 evidence-complete, Production frozen, and MLEK blocked.
- [ ] Run `qmd update && qmd embed`.
- [ ] Verify no board/SD/USB/reboot/UART action occurred during this plan.
