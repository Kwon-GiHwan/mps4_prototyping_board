#!/usr/bin/env python3
"""One boot of the driver runner (firmware/driver_runner): read the capabilities, upload a DRWL workload once, run each
event set --repeats times, archive every RUN. The counterpart of run_pmu_events.py for record v2; runs.csv keeps the
same columns, so the existing analyses (fi101_s013.load_runs and those built on it) read it unchanged:
window_cycles = infer_npu_cycles = NPU_EXECUTION_CYCLES (PMCCNTR, arm -> completion IRQ), infer_cpu_cycles = the same
span in CPU DWT cycles; the driver runner's own columns follow.

  python3 run_driver_events.py --out <dir> --host-boot-index N --workload <x.drwl> --ids @<ids file> --repeats 10 \
      [--wait-mode 0|1|2] [--pmccntr-cfg 0x..] [--trace-word 0x..] --image-sha256 <boot>,<bram>,<ddr>,<images.txt>
"""
import argparse, csv, datetime, hashlib, json, pathlib, sys, zlib
from dataclasses import dataclass
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import drwl
import pmu_events_parse as E
import qread_trace
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


@dataclass(frozen=True)
class Condition:
    """One run-option setting of a boot: wait mode, PMCCNTR_CFG, trace word, and the event sets it runs (ids file
    order numbers; None = all)."""
    name: str
    wait_mode: int
    pmccntr_cfg: int
    trace_word: int
    set_ids: tuple[int, ...] | None


def check_condition(c: Condition) -> Condition:
    if (c.wait_mode == 2) != (c.trace_word != qread_trace.OFF):
        raise ValueError(f"{c.name}: wait mode 2 (WAIT_TRACE) and a trace word go together")
    if c.wait_mode not in (0, 1, 2) or (c.name and not c.name.replace("_", "").isalnum()):
        raise ValueError(f"{c.name}: bad name or wait mode")
    qread_trace.config_from_word(c.trace_word)   # refuses a malformed word before touching the board
    return c


def parse_conditions(text: str) -> list[Condition]:
    """One per line, '#' ignored: name wait_mode pmccntr_cfg trace_word|off sets (comma list or 'all')."""
    out = []
    for ln in text.splitlines():
        f = ln.split("#")[0].split()
        if not f:
            continue
        if len(f) != 5:
            raise ValueError(f"condition line needs 5 fields: {ln!r}")
        tw = qread_trace.OFF if f[3] == "off" else int(f[3], 0)
        sets = None if f[4] == "all" else tuple(int(x) for x in f[4].split(","))
        out.append(check_condition(Condition(f[0], int(f[1]), int(f[2], 0), tw, sets)))
    if len({c.name for c in out}) != len(out):
        raise ValueError("condition names must be unique")
    return out


def write_outputs(d: pathlib.Path, raw: list, rows: list, summ: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "raw_runs.json").write_text(json.dumps(raw, indent=1, default=str))
    if rows:
        cols = list(dict.fromkeys(k for r in rows for k in r))
        with (d / "runs.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    (d / "summary.json").write_text(json.dumps(summ, indent=2, default=str))


def run_condition(link, cond, sets, ctx, d: pathlib.Path, raw: list, rows: list) -> None:
    """Every RUN of one condition into raw/rows (appended as they come, so a refusal keeps what ran)."""
    link.set_run_options(cond.wait_mode, cond.pmccntr_cfg, cond.trace_word)
    for set_id, codes in sets:
        if cond.set_ids is not None and set_id not in cond.set_ids:
            continue
        try:
            req, applied, cnt, cseq = link.set_instrumentation_mode(E.INSTRUMENTATION_EVENTS, codes, set_id)
        except Nack as n:
            raise E.fail_rule("RULE_MODE_NACK", repr(n))
        if applied != E.INSTRUMENTATION_EVENTS or cnt != len(codes):
            raise E.fail_rule("RULE_MODE_NACK", f"applied={applied} count={cnt}")
        if not ctx["primed"]:
            try:
                prime(link, ctx["blob"])
            except (Nack, ProtocolError) as e:
                raise E.fail_rule("RULE_RUN_TRANSPORT", f"prime: {e!r}")
            ctx["primed"] = True
        for rep in range(1, ctx["repeats"] + 1):
            try:
                link.run(timeout=ctx["run_timeout"])
            except (Nack, ProtocolError) as e:
                raise E.fail_rule("RULE_RUN_TRANSPORT", f"{cond.name} set {set_id} rep {rep}: {e!r}")
            r = link.last_measurement
            ok, failed = record_v2.validity(r, codes)
            raw.append(dict(set_id=set_id, rep=rep, run_sequence=r.run_sequence, valid_flags=r.valid_flags,
                            run_rc=r.run_rc, record=r.f, host_run_s=link.last_run_host_s))
            if ctx["outputs"]:
                try:
                    raw[-1]["output_crc32"], raw[-1]["output_len"] = link.output_crc()
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"output crc {cond.name} set {set_id} rep {rep}: {e!r}")
            if cond.trace_word != qread_trace.OFF:
                h = qread_trace.header_from_record(r.f)
                try:
                    words = link.get_trace(qread_trace.n_words(h))
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"trace {cond.name} set {set_id} rep {rep}: {e!r}")
                (d / "traces").mkdir(parents=True, exist_ok=True)
                (d / "traces" / f"set{set_id}_rep{rep}.bin").write_bytes(
                    b"".join(w.to_bytes(4, "little") for w in words))
            rows += rows_of(r, codes, ok, failed, ctx["names"], ctx["trm"],
                            dict(set_id=set_id, rep=rep, host_run_s=link.last_run_host_s, condition=cond.name,
                                 **ctx["prov"]))
            print(f"{cond.name} set {set_id:2d} rep {rep} rc={r.run_rc} flags=0x{r.valid_flags:02x} "
                  f"npu_exec={r.npu_execution_cycles()} ofm_mismatch={r.f['ofm_mismatch']} valid={ok} "
                  f"{failed or ''}", flush=True)
    if ctx["outputs"] and len(raw) > 1:   # the last RUN's outputs, once per condition; its CRC must match
        try:
            data = link.get_output(raw[-1]["output_len"])
        except (Nack, ProtocolError) as e:
            raise E.fail_rule("RULE_RUN_TRANSPORT", f"output {cond.name}: {e!r}")
        if zlib.crc32(data) != raw[-1]["output_crc32"]:
            raise E.fail_rule("RULE_RUN_TRANSPORT", f"output {cond.name}: CRC differs from the RUN's")
        d.mkdir(parents=True, exist_ok=True)
        (d / "output.bin").write_bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--port", default=PORT)
    ap.add_argument("--host-boot-index", type=int, required=True)
    ap.add_argument("--workload", required=True, help="DRWL workload (pack_vela_workload.py --format drwl)")
    ap.add_argument("--ids", required=True, help="comma-separated event ids or @file (sets per line)")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--wait-mode", type=int, default=0, help="0 = WFE (the driver's own wait, MLEK), 1 = busy loop, "
                                                              "2 = busy loop sampling QREAD")
    ap.add_argument("--pmccntr-cfg", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--trace-word", type=lambda x: int(x, 0), default=qread_trace.OFF,
                    help="QREAD trace word (qread_trace.TraceConfig); needs --wait-mode 2; traces/set<S>_rep<R>.bin")
    ap.add_argument("--conditions", help="@file of conditions (parse_conditions), run in order in this boot; each "
                                         "writes <out>/<name>/; replaces --wait-mode/--pmccntr-cfg/--trace-word")
    ap.add_argument("--run-timeout", type=float, default=120.0)
    ap.add_argument("--outputs", action="store_true", help="CRC of the outputs after every RUN (raw_runs.json) and the "
                                                            "last RUN's outputs per condition (output.bin)")
    ap.add_argument("--image-sha256", required=True, help="boot.bin,bram.bin,ddr.bin,images.txt digests")
    a = ap.parse_args()
    try:
        if a.conditions:
            conds = parse_conditions(pathlib.Path(a.conditions.lstrip("@")).read_text())
        else:
            conds = [check_condition(Condition("", a.wait_mode, a.pmccntr_cfg, a.trace_word, None))]
    except ValueError as e:
        ap.error(str(e))
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
    txt = pathlib.Path(a.ids[1:]).read_text() if a.ids.startswith("@") else a.ids.replace(",", "\n")
    ids, explicit = E.parse_ids_text(txt)
    sets = E.event_sets(ids, sets=explicit)
    ctx = dict(blob=blob, primed=False, repeats=a.repeats, run_timeout=a.run_timeout, prov=prov, outputs=a.outputs,
               names=reference.driver_ids(), trm=reference.trm_ids())
    done, refusal, ping = [], None, None
    link = DriverLink(a.port)
    try:
        ping = link.ping().__dict__
        if ping["state"] != 1:
            raise E.fail_rule("RULE_PING", f"state={ping['state']}")
        (out / "capabilities.json").write_text(json.dumps(link.capabilities(), indent=1))
        for cond in conds:
            done.append((cond, out / cond.name if cond.name else out, [{"ping": ping}], []))
            run_condition(link, cond, sets, ctx, *done[-1][1:])
    except E.Refusal as e:
        refusal = {"rule": E.refusal_rule(e), "msg": str(e)}
        print(f"REFUSED {e}")
    finally:
        link.close()
    for cond, d, raw, rows in done or [(conds[0], out, [{"ping": ping}], [])]:
        write_outputs(d, raw, rows, dict(provenance=prov, condition=cond.name, wait_mode=cond.wait_mode,
                                         pmccntr_cfg=cond.pmccntr_cfg, trace_word=cond.trace_word,
                                         runs=len(raw) - 1, rows=len(rows), refusal=refusal,
                                         text_log_lines=len(link.text_log), text_log_tail=link.text_log[-40:]))
    print(json.dumps({"runs": sum(len(x[2]) - 1 for x in done), "conditions": len(done), "refusal": refusal}))
    return 1 if refusal else 0


if __name__ == "__main__":
    sys.exit(main())
