#!/bin/sh
# One boot per plan line: REBOOT -> boot markers -> upload the blob once -> --repeats RUNs of the event set.
# Usage (board host, from anywhere):
#   sh run_campaign.sh <staging dir with APP/VECTORS/DDR.BIN and <workload>.<cond>.pmwl> <evidence root> <ids file> <plan file>
# plan file: one "boot_index workload condition" per line; '#' lines ignored.
# The image on the card must be the one in <staging dir> (deploy.sh first); its digests are recorded per RUN.
set -u
[ $# -eq 4 ] || { echo "usage: $0 <staging> <evidence root> <ids file> <plan file>"; exit 2; }
S=$1; OUT=$2; IDS=$3; PLAN=$4
EVS=/home/gihwan/evsweep
for f in APP.BIN VECTORS.BIN DDR.BIN; do [ -f "$S/$f" ] || { echo "FAIL: $S/$f missing"; exit 2; }; done
[ -f "$IDS" ] && [ -f "$PLAN" ] || { echo "FAIL: ids or plan file missing"; exit 2; }
APP=$(sha256sum "$S/APP.BIN" | cut -d" " -f1); VEC=$(sha256sum "$S/VECTORS.BIN" | cut -d" " -f1); DDR=$(sha256sum "$S/DDR.BIN" | cut -d" " -f1)
mkdir -p "$OUT"; cp "$PLAN" "$OUT/plan.txt"; cp "$IDS" "$OUT/ids.txt"
grep -v '^#' "$PLAN" | while read -r B N C; do
  [ -n "$B" ] || continue
  BLOB="$S/$N.$C.pmwl"; [ -f "$BLOB" ] || { echo "FAIL boot$B: $BLOB missing"; continue; }
  EV="$OUT/$C/$N"; mkdir -p "$EV"
  python3 "$EVS/mcc_reboot_capture.py" "$EV/mcc_boot.log" 150
  strings "$EV/mcc_boot.log" | grep -E "Image loaded|DDR memory test|CPUWAIT"
  strings "$EV/mcc_boot.log" | grep -q "Clearing SCC CPUWAIT" || { echo "FAIL boot$B: CPUWAIT not released"; continue; }
  sleep 3
  date -u +%FT%TZ > "$EV/started_utc"
  python3 "$EVS/host/board/run_pmu_events.py" --out "$EV" --host-boot-index "$B" --build-id 0x504d574c --blob "$BLOB" \
     --ids "@$IDS" --validity model --keep-model --repeats 35 \
     --app-sha256 "$APP" --vectors-sha256 "$VEC" --ddr-sha256 "$DDR" > "$EV/campaign.out" 2>&1 < /dev/null
  echo "--- boot$B $N $C campaign exit=$?"; date -u +%FT%TZ > "$EV/finished_utc"; grep -c "valid=True" "$EV/campaign.out"
done
echo "CAMPAIGN DONE"
