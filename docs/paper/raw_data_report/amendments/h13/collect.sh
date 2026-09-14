#!/bin/sh
# Pull the H13 evidence (results, raw UART, verify dumps, vela dumps, logs) from the server into the repo
# and run the analysis. Usage: sh docs/paper/raw_data_report/amendments/h13/collect.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ssh -o ConnectTimeout=8 -o BatchMode=yes gihwan 'docker exec benchmark-runner sh -lc "cd /tmp/h13 && tar czf /tmp/h13_out.tgz results.jsonl run_*.log h13_sweep.py synthetic_cells.json ta_parameters.csv uart verify vela smoke 2>/dev/null; sha256sum /tmp/h13_out.tgz" && docker cp benchmark-runner:/tmp/h13_out.tgz /tmp/h13_out.tgz'
scp -q gihwan:/tmp/h13_out.tgz "$HERE/h13_out.tgz"
shasum -a 256 "$HERE/h13_out.tgz"
tar xzf "$HERE/h13_out.tgz" -C "$HERE" && rm "$HERE/h13_out.tgz"
find "$HERE" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
/usr/bin/python3 -W ignore "$HERE/h13_analyze.py"
