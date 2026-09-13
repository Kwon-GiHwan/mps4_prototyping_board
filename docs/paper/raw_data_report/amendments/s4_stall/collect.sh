#!/bin/sh
# Pull the S4 stall-counter evidence (results + raw UART) from the server into the repo and run the analysis.
# Usage: sh docs/paper/raw_data_report/amendments/x4/collect.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ssh -o ConnectTimeout=8 -o BatchMode=yes gihwan 'docker exec benchmark-runner sh -lc "cd /tmp/s4 && tar czf /tmp/s4_out.tgz results.jsonl run.log s4_stall_counters.py patch_driver.py expected.json uart && sha256sum /tmp/s4_out.tgz" && docker cp benchmark-runner:/tmp/s4_out.tgz /tmp/s4_out.tgz'
scp -q gihwan:/tmp/s4_out.tgz "$HERE/s4_out.tgz"
shasum -a 256 "$HERE/s4_out.tgz"
tar xzf "$HERE/s4_out.tgz" -C "$HERE" && rm "$HERE/s4_out.tgz"
/usr/bin/python3 -W ignore "$HERE/s4_analyze.py"
