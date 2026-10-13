#!/bin/sh
# One sudo: mount -> write the backup back to SOFTWARE/ -> verify == backup.sha256 -> umount.
# Usage: sudo restore.sh <evidence_root>
set -u
EV="$1"; B="$EV/board-backup/current"; DEV=/dev/sdb1
[ -f "$B/backup.sha256" ] || { echo "FAIL: no backup to restore from"; exit 1; }
MP=$(mktemp -d /tmp/evsweep_mnt.XXXXXX) || exit 2
fail() { echo "FAIL: $1"; sync; umount "$MP" 2>/dev/null && rmdir "$MP" && echo "unmounted (FAILCLEAN)"; exit 1; }
mount "$DEV" "$MP" || { rmdir "$MP"; echo "FAIL: mount"; exit 1; }
for f in APP.BIN VECTORS.BIN DDR.BIN; do [ -f "$MP/SOFTWARE/$f" ] || fail "destination set changed: SOFTWARE/$f missing"; done
for f in APP.BIN VECTORS.BIN DDR.BIN; do cp "$B/$f" "$MP/SOFTWARE/$f" || fail "restore copy $f"; done
sync
( cd "$MP/SOFTWARE" && sha256sum APP.BIN VECTORS.BIN DDR.BIN ) > "$EV/RESTORE_DESTINATION.sha256"
a=$(cut -d' ' -f1 "$B/backup.sha256" | tr '\n' ' '); b=$(cut -d' ' -f1 "$EV/RESTORE_DESTINATION.sha256" | tr '\n' ' ')
[ "$a" = "$b" ] || fail "restore destination != backup"
echo "RESTORE VERIFIED"; cat "$EV/RESTORE_DESTINATION.sha256"
sync; umount "$MP" || { echo "FAIL: umount -- DO NOT USB_OFF"; exit 3; }
rmdir "$MP"; echo "RESTORE DONE: unmounted, safe to REBOOT then USB_OFF"
