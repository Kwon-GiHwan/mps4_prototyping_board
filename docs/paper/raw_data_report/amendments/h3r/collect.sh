#!/bin/sh
# Pull the H3-R evidence (results, raw UART, verify dumps, vela dumps, logs, driver mask excerpt) from the server
# into the repo and run the analysis + tables. Usage: sh docs/paper/raw_data_report/amendments/h3r/collect.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ssh -o ConnectTimeout=8 -o BatchMode=yes gihwan 'docker exec benchmark-runner sh -lc "cd /tmp/h3r && tar czf /tmp/h3r_out.tgz results.jsonl run_*.log h3r_sweep.py cells.json ta_parameters.csv driver_masks.txt uart verify vela 2>/dev/null; sha256sum /tmp/h3r_out.tgz" && docker cp benchmark-runner:/tmp/h3r_out.tgz /tmp/h3r_out.tgz'
scp -q gihwan:/tmp/h3r_out.tgz "$HERE/h3r_out.tgz"
shasum -a 256 "$HERE/h3r_out.tgz"
tar xzf "$HERE/h3r_out.tgz" -C "$HERE" && rm "$HERE/h3r_out.tgz"
find "$HERE" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
/usr/bin/python3 -W ignore "$HERE/h3r_analyze.py"
/usr/bin/python3 -W ignore "$HERE/h3r_tables.py"
