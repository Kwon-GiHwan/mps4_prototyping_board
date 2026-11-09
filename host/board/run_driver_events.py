#!/usr/bin/env python3
"""One boot of the driver runner (firmware/driver_runner): read the capabilities, upload a DRWL workload once, run each
event set --repeats times, archive every RUN. The counterpart of run_pmu_events.py for record v2; runs.csv keeps the
same columns, so the existing analyses (fi101_s013.load_runs and those built on it) read it unchanged:
window_cycles = infer_npu_cycles = NPU_EXECUTION_CYCLES (PMCCNTR, arm -> completion IRQ), infer_cpu_cycles = the same
span in CPU DWT cycles; the driver runner's own columns follow.

  python3 run_driver_events.py --out <dir> --host-boot-index N --workload <x.drwl> --ids @<ids file> --repeats 10 \
      [--wait-mode 0|1] [--pmccntr-cfg 0x..] --image-sha256 <boot>,<bram>,<ddr>,<images.txt>
"""
import argparse, csv, datetime, hashlib, json, pathlib, sys, zlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import drwl
import pmu_events_parse as E
import record_v2
import reference
from driver_link import DriverLink
from runner_proto import MAX_PAYLOAD, Nack, ProtocolError, load_end_timeout

CHUNK = MAX_PAYLOAD - 4
PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
PROV = dict(board_serial="FTDI-00FT46259002B", fpga_image="FI101-r1p0 (109762 v0100)", runner="driver_runner")


def prime(link, blob):
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    for off in range(0, len(blob), CHUNK):
        link.load_model_chunk(off, blob[off:off + CHUNK])
    link.load_model_end(timeout=load_end_timeout(len(blob)))
    link.load_input(b"")


def rows_of(r, codes, ok, failed, names, trm, base):
    """One runs.csv row per event slot of a RUN."""
    f = r.f
    common = dict(run_rc=r.run_rc, run_valid=ok, invalid_reasons=";".join(failed),
                  window_cycles=r.npu_execution_cycles(), cycle_valid=int(f["ccnt_irq_hi"] >> 16 == 0),
                  valid_flags=r.valid_flags, vendor_rc=f["job_result"], ofm_mismatch_count=f["ofm_mismatch"],
                  ofm_max_abs_diff=f["ofm_max_diff"], infer_npu_cycles=r.npu_execution_cycles(),
                  infer_cpu_cycles=r.npu_execution_dwt(), infer_sys_ticks=None,
                  host_end_to_end_cycles=r.host_end_to_end(), wait_mode=f["wait_mode"],
                  pmccntr_cfg=f"0x{f['pmccntr_cfg']:08x}", dcache_on=f["dcache_on"],
                  power_requests=f["power_requests"], status_at_irq=f"0x{f['status_at_irq']:08x}",
                  qread_at_irq=f["qread_at_irq"], qsize=f["qsize"], output_match=int(f["ofm_mismatch"] == 0),
                  arena_base=f"0x{f['arena_base']:08x}", **base)
    out = []
    for slot, ev in enumerate(codes):
        ovf = bool(f["ovf_irq"] >> slot & 1)
        out.append(dict(slot=slot, ev_type=ev, name=names[ev], in_trm110=ev in trm,
                        event_value=f[f"ev_irq{slot}"] if ok else None, event_valid=not ovf, event_overflow=ovf,
                        ev_post_value=f[f"ev_post{slot}"], **common))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--port", default=PORT)
    ap.add_argument("--host-boot-index", type=int, required=True)
    ap.add_argument("--workload", required=True, help="DRWL workload (pack_vela_workload.py --format drwl)")
    ap.add_argument("--ids", required=True, help="comma-separated event ids or @file (sets per line)")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--wait-mode", type=int, default=0, help="0 = WFE (the driver's own wait, MLEK), 1 = busy loop")
    ap.add_argument("--pmccntr-cfg", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--run-timeout", type=float, default=120.0)
    ap.add_argument("--image-sha256", required=True, help="boot.bin,bram.bin,ddr.bin,images.txt digests")
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    blob = pathlib.Path(a.workload).read_bytes()
    h = drwl.parse(blob)   # refuses a malformed workload before touching the board
    m0 = h["model_off"]
    boot, bram, ddr, images = a.image_sha256.split(",")
    prov = dict(PROV, boot_sha256=boot, bram_sha256=bram, ddr_sha256=ddr, images_txt_sha256=images,
                workload_sha256=hashlib.sha256(blob).hexdigest(),
                model_sha256=hashlib.sha256(blob[m0:m0 + h["model_len"]]).hexdigest(),
                host_boot_index=a.host_boot_index,
                captured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    names, trm = reference.driver_ids(), reference.trm_ids()
    txt = pathlib.Path(a.ids[1:]).read_text() if a.ids.startswith("@") else a.ids.replace(",", "\n")
    ids, explicit = E.parse_ids_text(txt)
    sets = E.event_sets(ids, sets=explicit)
    rows, raw, refusal = [], [], None
    link = DriverLink(a.port)
    try:
        c = link.ping()
        raw.append({"ping": c.__dict__})
        if c.state != 1:
            raise E.fail_rule("RULE_PING", f"state={c.state}")
        caps = link.capabilities()
        (out / "capabilities.json").write_text(json.dumps(caps, indent=1))
        link.set_run_options(a.wait_mode, a.pmccntr_cfg)
        for set_id, codes in sets:
            first = set_id == sets[0][0]
            try:
                req, applied, cnt, cseq = link.set_instrumentation_mode(E.INSTRUMENTATION_EVENTS, codes, set_id)
            except Nack as n:
                raise E.fail_rule("RULE_MODE_NACK", repr(n))
            if applied != E.INSTRUMENTATION_EVENTS or cnt != len(codes):
                raise E.fail_rule("RULE_MODE_NACK", f"applied={applied} count={cnt}")
            if first:
                try:
                    prime(link, blob)
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"prime: {e!r}")
            for rep in range(1, a.repeats + 1):
                try:
                    link.run(timeout=a.run_timeout)
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"set {set_id} rep {rep}: {e!r}")
                r = link.last_measurement
                ok, failed = record_v2.validity(r, codes)
                raw.append(dict(set_id=set_id, rep=rep, run_sequence=r.run_sequence, valid_flags=r.valid_flags,
                                run_rc=r.run_rc, record=r.f, host_run_s=link.last_run_host_s))
                rows += rows_of(r, codes, ok, failed, names, trm,
                                dict(set_id=set_id, rep=rep, host_run_s=link.last_run_host_s, **prov))
                print(f"set {set_id:2d} rep {rep} rc={r.run_rc} flags=0x{r.valid_flags:02x} "
                      f"npu_exec={r.npu_execution_cycles()} ofm_mismatch={r.f['ofm_mismatch']} valid={ok} "
                      f"{failed or ''}", flush=True)
    except E.Refusal as e:
        refusal = {"rule": E.refusal_rule(e), "msg": str(e)}
        print(f"REFUSED {e}")
    finally:
        link.close()
    (out / "raw_runs.json").write_text(json.dumps(raw, indent=1, default=str))
    if rows:
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with (out / "runs.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    summ = dict(provenance=prov, wait_mode=a.wait_mode, pmccntr_cfg=a.pmccntr_cfg, runs=len(raw) - 1, rows=len(rows),
                refusal=refusal, text_log_lines=len(link.text_log), text_log_tail=link.text_log[-40:])
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str))
    print(json.dumps({k: summ[k] for k in ("runs", "rows", "refusal")}))
    return 1 if refusal else 0


if __name__ == "__main__":
    sys.exit(main())
