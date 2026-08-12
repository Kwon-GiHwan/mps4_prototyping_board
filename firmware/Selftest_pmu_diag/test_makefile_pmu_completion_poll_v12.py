import pathlib
import subprocess
import sys


MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / "Makefile.pmu_completion_poll_v12"


def require(text: str, needle: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing required text: {needle}")


def forbid(text: str, needle: str) -> None:
    if needle in text:
        raise SystemExit(f"forbidden text present: {needle}")


def main() -> int:
    text = MAKEFILE.read_text(encoding="utf-8")

    require(text, "BUILD  := build_pmu_completion_poll_v12")
    require(text, "PATCHER := patches/patch_pmu_completion_poll_v12.py")
    require(text, "GATE    := Selftest_pmu_diag/check_pmu_completion_poll_v12.py")
    require(text, "-DPMU_QUAL_SCHEMA_V12")
    require(text, "-DPMU_COMPLETION_POLL_DIAG_V12")
    require(text, "TARGET := $(BUILD)/runner_pmu_completion_poll_v12")
    require(text, "MANIFEST := $(BUILD)/pmu_completion_poll_v12_manifest.json")
    require(text, "--manifest-out $(MANIFEST)")
    require(text, "--runner-generated $(GEN_RUNNER)")
    require(text, "--vendor-generated $(GEN_VENDOR)")
    require(text, "--elf $(TARGET).elf")
    require(text, "--map $(TARGET).map")
    require(text, "--app-bin $(BUILD)/APP.BIN")
    require(text, "--vectors-bin $(BUILD)/VECTORS.BIN")
    require(text, "--ddr-bin $(BUILD)/DDR.BIN")
    require(text, "--objdump $(OBJDUMP)")
    require(text, "--nm $(NM)")
    require(text, "--readelf $(READELF)")
    require(text, "--runner-in $(RUNNER_SRC)")
    require(text, "--vendor-in $(VENDOR_SRC)")
    require(text, "--runner-out $(GEN_RUNNER)")
    require(text, "--vendor-out $(GEN_VENDOR)")
    forbid(text, "--vendor-src")
    forbid(text, "--interface-header")
    forbid(text, "--vendor-object")
    forbid(text, "--regs-header")
    forbid(text, "--preprocessed")
    forbid(text, "--cflags")
    forbid(text, "--allow-synthetic-evidence")

    forbid(text, "v11a")
    forbid(text, "pmu_interval")
    forbid(text, "entry.S")
    forbid(text, "ENTRY_SRC")
    forbid(text, "ENTRY_OBJ")

    help_text = subprocess.run(
        ["python3", "patches/patch_pmu_completion_poll_v12.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(MAKEFILE.parent),
    ).stdout
    require(help_text, "--runner-in")
    require(help_text, "--vendor-in")
    require(help_text, "--runner-out")
    require(help_text, "--vendor-out")

    print("PASS makefile graph semantics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
