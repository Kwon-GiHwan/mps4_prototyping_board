"""MCC transport harness v0 for the MPS4 FI101 board.

This is NOT runner firmware. PING / WRITE_MEMORY / READ_MEMORY / RUN_FIXED /
RESET_RUNNER_STATE are host-side compositions of existing MCC console commands
and the stock FI101 Selftest CLI. Address-range checking, CRC verification and
protocol versioning are policies enforced *by this host script*; the board does
not implement them. Target-side protocol, range protection and PMU access are
firmware-runner v1 work.

Transport path:
    host file -> SD card (USB mass storage) -> MCC WRITE_AXI -> DDR
"""

from __future__ import annotations

import subprocess
import time
import zlib
from dataclasses import dataclass
from typing import Sequence

HARNESS_VERSION = "v0"

SERIAL_BASE = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if0"
MCC_PORT = SERIAL_BASE + "0-port0"
SELFTEST_PORT = SERIAL_BASE + "1-port0"

SD_DEVICE = "/dev/sdb1"
SD_MOUNT = "/mnt"


# --- LAR addressing -------------------------------------------------------
#
# The MCC addresses system memory through Long Address Range ports. Passing a
# bare CPU address silently targets port 0 (QSPI) and returns garbage, so the
# port is always carried explicitly and DDR access is pinned to port 1.

LAR_PORT_QSPI = 0
LAR_PORT_DDR = 1
LAR_PORT_SBROM = 2


@dataclass(frozen=True)
class LarAddress:
    port: int
    offset: int

    def encode(self) -> int:
        if not 0 <= self.port <= 0xFF:
            raise ValueError("LAR port out of range: %d" % self.port)
        if not 0 <= self.offset < (1 << 40):
            raise ValueError("LAR offset out of range: 0x%x" % self.offset)
        return (self.port << 40) | self.offset

    def text(self) -> str:
        return '"0x%012X"' % self.encode()

    def plus(self, delta: int) -> "LarAddress":
        return LarAddress(port=self.port, offset=self.offset + delta)


# Selftest occupies 0x90000000 (LR_DDR window, 0x20000) and 0x90020000
# (LR_NoInit window, 0x100000). Staging starts immediately after both.
STAGING = LarAddress(port=LAR_PORT_DDR, offset=0x9012_0000)
STAGING_SIZE = 0x0100_0000  # 16 MiB, well inside the 0x8000_0000-0x9FFF_FFFF window
STAGING_LIMIT = STAGING.offset + STAGING_SIZE

# u85_Convolution.o .bss.sec_output_data, per Debug/selftest.map
CONV_OUTPUT = LarAddress(port=LAR_PORT_DDR, offset=0x9002_03C0)
CONV_OUTPUT_LEN = 0x100


def checked_end(base: int, length: int, limit: int) -> int:
    """Return the exclusive end address, rejecting overflow and out-of-window."""
    if length <= 0:
        raise ValueError("length must be positive, got %d" % length)
    end = base + length
    if end <= base:
        raise OverflowError("address overflow: 0x%x + %d" % (base, length))
    if end > limit:
        raise ValueError(
            "range exceeds allowed window: 0x%x..0x%x > limit 0x%x" % (base, end, limit)
        )
    return end


def check_staging(lar: LarAddress, length: int) -> int:
    """Validate a staging-window access. Returns the exclusive end offset."""
    if lar.port != LAR_PORT_DDR:
        raise ValueError("DDR access must use LAR port %d, got %d" % (LAR_PORT_DDR, lar.port))
    if lar.offset < STAGING.offset:
        raise ValueError("address 0x%x below staging base 0x%x" % (lar.offset, STAGING.offset))
    return checked_end(lar.offset, length, STAGING_LIMIT)


# --- shell / SD plumbing --------------------------------------------------


def _sudo(cmd: str, password: str) -> str:
    proc = subprocess.run(
        ["sudo", "-S", "sh", "-c", cmd],
        input=password + "\n",
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr


class SdCard:
    """USB mass-storage staging area. Each transfer needs a full mount cycle."""

    def __init__(self, mcc: "MccConsole", password: str) -> None:
        self._mcc = mcc
        self._password = password

    def __enter__(self) -> "SdCard":
        self._mcc.command("USB_ON", wait=3.0)
        time.sleep(2)
        _sudo("mount %s %s" % (SD_DEVICE, SD_MOUNT), self._password)
        return self

    def __exit__(self, *exc: object) -> None:
        _sudo("sync", self._password)
        _sudo("umount %s" % SD_MOUNT, self._password)
        self._mcc.command("USB_OFF", wait=3.0)

    def put(self, name: str, payload: bytes) -> None:
        tmp = "/tmp/_harness_stage.bin"
        with open(tmp, "wb") as handle:
            handle.write(payload)
        _sudo("cp %s %s/%s" % (tmp, SD_MOUNT, name), self._password)

    def get(self, name: str) -> bytes:
        with open("%s/%s" % (SD_MOUNT, name), "rb") as handle:
            return handle.read()

    def remove(self, *names: str) -> None:
        for name in names:
            _sudo("rm -f %s/%s" % (SD_MOUNT, name), self._password)


# --- serial consoles ------------------------------------------------------


class MccConsole:
    """Serial Port 0. Line ending is CR."""

    def __init__(self) -> None:
        import serial

        self._ser = serial.Serial(
            MCC_PORT, 115200, timeout=1, write_timeout=2,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )

    def command(self, line: str, wait: float = 2.0) -> str:
        self._ser.reset_input_buffer()
        self._ser.write(line.encode() + b"\r")
        self._ser.flush()
        time.sleep(wait)
        return self._ser.read(65536).decode("ascii", errors="replace")

    def close(self) -> None:
        self._ser.close()


class SelftestConsole:
    """Serial Port 1 (FPGA UART0). Line ending is LF."""

    def __init__(self) -> None:
        import serial

        self._ser = serial.Serial(
            SELFTEST_PORT, 115200, timeout=1, write_timeout=2,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )

    CHAR_GAP = 0.15
    """The GCC-built firmware drops back-to-back UART bytes, so pace them."""

    def command(self, line: str, wait: float = 4.0) -> str:
        self._ser.reset_input_buffer()
        for ch in line.encode():
            self._ser.write(bytes([ch]))
            self._ser.flush()
            time.sleep(self.CHAR_GAP)
        self._ser.write(b"\n")
        self._ser.flush()
        time.sleep(wait)
        return self._ser.read(65536).decode("ascii", errors="replace")

    def close(self) -> None:
        self._ser.close()


# --- harness --------------------------------------------------------------


@dataclass(frozen=True)
class PingResult:
    harness_version: str
    mcc_responsive: bool
    selftest_responsive: bool
    staging_lar: str
    staging_size: int


@dataclass(frozen=True)
class TransferResult:
    length: int
    source_crc32: int
    readback_crc32: int
    identical: bool


class Harness:
    def __init__(self, password: str) -> None:
        self.mcc = MccConsole()
        self.selftest = SelftestConsole()
        self._password = password

    def close(self) -> None:
        self.mcc.close()
        self.selftest.close()

    # -- logical commands --------------------------------------------------

    def ping(self) -> PingResult:
        mcc_ok = "Cmd>" in self.mcc.command("")
        st_ok = "Selftest>" in self.selftest.command("", wait=2.0)
        return PingResult(
            harness_version=HARNESS_VERSION,
            mcc_responsive=mcc_ok,
            selftest_responsive=st_ok,
            staging_lar="0x%012X" % STAGING.encode(),
            staging_size=STAGING_SIZE,
        )

    def reset_on(self) -> str:
        """WARNING: measured to leave DDR unusable until a full REBOOT.

        RESET_ON/RESET_OFF resets the CPU but does not re-run the MCC's DDR
        initialisation, which only happens during the boot sequence (the
        "DDR memory test at 0x70000000: PASSED" line). After RESET_ON every
        DDR readback returns zeros. Do not use it to guard writes.
        """
        return self.mcc.command("RESET_ON", wait=2.0)

    def reset_off(self) -> str:
        return self.mcc.command("RESET_OFF", wait=3.0)

    def reboot(self, timeout: float = 150.0) -> bool:
        """Full power-cycle boot. The only way to (re-)initialise DDR."""
        self.mcc.command("REBOOT", wait=3.0)
        deadline = time.time() + timeout
        seen = ""
        while time.time() < deadline:
            seen += self.mcc.command("", wait=3.0)
            if "Clearing SCC CPUWAIT" in seen and "Cmd>" in seen:
                time.sleep(3)
                return "DDR memory test at 0x70000000: PASSED" in seen
        return False

    def assert_idle(self) -> None:
        """Refuse to write unless the target is quiescent.

        Region isolation is what actually prevents a collision; this guard
        additionally ensures no inference is mid-flight, so a write cannot
        land while the NPU is streaming commands. CRC only tells us afterwards
        whether the bytes match -- it prevents nothing.
        """
        if "Selftest>" not in self.selftest.command("", wait=2.0):
            raise RuntimeError(
                "target not idle: no Selftest> prompt (inference running, "
                "MEMORY_TEST in progress, or CPU halted)"
            )

    def write_memory(self, lar: LarAddress, payload: bytes, name: str = "STAGE_W.BIN") -> None:
        """Offline load into the staging window while the target is idle."""
        check_staging(lar, len(payload))
        self.assert_idle()
        with SdCard(self.mcc, self._password) as sd:
            sd.put(name, payload)
        out = self.mcc.command('WRITE_AXI "\\%s" %s' % (name, lar.text()), wait=6.0)
        if "written to memory address" not in out:
            raise RuntimeError("WRITE_AXI did not confirm: %s" % out.strip())

    def read_memory(self, lar: LarAddress, length: int, name: str = "STAGE_R.BIN") -> bytes:
        end = checked_end(lar.offset, length, 1 << 40)
        end_lar = LarAddress(port=lar.port, offset=end)
        out = self.mcc.command(
            'READ_AXI "\\%s" %s %s' % (name, lar.text(), end_lar.text()), wait=6.0
        )
        if "File closed." not in out:
            raise RuntimeError("READ_AXI did not confirm: %s" % out.strip())
        with SdCard(self.mcc, self._password) as sd:
            data = sd.get(name)
            sd.remove(name)
        return data

    def round_trip(self, lar: LarAddress, payload: bytes) -> TransferResult:
        """Write, read back and compare.

        No RESET_ON guard: it would leave DDR unusable (see reset_on).
        Safety instead rests on two things -- the staging window lies outside
        every region the Selftest image occupies (verified against
        Debug/selftest.map), and every transfer is verified by readback.
        """
        self.write_memory(lar, payload)
        back = self.read_memory(lar, len(payload))
        return TransferResult(
            length=len(payload),
            source_crc32=zlib.crc32(payload) & 0xFFFFFFFF,
            readback_crc32=zlib.crc32(back) & 0xFFFFFFFF,
            identical=(back == payload),
        )

    def run_fixed(self, test_num: int = 19) -> str:
        return self.selftest.command(str(test_num), wait=6.0)

    def reset_runner_state(self) -> str:
        return self.selftest.command("-clearsummary", wait=4.0)
