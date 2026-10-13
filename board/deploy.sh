#!/bin/sh
# One sudo: mount -> DISCOVER boot images from the card's images.txt -> backup -> deploy -> verify -> umount.
# Usage: sudo deploy.sh <srcdir> <evidence_root>     Writes only the discovered image files.
set -u
SRC="$1"; EV="$2"; DEV=/dev/sdb1
MP=$(mktemp -d /tmp/evsweep_mnt.XXXXXX) || exit 2
fail() { echo "FAIL: $1"; sync; umount "$MP" 2>/dev/null && rmdir "$MP" && echo "unmounted (FAILCLEAN)"; exit 1; }
mount "$DEV" "$MP" || { rmdir "$MP"; echo "FAIL: mount"; exit 1; }
echo "MOUNTPOINT=$MP"

echo "=== config.txt"; cat "$MP/config.txt"
IMG=$(find "$MP/MB" -iname 'images.txt' | head -1); [ -n "$IMG" ] || fail "no images.txt under MB/"
N=$(find "$MP/MB" -iname 'images.txt' | wc -l); [ "$N" = "1" ] || fail "ambiguous: $N images.txt files under MB/"
echo "=== $IMG"; cat "$IMG"

# Discover: every IMAGEnFILE: \SOFTWARE\NAME.BIN -> SOFTWARE/NAME.BIN on the card.
REL=$(grep -iE '^IMAGE[0-9]+FILE:' "$IMG" | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*;.*$//; s/\r$//; s#\\#/#g; s#^/##')
echo "=== discovered boot images:"; echo "$REL"
for r in $REL; do [ -f "$MP/$r" ] || fail "images.txt names $r but it is not on the card"; done
WANT="SOFTWARE/APP.BIN SOFTWARE/DDR.BIN SOFTWARE/VECTORS.BIN"
GOT=$(echo "$REL" | sort | tr '\n' ' ' | sed 's/ $//')
[ "$GOT" = "$WANT" ] || fail "discovered set [$GOT] != expected [$WANT] -- not writing"

echo "=== SOFTWARE/"; ls -la "$MP/SOFTWARE"
B="$EV/board-backup/current"; mkdir -p "$B" || fail "mkdir backup"
for r in $REL; do cp "$MP/$r" "$B/$(basename $r)" || fail "backup copy $r"; done
( cd "$B" && sha256sum APP.BIN VECTORS.BIN DDR.BIN > backup.sha256 && sha256sum -c backup.sha256 ) || fail "backup verify"
echo "=== backup (restore reference):"; cat "$B/backup.sha256"
( cd "$MP/SOFTWARE" && sha256sum APP.BIN VECTORS.BIN DDR.BIN ) > "$EV/PRE_DEPLOY_DESTINATION.sha256"
cp "$IMG" "$EV/images.txt.card"; cp "$MP/config.txt" "$EV/config.txt.card"

for r in $REL; do cp "$SRC/$(basename $r)" "$MP/$r" || fail "deploy copy $r"; done
sync
( cd "$MP/SOFTWARE" && sha256sum APP.BIN VECTORS.BIN DDR.BIN ) > "$EV/POST_DEPLOY_DESTINATION.sha256"
( cd "$SRC" && sha256sum APP.BIN VECTORS.BIN DDR.BIN ) > "$EV/SOURCE.sha256"
a=$(cut -d' ' -f1 "$EV/SOURCE.sha256" | tr '\n' ' '); b=$(cut -d' ' -f1 "$EV/POST_DEPLOY_DESTINATION.sha256" | tr '\n' ' ')
[ "$a" = "$b" ] || fail "destination != source after copy"
echo "DEPLOY VERIFIED: source == destination"; cat "$EV/POST_DEPLOY_DESTINATION.sha256"
sync; umount "$MP" || { echo "FAIL: umount -- DO NOT USB_OFF; operator recovery"; exit 3; }
rmdir "$MP"; findmnt | grep -qE "sdb" && { echo "FAIL: still mounted"; exit 3; }
echo "DEPLOY DONE: unmounted, safe to REBOOT (keep USB on until postflight)"
