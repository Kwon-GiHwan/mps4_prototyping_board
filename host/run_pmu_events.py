#!/usr/bin/env python3
"""Tier B: one boot, 22 sets x 3 repeats, archive every run under the contract.

  python3 run_pmu_events.py --out evidence/pmu_events/boot1 --host-boot-index N \
      --app-sha256 .. --vectors-sha256 .. --ddr-sha256 ..
"""
import argparse, csv, datetime, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pmu_events_parse as E
from runner_proto import RunnerLink, PROTO_MEASURE_V2, Nack, ProtocolError

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
ERR_UNSUPPORTED_NAMES = ("ERR_UNSUPPORTED",)
PROV = dict(board_serial="FTDI-00FT46259002B", fpga_image="FI101-r1p0 (109762 v0100)",
            build_id=f"0x{E.BUILD_ID_PMEV:08x}", authorization="owner-verbal-2026-09-23")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--port", default=PORT)
    ap.add_argument("--host-boot-index", type=int, required=True)
    for k in ("app", "vectors", "ddr"): ap.add_argument(f"--{k}-sha256", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prov = dict(PROV, app_sha256=a.app_sha256, vectors_sha256=a.vectors_sha256, ddr_sha256=a.ddr_sha256,
                host_boot_index=a.host_boot_index, captured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    names = E.driver_ids(); trm = E.trm_ids()
    rows, raw, refusal = [], [], None
    link = RunnerLink(a.port, protocol=PROTO_MEASURE_V2)
    try:
        c = link.ping()
        raw.append({"ping": c.__dict__})
        if c.state != 1: raise E.fail_rule("RULE_PING", f"state={c.state}")
        counters = {k: v for k, v in c.__dict__.items() if k not in ("state", "version")}
        if any(counters.values()):   # contract: all error/traffic counters zero before the first set
            raise E.fail_rule("RULE_PING", f"counters not zero on fresh boot: {counters}")
        for set_id, codes in E.event_sets():
            for rep in range(1, E.REPEATS + 1):
                try:
                    req, applied, cnt, cseq = link.set_instrumentation_mode(E.INSTRUMENTATION_EVENTS, codes, set_id)
                except Nack as n:
                    rule = "RULE_CAPABILITY" if (set_id == 1 and rep == 1 and "UNSUPPORTED" in repr(n)) else "RULE_MODE_NACK"
                    raise E.fail_rule(rule, repr(n))
                if applied != E.INSTRUMENTATION_EVENTS or cnt != len(codes):
                    raise E.fail_rule("RULE_MODE_NACK", f"applied={applied} count={cnt}")
                try:
                    rc = link.run(timeout=60.0)
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"set {set_id} rep {rep}: {e!r}")
                m = link.last_measurement
                if m is None or m.pmu is None: raise E.fail_rule("RULE_RECORD_SCHEMA", "no PMU block in record")
                if m.pmu["record_schema_version"] != 1: raise E.fail_rule("RULE_RECORD_SCHEMA", str(m.pmu["record_schema_version"]))
                r = dict(run_rc=rc, required_flags_ok=m.required_flags_ok(), pmu=m.pmu)
                ok, failed = E.run_validity(r, codes)
                if "codes_echo" in failed and ok is False and m.pmu["event_valid_mask"] == (1 << len(codes)) - 1:
                    raise E.fail_rule("RULE_CODES_ECHO", f"set {set_id}: {m.pmu['event_codes'][:len(codes)]} != {codes}")
                raw.append({"set_id": set_id, "rep": rep, "rc": rc, "valid_flags": m.valid_flags, "pmu": m.pmu})
                for slot, ev in enumerate(codes):
                    rows.append(dict(set_id=set_id, rep=rep, slot=slot, ev_type=ev, name=names[ev], in_trm110=ev in trm,
                                     event_value=m.pmu["event_values"][slot] if ok else None,
                                     event_valid=bool((m.pmu["event_valid_mask"] >> slot) & 1),
                                     event_overflow=m.pmu["event_overflow"][slot], run_rc=rc, run_valid=ok,
                                     invalid_reasons=";".join(failed), window_cycles=m.pmu["npu_pmu_window_cycles"],
                                     cycle_valid=m.pmu["npu_pmu_cycle_valid"], valid_flags=m.valid_flags, **prov))
                print(f"set {set_id:2d} rep {rep} rc={rc} valid={ok} {failed or ''}", flush=True)
    except E.Refusal as e:
        refusal = {"rule": E.refusal_rule(e), "msg": str(e)}; print(f"REFUSED {e}")
    finally:
        link.close()
    (out / "raw_runs.json").write_text(json.dumps(raw, indent=1, default=str))
    if rows:
        with (out / "runs.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    by = {}
    for r in rows: by.setdefault(r["ev_type"], []).append(r["event_value"])
    per = [dict(ev_type=ev, name=names[ev], in_trm110=ev in trm, verdict=E.verdict(vals), values=vals,
                tier="B-count", where=f"{prov['board_serial']} / {prov['fpga_image']} / PMEVCNTR[slot]",
                how="EVENTS mode: PMEVTYPER=id, PMCNTENSET, run apU85Conv_TEST, read PMEVCNTR after disable; 3 repeats",
                boot=out.name, app_sha256=prov["app_sha256"], captured_at_utc=prov["captured_at_utc"],
                authorization=prov["authorization"]) for ev, vals in sorted(by.items())]
    if per:
        with (out / "per_event.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(per[0].keys())); w.writeheader(); w.writerows(per)
    summ = dict(provenance=prov, runs=len(raw) - 1, rows=len(rows), refusal=refusal,
                consistency=E.consistency(rows), verdict_counts={v: sum(1 for p in per if p["verdict"] == v) for v in E.VERDICTS})
    try:
        E.check_coverage(by); summ["coverage"] = "COMPLETE"
    except E.Refusal as e:
        summ["coverage"] = str(e)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str))
    print(json.dumps({k: summ[k] for k in ("runs", "coverage", "consistency", "verdict_counts", "refusal")}, indent=1))
    return 1 if refusal else 0


if __name__ == "__main__":
    sys.exit(main())
