#!/bin/sh
# One sudo: undo deploy_mlek.sh -- images.txt and APP/VECTORS/DDR.BIN back from the backup, remove the boot.bin and
# bram.bin it added (only if they still equal the deployed source), verify against the backup, umount.
# Usage: sudo restore_mlek.sh <evidence_root of deploy_mlek.sh> <srcdir it deployed>
set -u
EV="$1"; SRC="$2"; B="$EV/board-backup"; DEV=/dev/sdb1
[ -f "$B/backup.sha256" ] && [ -f "$EV/IMAGES_TXT_PATH" ] || { echo "FAIL: no backup in $EV"; exit 1; }
MP=$(mktemp -d /tmp/evsweep_mnt.XXXXXX) || exit 2
fail() { echo "FAIL: $1"; sync; umount "$MP" 2>/dev/null && rmdir "$MP" && echo "unmounted (FAILCLEAN)"; exit 1; }
mount "$DEV" "$MP" || { rmdir "$MP"; echo "FAIL: mount"; exit 1; }
IMG="$MP/$(cat "$EV/IMAGES_TXT_PATH")"; [ -f "$IMG" ] || fail "images.txt not where it was"
for f in boot.bin bram.bin; do
  [ "$(sha256sum "$MP/SOFTWARE/$f" | cut -d' ' -f1)" = "$(sha256sum "$SRC/$f" | cut -d' ' -f1)" ] || fail "SOFTWARE/$f is not the deployed file -- not removing"
done
cp "$B/images.txt" "$IMG" || fail "restore images.txt"
for f in APP.BIN VECTORS.BIN DDR.BIN; do cp "$B/$f" "$MP/SOFTWARE/$f" || fail "restore $f"; done
rm "$MP/SOFTWARE/boot.bin" "$MP/SOFTWARE/bram.bin" || fail "remove added files"
sync
a=$(cut -d' ' -f1 "$B/backup.sha256" | tr '\n' ' ')
b=$( (sha256sum "$IMG"; cd "$MP/SOFTWARE" && sha256sum APP.BIN VECTORS.BIN DDR.BIN) | cut -d' ' -f1 | tr '\n' ' ')
[ "$a" = "$b" ] || fail "restored != backup"
( cd "$MP/SOFTWARE" && ls -1 ) > "$EV/SOFTWARE_AFTER.ls"
cmp -s "$EV/SOFTWARE_BEFORE.ls" "$EV/SOFTWARE_AFTER.ls" || fail "SOFTWARE/ listing differs from before deploy"
echo "RESTORE VERIFIED"; cat "$B/backup.sha256"
sync; umount "$MP" || { echo "FAIL: umount -- DO NOT USB_OFF"; exit 3; }
rmdir "$MP"; echo "RESTORE DONE: unmounted, safe to REBOOT then USB_OFF"
