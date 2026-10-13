#!/bin/sh
# Copy the repo's runtime files to where they run, keeping repo-relative paths, then verify by sha256.
#   sh sync.sh board       host/*.py, docs/reference/*.json, config/*  -> gihwan:~/evsweep/<same path>
#                          board/*                                    -> gihwan:~/evsweep/
#   sh sync.sh container   host/{pmwl,pack_vela_workload}.py, config/mlek_baseline.json
#                          -> /work/mps4_host/ (benchmark-runner, flat)
#                          firmware/**                                -> /work/selftest/<same path>
#   sh sync.sh check       verify both, change nothing
# Board-host copies resolve docs/reference via host/.. (pmu_events_parse.REPO), so the layout must match.
set -u
cd "$(dirname "$0")" || exit 2
H=gihwan; EVS=evsweep; C=benchmark-runner
export COPYFILE_DISABLE=1   # no macOS ._ files in the tar stream

BOARD_FILES=$(ls host/*.py docs/reference/*.json config/*.txt config/*.json)
CT_HOST_FILES="host/pmwl.py host/pack_vela_workload.py config/mlek_baseline.json"
CT_FW_FILES=$(cd firmware && git ls-files .)

push_board() {
  tar --no-xattrs -cf - $BOARD_FILES | ssh $H "mkdir -p $EVS && tar xf - -C $EVS" || return 1
  tar --no-xattrs -cf - -C board $(cd board && ls) | ssh $H "tar xf - -C $EVS" || return 1
}

push_container() {
  tar --no-xattrs -cf - $CT_HOST_FILES | ssh $H "docker exec -i $C sh -c 'mkdir -p /work/mps4_host && tar xf - -C /work/mps4_host --strip-components=1'" || return 1
  (cd firmware && tar --no-xattrs -cf - $CT_FW_FILES) | ssh $H "docker exec -i $C tar xf - -C /work/selftest" || return 1
}

check_board() {
  bad=0
  for f in $BOARD_FILES; do
    want=$(shasum -a 256 "$f" | cut -d' ' -f1); got=$(ssh $H "sha256sum $EVS/$f 2>/dev/null" | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "MISMATCH board $EVS/$f"; bad=1; }
  done
  for f in $(cd board && ls); do
    want=$(shasum -a 256 "board/$f" | cut -d' ' -f1); got=$(ssh $H "sha256sum $EVS/$f 2>/dev/null" | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "MISMATCH board $EVS/$f"; bad=1; }
  done
  return $bad
}

check_container() {
  bad=0
  for f in $CT_HOST_FILES; do
    want=$(shasum -a 256 "$f" | cut -d' ' -f1)
    got=$(ssh $H "docker exec $C sha256sum /work/mps4_host/$(basename $f) 2>/dev/null" | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "MISMATCH container /work/mps4_host/$(basename $f)"; bad=1; }
  done
  for f in $CT_FW_FILES; do
    want=$(shasum -a 256 "firmware/$f" | cut -d' ' -f1)
    got=$(ssh $H "docker exec $C sha256sum /work/selftest/$f 2>/dev/null" | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "MISMATCH container /work/selftest/$f"; bad=1; }
  done
  return $bad
}

case "${1:-}" in
  board)     push_board && check_board && echo "SYNC board OK" ;;
  container) push_container && check_container && echo "SYNC container OK" ;;
  check)     b=0; check_board || b=1; check_container || b=1; [ $b -eq 0 ] && echo "CHECK OK" || { echo "CHECK FAILED"; exit 1; } ;;
  *)         echo "usage: sh sync.sh board|container|check"; exit 2 ;;
esac
