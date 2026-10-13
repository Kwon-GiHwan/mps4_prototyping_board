#!/bin/sh
# One sudo: mount -> back up the card's images.txt and every SOFTWARE file the MLEK set touches -> write the MLEK
# set (boot.bin, bram.bin, ddr.bin, images.txt) -> verify -> umount. Undo with restore_mlek.sh <evidence_root>.
# Usage: sudo deploy_mlek.sh <srcdir with boot.bin bram.bin ddr.bin images.txt> <evidence_root (new)>
set -u
SRC="$1"; EV="$2"; DEV=/dev/sdb1; B="$EV/board-backup"
[ -e "$EV" ] && { echo "FAIL: $EV exists -- use a new evidence root"; exit 1; }
for f in boot.bin bram.bin ddr.bin images.txt; do [ -f "$SRC/$f" ] || { echo "FAIL: $SRC/$f missing"; exit 1; }; done
MP=$(mktemp -d /tmp/evsweep_mnt.XXXXXX) || exit 2
fail() { echo "FAIL: $1"; sync; umount "$MP" 2>/dev/null && rmdir "$MP" && echo "unmounted (FAILCLEAN)"; exit 1; }
mount "$DEV" "$MP" || { rmdir "$MP"; echo "FAIL: mount"; exit 1; }
IMG=$(find "$MP/MB" -iname 'images.txt'); [ "$(echo "$IMG" | grep -c .)" = "1" ] || fail "expected exactly one images.txt under MB/"
mkdir -p "$B" || fail "mkdir backup"
echo "${IMG#$MP/}" > "$EV/IMAGES_TXT_PATH"
cp "$IMG" "$B/images.txt" || fail "backup images.txt"
( cd "$MP/SOFTWARE" && ls -1 ) > "$EV/SOFTWARE_BEFORE.ls"
for f in APP.BIN VECTORS.BIN DDR.BIN; do [ -f "$MP/SOFTWARE/$f" ] || fail "original SOFTWARE/$f missing"; cp "$MP/SOFTWARE/$f" "$B/$f" || fail "backup $f"; done
for f in boot.bin bram.bin; do ls "$MP/SOFTWARE" | grep -qix "$f" && fail "SOFTWARE/$f already on the card -- not overwriting"; done
( cd "$B" && sha256sum images.txt APP.BIN VECTORS.BIN DDR.BIN > backup.sha256 && sha256sum -c backup.sha256 ) || fail "backup verify"
for f in boot.bin bram.bin ddr.bin; do cp "$SRC/$f" "$MP/SOFTWARE/$f" || fail "write $f"; done
cp "$SRC/images.txt" "$IMG" || fail "write images.txt"
sync
a=$(cd "$SRC" && sha256sum boot.bin bram.bin ddr.bin images.txt | cut -d' ' -f1 | tr '\n' ' ')
b=$( (cd "$MP/SOFTWARE" && sha256sum boot.bin bram.bin ddr.bin; sha256sum "$IMG") | cut -d' ' -f1 | tr '\n' ' ')
[ "$a" = "$b" ] || fail "destination != source"
echo "DEPLOY VERIFIED: source == destination"; ( cd "$SRC" && sha256sum boot.bin bram.bin ddr.bin images.txt )
sync; umount "$MP" || { echo "FAIL: umount -- DO NOT USB_OFF"; exit 3; }
rmdir "$MP"; echo "DEPLOY DONE: unmounted, safe to REBOOT"
