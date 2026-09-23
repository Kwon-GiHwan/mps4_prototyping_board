#!/usr/bin/env python3
"""Capture ONE Tier A sweep from ONE boot and archive it with provenance.

Start this BEFORE the operator issues REBOOT (ordering guard 1 of the contract).
It records raw UART bytes until EVSWEEP-END or --timeout, then parses under
the contract and writes:

  <out>/uart.log            raw capture, byte-exact
  <out>/cells.csv           one row per (pass,slot,ev) with provenance columns
  <out>/summary.json        preregistered P1 summaries + digests + refusal (if any)

  python3 run_pmu_evsweep.py --out evidence/pmu_evsweep/boot1 \
      --app-sha256 ... --vectors-sha256 ... --ddr-sha256 ...
"""
import argparse, csv, datetime, hashlib, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pmu_evsweep_parse as P

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
BOARD_SERIAL = "FTDI-00FT46259002B"
FPGA_IMAGE = "FI101-r1p0 (109762 v0100)"
AUTHORIZATION = "owner-verbal-2026-09-23"


def capture(port, timeout):
    import serial
    s = serial.Serial(port, 115200, timeout=0.5)
    s.reset_input_buffer()
    started = datetime.datetime.now(datetime.timezone.utc)
    print(f"capturing on {port} from {started.isoformat()} -- REBOOT the board now", flush=True)
    buf = bytearray(); t0 = time.time(); seen_hdr = False
    while time.time() - t0 < timeout:
        chunk = s.read(4096)
        if chunk:
            buf += chunk
            if not seen_hdr and b"EVSWEEP-HDR" in buf:
                seen_hdr = True; print("header seen", flush=True)
            if b"EVSWEEP-END," in buf and buf.endswith(b"\n"):
                break
    s.close()
    return bytes(buf), started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--port", default=PORT)
    ap.add_argument("--timeout", type=float, default=300.0)
    for k in ("app", "vectors", "ddr"): ap.add_argument(f"--{k}-sha256", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    raw, started = capture(a.port, a.timeout)
    (out / "uart.log").write_bytes(raw)
    log_sha = hashlib.sha256(raw).hexdigest()
    prov = dict(board_serial=BOARD_SERIAL, fpga_image=FPGA_IMAGE,
                build_id=f"0x{P.BUILD_ID_EVSW:08x}", app_sha256=a.app_sha256,
                vectors_sha256=a.vectors_sha256, ddr_sha256=a.ddr_sha256,
                uart_log_sha256=log_sha, captured_at_utc=started.isoformat(),
                authorization=AUTHORIZATION)
    summary = dict(provenance=prov, raw_bytes=len(raw))
    try:
        hdr, cells = P.parse(raw.decode("ascii", errors="replace"))
    except P.Refusal as e:
        summary["refusal"] = {"rule": P.refusal_rule(e), "msg": str(e)}
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"REFUSED {e}"); return 1

    with (out / "cells.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pass", "slot", "ev", "written_hex", "readback_hex", "verdict", *prov.keys()])
        for c in cells:
            w.writerow([c.pass_, c.slot, c.ev, f"{c.ev:08x}", f"{c.readback:08x}", c.verdict, *prov.values()])
    summary["header"] = dict(build_id=f"0x{hdr.build_id:08x}", pmcr=f"0x{hdr.pmcr:08x}",
                             config=f"0x{hdr.config:08x}", num_event_cnt=hdr.num_event_cnt)
    summary["preregistered"] = P.summarize(cells)
    summary["cells"] = len(cells)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"OK {len(cells)} cells -> {out}"); return 0


if __name__ == "__main__":
    sys.exit(main())
