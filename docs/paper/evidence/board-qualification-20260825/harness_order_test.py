"""Capture-ordering must be enforced by the code, not by call-site discipline.

Attempt #1 was NOT_OBSERVED because the port opened after the application had
already finished. These run without a board: the guard is checked before any
serial I/O, so the mutation is testable offline.
"""
import sys, time, types
sys.path.insert(0, "/tmp")
import board_probe as B

R = {}
def ok(n, c): R[n] = bool(c)

class FakeCapture:
    def __init__(self, running=True): self.running = running

# --- the mutation the manager asked for: capture started AFTER reboot -------
# Simulated by a reset attempted with no capture running at all.
B.ORDER["capture_started_at"] = None
try:
    B.assert_capture_before_reset(None)
    ok("MUT_reboot_with_no_capture_rejected", False)
except B.CaptureOrderViolation:
    ok("MUT_reboot_with_no_capture_rejected", True)

try:
    B.assert_capture_before_reset(FakeCapture(running=False))
    ok("MUT_reboot_with_dead_capture_rejected", False)
except B.CaptureOrderViolation:
    ok("MUT_reboot_with_dead_capture_rejected", True)

# capture object claims to run but its start was never recorded
B.ORDER["capture_started_at"] = None
try:
    B.assert_capture_before_reset(FakeCapture(running=True))
    ok("MUT_unrecorded_capture_start_rejected", False)
except B.CaptureOrderViolation:
    ok("MUT_unrecorded_capture_start_rejected", True)

# --- boot_and_gate itself must refuse before touching the serial port -------
touched = {"serial": False}
real_mcc = B.mcc
BOOT_OK = ("DDR memory test at 0x70000000: PASSED\n"
           "Clearing SCC CPUWAIT\n"
           "Cmd> ")
def spy(cmd, wait=3.0):
    touched["serial"] = True
    return BOOT_OK          # let the boot loop terminate immediately
B.mcc = spy
B.ORDER["capture_started_at"] = None
try:
    B.boot_and_gate(None)
    ok("MUT_boot_and_gate_rejects_bad_order", False)
except B.CaptureOrderViolation:
    ok("MUT_boot_and_gate_rejects_bad_order", True)
ok("MUT_no_serial_io_before_guard", touched["serial"] is False)

# --- positive: a running, recorded capture is accepted ----------------------
B.ORDER["capture_started_at"] = time.monotonic()
try:
    ok("POS_running_capture_accepted", B.assert_capture_before_reset(FakeCapture(True)) is True)
except B.CaptureOrderViolation:
    ok("POS_running_capture_accepted", False)
ok("POS_reboot_time_recorded_after_capture",
   B.ORDER["reboot_issued_at"] is not None
   and B.ORDER["reboot_issued_at"] >= B.ORDER["capture_started_at"])

# postflight reboot is allowed without a capture, explicitly
touched["serial"] = False
try:
    B.boot_and_gate(require_capture=False)
    ok("POS_postflight_reboot_allowed_without_capture", touched["serial"] is True)
except B.CaptureOrderViolation:
    ok("POS_postflight_reboot_allowed_without_capture", False)
B.mcc = real_mcc

for k in sorted(R): print("  %-46s %s" % (k, "PASS" if R[k] else "FAIL"))
print("ALL_PASS" if all(R.values()) else "SOME_FAILED")

# --- postflight ordering: USB_OFF must FOLLOW the postflight REBOOT ---------
# Both probe attempts showed the reboot re-presents the debug USB card, so
# "USB_OFF -> REBOOT -> assert absent" leaves it exposed.
B.PF["reboot_at"] = None
B.PF["usb_off_at"] = None
try:
    B.assert_postflight_usb_off_order()
    ok("MUT_usb_off_before_postflight_reboot_rejected", False)
except B.PostflightOrderViolation:
    ok("MUT_usb_off_before_postflight_reboot_rejected", True)

# postflight_usb_off() must refuse before touching the serial port
touched["serial"] = False
try:
    B.postflight_usb_off()
    ok("MUT_postflight_usb_off_guarded", False)
except B.PostflightOrderViolation:
    ok("MUT_postflight_usb_off_guarded", True)
ok("MUT_no_serial_io_before_postflight_guard", touched["serial"] is False)

# positive: after a recorded postflight reboot the order is accepted
B.PF["reboot_at"] = time.monotonic()
try:
    ok("POS_usb_off_after_reboot_accepted", B.assert_postflight_usb_off_order() is True)
except B.PostflightOrderViolation:
    ok("POS_usb_off_after_reboot_accepted", False)
ok("POS_usb_off_time_after_reboot_time",
   B.PF["usb_off_at"] is not None and B.PF["usb_off_at"] >= B.PF["reboot_at"])

print()
for k in sorted(R):
    if k.startswith(("MUT_usb", "MUT_postflight", "MUT_no_serial_io_before_postflight", "POS_usb")):
        print("  %-46s %s" % (k, "PASS" if R[k] else "FAIL"))
print("POSTFLIGHT_ALL_PASS" if all(R[k] for k in R if "usb" in k or "postflight" in k)
      else "POSTFLIGHT_SOME_FAILED")
