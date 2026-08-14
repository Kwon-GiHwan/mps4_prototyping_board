import pathlib
import subprocess
import sys


MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / "Makefile.pmu_completion_poll_count_v13"
AUTHORITATIVE_V12_SHA256 = "cd44ad3e5f370833b03fb3c664da2a8cb9320e38d97786d4c2af6ec1109cf401"


def require(text: str, needle: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing required text: {needle}")


def forbid(text: str, needle: str) -> None:
    if needle in text:
        raise SystemExit(f"forbidden text present: {needle}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def validate_makefile(text: str) -> None:
    require(text, "BUILD  := build_pmu_completion_poll_count_v13")
    require(text, "PATCHER := patches/patch_pmu_completion_poll_count_v13.py")
    require(text, "GATE    := Selftest_pmu_diag/check_pmu_completion_poll_count_v13.py")
    require(text, "-DPMU_QUAL_SCHEMA_V13")
    require(text, "-DPMU_QUAL_SCHEMA_V8")
    require(text, "-DPMU_COMPLETION_POLL_COUNT_DIAG_V13")
    require(text, "TARGET := $(BUILD)/runner_pmu_completion_poll_count_v13")
    require(text, "MANIFEST := $(BUILD)/pmu_completion_poll_count_v13_manifest.json")
    require(text, "AUTHORITATIVE_V12_ELF := authoritative-v12/runner_pmu_completion_poll_v12.elf")
    require(text, f"AUTHORITATIVE_V12_SHA256 := {AUTHORITATIVE_V12_SHA256}")
    require(text, "CROSS_ELF_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_cross_elf_evidence.json")
    require(
        text,
        "RUNNER_RECORD_WIRE_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_runner_record_wire_evidence.json",
    )
    require(text, "all: bins preprocess check manifest")
    require(text, "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE)")
    require(text, "manifest: $(MANIFEST)")
    require(text, "$(CROSS_ELF_EVIDENCE): $(TARGET).elf $(AUTHORITATIVE_V12_ELF) $(GATE)")
    require(text, "$(RUNNER_RECORD_WIRE_EVIDENCE): $(TARGET).elf $(GATE)")
    require(text, "verify_cross_elf_contract(")
    require(text, "hashlib.sha256")
    require(text, "authoritative V12 ELF hash mismatch")
    require(text, "runner-record and wire dataflow gate")
    require(text, "must be produced by distinct linked-image proof")
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
    require(text, "--manifest-out $(MANIFEST)")

    forbid(text, "--allow-synthetic-evidence")
    forbid(text, "--vendor-src")
    forbid(text, "--interface-header")
    forbid(text, "--vendor-object")
    forbid(text, "--regs-header")
    forbid(text, "--preprocessed")
    forbid(text, "--cflags")
    forbid(text, "build_pmu_completion_poll_v12")
    forbid(text, "pmu_interval")
    forbid(text, "entry.S")
    forbid(text, "ENTRY_SRC")
    forbid(text, "ENTRY_OBJ")
    forbid(text, "ttyUSB")
    forbid(text, "mount")
    forbid(text, "github")
    forbid(text, "actions")


def expect_invalid(text: str, label: str) -> None:
    try:
        validate_makefile(text)
    except SystemExit:
        return
    raise SystemExit(f"{label}: mutation unexpectedly passed")


def main() -> int:
    text = MAKEFILE.read_text(encoding="utf-8")
    validate_makefile(text)

    expect_invalid(
        text.replace("check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE)", "check: $(CROSS_ELF_EVIDENCE)"),
        "missing runner-record/wire dependency",
    )
    expect_invalid(
        replace_once(
            text,
            "RUNNER_RECORD_WIRE_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_runner_record_wire_evidence.json",
            "RUNNER_RECORD_WIRE_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_helper_store_lock.json",
            "runner-record/wire evidence rename",
        ),
        "bypassed runner-record/wire evidence",
    )
    expect_invalid(
        text.replace(AUTHORITATIVE_V12_SHA256, "0" * 64),
        "wrong authoritative V12 hash plumbing",
    )

    help_text = subprocess.run(
        ["python3", "patches/patch_pmu_completion_poll_count_v13.py", "--help"],
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
