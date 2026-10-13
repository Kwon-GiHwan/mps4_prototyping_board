import pathlib
import re
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
    require(text, "BASE_PMU_GATE := Selftest_pmu_diag/check_pmu_qual.py")
    require(text, "-DPMU_QUAL_SCHEMA_V13")
    require(text, "-DPMU_QUAL_SCHEMA_V8")
    require(text, "-DPMU_COMPLETION_POLL_COUNT_DIAG_V13")
    require(text, "TARGET := $(BUILD)/runner_pmu_completion_poll_count_v13")
    require(text, "MANIFEST := $(BUILD)/pmu_completion_poll_count_v13_manifest.json")
    require(text, "AUTHORITATIVE_V12_ELF := authoritative-v12/runner_pmu_completion_poll_v12.elf")
    require(text, f"AUTHORITATIVE_V12_SHA256 := {AUTHORITATIVE_V12_SHA256}")
    require(text, "V13_DWARF := $(BUILD)/runner_pmu_completion_poll_count_v13.dwarf.txt")
    require(text, "CROSS_ELF_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_cross_elf_evidence.json")
    require(
        text,
        "RUNNER_RECORD_WIRE_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_runner_record_wire_evidence.json",
    )
    require(
        text,
        "RETAINED_V12_EXECUTABLE_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_retained_v12_executable_evidence.json",
    )
    require(
        text,
        "RETAINED_V12_BASE_PMU_EVIDENCE := $(BUILD)/pmu_completion_poll_count_v13_retained_v12_base_pmu_evidence.json",
    )
    require(text, "all: bins preprocess check manifest")
    require(text, "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)")
    require(text, "manifest: $(MANIFEST)")
    require(text, "$(CROSS_ELF_EVIDENCE): $(TARGET).elf $(AUTHORITATIVE_V12_ELF) $(GATE)")
    require(text, "$(RUNNER_RECORD_WIRE_EVIDENCE): $(TARGET).elf $(GEN_RUNNER) $(GATE) $(V13_OBJDUMP) $(V13_NM) $(V13_DWARF)")
    require(text, "$(RETAINED_V12_EXECUTABLE_EVIDENCE): $(TARGET).elf $(GEN_RUNNER) $(GEN_VENDOR) $(GATE) $(V13_OBJDUMP) $(V13_NM)")
    require(text, "$(RETAINED_V12_BASE_PMU_EVIDENCE): $(TARGET).elf $(GEN_VENDOR) $(GEN_VENDOR_OBJ) $(PREPROCESSED) $(INTERFACE_HEADER) $(REGS_HEADER) $(GATE) $(BASE_PMU_GATE) $(V13_OBJDUMP) $(V13_NM)")
    require(text, "$(V13_DWARF): $(TARGET).elf")
    require(text, "verify_cross_elf_contract(")
    require(text, "verify_runner_record_wire_contract(")
    require(text, "verify_retained_v12_executable_contract(")
    require(text, "verify_retained_v12_base_pmu_contract(")
    require(text, "hashlib.sha256")
    require(text, "authoritative V12 ELF hash mismatch")
    require(text, "--debug-dump=info,loc")
    require(text, "--runner-generated $(GEN_RUNNER)")
    require(text, "--vendor-generated $(GEN_VENDOR)")
    require(text, "--elf $(TARGET).elf")
    require(text, "--authoritative-v12-elf $(AUTHORITATIVE_V12_ELF)")
    require(text, "--objdump-tool $(OBJDUMP)")
    require(text, "--nm-tool $(NM)")
    require(text, "--map $(TARGET).map")
    require(text, "--app-bin $(BUILD)/APP.BIN")
    require(text, "--vectors-bin $(BUILD)/VECTORS.BIN")
    require(text, "--ddr-bin $(BUILD)/DDR.BIN")
    require(text, "--v12-objdump $(V12_OBJDUMP)")
    require(text, "--v12-nm $(V12_NM)")
    require(text, "--v13-objdump $(V13_OBJDUMP)")
    require(text, "--v13-nm $(V13_NM)")
    require(text, "--v13-dwarf $(V13_DWARF)")
    require(text, "--readelf $(READELF)")
    require(text, "--cross-elf-evidence $(CROSS_ELF_EVIDENCE)")
    require(text, "--runner-record-wire-evidence $(RUNNER_RECORD_WIRE_EVIDENCE)")
    require(text, "--retained-v12-executable-evidence $(RETAINED_V12_EXECUTABLE_EVIDENCE)")
    require(text, "--retained-v12-base-pmu-evidence $(RETAINED_V12_BASE_PMU_EVIDENCE)")
    require(text, "--vendor-object $(GEN_VENDOR_OBJ)")
    require(text, "--interface-header $(INTERFACE_HEADER)")
    require(text, "--regs-header $(REGS_HEADER)")
    require(text, "--preprocessed $(PREPROCESSED)")
    require(text, '--cflags="$(CFLAGS)"')
    require(text, "--manifest-out $(MANIFEST)")
    require(text, "$(MANIFEST): $(TARGET).elf $(GEN_RUNNER) $(GEN_VENDOR) $(GEN_VENDOR_OBJ) $(PREPROCESSED) $(INTERFACE_HEADER) $(REGS_HEADER) $(GATE) $(BASE_PMU_GATE) bins")
    require(text, "\t@test -s $(MANIFEST)\n")

    forbid(text, "--allow-synthetic-evidence")
    forbid(text, "--vendor-src")
    forbid(text, "build_pmu_completion_poll_v12")
    forbid(text, "pmu_interval")
    forbid(text, "entry.S")
    forbid(text, "ENTRY_SRC")
    forbid(text, "ENTRY_OBJ")
    forbid(text, "ttyUSB")
    forbid(text, "mount")
    forbid(text, "ssh")
    forbid(text, "scp")
    forbid(text, "docker")
    forbid(text, "sudo")
    forbid(text, "github")
    forbid(text, "actions")


def expect_invalid(text: str, label: str) -> None:
    try:
        validate_makefile(text)
    except SystemExit:
        return
    raise SystemExit(f"{label}: mutation unexpectedly passed")


def extract_cross_elf_python(text: str) -> str:
    match = re.search(
        r"\$\(CROSS_ELF_EVIDENCE\):.*?\n\tpython3 -c '(.*?)'\n\n",
        text,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit("missing CROSS_ELF_EVIDENCE python3 -c body")
    return match.group(1)


def extract_runner_record_wire_python(text: str) -> str:
    match = re.search(
        r"\$\(RUNNER_RECORD_WIRE_EVIDENCE\):.*?\n\tpython3 -c '(.*?)'\n\n",
        text,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit("missing RUNNER_RECORD_WIRE_EVIDENCE python3 -c body")
    return match.group(1)


def extract_retained_v12_executable_python(text: str) -> str:
    match = re.search(
        r"\$\(RETAINED_V12_EXECUTABLE_EVIDENCE\):.*?\n\tpython3 -c '(.*?)'\n\n",
        text,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit("missing RETAINED_V12_EXECUTABLE_EVIDENCE python3 -c body")
    return match.group(1)


def extract_retained_v12_base_pmu_python(text: str) -> str:
    match = re.search(
        r"\$\(RETAINED_V12_BASE_PMU_EVIDENCE\):.*?\n\tpython3 -c '(.*?)' \"\$\(CFLAGS\)\"\n\n",
        text,
        re.DOTALL,
    )
    if match is None:
        raise SystemExit("missing RETAINED_V12_BASE_PMU_EVIDENCE python3 -c body")
    return match.group(1)


def main() -> int:
    text = MAKEFILE.read_text(encoding="utf-8")
    validate_makefile(text)
    compile(extract_cross_elf_python(text), str(MAKEFILE), "exec")
    compile(extract_runner_record_wire_python(text), str(MAKEFILE), "exec")
    compile(extract_retained_v12_executable_python(text), str(MAKEFILE), "exec")
    compile(extract_retained_v12_base_pmu_python(text), str(MAKEFILE), "exec")

    expect_invalid(
        text.replace(
            "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)",
            "check: $(CROSS_ELF_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)",
        ),
        "missing runner-record/wire dependency",
    )
    expect_invalid(
        text.replace(
            "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)",
            "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)",
        ),
        "missing retained-V12 executable dependency",
    )
    expect_invalid(
        text.replace(
            "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE) $(RETAINED_V12_BASE_PMU_EVIDENCE)",
            "check: $(CROSS_ELF_EVIDENCE) $(RUNNER_RECORD_WIRE_EVIDENCE) $(RETAINED_V12_EXECUTABLE_EVIDENCE)",
        ),
        "missing retained-V12 base PMU dependency",
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
    expect_invalid(
        text.replace("$(RUNNER_RECORD_WIRE_EVIDENCE): $(TARGET).elf $(GEN_RUNNER) $(GATE) $(V13_OBJDUMP) $(V13_NM) $(V13_DWARF)", "$(RUNNER_RECORD_WIRE_EVIDENCE): $(TARGET).elf $(GATE)"),
        "missing linked proof inputs",
    )
    expect_invalid(
        text.replace(
            "$(RETAINED_V12_EXECUTABLE_EVIDENCE): $(TARGET).elf $(GEN_RUNNER) $(GEN_VENDOR) $(GATE) $(V13_OBJDUMP) $(V13_NM)",
            "$(RETAINED_V12_EXECUTABLE_EVIDENCE): $(TARGET).elf $(GEN_RUNNER) $(GATE)",
        ),
        "missing retained-V12 executable proof inputs",
    )
    expect_invalid(
        text.replace("\t@test -s $(MANIFEST)\n", ""),
        "missing manifest non-empty guard",
    )
    expect_invalid(
        text.replace("--cross-elf-evidence $(CROSS_ELF_EVIDENCE) \\\n", ""),
        "missing cross-elf manifest binding",
    )
    expect_invalid(
        text.replace("--runner-record-wire-evidence $(RUNNER_RECORD_WIRE_EVIDENCE) \\\n", ""),
        "missing runner-record/wire manifest binding",
    )
    expect_invalid(
        text.replace("--retained-v12-executable-evidence $(RETAINED_V12_EXECUTABLE_EVIDENCE) \\\n", ""),
        "missing retained-V12 executable manifest binding",
    )
    expect_invalid(
        text.replace("--retained-v12-base-pmu-evidence $(RETAINED_V12_BASE_PMU_EVIDENCE) \\\n", ""),
        "missing retained-V12 base PMU manifest binding",
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
