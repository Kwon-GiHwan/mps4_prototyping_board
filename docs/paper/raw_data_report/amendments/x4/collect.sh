#!/bin/sh
# Pull the X4 sweep evidence (results + raw UART) from the server into the repo and run the analysis.
# Usage: sh docs/paper/raw_data_report/amendments/x4/collect.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ssh -o ConnectTimeout=8 -o BatchMode=yes gihwan 'docker exec benchmark-runner sh -lc "cd /tmp/x4 && tar czf /tmp/x4_out.tgz results.jsonl run.log x4_ta_sweep.py uart && sha256sum /tmp/x4_out.tgz" && docker cp benchmark-runner:/tmp/x4_out.tgz /tmp/x4_out.tgz'
scp -q gihwan:/tmp/x4_out.tgz "$HERE/x4_out.tgz"
shasum -a 256 "$HERE/x4_out.tgz"
tar xzf "$HERE/x4_out.tgz" -C "$HERE" && rm "$HERE/x4_out.tgz"
/usr/bin/python3 -W ignore "$HERE/x4_analyze.py"
