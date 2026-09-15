"""Plan A7 diagnostic: is the 1,000-cycle grid of PMU TOTAL a Fast Models scheduling-quantum artifact?

Builds the RNNoise U85-256 base arm exactly as h13_sweep does (stock build, full TA defines, FetchContent cache)
and runs the FVP with the default quantum and with -Q 100 / -Q 1000. Only the simulator scheduling quantum
changes; binary, TA and model are identical. Records TOTAL / ACTIVE / IDLE per run into /tmp/h13/quantum.jsonl.
Run inside the container:  python3 /tmp/h13/h13_quantum.py
"""
import json, os, re, shutil, subprocess, sys, time

sys.path.insert(0, "/tmp/h13"); sys.path.insert(0, "/tmp/xqbin")
import h13_sweep as H  # noqa: E402
import stage1  # noqa: E402

CELL = "rnnoise_INT8__SSE-320__ethos-u85-256"
OUT = "/tmp/h13/quantum.jsonl"


def run_fvp(cell, axf, uart, extra):
    board, mac_param = stage1.board_and_param(cell)
    for f in (uart,):
        try: os.remove(f)
        except OSError: pass
    cmd = [cell["fvp"], "-a", axf, "-C", "%s=%d" % (mac_param, cell["mac_config"]),
           "-C", "%s.visualisation.disable-visualisation=1" % board, "-C", "%s.telnetterminal0.start_telnet=0" % board,
           "-C", "%s.uart0.out_file=%s" % (board, uart), "-C", "%s.uart0.unbuffered_output=1" % board] + extra
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
    t0 = time.monotonic(); txt = ""
    while time.monotonic() - t0 < 600:
        try: txt = open(uart).read()
        except OSError: txt = ""
        if "Inference completed." in txt or p.poll() is not None:
            break
        time.sleep(0.05)
    try: os.killpg(os.getpgid(p.pid), 9)
    except Exception: pass
    return H.parse_uart(txt), " ".join(cmd)


def main():
    cells = H.load_cells(); cell = cells[CELL]
    defines = H.full_defines(cell, {})
    ws = os.path.join(stage1.ROOT, "h13_quantum_" + CELL); shutil.rmtree(ws, ignore_errors=True)
    art, vcmd, vdir = H.vela(cell, ws)
    b = H.build(cell, defines, False, ws, art)
    assert b["ok"], b
    axf_ok = b["axf_sha256"] == cell["FORMAL_REFERENCE_AXF_SHA256"]
    with open(OUT, "a") as f:
        for extra in ([], ["-Q", "1000"], ["-Q", "100"], ["-Q", "10"]):
            for rep in (1, 2):
                m, cmd = run_fvp(cell, b["axf"], os.path.join(ws, "uart_q.txt"), extra)
                rec = {"cell_id": CELL, "quantum": extra[1] if extra else "default(10000)", "rep": rep, "measurement": m,
                       "axf_sha256": b["axf_sha256"], "axf_equals_frozen": axf_ok, "defines": defines, "fvp_cmd": cmd}
                f.write(json.dumps(rec) + "\n"); f.flush()
                print("quantum=%-15s rep=%d total=%s active=%s idle=%s" % (rec["quantum"], rep, m["npu_total_cycles"], m["npu_active_cycles"], m["npu_idle_cycles"]), flush=True)
    shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    main()
