#!/bin/sh
# Judge-level regression: every judge on the stage4k.identity path, run from the code tree $1 on the data of repo $2,
# outputs into $3. Arguments are the ones the committed results were made with (each reproduced byte for byte by the
# before-change code). Compare two output trees with `diff -r` (logs excluded).
#   judges.sh <code root> <data repo> <out>
set -e
C=$(cd "$1" && pwd); D=$(cd "$2" && pwd); O=$3; mkdir -p "$O"; O=$(cd "$O" && pwd)
cd "$D"
P="python3 -B $C/host/analysis"
run() { n=$1; shift; mkdir -p "$O/$n"; "$@" > "$O/$n.log" 2>&1; echo "$n rc=$?"; }
W=$(mktemp -d)                                   # 4WD read its configs from a merged workload dir
for d in evidence/stage4wd/workloads evidence/stage4ao/workloads evidence/stage4wd/board; do
  for f in $d/*; do [ -e "$W/$(basename $f)" ] || cp "$f" "$W/"; done
done
cp results/fi101_stage4wd/static.json "$O/4wd.static.json"; mkdir -p "$O/4wd"; cp "$O/4wd.static.json" "$O/4wd/static.json"
CK=evidence/stage4k/raw/evsweep_s4k_run/conds/s4c2_conv_cin48
R375=evidence/stage6b/stage6be1r/raw/evsweep_s6be1r/ref/wfe
run 4k   $P/stage4k.py judge evidence/stage4k/raw/evsweep_s4k_run evidence/stage4k/workloads results/fi101_stage4k/predictions.json "$O/4k"
run 4ao  $P/stage4ao.py judge evidence/stage4ao/raw/evsweep_s4ao_run evidence/stage4ao/workloads results/fi101_stage4ao/predictions.json "$O/4ao" s4ao_conv1x1_h24,s4ao_conv1x1_h36,s4ao_conv1x1_h54,s4ao_conv1x1_h72 s4ao_act_none,s4ao_act_relu evidence/stage4ao/raw/evsweep_s4ao/ref/wfe
run 4aoe $P/stage4aoe.py judge evidence/stage4aoe/raw_a1/evsweep_s4aoe2_run evidence/stage4aoe/workloads results/fi101_stage4aoe/predictions.json "$O/4aoe"
run 4wd  $P/stage4wd.py judge evidence/stage4wd/raw/evsweep_s4wd_run "$W" results/fi101_stage4wd/predictions.json "$O/4wd"
run 6bb  $P/stage6bb.py judge evidence/stage6b/stage6bb/raw/evsweep_s6bb_run evidence/stage6b/stage6bb/workloads $CK/wfe $CK/capabilities.json "$O/6bb"
run e1   $P/stage6be1.py judge evidence/stage6b/stage6be1/raw/evsweep_s6be1_run evidence/stage6b/stage6be1/workloads $CK/wfe $CK/capabilities.json "$O/e1"
run e1r  $P/stage6be1r.py judge evidence/stage6b/stage6be1r/raw/evsweep_s6be1r_run evidence/stage6b/stage6be1r/workloads $CK/wfe $CK/capabilities.json "$O/e1r"
run e2b  $P/stage6be2b.py judge evidence/stage6b/stage6be2b/raw/evsweep_s6be2b_run_l500 evidence/stage6b/stage6be2b/raw/evsweep_s6be2b_run_l1000 evidence/stage6b/stage6be2b/workloads $R375 "$O/e2b"
run e2d  $P/stage6be2d.py judge evidence/stage6b/stage6be2d/raw_a/evsweep_s6be2d_a_run_l500 evidence/stage6b/stage6be2d/raw_a/evsweep_s6be2d_a_run_l1000 evidence/stage6b/stage6be2d/workloads $R375 "$O/e2d"
rm -rf "$W"
