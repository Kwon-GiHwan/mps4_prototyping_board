#!/usr/bin/env python3
"""Generate a copy of the vendor u85.c with ONE change: BUSY_SLEEP_TIMEOUT raised.

The original waits ~10k busy iterations for the NPU IRQ, then gives up and goes on to write
CMD=0xC (clock/power release) under a still-running NPU. Real networks run longer. The define is
unconditional in the source, so -D cannot override it. Contract:
docs/superpowers/specs/2026-10-07-pmu-model-step1-contract.md
"""
import argparse, hashlib, pathlib, re

VENDOR_SHA256 = "bcd877bbd42a35d83c8696d02b64d2ae4985a46fcce91b98102e08661b356bcf"
# The vendor file uses CRLF line endings; the anchor must not assume LF.
OLD = re.compile(r"#define BUSY_SLEEP_TIMEOUT 10000(?=\r?\n)")
NEW = "#define BUSY_SLEEP_TIMEOUT 200000000 /* Tier C step 1: was 10000 */"


# Change 2 (step 2): irq_never_triggered is set on a timeout and never cleared, so one timeout
# fails every later run on the same boot. The vendor test assumes one run per boot; this harness
# runs many. Clear it at test_u85 entry, next to the vendor's own `ret_code = 0`.
OLD2 = re.compile(r"(\{\r?\n    int ret_code = 0;)(\r?\n)")
NEW2 = r"\1 irq_never_triggered = false; /* Tier C step 2: per-run, not per-boot */\2"


def generate(text):
    out, n = OLD.subn(NEW, text)
    if n != 1:
        raise SystemExit(f"anchor matched {n} times, need 1")
    out, n = OLD2.subn(NEW2, out)
    if n != 1:
        raise SystemExit(f"test_u85 entry anchor matched {n} times, need 1")
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = pathlib.Path(a.base).read_bytes()
    if hashlib.sha256(data).hexdigest() != VENDOR_SHA256:
        raise SystemExit("vendor u85.c sha256 differs from the pinned original")
    out = pathlib.Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(generate(data.decode()).encode())
    print(f"generated {out}")


if __name__ == "__main__":
    main()
