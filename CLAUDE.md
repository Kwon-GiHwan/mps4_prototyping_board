# MPS4 / Ethos-U85 PMU diagnostics

Firmware diagnostics for an ARM Ethos-U85 NPU on an MPS4 board, with host-side
static gates over the built ELF. Bare-metal Cortex-M85, `arm-none-eabi-gcc
15.2.1`, `-O1 -g3`.

## The one thing this project is about

**A check that cannot fail is worse than no check.** Eleven such gates have been
found here — rules that examined nothing and reported success. Several more were
introduced and caught during V15 development, in code written the same week.

So: every gate gets mutation-tested. Neuter the check, run the suite, require
RED. A mutation that survives means the branch has no reaching fixture; add the
fixture, do not delete the mutation. Restore by digest afterwards (`shasum -a
256` against a saved copy) rather than by eye.

Related conventions that exist for the same reason:

- Every refusal carries a rule id: `raise fail_rule(RULE_X, "...")`, and
  `refusal_rule(exc)` reads it back. A negative fixture must fail **at its own
  rule** — tripping a neighbouring rule is a failed fixture, not a pass.
- Each module keeps a `RULES` tuple and a test that runs every fixture and
  asserts the tripped set equals it.
- Tri-state, always: PASS / FAIL / **UNPROVEN**. Unproven is not "probably fine".
- Outcomes are preregistered values from a closed set, never prose written after
  looking at the data.

## Running the tests

`pytest` does **not** work on this repo. Several `host/tests/test_*.py` are
scripts that call `sys.exit()` at import, so collection dies with an
INTERNALERROR. Use unittest, per module:

```sh
python3 -m unittest host.tests.test_deployment_pmu_completion_s5_only_control
```

Run from the repo root. `.claude/commands/suite.md` runs the whole set.

Clear `__pycache__` before trusting a result after editing or restoring a file —
stale bytecode has previously made a restored file look like it still failed:

```sh
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
```

## Import conventions — this has bitten twice

Two conventions coexist and **must not be mixed within one module's reach**:

| era | modules import as | tests import as |
| --- | --- | --- |
| V14 wire parsers | `from host import runner_proto as v8` | `from host import ...` |
| V15 (`*_s5_only_control`) | bare `import contract_...` with `host/` on `sys.path` | `sys.path.insert(REPO/"host")` then bare |

Reaching the same file by both paths loads it **twice**, as two module objects.
The consequences are silent and confusing:

- `mock.patch.object(module, ...)` patches one copy while the code under test
  runs the other, so the patch appears to do nothing.
- `except ProtocolError` misses, because `host.runner_proto.ProtocolError` and
  `runner_proto.ProtocolError` are different classes.

A module that needs both worlds should bootstrap `host/` onto `sys.path` itself
and then use bare imports throughout (see
`host/deployment_pmu_completion_s5_only_control.py`).

## Build environment

Builds run in a container on a remote host. Nothing builds on the Mac — there is
no local `arm-none-eabi-gcc`, and part of the source tree (`Device_SSE-320`,
`Selftest_cli`) lives only in the container.

```sh
ssh gihwan                     # ssh.gihwan.uk via cloudflared; x86_64
                               # NOT gihwan-local / gihwan-web — those are other boxes
docker exec benchmark-runner sh -lc "cd /work/selftest && ..."
```

Example, V14 Q:

```sh
make -f Makefile.pmu_completion_visibility_v14 V14_VARIANT=Q clean bins
# -> build_pmu_completion_visibility_v14/Q/{APP,VECTORS,DDR}.BIN + .elf
```

`bins` is `objcopy` from the linked ELF into the three images; that is the
ELF→APP relation the provenance chain depends on.

## Wire format (schema 15, S5-only)

127 words / 508 bytes: 8 header + 85 frozen v8 body + 34 appendix.

The appendix is declared **independently** in
`firmware/patches/patch_pmu_completion_s5_only_control_source.py` and
`host/runner_proto_pmu_completion_s5_only_control.py`, and
`verify_wire_contract()` asserts the two tuples are equal. Do not make one
import the other — a copy agrees with itself and proves nothing.

Never name wire words by zipping: `dict(zip(names, words))` truncates to the
shorter side without raising. Enforce exact length first.

**`comparison_mode` and `build_id` are not on the wire and cannot be.** The mode
says whether this image's loop matches the frozen V14 Q reference, which
host-side ELF analysis decides; the target has no way to know it. They reach a
record from a `VerifiedCellContext`. Keep the boundary:

```
parse_frame(raw)                    -> ParsedFrame        wire facts only
normalize(parsed, cell_context)     -> NormalizedRecord   + static/derived facts
```

A parser that reads a manifest has re-mixed the provenances. See
`docs/superpowers/plans/2026-08-21-*-amendment-2.md`.

## Where the work stands

V13, V14 and V15 are closed. `v15-frozen` is the final tag; the closing state is
`docs/superpowers/evidence/v15-campaign-20260823/CLOSING_STATEMENT.md` and the
combined narrative is `docs/superpowers/evidence/V13_V15_CHARACTERIZATION.md`.

Further completion-observability board work is **not recommended** — the
question is characterized as far as the observation boundary allows.

Two claims that look available and are not:

- **The V14 Q floor (732) minus the V15 S5 floor (754) is not a result.**
  `RULE_CROSS_VARIANT_ABSOLUTE_COMPARISON` refuses it, and the vocabulary guard
  refuses the sentence. `Q_S5_EQUIVALENT` means the control structures are
  matched, not that counts against two different MMIO observables share an axis.
- **"Falsified as a necessary condition" is not "falsified."** The structure no
  longer *requires* QREAD; whether Q and S5 share a mechanism is
  `NOT ESTABLISHED`.

## Paper campaign — what carries forward

Full record in `docs/paper/PROJECT_RECORD.md`; every digest and tag in
`docs/paper/EVIDENCE_INDEX.md`. The traps worth knowing before touching this
again:

- **A build that compiles is not a cell that runs.** 133 cells compiled, 6 could
  not run. `NOT_EXECUTABLE_MEMORY` is a result; never drop such a cell silently
  or rebase a scaling ladder onto a higher MAC to fill the hole.
- **Timing adapter state changes what is being measured.** It is forced OFF for
  `sse-310`/`sse-315` — visible as *absent compiled source files*, not merely a
  flag. Those 56 cells are executability evidence, never performance data.
- **The firmware embeds its own build time** (`Main.cc:38`), so no AXF is
  reproducible without `SOURCE_DATE_EPOCH` pinned to the MLEK commit timestamp.
- **The stock MLEK runner does exactly one inference per boot.** Any protocol
  wanting N runs per boot is a V15 custom-runner idea and does not apply here.
- **The generated model `.cc` carries a wall-clock comment** that never reaches
  the binary. Hash the canonical body; the raw hash is informational only.
- **PMU event names are generation-conditional** — U55/U65 emit `AXI*`, U85 emits
  `SRAM_*`/`EXT_*`. Discover the emitted set; never hardcode names.
- **Board restore is not "write the backups back."** The card may not contain the
  files being deployed, so restore includes deleting created files. Discover the
  destination set from the card and abort before writing if it is ambiguous.
- **Order matters where hardware is concerned**: the UART listener must be alive
  *before* `REBOOT`, and postflight `USB_OFF` must come *after* the reboot, which
  re-presents the card. Both are enforced by guards, not by call order.

Contracts are frozen before the data exists, and a superseded contract is
recorded as an amendment — never edited away. If a metric was not preregistered,
it is not computed after seeing the values; it may only be run later, labelled
`POST_HOC_DESCRIPTIVE`.

## Standing constraints

- Pushing to `origin/main` — **HOLD**. Feature branches may be pushed.
- Production `END_ONLY` — **FROZEN**.
- MLEK — was globally **BLOCKED**; the paper campaign proceeded under narrow,
  per-step manager authorizations. Treat it as blocked again absent a new one.
- Board access is granted per named step, never standing. V15 board work is not
  authorized.
- Never patch `inference_runner` to obtain a metric. If the stock path cannot
  produce an observation, that is the finding.
- Never issue `USB_OFF` while the card is mounted.
- Operator credentials are never written to documents, evidence, commits,
  history, environment variables or files. Record only that approval was given.
- Frozen anchors (`58b0cad`, `3ca7bb1`, `d96fa97`, `153f368`) are never
  rewritten. Corrections go in a new amendment.

## Reporting

State the verification level and be exact about scope:

```
검증 수준: [구문 | 단위 | 통합 | E2E]
실제 실행한 것: ...
실행하지 않은 것: ...
```

"Syntax-checked" and "works" are different claims. Never report the second
without having run it.
