"""Deploy the anchored V15 candidate, then read it back from the device.

The read-back is deliberately not a re-read of the files just written: that can
be answered from the page cache and would confirm the write call rather than the
write. The card is unmounted and remounted read-only first, so the hashes come
off the device.
"""
import hashlib, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcc_harness import MccConsole, SD_DEVICE, SD_MOUNT

PASSWORD = sys.stdin.readline().rstrip("\n")
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(HERE, "deploy")
CARD_DIR = os.path.join(SD_MOUNT, "SOFTWARE")
IMAGES = ("APP.BIN", "VECTORS.BIN", "DDR.BIN")

MANIFEST = {
    "APP.BIN": "4967fa39205eefb11601be165b0e553239d2b201e4b5019d4efb7bf1ba6dc693",
    "VECTORS.BIN": "6864a22bf98b0172ee7ace58aead9c6d85ebd3afec64ddae0771bbe2474d0d91",
    "DDR.BIN": "81d37a219a6b4141d0b433796711ab8af2ee2c3c668a28143a3ffe6a574ade98",
}


def sudo(cmd):
    p = subprocess.run(["sudo", "-S", "sh", "-c", cmd],
                       input=PASSWORD + "\n", capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def sha(path):
    rc, out = sudo("sha256sum %s" % path)
    return out.split()[0] if rc == 0 and out else None


def mount_rows():
    rc, out = sudo("findmnt -rn -S %s | wc -l" % SD_DEVICE)
    try:
        return int(out.strip().splitlines()[-1])
    except Exception:
        return -1


log = []
def step(_step, **kw):
    kw["step"] = _step
    log.append(kw)
    print("%-28s %s" % (name, {k: v for k, v in kw.items() if k != "step"}))


# source digests, computed here rather than trusted
source = {}
for name in IMAGES:
    with open(os.path.join(STAGE, name), "rb") as fh:
        source[name] = hashlib.sha256(fh.read()).hexdigest()
step("source_digests", ok=all(source[n] == MANIFEST[n] for n in IMAGES))
if any(source[n] != MANIFEST[n] for n in IMAGES):
    step("ABORT_SOURCE_NOT_MANIFEST")
    sys.exit(1)

mcc = MccConsole()
mcc.command("USB_ON", wait=3.0)
time.sleep(3)
step("usb_on", sdb=os.path.exists(SD_DEVICE))

rc, out = sudo("mount %s %s" % (SD_DEVICE, SD_MOUNT))
step("mount_rw", rc=rc, out=out[:100])

before = {n: sha(os.path.join(CARD_DIR, n)) for n in IMAGES}
step("on_card_before", **{n: (before[n] or "")[:12] for n in IMAGES})

for name in IMAGES:
    rc, out = sudo("cp %s %s/%s" % (os.path.join(STAGE, name), CARD_DIR, name))
    step("wrote", name=name, rc=rc, err=out[:80])
sudo("sync")

# unmount and remount read-only so the read-back comes off the device
rc, out = sudo("umount %s" % SD_MOUNT)
step("umount_after_write", rc=rc, rows=mount_rows())
rc, out = sudo("mount -o ro %s %s" % (SD_DEVICE, SD_MOUNT))
step("remount_ro", rc=rc)

destination = {n: sha(os.path.join(CARD_DIR, n)) for n in IMAGES}
step("destination_digests", **{n: (destination[n] or "")[:12] for n in IMAGES})

match = all(source[n] == MANIFEST[n] == destination[n] for n in IMAGES)
step("source_eq_manifest_eq_destination", value=match)

rc, out = sudo("umount %s" % SD_MOUNT)
rows = mount_rows()
step("final_umount", rc=rc, rows=rows)

if rows != 0:
    step("USB_OFF_WITHHELD_STILL_MOUNTED")
else:
    reply = mcc.command("USB_OFF", wait=3.0)
    time.sleep(3)
    step("usb_off", disabling=("Disabling debug USB" in reply),
         sdb_present=os.path.exists(SD_DEVICE) or os.path.exists("/dev/sdb"))
mcc.close()

print("\nJSON " + json.dumps({
    "source": source, "manifest": MANIFEST, "destination": destination,
    "match": match, "on_card_before": before, "log": log,
}))
