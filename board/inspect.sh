#!/bin/sh
# READ-ONLY: mount, print what selects the boot images, digest SOFTWARE/, umount. Writes nothing to the card.
set -u
EV="$1"; DEV=/dev/sdb1
MP=$(mktemp -d /tmp/evsweep_mnt.XXXXXX) || exit 2
mount -o ro "$DEV" "$MP" || { rmdir "$MP"; echo "FAIL: mount"; exit 1; }
echo "=== config.txt"; cat "$MP/config.txt"
echo; echo "=== images.txt (all under MB/)"; find "$MP/MB" -iname 'images.txt' | while read f; do echo "--- $f"; cat "$f"; done
echo; echo "=== SOFTWARE/"; ls -la "$MP/SOFTWARE"
echo; echo "=== SOFTWARE/ sha256"; ( cd "$MP/SOFTWARE" && sha256sum * ) | tee "$EV/CARD_SOFTWARE_PRE.sha256"
echo; echo "=== readme.txt / ee0376b.txt"; cat "$MP/readme.txt" "$MP/ee0376b.txt" 2>/dev/null
sync; umount "$MP" || { echo "FAIL: umount -- DO NOT USB_OFF"; exit 3; }
rmdir "$MP"; echo "INSPECT DONE: unmounted"
