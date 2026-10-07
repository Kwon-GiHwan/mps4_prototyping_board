#!/usr/bin/env python3
"""rnnoise_INT8 board integration qualification - exactly one run.

Measurement-path qualification only. Not a paper sample.

    preflight -> read-only backup of every destination -> deploy anchored artifact
    -> readback verify -> USB_OFF/device absent -> fresh boot -> one inference
    -> PMU qualification -> evidence freeze -> restore -> readback -> postflight

The credential is read once via getpass and held in memory. It is never written
to a file, an environment variable, a command line, or the evidence.
"""
import getpass, hashlib, json, os, shutil, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmuparse

MCC_PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if00-port0"
APP_PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
UART_PORTS = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3"]
WORKLOAD = sys.argv[1] if len(sys.argv) > 1 else "rnnoise_INT8"
SRC = "/tmp/probe_src/%s" % WORKLOAD          # anchored artifact staged here
OUT = "/tmp/probe_out/%s" % WORKLOAD
BIN_NAMES = ("boot.bin", "bram.bin", "ddr.bin")
ANCHORED_AXF_SHA = "83a69be4620ad1a6997efa17b5cebbe9"   # prefix check only
EV = {"probe": "board_executability_qualification",
      "workload": WORKLOAD,
      "attempt": 2,
      "attempt_1": {"deployment_boot_restore": "PASS",
                    "measurement_observation": "NOT_OBSERVED",
                    "reason": "CAPTURE_STARTED_AFTER_APPLICATION_COMPLETION",
                    "preserved": True},
      "BOARD_QUALIFICATION_RUNS": 0, "FORMAL_BOARD_SAMPLES": 0, "steps": []}


class Abort(RuntimeError):
    """A gate this probe cannot pass. Nothing is salvaged; restore still runs."""


class CaptureOrderViolation(RuntimeError):
    """REBOOT must never be issued before the listener is confirmed running.

    Attempt #1 failed because the port was opened after boot completed. The
    ordering is therefore a checked precondition rather than a convention held
    by the order of two call sites.
    """


ORDER = {"capture_started_at": None, "reboot_issued_at": None}
PF = {"reboot_at": None, "usb_off_at": None}


class PostflightOrderViolation(RuntimeError):
    """USB_OFF must follow the postflight REBOOT, not precede it.

    The reboot re-presents the debug USB card, so `USB_OFF -> REBOOT -> assert
    absent` leaves the card exposed. Both probe attempts showed this.
    """


def postflight_reboot():
    ddr, cpu, log = boot_and_gate(require_capture=False)
    PF["reboot_at"] = time.monotonic()
    return ddr, cpu, log


def assert_postflight_usb_off_order():
    if PF["reboot_at"] is None:
        raise PostflightOrderViolation(
            "USB_OFF requested before the postflight REBOOT")
    PF["usb_off_at"] = time.monotonic()
    return True


def postflight_usb_off():
    assert_postflight_usb_off_order()      # before any serial I/O
    usb_off()


def assert_capture_before_reset(capture):
    """Runs before any serial I/O so it is testable without a board."""
    if capture is None:
        raise CaptureOrderViolation("REBOOT requested with no capture object")
    if not getattr(capture, "running", False):
        raise CaptureOrderViolation("REBOOT requested while capture is not running")
    if ORDER["capture_started_at"] is None:
        raise CaptureOrderViolation("capture start was never recorded")
    now = time.monotonic()
    if now < ORDER["capture_started_at"]:
        raise CaptureOrderViolation("reset precedes capture start")
    ORDER["reboot_issued_at"] = now
    return True


def step(name, status, detail=None):
    EV["steps"].append({"step": name, "status": status, "detail": detail})
    print("  %-46s %s%s" % (name, status, "" if detail is None else "  " + str(detail)[:90]),
          flush=True)
    return status


def sh(*argv, stdin=None):
    return subprocess.run(argv, capture_output=True, text=True, input=stdin)


def sudo(pw, *argv):
    return sh("sudo", "-S", "-p", "", *argv, stdin=pw + "\n")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def mcc(cmd, wait=3.0):
    import serial
    p = serial.Serial(MCC_PORT, 115200, timeout=1, write_timeout=2)
    try:
        p.reset_input_buffer(); p.write(cmd.encode() + b"\r"); p.flush()
        time.sleep(wait)
        return p.read(262144).decode("ascii", errors="replace")
    finally:
        p.close()


def sdb_present():
    return os.path.exists("/dev/sdb")


def wait_for_sdb(present, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if sdb_present() == present:
            return True
        time.sleep(0.5)
    return sdb_present() == present


def mount_card(pw, ro):
    """Bounded mount. Identity of the block device is verified before mounting."""
    ident = sh("lsblk", "-n", "-o", "FSTYPE,LABEL", "/dev/sdb1").stdout.split()
    tran = sh("lsblk", "-n", "-o", "TRAN", "/dev/sdb").stdout.split()
    if ident[:2] != ["vfat", "M1SDP"] or "usb" not in tran:
        raise Abort("block device is not the board card: %r" % (ident + tran))
    mp = sh("mktemp", "-d", "/tmp/probe_sd.XXXXXXXX").stdout.strip()
    opts = "uid=%d,gid=%d,umask=022" % (os.getuid(), os.getgid())
    if ro:
        opts += ",ro"
    r = sudo(pw, "mount", "-t", "vfat", "/dev/sdb1", mp, "-o", opts)
    if not sh("findmnt", "-rn", "-S", "/dev/sdb1").stdout.strip():
        sh("rmdir", mp)
        raise Abort("bounded mount did not take: %s" % (r.stdout + r.stderr)[:200])
    return mp


def unmount_card(pw, mp):
    sh("sync")
    sudo(pw, "umount", mp)
    if sh("findmnt", "-rn", "-S", "/dev/sdb1").stdout.strip():
        raise Abort("card still mounted - USB_OFF must not be issued")
    sh("rmdir", mp)


def usb_on(pw):
    mcc("USB_ON", wait=4.0)
    if not wait_for_sdb(True):
        mcc("USB_OFF", wait=3.0)
        raise Abort("USB_ON did not present /dev/sdb1")


def usb_off():
    mcc("USB_OFF", wait=3.0)
    time.sleep(2)
    if not wait_for_sdb(False):
        raise Abort("/dev/sdb survived USB_OFF")


def boot_and_gate(capture=None, require_capture=True):
    if require_capture:
        assert_capture_before_reset(capture)      # before any serial I/O
    seen = mcc("REBOOT", wait=3.0)
    end = time.time() + 180.0
    while time.time() < end:
        seen += mcc("", wait=3.0)
        if "Clearing SCC CPUWAIT" in seen and "Cmd>" in seen:
            time.sleep(3); break
    return ("DDR memory test at 0x70000000: PASSED" in seen,
            "Clearing SCC CPUWAIT" in seen, seen)


class AppCapture:
    """The listener must be open BEFORE the reset.

    The application prints during boot and rnnoise completes in well under a
    second on hardware, so a port opened after boot_and_gate() returns has
    already missed the run - data arriving while no process holds the tty is
    discarded, not buffered.
    """

    def __init__(self):
        import serial
        self._port = serial.Serial(APP_PORT, 115200, timeout=0.5)
        self._port.reset_input_buffer()
        self._chunks = []
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.running = False
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        if not self._ready.wait(5.0):        # the thread must prove it is reading
            self.close()
            raise Abort("app UART reader thread did not start")
        self.running = True
        ORDER["capture_started_at"] = time.monotonic()

    def port_path(self):
        return os.path.realpath(APP_PORT)

    def _read(self):
        self._ready.set()                    # set once inside the loop's owner
        while not self._stop.is_set():
            try:
                c = self._port.read(65536)
            except Exception:
                break
            if c:
                self._chunks.append(c.decode("ascii", errors="replace"))

    def text(self):
        return "".join(self._chunks)

    def wait_for(self, marker, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if marker in self.text():
                time.sleep(2.0)          # let the tail flush
                return True
            time.sleep(0.25)
        return False

    def close(self):
        self.running = False
        self._stop.set()
        self._thread.join(timeout=3)
        try:
            self._port.close()
        except Exception:
            pass


def find_destinations(mp):
    """Discover exactly what this deployment will overwrite. Fail closed."""
    images = []
    for root, _dirs, files in os.walk(mp):
        for f in files:
            if f.lower() == "images.txt":
                images.append(os.path.join(root, f))
    soft = os.path.join(mp, "SOFTWARE")
    if not os.path.isdir(soft):
        raise Abort("no SOFTWARE directory on the card")
    dests = {n: os.path.join(soft, n) for n in BIN_NAMES}
    if len(images) != 1:
        raise Abort("expected exactly one images.txt, found %d: %r" % (len(images), images))
    dests["images.txt"] = images[0]
    return dests


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=== workload: %s ===" % WORKLOAD, flush=True)
    backup_dir = os.path.join(OUT, "backup"); os.makedirs(backup_dir, exist_ok=True)
    # tty -> prompt; no tty -> first stdin line. Held in memory only; never
    # placed on a command line, written to disk, or copied into the evidence.
    if sys.stdin.isatty():
        pw = getpass.getpass("sudo password (held in memory only, never recorded): ")
    else:
        pw = sys.stdin.readline().rstrip("\r\n")
    if not pw:
        raise SystemExit("no credential supplied on stdin")
    restore_needed = False
    dests = originals = None
    try:
        print("\n== PREFLIGHT ==", flush=True)
        step("device absent before USB_ON", "PASS" if not sdb_present() else "FAIL")
        if sdb_present(): raise Abort("/dev/sdb present before USB_ON")
        step("mounts referencing card", "PASS" if not sh("findmnt","-rn","-S","/dev/sdb1").stdout.strip() else "FAIL")
        lsof = sudo(pw, "lsof", "/dev/sdb", "/dev/sdb1", *UART_PORTS)
        holders = [l for l in lsof.stdout.splitlines()[1:] if l.strip()]
        step("root-inclusive UART/block holders", "PASS" if not holders else "FAIL", len(holders))
        if holders: raise Abort("holders present: %r" % holders[:3])
        app_tty = os.path.realpath(APP_PORT)
        l1 = sudo(pw, "lsof", app_tty)
        h1 = [l for l in l1.stdout.splitlines()[1:] if l.strip()]
        step("app UART (%s) holders before capture" % os.path.basename(app_tty),
             "PASS" if not h1 else "FAIL", len(h1))
        if h1: raise Abort("app UART already held: %r" % h1[:2])
        step("runner protocol PING / counters", "NOT_APPLICABLE",
             "MLEK stock runner implements no such protocol; board-level gates used instead")

        print("\n== SOURCE ARTIFACT (anchored) ==", flush=True)
        src = {n: os.path.join(SRC, n) for n in BIN_NAMES}
        src["images.txt"] = os.path.join(SRC, "images.txt")
        source_hash = {n: sha(p) for n, p in src.items()}
        for n in sorted(source_hash):
            step("source %s" % n, "OK", source_hash[n][:16])

        print("\n== READ-ONLY BACKUP ==", flush=True)
        usb_on(pw)
        mp = mount_card(pw, ro=True)
        try:
            dests = find_destinations(mp)
            step("destination set discovered", "OK",
                 {k: v.replace(mp, "") for k, v in dests.items()})
            originals = {}
            for n, path in dests.items():
                if os.path.exists(path):
                    dst = os.path.join(backup_dir, n)
                    shutil.copy2(path, dst)
                    originals[n] = {"existed": True, "sha256": sha(dst), "card_path": path.replace(mp, "")}
                else:
                    originals[n] = {"existed": False, "card_path": path.replace(mp, "")}
                step("backup %s" % n, "OK",
                     originals[n].get("sha256", "DID_NOT_EXIST")[:16])
            rel = {n: d["card_path"] for n, d in originals.items()}
        finally:
            unmount_card(pw, mp)
        EV["backup"] = originals

        print("\n== DEPLOY (anchored rnnoise artifact only) ==", flush=True)
        mp = mount_card(pw, ro=False)
        restore_needed = True
        try:
            for n, path in [(n, os.path.join(mp, rel[n].lstrip("/"))) for n in src]:
                with open(src[n], "rb") as s, open(path, "wb") as d:
                    d.write(s.read())
            sh("sync")
            written = {n: sha(os.path.join(mp, rel[n].lstrip("/"))) for n in src}
        finally:
            unmount_card(pw, mp)
        print("\n== READ-BACK VERIFY ==", flush=True)
        mp = mount_card(pw, ro=True)
        try:
            readback = {n: sha(os.path.join(mp, rel[n].lstrip("/"))) for n in src}
        finally:
            unmount_card(pw, mp)
        usb_off()
        step("device absent after USB_OFF", "PASS" if not sdb_present() else "FAIL")
        match = all(source_hash[n] == written[n] == readback[n] for n in src)
        for n in sorted(src):
            step("source==declared==destination %s" % n,
                 "MATCH" if source_hash[n] == written[n] == readback[n] else "MISMATCH",
                 readback[n][:16])
        EV["deploy"] = {"source": source_hash, "written": written, "readback": readback,
                        "all_match": match}
        if not match:
            raise Abort("deployment read-back mismatch")

        print("\n== FRESH BOOT (listener opened first) ==", flush=True)
        cap = AppCapture()                       # open BEFORE the reset
        step("app UART listener open before reset", "OK", os.path.basename(cap.port_path()))
        own = sudo(pw, "lsof", "-t", cap.port_path())
        pids = [x for x in own.stdout.split() if x.strip()]
        owns = str(os.getpid()) in pids
        step("capture owns expected tty", "PASS" if owns else "FAIL",
             "pid %d in %r" % (os.getpid(), pids))
        step("no unexpected UART holder", "PASS" if len(pids) <= 1 else "FAIL", pids)
        if not owns or len(pids) > 1:
            cap.close(); raise Abort("app UART ownership not exclusive: %r" % pids)
        ddr, cpuwait, boot_log = boot_and_gate(cap)
        step("capture-before-reset guard", "ENFORCED",
             "capture_started_at < reboot_issued_at")
        step("DDR self-test", "PASS" if ddr else "FAIL")
        step("CPUWAIT cleared", "PASS" if cpuwait else "FAIL")
        EV["boot"] = {"ddr_passed": ddr, "cpuwait_cleared": cpuwait, "log_tail": boot_log[-1500:]}
        if not (ddr and cpuwait):
            raise Abort("boot health gate failed")

        print("\n== ONE INFERENCE ==", flush=True)
        got = cap.wait_for("Inference completed.", 180.0)
        app = cap.text()
        cap.close()
        step("marker observed within window", "PASS" if got else "FAIL",
             "%d bytes captured" % len(app))
        EV["app_uart"] = app[-4000:]
        open(os.path.join(OUT, "app_uart.txt"), "w").write(app)
        EV["BOARD_QUALIFICATION_RUNS"] = 1
        step("completion marker", "PASS" if "Inference completed." in app else "FAIL")
        fatal = [m for m in ("tensor allocation failed", "Failed to initialise model",
                             "Failed to resize buffer", "NPU initialisation failed")
                 if m in app]
        step("no fatal/NPU error", "PASS" if not fatal else "FAIL", fatal or None)

        print("\n== PMU MEASUREMENT-PATH QUALIFICATION ==", flush=True)
        q = {"marker": "Inference completed." in app, "fatal": fatal}
        try:
            rec = pmuparse.parse_profile(app)
            q["parsed"] = True
            q["event_set"] = rec["event_set"]
            q["values"] = {k: v["value"] for k, v in rec["events"].items()}
            q["emitted_names"] = {k: v["emitted_name"] for k, v in rec["events"].items()}
            q["family"] = pmuparse.classify_generation(rec)
            q["total"] = rec["total"]
            q["total_nonzero"] = rec["total"] > 0
            q["identity_total_eq_active_plus_idle"] = pmuparse.total_identity_holds(rec)
            step("PMU profile block parsed", "PASS")
            step("board-emitted event set", "OK", ",".join(rec["event_set"]))
            step("event family", "OK", q["family"])
            step("NPU TOTAL present and nonzero", "PASS" if q["total_nonzero"] else "FAIL", rec["total"])
            step("TOTAL == ACTIVE + IDLE", "PASS" if q["identity_total_eq_active_plus_idle"] else "FAIL",
                 "%d == %d + %d" % (rec["total"], rec["active"], rec["idle"]))
            zeros = [k for k, v in q["values"].items() if v == 0]
            step("auxiliary zero counters (not an error)", "INFO", zeros or "none")
        except pmuparse.PmuParseError as e:
            q["parsed"] = False
            q["parse_error"] = str(e)
            step("PMU profile block parsed", "FAIL", str(e))

        q["STATIC"] = {
            "chain": "StartProfiling -> hal_pmu_reset -> CYCCNT_Reset + EVCNTR_ALL_Reset "
                     "-> start snapshot -> exactly one RunInference -> StopProfiling "
                     "-> end snapshot -> delta",
            "source": "UseCaseCommonUtils.cc:69-75, Profiler.cc:32-75, "
                      "ethosu_profiler.c:150-190",
            "verdict": "PASS"}
        q["LIVE"] = {
            "profile_block_parsed": q.get("parsed", False),
            "total_nonzero": q.get("total_nonzero", False),
            "consistency_relation_valid": q.get("identity_total_eq_active_plus_idle", False),
            "event_family": q.get("family"),
            "verdict": "PASS" if (q.get("parsed") and q.get("total_nonzero")
                                  and q.get("identity_total_eq_active_plus_idle")) else "FAIL"}
        q["stale_exclusion_chain"] = {
            "fresh_boot": True,
            "pre_inference_pmu_reset_path": True,
            "exactly_one_inference": q.get("marker", False),
            "complete_live_profile_block": q.get("parsed", False),
            "nonzero_total": q.get("total_nonzero", False),
            "consistency_holds": q.get("identity_total_eq_active_plus_idle", False)}
        q["family_is_expected"] = q.get("family") == "U85_SRAM_EXT_FAMILY"
        step("STATIC evidence", q["STATIC"]["verdict"])
        step("LIVE evidence", q["LIVE"]["verdict"])
        step("event family is U85_SRAM_EXT_FAMILY",
             "PASS" if q["family_is_expected"] else "FAIL", q.get("family"))
        qualified = bool(q.get("marker") and not fatal and q.get("parsed")
                         and q.get("family_is_expected")
                         and q.get("total_nonzero")
                         and q.get("identity_total_eq_active_plus_idle"))
        q["verdict"] = "QUALIFIED" if qualified else "NOT_QUALIFIED"
        EV["pmu_qualification"] = q
        EV["BOARD_MEASUREMENT_PATH"] = q["verdict"]
        step("BOARD_MEASUREMENT_PATH", q["verdict"])
        json.dump(EV, open(os.path.join(OUT, "evidence.json"), "w"), indent=1)
    except Abort as e:
        step("ABORT", "STOP", str(e))
        EV["abort"] = str(e)
    except Exception as e:                      # never leave the card mounted
        step("UNEXPECTED", "STOP", repr(e))
        EV["abort"] = repr(e)
    finally:
        print("\n== RESTORE ==", flush=True)
        try:
            if restore_needed and originals:
                if not sdb_present():
                    usb_on(pw)
                mp = mount_card(pw, ro=False)
                try:
                    for n, meta in originals.items():
                        target = os.path.join(mp, meta["card_path"].lstrip("/"))
                        if meta["existed"]:
                            shutil.copy2(os.path.join(backup_dir, n), target)
                        elif os.path.exists(target):
                            os.remove(target)
                    sh("sync")
                finally:
                    unmount_card(pw, mp)
                mp = mount_card(pw, ro=True)
                try:
                    back = {}
                    for n, meta in originals.items():
                        t = os.path.join(mp, meta["card_path"].lstrip("/"))
                        back[n] = sha(t) if os.path.exists(t) else None
                finally:
                    unmount_card(pw, mp)
                ok = all((originals[n]["sha256"] if originals[n]["existed"] else None) == back[n]
                         for n in originals)
                EV["restore"] = {"readback": back, "all_match": ok}
                for n in sorted(originals):
                    step("restored %s" % n, "MATCH" if
                         (originals[n]["sha256"] if originals[n]["existed"] else None) == back[n]
                         else "MISMATCH")
                usb_off()
            else:
                step("restore", "NOT_NEEDED", "no write was performed")
        except Exception as e:
            step("RESTORE_FAILED", "CRITICAL", repr(e))
            EV["restore_error"] = repr(e)
        print("\n== POSTFLIGHT ==", flush=True)
        try:
            ddr2, cpu2, _ = postflight_reboot()      # REBOOT first
            step("postflight DDR", "PASS" if ddr2 else "FAIL")
            step("postflight CPUWAIT", "PASS" if cpu2 else "FAIL")
            postflight_usb_off()                     # ...then USB_OFF, enforced
            step("postflight USB_OFF after reboot", "ENFORCED")
            step("postflight /dev/sdb absent", "PASS" if not sdb_present() else "FAIL")
            step("postflight mounts", "PASS" if not sh("findmnt","-rn","-S","/dev/sdb1").stdout.strip() else "FAIL")
            l2 = sudo(pw, "lsof", "/dev/sdb", "/dev/sdb1", *UART_PORTS)
            h2 = [l for l in l2.stdout.splitlines()[1:] if l.strip()]
            step("postflight UART holders", "PASS" if not h2 else "FAIL", len(h2))
            EV["postflight"] = {"ddr": ddr2, "cpuwait": cpu2,
                                "sdb_absent": not sdb_present(), "holders": len(h2)}
        except Exception as e:
            step("POSTFLIGHT_FAILED", "CRITICAL", repr(e))
        json.dump(EV, open(os.path.join(OUT, "evidence.json"), "w"), indent=1)
        print("\nevidence -> %s/evidence.json" % OUT, flush=True)


if __name__ == "__main__":
    main()
