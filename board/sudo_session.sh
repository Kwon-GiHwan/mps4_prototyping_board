#!/bin/sh
# One owner sudo for one approved board session. The owner reads the session file, then runs
#   ssh -t gihwan 'sudo sh /home/gihwan/evsweep/sudo_session.sh <session file>'
# and types the password at that sudo prompt only. Nothing here reads, stores or forwards a password; the agent never
# needs one. The session is checked first (every line, root steps balanced), then detaches and logs to <file>.log.
#   sh sudo_session.sh --check <session file>     check only (no root needed)
# Session file: one step per line, '#' and blank lines ignored.
#   deploy_mlek <srcdir> <evidence root>    root: deploy_mlek.sh        restore_mlek <evidence root> <srcdir>
#   deploy <srcdir> <evidence root>         root: deploy.sh             restore <evidence root>
#   user <command line>                     as the board user (never root), in the evsweep directory
# A failed step stops the session; an image set left on the card by this session is restored before exit.
set -u
EVS=${EVS_DIR:-/home/gihwan/evsweep}; BOARD_USER=${BOARD_USER:-gihwan}
as_user() { if [ "${SESSION_TEST:-0}" = 1 ]; then sh -c "cd '$EVS' && $1"; else runuser -u "$BOARD_USER" -- env HOME="/home/$BOARD_USER" sh -c "cd '$EVS' && $1"; fi; }

check() {   # prints nothing on success; one FAIL line per problem
  [ -f "$1" ] || { echo "FAIL: no session file $1"; return 1; }
  awk '
    /^[ \t]*(#|$)/ { next }
    $1 == "deploy_mlek"  { if (NF != 3 || open) bad = bad "\nFAIL line " NR ": deploy_mlek <src> <ev> with nothing deployed"; open = "mlek " $3 " " $2; next }
    $1 == "restore_mlek" { if (NF != 3 || open != "mlek " $2 " " $3) bad = bad "\nFAIL line " NR ": restore_mlek must undo the open deploy_mlek (ev src)"; open = ""; next }
    $1 == "deploy"       { if (NF != 3 || open) bad = bad "\nFAIL line " NR ": deploy <src> <ev> with nothing deployed"; open = "app " $3; next }
    $1 == "restore"      { if (NF != 2 || open != "app " $2) bad = bad "\nFAIL line " NR ": restore must undo the open deploy (ev)"; open = ""; next }
    $1 == "user"         { if (NF < 2) bad = bad "\nFAIL line " NR ": user <command>"; next }
    { bad = bad "\nFAIL line " NR ": unknown step " $1 }
    END { if (open) bad = bad "\nFAIL: the session ends with an image set on the card (" open ")"; if (bad) { print substr(bad, 2); exit 1 } }
  ' "$1"
}

restore_open() {   # undo a deploy this session made; the card is never left with a session image after a failure
  case "$OPEN" in
    mlek\ *) set -- $OPEN; echo "=== $(date -u +%FT%TZ) recovery: restore_mlek $2 $3"; sh "$EVS/restore_mlek.sh" "$2" "$3";;
    app\ *) set -- $OPEN; echo "=== $(date -u +%FT%TZ) recovery: restore $2"; sh "$EVS/restore.sh" "$2";;
  esac
}

run() {
  OPEN=""; n=0
  while IFS= read -r line || [ -n "$line" ]; do
    n=$((n + 1)); case "$line" in ''|\#*) continue;; esac
    set -- $line; step=$1; shift
    echo "=== $(date -u +%FT%TZ) step $n: $line"
    case $step in
      deploy_mlek) sh "$EVS/deploy_mlek.sh" "$1" "$2"; rc=$?; [ $rc = 0 ] && OPEN="mlek $2 $1";;
      restore_mlek) sh "$EVS/restore_mlek.sh" "$1" "$2"; rc=$?; [ $rc = 0 ] && OPEN="";;
      deploy) sh "$EVS/deploy.sh" "$1" "$2"; rc=$?; [ $rc = 0 ] && OPEN="app $2";;
      restore) sh "$EVS/restore.sh" "$1"; rc=$?; [ $rc = 0 ] && OPEN="";;
      user) as_user "${line#user }"; rc=$?;;
    esac
    [ $rc = 0 ] || { echo "=== $(date -u +%FT%TZ) SESSION FAILED at step $n (rc=$rc)"; restore_open; exit 1; }
  done < "$F"
  echo "=== $(date -u +%FT%TZ) SESSION DONE"
}

case "${1:-}" in
  --check) F=${2:-}; check "$F" && echo "SESSION OK: $F";;
  --run) F=$2; run;;
  *) F=${1:-}
     [ "${SESSION_TEST:-0}" = 1 ] || [ "$(id -u)" = 0 ] || { echo "FAIL: run with sudo"; exit 2; }
     check "$F" || exit 1
     touch "$F.log" && chown "$BOARD_USER" "$F.log" 2>/dev/null
     setsid nohup sh "$0" --run "$F" > "$F.log" 2>&1 < /dev/null &
     echo "SESSION STARTED: log $F.log";;
esac
