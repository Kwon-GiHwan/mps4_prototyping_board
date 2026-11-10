#!/bin/sh
# Driver runner campaign (docs/plan/driver_runner_plan.md): one boot per plan line: REBOOT -> boot markers -> upload the
# DRWL workload once -> --repeats RUNs per event set. The card must hold the driver runner's MLEK-style image set
# (deploy_mlek.sh with <staging>); its digests are recorded with every RUN.
# Usage (board host): sh run_driver_campaign.sh <staging with boot.bin bram.bin ddr.bin images.txt and <workload>.drwl>
#                        <evidence root> <ids file> <plan file> [repeats]
# plan file: "boot_index workload condition" per line, '#' ignored; condition = wfe | busy (the CPU wait while the NPU
# runs: the driver's own WFE semaphore, or the same loop without WFE) | @<conditions file> (several run-option
# conditions in this boot, run_driver_events.py --conditions; output <evidence root>/conds/<workload>/<name>/).
# RUN_TIMEOUT (seconds, default 120).
set -u
[ $# -eq 4 ] || [ $# -eq 5 ] || { echo "usage: $0 <staging> <evidence root> <ids file> <plan file> [repeats]"; exit 2; }
S=$1; OUT=$2; IDS=$3; PLAN=$4; REPEATS=${5:-10}; RUN_TIMEOUT=${RUN_TIMEOUT:-120}
case $REPEATS$RUN_TIMEOUT in ''|*[!0-9]*) echo "FAIL: repeats and RUN_TIMEOUT must be numbers"; exit 2;; esac
EVS=/home/gihwan/evsweep
for f in boot.bin bram.bin ddr.bin images.txt; do [ -f "$S/$f" ] || { echo "FAIL: $S/$f missing"; exit 2; }; done
[ -f "$IDS" ] && [ -f "$PLAN" ] || { echo "FAIL: ids or plan file missing"; exit 2; }
SHA=$(cd "$S" && sha256sum boot.bin bram.bin ddr.bin images.txt | cut -d" " -f1 | paste -sd,)
mkdir -p "$OUT"; cp "$PLAN" "$OUT/plan.txt"; cp "$IDS" "$OUT/ids.txt"
grep -v '^#' "$PLAN" | while read -r B N C; do
  [ -n "$B" ] || continue
  case $C in
    wfe) OPT="--wait-mode 0"; EV="$OUT/wfe/$N";;
    busy) OPT="--wait-mode 1"; EV="$OUT/busy/$N";;
    @*) [ -f "${C#@}" ] || { echo "FAIL boot$B: ${C#@} missing"; continue; }; OPT="--conditions $C"; EV="$OUT/conds/$N";;
    *) echo "FAIL boot$B: condition $C"; continue;;
  esac
  WL="$S/$N.drwl"; [ -f "$WL" ] || { echo "FAIL boot$B: $WL missing"; continue; }
  mkdir -p "$EV"
  python3 "$EVS/mcc_reboot_capture.py" "$EV/mcc_boot.log" 150
  strings "$EV/mcc_boot.log" | grep -E "Image loaded|DDR memory test|CPUWAIT"
  strings "$EV/mcc_boot.log" | grep -q "Clearing SCC CPUWAIT" || { echo "FAIL boot$B: CPUWAIT not released"; continue; }
  sleep 5
  date -u +%FT%TZ > "$EV/started_utc"
  python3 "$EVS/host/board/run_driver_events.py" --out "$EV" --host-boot-index "$B" --workload "$WL" --ids "@$IDS" \
     --repeats "$REPEATS" $OPT --run-timeout "$RUN_TIMEOUT" --image-sha256 "$SHA" \
     > "$EV/campaign.out" 2>&1 < /dev/null
  echo "--- boot$B $N $C campaign exit=$?"; date -u +%FT%TZ > "$EV/finished_utc"; grep -c "valid=True" "$EV/campaign.out"
  case $C in @*) cp "${C#@}" "$EV/conditions.txt";; esac
done
echo "CAMPAIGN DONE"
