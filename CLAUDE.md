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

## Standing constraints

- Pushing to `origin/main` — **HOLD**.
- Production `END_ONLY` — **FROZEN**.
- MLEK — **BLOCKED**.
- Board access is granted per named step, never standing. V15 board work is not
  authorized.
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
