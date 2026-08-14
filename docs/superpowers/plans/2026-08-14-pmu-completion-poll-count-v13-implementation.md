# PMU Completion Poll Count V13 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic-only schema-13 variant that publishes the actual V12 polling-loop remaining state once after P2, while proving that the final ARM poll loop is semantically and control-flow equivalent to V12.

**Architecture:** Generate V13 from the same frozen raw runner/vendor inputs as V12 and retain the complete V12 IRQ hard-bypass, completion polling, CMD/QREAD, PMU, golden-output, and terminal-release paths. Add one success-only SRAM publication after P2, then make a cross-ELF checker prove both V12-to-V13 loop equivalence and dataflow from the actual failed-poll back-edge induction state to that publication. Extend the host ABI by one word and derive poll count and descriptive count-versus-cycle statistics without treating them as latency or performance data.

**Tech Stack:** Cortex-M85 Thumb-2 C firmware, Arm GNU Toolchain, CMSIS/NPU MMIO, Python 3 standard library, objdump/nm/readelf final-ELF analysis, existing MPS4 UART qualification harness.

---

## File structure and ownership

Create V13-specific files; do not modify V12 files to implement V13:

- `firmware/Makefile.pmu_completion_poll_count_v13` — isolated V13 build graph and cross-ELF gate invocation.
- `firmware/patches/patch_pmu_completion_poll_count_v13.py` — frozen-input generator with the single success-only publication.
- `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md` — executable, ABI, interpretation, and campaign contract.
- `firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py` — source, artifact, actual-ELF, V12↔V13 equivalence, and induction-dataflow gate.
- `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py` — positive and deliberate-mutation checker tests.
- `firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py` — isolated build-graph tests.
- `host/runner_proto_pmu_completion_poll_count_v13.py` — schema-13 decode, validity, and derived fields.
- `host/run_pmu_completion_poll_count_v13.py` — fail-closed collector with timeout boot-abort behavior.
- `host/analyze_pmu_completion_poll_count_v13.py` — 3×10 count-versus-cycle characterization.
- `host/tests/test_pmu_completion_poll_count_v13_unit.py` — parser, classifier, collector, and analyzer tests.

Modify documentation only after the corresponding evidence exists:

- `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md`
- `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md`
- `/Users/kwongihwan/Documents/Obsidian/index.md`
- `/Users/kwongihwan/Documents/Obsidian/log.md`

Frozen inputs and references:

- Design: `docs/superpowers/specs/2026-08-14-pmu-completion-poll-count-v13-design.md`
- Design anchor: `09457e3`
- V12 board-evidence fork: `f7da7e85bb50431818fdd59f7784ffe1cbd43842`
- V12 authoritative ELF SHA-256: `cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401`
- V12 firmware/ELF anchor: `126ef064a3eff8b41429bb8a82c4756dc20fd000`
- V12 host-fix anchor: `de50534b1b92595a04f73ae82e0e5d0d96eb01e3`

Never modify V12/V11-A/V10/V9/V8/CFG/DIAG or Production END_ONLY tracked artifacts. V13 remains diagnostic-only and MLEK remains blocked.

---

## Chunk 1: RED firmware and cross-ELF contract

### Task 1: Define the V13 generator and source-contract RED suite

**Files:**
- Create: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py`
- Test absent: `firmware/patches/patch_pmu_completion_poll_count_v13.py`
- Test absent: `firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Mark the test before writing**

```bash
codex-mark-used firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
```

Expected: exit zero.

- [ ] **Step 2: Add frozen-input and exact-one patch fixtures**

Model the V12 helper shape and require the V13 generator to consume each target exactly once:

```c
for (uint32_t i = 0U; i < 10000U; ++i) {
    uint32_t status = *status_reg;
    if ((status & 0x02U) != 0U) {
        pmu_completion_poll_v12_t_status_completion_seen = DWT->CYCCNT;
        pmu_completion_poll_v12_t_poll_exit = DWT->CYCCNT;
        return status;
    }
}
```

Require the future generator to reject mismatched raw runner/vendor hashes, V11 generated input, V12 generated input as a raw source, zero matches, or multiple matches.

- [ ] **Step 3: Add positive V13 source fixtures**

Require the generated helper to have this logical success suffix:

```c
pmu_completion_poll_count_v13_t_status_completion_seen = DWT->CYCCNT; /* P1 */
pmu_completion_poll_count_v13_t_poll_exit = DWT->CYCCNT;              /* P2 */
pmu_completion_poll_count_v13_t_poll_remaining_at_success = 10000U - i;
return status;
```

Require reset to an invalid sentinel, schema `13`, build ID `0x33314950`, one appended wire word, and no publication on timeout.

- [ ] **Step 4: Add source-level negative fixtures**

At minimum mutate and reject:

1. publication before P2;
2. publication twice;
3. publication on timeout;
4. constant remaining value;
5. unrelated/reinitialized counter;
6. per-iteration counter increment or SRAM store;
7. second STATUS read;
8. extra PMU/NPU/NVIC MMIO;
9. completion mask other than `0x02`;
10. V12 hard-bypass/CMD/QREAD/release drift.

- [ ] **Step 5: Run RED**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
```

Expected: fail because V13 generator/checker modules are absent, not because the fixture is malformed.

- [ ] **Step 6: Commit the RED source contract**

```bash
git add firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git commit -m "test(pmu-v13): define firmware contract"
```

### Task 2: Define the V12↔V13 final-ELF RED gate

**Files:**
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Add canonical V12 and proposed V13 disassembly fixtures**

The V12 fixture must preserve the observed loop:

```text
ldr STATUS
tst #2
bne success
subs remaining,#1
subs timeout,#1
bne loop
```

The V13 fixture may rename registers or relocate code, but must add no loop-path instruction, load/store, MMIO, spill, or edge. Its only new active effect is one remaining-value SRAM store after P2 and before return.

- [ ] **Step 2: Add normalized loop-effect expectations**

Lock a small checker interface in tests:

```python
v12 = extract_poll_loop(v12_disassembly, v12_nm)
v13 = extract_poll_loop(v13_disassembly, v13_nm)
assert normalize_poll_loop(v12) == normalize_poll_loop(v13)
assert prove_remaining_dataflow(v13).source == "back_edge_induction"
```

Normalized effects must encode one STATUS load, `0x02` test, success edge, two failed-poll decrements, one conditional back-edge, and timeout exit.

- [ ] **Step 3: Add deliberate final-ELF mutations**

Each mutation must fail for its intended gate:

- extra loop `mov`, bookkeeping, spill/reload, load/store, or call;
- one decrement removed or a third decrement added;
- branch topology/back-edge changed;
- extra STATUS load or different MMIO address;
- P2/remaining store order reversed;
- store value constant, recomputed, reinitialized, or from a different loop;
- timeout reaches the remaining store;
- helper gains push/pop or stack access;
- retained V12 vector/NVIC/CMD/QREAD/PMU/release gate changes.

- [ ] **Step 4: Add boundary-value fixtures**

Prove the ABI semantics independently of compiler layout:

```text
first successful poll      remaining=10000 iterations=1
interior successful poll   remaining=N     iterations=10001-N
10000th successful poll    remaining=1     iterations=10000
timeout                    remaining invalid, no iterations
```

- [ ] **Step 5: Run RED and commit**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git add firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git commit -m "test(pmu-v13): define cross-ELF equivalence gate"
```

Expected before implementation: missing checker/generator failure.

---

## Chunk 2: Minimal generator and actual checker

### Task 3: Implement the frozen-input V13 generator

**Files:**
- Create: `firmware/patches/patch_pmu_completion_poll_count_v13.py`
- Create: `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Mark new files**

```bash
codex-mark-used firmware/patches/patch_pmu_completion_poll_count_v13.py
codex-mark-used firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md
```

- [ ] **Step 2: Copy the V12 generator structure under V13 names**

Keep exact-one substitutions and frozen raw-input hashes. Change only V13 identity and the new word:

```python
SCHEMA_VERSION = 13
BUILD_ID = 0x33314950
POLL_REMAINING_INVALID = 0
```

Do not read V12 generated files as generator inputs.

- [ ] **Step 3: Extend the runner wire shape by exactly one word**

Append `poll_remaining_at_success` after the 15 V12 appendix words. Update compile-time assertions from 108 to 109 total words and from 432 to 436 bytes. Reset the target storage to the invalid sentinel before every run and serialize it once.

- [ ] **Step 4: Add the success-only publication after P2**

Use the existing loop induction variable and no new per-iteration state:

```c
for (uint32_t i = 0U; i < 10000U; ++i) {
    uint32_t status = *status_reg;
    if ((status & 0x02U) != 0U) {
        pmu_completion_poll_count_v13_t_status_completion_seen = DWT->CYCCNT;
        pmu_completion_poll_count_v13_t_poll_exit = DWT->CYCCNT;
        pmu_completion_poll_count_v13_t_poll_remaining_at_success = 10000U - i;
        return status;
    }
}
return 0U;
```

If this source form changes the actual loop, later qualification must fail; do not add compiler-specific tricks until the actual ELF demonstrates a need.

- [ ] **Step 5: Preserve every V12 path contract**

Require the generated V13 sources to retain:

- runtime vector = exact stock `u85_irq_handler`;
- NVIC disabled during measurement and no ISER enable;
- same STATUS success value feeds branch, returned status, and `irq_history_mask`;
- success CMD=2 twice with QREAD between;
- timeout CMD=2 once and no P1/P2/remaining publication;
- common CMD=0, H-PRINTF PMU seam, and terminal CMD=0xC.

- [ ] **Step 6: Write the contract document**

Record the diagnostic-only labels, exact formula `poll_iterations = 10001 - remaining`, success range, timeout invalidation, authoritative `P1-T2` timing, and the primary final-ELF equivalence/dataflow gate. State explicitly that a source-level no-loop-change claim is insufficient.

- [ ] **Step 7: Run generator checks**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
python3 -m py_compile \
  firmware/patches/patch_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
```

Expected: generator/source tests pass; checker-related tests remain RED.

- [ ] **Step 8: Commit**

```bash
git add firmware/patches/patch_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git commit -m "feat(pmu-v13): add poll-count generator"
```

### Task 4: Implement semantic/CFG equivalence and induction proof

**Files:**
- Create: `firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py`
- Modify: `firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Mark the checker**

```bash
codex-mark-used firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py
```

- [ ] **Step 2: Reuse bounded Thumb parsing from the V12 checker**

Copy only established parsing helpers needed for symbol lookup, instruction decoding, literal resolution, basic blocks, direct edges, and reaching definitions. Do not refactor V12 or introduce a general disassembler framework.

- [ ] **Step 3: Extract semantic loop regions from both actual ELFs**

Require checker arguments for authoritative V12 and candidate V13 ELF/tool outputs. Locate each loop from the helper symbol, exact STATUS address, `0x02` test, success edge, back-edge, and timeout edge—not fixed instruction addresses.

- [ ] **Step 4: Compare normalized CFG and effects**

Normalize away register names, code addresses, literal pool positions, and equivalent branch encodings. Require equality of:

```text
STATUS reads/iteration = 1
mask                   = 0x02
failed-path decrements = 2
conditional back-edge = 1
success/timeout edges  = same topology
extra loop effects     = 0
```

Reject any loop call, barrier, stack access, spill/reload, or other MMIO.

- [ ] **Step 5: Prove the success-only induction dataflow**

Starting at the decrement target used by the failed-poll back-edge, require that the same induction value reaches the success edge and the one post-P2 SRAM store without reinitialization, reload from unrelated storage, or recomputation from another counter. Prove timeout cannot reach that store.

- [ ] **Step 6: Retain the entire V12 executable gate**

Re-run stock vector, NVIC hard-bypass, STATUS single-source, path-sensitive CMD/QREAD, PMU, H-PRINTF, golden, artifact, and terminal-release proofs against V13. Emit manifest booleans for all retained gates plus:

```text
v12_v13_poll_loop_semantically_equivalent
v13_extra_per_iteration_instruction_count_zero
remaining_store_after_p2_exactly_once
remaining_from_back_edge_induction
remaining_store_timeout_unreachable
helper_leaf_no_stack_access
```

- [ ] **Step 7: Make the complete mutation matrix GREEN**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
python3 -m py_compile \
  firmware/patches/patch_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git diff --check
```

Expected: every positive case passes; every deliberate mutation fails for its named reason; syntax and whitespace checks pass.

- [ ] **Step 8: Commit**

```bash
git add firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
git commit -m "test(pmu-v13): prove loop equivalence and count dataflow"
```

---

## Chunk 3: Isolated ARM build and real-ELF qualification

### Task 5: Add and test the isolated build graph

**Files:**
- Create: `firmware/Makefile.pmu_completion_poll_count_v13`
- Create: `firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Write the failing Makefile test**

```bash
codex-mark-used firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
```

Require V13-only build directory, patcher/checker, schema define, target/manifest names, V12 reference-ELF input, and no board/CI command.

- [ ] **Step 2: Run RED**

```bash
python3 firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
```

Expected: fail because the Makefile is absent.

- [ ] **Step 3: Create the Makefile**

```bash
codex-mark-used firmware/Makefile.pmu_completion_poll_count_v13
```

Clone the V12 graph under V13 names. The final gate must receive both the frozen authoritative V12 ELF and the freshly linked V13 ELF; fail if the V12 ELF hash is not exactly the frozen SHA-256.

- [ ] **Step 4: Run graph and firmware tests**

```bash
python3 firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
rg -n "board|mount|ttyUSB|github|actions" firmware/Makefile.pmu_completion_poll_count_v13
```

Expected: tests pass; grep finds no board/CI operation.

- [ ] **Step 5: Commit**

```bash
git add firmware/Makefile.pmu_completion_poll_count_v13 \
  firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
git commit -m "build(pmu-v13): add isolated ARM graph"
```

### Task 6: Run two clean ARM builds and freeze the executable evidence

**Files:**
- Modify only if evidence requires it: V13 generator/checker/tests/contract/Makefile.

- [ ] **Step 1: Run read-only remote preflight**

```bash
ssh gihwan 'set -eu
test "$(docker inspect -f "{{.State.Running}}" benchmark-runner)" = true
docker exec -w /work/selftest benchmark-runner sha256sum \
  Selftest_pmu_diag/runner_pmu_diag_main.c \
  Drivers/u85_driver/u85.c
df -Pk /home/gihwan/mps4'
```

Expected raw hashes remain `69cab8c4…` and `bcd877bb…`. No board, SD, USB, MCC, or UART action is permitted in this chunk.

- [ ] **Step 2: Stage only the V13 build inputs to a new host-persistent directory**

Use this exact new path and fail if it already exists. Never delete or reuse an
older evidence root:

```bash
ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
test ! -e "$STAGE"
mkdir -p "$STAGE"/firmware/patches "$STAGE"/firmware/Selftest_pmu_diag
mkdir -p "$STAGE"/authoritative-v12'

scp firmware/Makefile.pmu_completion_poll_count_v13 \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE/firmware/
scp firmware/patches/patch_pmu_completion_poll_count_v13.py \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE/firmware/patches/
scp firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md \
  gihwan:/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE/firmware/Selftest_pmu_diag/

ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
cd "$STAGE"/firmware
sha256sum \
  Makefile.pmu_completion_poll_count_v13 \
  patches/patch_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md \
  > "$STAGE"/V13_SOURCE_HOST.sha256
docker cp "$STAGE"/firmware/. benchmark-runner:/work/selftest/
docker exec -w /work/selftest benchmark-runner sha256sum \
  Makefile.pmu_completion_poll_count_v13 \
  patches/patch_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py \
  Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md \
  > "$STAGE"/V13_SOURCE_CONTAINER.sha256
diff -u "$STAGE"/V13_SOURCE_HOST.sha256 "$STAGE"/V13_SOURCE_CONTAINER.sha256'
```

Expected: source-list diff has no output.

- [ ] **Step 3: Supply the frozen V12 ELF as a read-only comparison input**

Copy the immutable ELF from the completed V12 evidence root, verify it on the
SSH host, then copy that exact byte sequence into the container. Do not use a
fresh V12 rebuild as the comparison authority:

```bash
ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
V12_ROOT=/home/gihwan/mps4/PMU_COMPLETION_POLL_V12_HOSTFIX_20260814T061500Z
cp "$V12_ROOT"/provenance/runner_pmu_completion_poll_v12.elf \
  "$STAGE"/authoritative-v12/
printf "%s  %s\n" \
  cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401 \
  "$STAGE"/authoritative-v12/runner_pmu_completion_poll_v12.elf \
  | sha256sum -c -
docker exec -w /work/selftest benchmark-runner mkdir -p authoritative-v12
docker cp "$STAGE"/authoritative-v12/runner_pmu_completion_poll_v12.elf \
  benchmark-runner:/work/selftest/authoritative-v12/
docker exec -w /work/selftest benchmark-runner sha256sum \
  authoritative-v12/runner_pmu_completion_poll_v12.elf \
  > "$STAGE"/V12_REFERENCE_CONTAINER.sha256
grep -q "^cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401 " \
  "$STAGE"/V12_REFERENCE_CONTAINER.sha256'
```

Expected: `cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401`.

- [ ] **Step 4: Run clean build A**

```bash
ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_completion_poll_count_v13 clean all manifest \
  > "$STAGE"/BUILD_A.log 2>&1
mkdir "$STAGE"/BUILD_A
docker cp benchmark-runner:/work/selftest/build_pmu_completion_poll_count_v13/. \
  "$STAGE"/BUILD_A/'
```

Expected: generator/source gates, compile/link, V12↔V13 loop gate, induction dataflow, retained V12 gates, and manifest binding all pass.

- [ ] **Step 5: Inspect the actual helper before accepting it**

Capture concrete tool output alongside the copied build:

```bash
ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
BUILD="$STAGE"/BUILD_A
ELF=/work/selftest/build_pmu_completion_poll_count_v13/runner_pmu_completion_poll_count_v13.elf
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump -drwC "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.objdump.txt
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm -n "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.nm.txt
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-readelf -h "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.readelf.txt
cd "$BUILD"
sha256sum \
  APP.BIN VECTORS.BIN DDR.BIN \
  runner_pmu_completion_poll_count_v13.elf \
  runner_pmu_completion_poll_count_v13.map \
  generated/Selftest_pmu_diag/runner_pmu_diag_main.c \
  generated/Drivers/u85_driver/u85.c \
  generated/Drivers/u85_driver/u85.o \
  runner_pmu_completion_poll_count_v13_main.i \
  pmu_completion_poll_count_v13_manifest.json \
  runner_pmu_completion_poll_count_v13.objdump.txt \
  runner_pmu_completion_poll_count_v13.nm.txt \
  runner_pmu_completion_poll_count_v13.readelf.txt \
  > "$STAGE"/REPRO_BUILD_A.sha256
test "$(wc -l < "$STAGE"/REPRO_BUILD_A.sha256)" -eq 13
python3 -m json.tool pmu_completion_poll_count_v13_manifest.json \
  > "$STAGE"/BUILD_A.manifest.pretty.json'
```

Verify from evidence—not source—that:

- V12 and V13 normalized poll loops match;
- no new loop spill/reload/bookkeeping exists;
- helper remains leaf/no-stack;
- P1 < P2 < remaining store < return;
- stored remaining reaches from the branch-control induction value;
- timeout cannot reach the store.

- [ ] **Step 6: Treat code-shape drift as RED**

If the live-out changes the loop, do not relax the checker. Change only the V13 publication implementation, rerun unit tests, and rebuild until the exact semantic gate passes or report the design blocked.

- [ ] **Step 7: Run independent clean build B**

Repeat the clean build and exact evidence extraction under `BUILD_B`, then
compare all 13 relative paths:

```bash
ssh gihwan 'set -eu
STAGE=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_PREBOARD_STAGE
docker exec -w /work/selftest benchmark-runner \
  make -f Makefile.pmu_completion_poll_count_v13 clean all manifest \
  > "$STAGE"/BUILD_B.log 2>&1
mkdir "$STAGE"/BUILD_B
docker cp benchmark-runner:/work/selftest/build_pmu_completion_poll_count_v13/. \
  "$STAGE"/BUILD_B/
BUILD="$STAGE"/BUILD_B
ELF=/work/selftest/build_pmu_completion_poll_count_v13/runner_pmu_completion_poll_count_v13.elf
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-objdump -drwC "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.objdump.txt
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-nm -n "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.nm.txt
docker exec benchmark-runner \
  /opt/arm/gcc-arm-none-eabi/bin/arm-none-eabi-readelf -h "$ELF" \
  > "$BUILD"/runner_pmu_completion_poll_count_v13.readelf.txt
cd "$BUILD"
sha256sum \
  APP.BIN VECTORS.BIN DDR.BIN \
  runner_pmu_completion_poll_count_v13.elf \
  runner_pmu_completion_poll_count_v13.map \
  generated/Selftest_pmu_diag/runner_pmu_diag_main.c \
  generated/Drivers/u85_driver/u85.c \
  generated/Drivers/u85_driver/u85.o \
  runner_pmu_completion_poll_count_v13_main.i \
  pmu_completion_poll_count_v13_manifest.json \
  runner_pmu_completion_poll_count_v13.objdump.txt \
  runner_pmu_completion_poll_count_v13.nm.txt \
  runner_pmu_completion_poll_count_v13.readelf.txt \
  > "$STAGE"/REPRO_BUILD_B.sha256
diff -u "$STAGE"/REPRO_BUILD_A.sha256 "$STAGE"/REPRO_BUILD_B.sha256 \
  > "$STAGE"/REPRO_BUILD_DIFF.txt || true
test ! -s "$STAGE"/REPRO_BUILD_DIFF.txt
cmp -s "$STAGE"/REPRO_BUILD_A.sha256 "$STAGE"/REPRO_BUILD_B.sha256'
```

Expected: every declared artifact is byte-identical across builds A/B.

- [ ] **Step 8: Record observed hashes and commit the ARM-qualified candidate**

Update the V13 contract only with observed hashes/addresses and qualification results, rerun all V13 firmware tests, then commit:

```bash
git add firmware/Makefile.pmu_completion_poll_count_v13 \
  firmware/patches/patch_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md \
  firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py \
  firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
git commit -m "build(pmu-v13): freeze ARM-qualified candidate"
```

---

## Chunk 4: Host schema, collector, and characterization

### Task 7: Establish the schema-13 host RED suite

**Files:**
- Create: `host/tests/test_pmu_completion_poll_count_v13_unit.py`
- Test absent: `host/runner_proto_pmu_completion_poll_count_v13.py`
- Test absent: `host/run_pmu_completion_poll_count_v13.py`
- Test absent: `host/analyze_pmu_completion_poll_count_v13.py`

- [ ] **Step 1: Mark and write the RED tests**

```bash
codex-mark-used host/tests/test_pmu_completion_poll_count_v13_unit.py
```

Cover exact 109-word/436-byte ABI, schema/build identity, one appended remaining word, retained V12 fields, raw/reread equality, modulo identities, success boundaries, timeout invalidation, manifest/ELF binding, artifact hashes, and V8–V12 parser rejection.

- [ ] **Step 2: Lock success derivation**

```python
assert 1 <= remaining <= 10000
iterations = 10001 - remaining
assert 1 <= iterations <= 10000
poll_cycles = (p1 - p0) & 0xFFFFFFFF
ratio = poll_cycles / iterations
```

Require `submit_to_status_completion_observed_cycles = u32(P1-T2)` to remain the authoritative timing.

- [ ] **Step 3: Lock timeout behavior**

On timeout require no `poll_remaining_at_success`, `poll_iterations`, `poll_observation_cycles`, or ratio in derived output; no valid archive entry; stop the rest of that boot and require a fresh boot.

- [ ] **Step 4: Lock analyzer behavior**

Create deterministic fixtures for three boots × ten runs with ties. Require average-rank Spearman, OLS `alpha/beta`, per-sample residuals, per-boot residual summaries, floor/excursion count distributions, and descriptive-only labels.

- [ ] **Step 5: Run RED and commit**

```bash
python3 host/tests/test_pmu_completion_poll_count_v13_unit.py
git add host/tests/test_pmu_completion_poll_count_v13_unit.py
git commit -m "test(pmu-v13): define host characterization contract"
```

Expected: missing V13 host module failure.

### Task 8: Implement parser, collector, and analyzer

**Files:**
- Create: `host/runner_proto_pmu_completion_poll_count_v13.py`
- Create: `host/run_pmu_completion_poll_count_v13.py`
- Create: `host/analyze_pmu_completion_poll_count_v13.py`
- Modify: `host/tests/test_pmu_completion_poll_count_v13_unit.py`

- [ ] **Step 1: Mark implementation files**

```bash
codex-mark-used host/runner_proto_pmu_completion_poll_count_v13.py
codex-mark-used host/run_pmu_completion_poll_count_v13.py
codex-mark-used host/analyze_pmu_completion_poll_count_v13.py
```

- [ ] **Step 2: Implement exact schema-13 decoding**

Reuse V12 parsing/classification by composition, not by weakening its identity gates. Parse the extra word only after the complete retained V12 body and reject truncation, extension, schema/build mismatch, header/body disagreement, and CRC failure.

- [ ] **Step 3: Implement fail-closed success/timeout derivation**

Success emits remaining, iterations, poll cycles, and ratio only after every V12 and V13 term passes. Timeout emits none of them. Preserve raw vector values and Thumb-canonical comparison from the V12 host fix.

- [ ] **Step 4: Implement collection without invalid dataset writes**

Classify before opening the valid-sample destination. Preserve raw payload, reread, SHA-256, exact manifest text/hash, artifact hashes, host boot ID, and run sequence. Timeout or invalid classification stops that boot.

- [ ] **Step 5: Implement standard-library statistics**

Use average ranks for ties:

```python
rho = pearson(average_ranks(iterations), average_ranks(poll_cycles))
beta = covariance(iterations, poll_cycles) / variance(iterations)
alpha = mean(poll_cycles) - beta * mean(iterations)
residual = poll_cycles - (alpha + beta * iterations)
```

Handle zero iteration variance by returning `None` for fit/correlation rather than fabricating a value. Report ratio as `average_cycles_per_observed_poll` and retain all diagnostic-only labels.

- [ ] **Step 6: Run host tests and syntax checks**

```bash
python3 host/tests/test_pmu_completion_poll_count_v13_unit.py
python3 -m py_compile \
  host/runner_proto_pmu_completion_poll_count_v13.py \
  host/run_pmu_completion_poll_count_v13.py \
  host/analyze_pmu_completion_poll_count_v13.py \
  host/tests/test_pmu_completion_poll_count_v13_unit.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add host/runner_proto_pmu_completion_poll_count_v13.py \
  host/run_pmu_completion_poll_count_v13.py \
  host/analyze_pmu_completion_poll_count_v13.py \
  host/tests/test_pmu_completion_poll_count_v13_unit.py
git commit -m "feat(pmu-v13): add host count characterization"
```

---

## Chunk 5: Regression, review, pre-board anchor, and board handoff

### Task 9: Run full qualification and independent reviews

**Files:**
- No planned changes unless evidence or review finds a concrete defect.

- [ ] **Step 1: Run V13 suites**

```bash
python3 firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py
python3 firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py
python3 host/tests/test_pmu_completion_poll_count_v13_unit.py
```

- [ ] **Step 2: Run retained regressions**

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

Expected: every command exits zero and each printed failure count is zero.

- [ ] **Step 3: Prove the change allowlist**

Run the exact allowlist against the V12 board-evidence fork. Any V12-or-earlier
or Production path change is a STOP:

```bash
git diff --name-only f7da7e85bb50431818fdd59f7784ffe1cbd43842..HEAD |
while IFS= read -r path; do
  case "$path" in
    docs/superpowers/specs/2026-08-14-pmu-completion-poll-count-v13-design.md|\
    docs/superpowers/plans/2026-08-14-pmu-completion-poll-count-v13-implementation.md|\
    firmware/Makefile.pmu_completion_poll_count_v13|\
    firmware/patches/patch_pmu_completion_poll_count_v13.py|\
    firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_CONTRACT.md|\
    firmware/Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py|\
    firmware/Selftest_pmu_diag/test_check_pmu_completion_poll_count_v13.py|\
    firmware/Selftest_pmu_diag/test_makefile_pmu_completion_poll_count_v13.py|\
    host/runner_proto_pmu_completion_poll_count_v13.py|\
    host/run_pmu_completion_poll_count_v13.py|\
    host/analyze_pmu_completion_poll_count_v13.py|\
    host/tests/test_pmu_completion_poll_count_v13_unit.py) ;;
    *) printf 'unexpected modified path: %s\n' "$path" >&2; exit 1 ;;
  esac
done
```

Expected: exit zero and no `unexpected modified path` line.

- [ ] **Step 4: Request correctness and security reviews**

Dispatch one `code-reviewer` and one `security-reviewer` against the exact
pre-board diff. Reviewers must attack actual-ELF loop equivalence,
induction-state provenance, timeout non-publication, manifest trust, raw
evidence preservation, statistical tie/zero-variance behavior, and frozen-file
isolation. No unresolved correctness blocker or critical/high/medium security
finding may remain.

- [ ] **Step 5: Independently rerun all affected evidence after fixes**

Read each changed file and rerun the exact command blocks in Task 9 Steps 1–3,
the build A/B comparison in Task 6, and the actual-ELF checker via the V13
Makefile `manifest` target. Reviewer summaries alone are insufficient.

- [ ] **Step 6: Commit and tag the pre-board candidate**

```bash
test -z "$(git status --porcelain)"
git tag -a pmu-completion-poll-count-v13-preboard \
  -m "PMU completion poll count V13 pre-board qualification"
```

Record the exact commit plus APP/VECTORS/DDR/ELF/manifest hashes. Keep the branch unmerged; push only when explicitly requested.

### Task 10: Record the pre-board handoff

**Files:**
- Modify: `/Users/kwongihwan/Documents/Obsidian/wiki/projects/npu-benchmark.md`
- Modify: `/Users/kwongihwan/Documents/Obsidian/npu-benchmark/hardware/Supervise Note.md`
- Modify: `/Users/kwongihwan/Documents/Obsidian/index.md`
- Modify: `/Users/kwongihwan/Documents/Obsidian/log.md`

- [ ] **Step 1: Mark notes before editing**

Run `codex-mark-used` for all four note paths.

- [ ] **Step 2: Record only proved state**

Before board work the maximum allowed status is:

```text
V12                                    FROZEN / EVIDENCE COMPLETE
PMU_COMPLETION_POLL_COUNT_DIAG_V13     PREBOARD QUALIFIED
V13 ARM executable                     QUALIFIED
V13 host schema                        UNIT-QUALIFIED
V13 board behavior                     NOT STARTED
Production END_ONLY                    FROZEN
MLEK                                   BLOCKED
```

Include the design, implementation, ARM/pre-board anchors and artifact hashes.

- [ ] **Step 3: Refresh the Obsidian search index**

```bash
qmd update
qmd embed
```

Expected: both commands exit zero.

### Task 11: Execute the 3×10 board campaign only after a separate GO

**Files:**
- No source changes permitted.
- Create a new timestamped evidence root on the remote host.
- Create after audit: `firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_BOARD_RESULT.md`

The sole destructive-operation authority is
`firmware/Selftest_pmu_diag/PMU_QUAL_PROCEDURE.md` §8, including FAILCLEAN,
mount-acquisition-path tracking, bounded 2-EXC rules, and the prohibition on
credential discovery/storage or `sudo -S`. V13 substitutes only its candidate
directory, manifest, collector, and evidence root. Do not use the legacy
`SdCard` helper in `host/mcc_harness.py` for deployment.

- [ ] **Step 1: Re-run the established board preflight**

First prove storage and user-visible ownership without changing state:

```bash
ssh gihwan 'set -eu
test -z "$(findmnt -rn -S /dev/sdb1)"
test ! -e /dev/sdb
for tty in /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3; do
  test -e "$tty"
  if fuser "$tty" >/dev/null 2>&1; then exit 1; fi
done'
```

Then the operator runs the root-inclusive check interactively; do not embed or
pipe a password:

```bash
ssh -t gihwan 'sudo fuser -v /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3; \
sudo lsof /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3'
```

Expected: no userspace holder rows. Without inserting another UART consumer,
immediately run the known-good reboot gate already preserved by V12:

```bash
ssh gihwan 'set -eu
cd /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_HOSTFIX_20260814T061500Z/host-tools
python3 do_reboot_capture.py'
```

Expected: `DDR self-test PASSED: True`, `CPUWAIT cleared: True`, and MCC prompt
returned. Run this exact PING gate three times against the known-good image:

```bash
ssh gihwan 'set -eu
cd /home/gihwan/mps4/PMU_COMPLETION_POLL_V12_HOSTFIX_20260814T061500Z/host-tools
python3 - <<"PY"
from run_pmu_qual import PORT_DEFAULT, PmuQualLink
for index in range(1, 4):
    link = PmuQualLink(PORT_DEFAULT)
    try:
        value = link.ping()
    finally:
        link.close()
    errors = (value.rx_overrun, value.bad_magic, value.bad_version,
              value.bad_crc, value.length_error, value.sequence_error,
              value.parser_resync)
    print(index, value.state, errors)
    assert value.state == 1 and errors == (0, 0, 0, 0, 0, 0, 0)
PY'
```

Only all-green output permits deployment.

- [ ] **Step 2: Deploy the exact pre-board image**

Create `EV=/home/gihwan/mps4/PMU_COMPLETION_POLL_COUNT_V13_<UTC>` and execute
§8 steps 0–8 verbatim, with a new pre-overwrite backup under `$EV`, the exact
pre-board V13 `APP.BIN/VECTORS.BIN/DDR.BIN`, and the recorded mount method and
mount point. The required source/destination check is:

```bash
sha256sum "$CANDIDATE"/{APP,VECTORS,DDR}.BIN > "$EV"/DEPLOY_SOURCE.sha256
sha256sum "$MOUNT"/SOFTWARE/{APP,VECTORS,DDR}.BIN > "$EV"/DEPLOY_DESTINATION.sha256
```

Normalize only the path column and require all three digests to match the
frozen manifest. Any mismatch invokes §8 FAILCLEAN; unmount failure forbids
USB_OFF. No `/mnt` assumption and no automated sudo credential are allowed.

- [ ] **Step 3: Run three independent boots × ten consecutive valid samples**

For each full boot, gate DDR/CPUWAIT with `do_reboot_capture.py`, then run the
collector ten times with sequence IDs restarting at 1 after each boot:

```bash
python3 host/run_pmu_completion_poll_count_v13.py \
  --bins-dir "$CANDIDATE" \
  --manifest "$CANDIDATE"/pmu_completion_poll_count_v13_manifest.json \
  --host-boot-index "$BOOT" \
  --out "$EV"/samples/boot${BOOT}_repeat${RUN}.json
```

For every sample require all V12 gates plus remaining range, derived count
range, raw/reread identity, and authoritative `P1-T2`. Any timeout or invalid
sample stops that boot and is excluded from the 30-sample dataset.

- [ ] **Step 4: Analyze count versus poll cycles**

Run the frozen analyzer against only the 30 accepted archives:

```bash
python3 host/analyze_pmu_completion_poll_count_v13.py \
  "$EV"/samples/*.json > "$EV"/analysis/FINAL_REPORT.json
```

Report raw per-sample points, boot/run IDs, Spearman, OLS, residuals,
floor/excursion count distributions, and ratio summaries. Do not compare
absolute V12/V13 cycles or label any value latency, `T_npu`, Production, or
MLEK.

- [ ] **Step 5: Restore the original image and prove liveness**

Execute §8 steps 10.1–10.8 against the one backup made before deployment; do
not make a new backup. Require `sha256sum -c backup.sha256`, per-file
destination equality, unmount before USB_OFF, and the same `do_reboot_capture`
plus three-PING commands from Step 1. Finish with:

```bash
ssh gihwan 'set -eu
test ! -e /dev/sdb
test -z "$(findmnt -rn -S /dev/sdb1)"
for tty in /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3; do
  if fuser "$tty" >/dev/null 2>&1; then exit 1; fi
done'
ssh -t gihwan 'sudo fuser -v /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3; \
sudo lsof /dev/ttyUSB0 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyUSB3'
```

Expected: byte-exact original APP/VECTORS/DDR, DDR/CPUWAIT pass, PING 3/3
IDLE, seven protocol counters zero, USB off, `/dev/sdb` absent, mount zero,
and no userspace UART holder including root-owned processes at the checked
instant.

- [ ] **Step 6: Commit/tag board evidence only after independent audit**

Record the evidence root, raw hashes, analyzer output, restore hashes, and
exact post-board commit/tag in
`firmware/Selftest_pmu_diag/PMU_COMPLETION_POLL_COUNT_DIAG_V13_BOARD_RESULT.md`
and the four Obsidian notes from Task 10. V13 becomes `BOARD QUALIFIED FOR
CHARACTERIZATION` only if the full campaign and restore close without invalid
samples.
