#!/usr/bin/env python3
"""Tier B: one boot, 22 sets x 3 repeats, archive every run under the contract.

  python3 run_pmu_events.py --out evidence/pmu_events/boot1 --host-boot-index N \
      --app-sha256 .. --vectors-sha256 .. --ddr-sha256 ..
"""
import argparse, csv, datetime, json, pathlib, struct, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import zlib
import pmu_events_parse as E
from runner_proto import (MAX_PAYLOAD, RunnerLink, PROTO_MEASURE_V2, Nack, ProtocolError,
                          GOLDEN_WINDOW_CRC, PMU_DIAG_GOLDEN_WINDOW_BASE, PMU_DIAG_GOLDEN_WINDOW_LEN)


BLOB = None   # Tier C step 1: a PMWL workload blob replaces the 64-byte dummy when --blob is given
CHUNK = 4092   # MAX_PAYLOAD 4096 minus the 4-byte offset; halves the per-chunk ACK round trips vs 2048


assert CHUNK + 4 <= MAX_PAYLOAD


def prime(link):
    """Walk the state machine to INPUT_READY exactly as run_pmu_diag.py / run_pmu_qual.py
    do: a dummy blob (or the PMWL workload blob) and an empty input."""
    blob = BLOB if BLOB is not None else b"\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    for off in range(0, len(blob), CHUNK):
        link.load_model_chunk(off, blob[off:off + CHUNK])
    link.load_model_end()
    link.load_input(b"")

PORT = "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_00FT46259002B-if01-port0"
ERR_UNSUPPORTED_NAMES = ("ERR_UNSUPPORTED",)
PROV = dict(board_serial="FTDI-00FT46259002B", fpga_image="FI101-r1p0 (109762 v0100)",
            build_id=f"0x{E.BUILD_ID_PMEV:08x}", authorization="owner-verbal-2026-09-23")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--port", default=PORT)
    ap.add_argument("--host-boot-index", type=int, required=True)
    ap.add_argument("--build-id", default=f"0x{E.BUILD_ID_PMEV:08x}")
    ap.add_argument("--check-golden", action="store_true", help="Tier C: GET_RESULT golden window after every RUN")
    ap.add_argument("--blob", help="Tier C step 1: PMWL workload blob to stage with LOAD_MODEL")
    ap.add_argument("--validity", choices=("exact", "model"), default="exact",
                    help="model: completion replaces exact OFM match (step-2 amendment 2)")
    ap.add_argument("--keep-model", action="store_true",
                    help="step 3: upload the blob once per boot; later sets only SET_MODE (MODEL builds)")
    ap.add_argument("--ids", help="Tier C step 2: comma-separated event ids or @file (default: all 171)")
    for k in ("app", "vectors", "ddr"): ap.add_argument(f"--{k}-sha256", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    global BLOB
    if a.blob:
        BLOB = pathlib.Path(a.blob).read_bytes()
    prov = dict(PROV, build_id=a.build_id, app_sha256=a.app_sha256, vectors_sha256=a.vectors_sha256, ddr_sha256=a.ddr_sha256,
                host_boot_index=a.host_boot_index, captured_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    names = E.driver_ids(); trm = E.trm_ids()
    ids = None
    if a.ids:
        txt = pathlib.Path(a.ids[1:]).read_text() if a.ids.startswith("@") else a.ids
        ids = [int(x) for x in txt.replace("\n", ",").split(",") if x.strip()]
    sets = E.event_sets(ids)
    rows, raw, refusal = [], [], None
    link = RunnerLink(a.port, protocol=PROTO_MEASURE_V2)
    try:
        c = link.ping()
        raw.append({"ping": c.__dict__})
        if c.state != 1: raise E.fail_rule("RULE_PING", f"state={c.state}")
        # Contract (amendment 2): the SEVEN error counters must be zero. rx_bytes/tx_bytes
        # are traffic counters and include this PING's own 20-byte frame, so they are not judged.
        errors = {k: getattr(c, k) for k in ("rx_overrun", "bad_magic", "bad_version", "bad_crc",
                                              "length_error", "sequence_error", "parser_resync")}
        if any(errors.values()):
            raise E.fail_rule("RULE_PING", f"error counters not zero on fresh boot: {errors}")
        for set_id, codes in sets:
            # State machine (amendment 3): SET_INSTRUMENTATION_MODE is accepted only in IDLE,
            # RUN only in INPUT_READY/RESULT_READY. Per set: RESET -> SET_MODE -> prime -> RUN x3.
            first = set_id == sets[0][0]
            try:
                if first or not a.keep_model:
                    link.reset_runner()
                req, applied, cnt, cseq = link.set_instrumentation_mode(E.INSTRUMENTATION_EVENTS, codes, set_id)
            except Nack as n:
                rule = "RULE_CAPABILITY" if (set_id == 1 and "UNSUPPORTED" in repr(n)) else "RULE_MODE_NACK"
                raise E.fail_rule(rule, repr(n))
            if applied != E.INSTRUMENTATION_EVENTS or cnt != len(codes):
                raise E.fail_rule("RULE_MODE_NACK", f"applied={applied} count={cnt}")
            try:
                if first or not a.keep_model:
                    prime(link)
            except (Nack, ProtocolError) as e:
                raise E.fail_rule("RULE_RUN_TRANSPORT", f"set {set_id} prime: {e!r}")
            for rep in range(1, E.REPEATS + 1):
                try:
                    rc = link.run(timeout=120.0)
                except (Nack, ProtocolError) as e:
                    raise E.fail_rule("RULE_RUN_TRANSPORT", f"set {set_id} rep {rep}: {e!r}")
                m = link.last_measurement
                if m is None or m.pmu is None: raise E.fail_rule("RULE_RECORD_SCHEMA", "no PMU block in record")
                if m.pmu["record_schema_version"] != 1: raise E.fail_rule("RULE_RECORD_SCHEMA", str(m.pmu["record_schema_version"]))
                seam = m.trailing[0] if len(m.trailing) >= 1 else None   # amendment 7: field 103
                golden_crc = None
                if a.check_golden:
                    try:
                        _, _, _, golden_crc = link.get_result(PMU_DIAG_GOLDEN_WINDOW_BASE, PMU_DIAG_GOLDEN_WINDOW_LEN, m.run_sequence)
                    except (Nack, ProtocolError) as e:
                        golden_crc = f"error: {e!r}"
                tr = list(m.trailing) + [None] * 7
                r = dict(run_rc=rc, required_flags_ok=m.required_flags_ok(), pmu=m.pmu, seam_fired=seam,
                         valid_flags=m.valid_flags, vendor_rc=tr[1], seam_npu_status=tr[2], seam_npu_qread=tr[3],
                         cms_len=(struct.unpack_from("<I", BLOB, 12)[0] if BLOB is not None else None))
                if a.check_golden:
                    r["golden_ok"] = (golden_crc == GOLDEN_WINDOW_CRC)
                ok, failed = E.run_validity(r, codes, a.validity)
                if "codes_echo" in failed and ok is False and m.pmu["event_valid_mask"] == (1 << len(codes)) - 1:
                    raise E.fail_rule("RULE_CODES_ECHO", f"set {set_id}: {m.pmu['event_codes'][:len(codes)]} != {codes}")
                raw.append({"set_id": set_id, "rep": rep, "rc": rc, "valid_flags": m.valid_flags, "pmu": m.pmu,
                            "seam_fired": seam, "trailing": list(m.trailing), "golden_crc": golden_crc,
                            "vendor_rc": (m.trailing[1] if len(m.trailing) >= 2 else None),
                            "base_fields": list(m.fields),
                            "seam_npu_status": (m.trailing[2] if len(m.trailing) >= 3 else None),
                            "seam_npu_qread": (m.trailing[3] if len(m.trailing) >= 4 else None),
                            "ofm_mismatch": (list(m.trailing[4:7]) if len(m.trailing) >= 7 else None)})
                for slot, ev in enumerate(codes):
                    rows.append(dict(set_id=set_id, rep=rep, slot=slot, ev_type=ev, name=names[ev], in_trm110=ev in trm,
                                     event_value=m.pmu["event_values"][slot] if ok else None,
                                     event_valid=bool((m.pmu["event_valid_mask"] >> slot) & 1),
                                     event_overflow=m.pmu["event_overflow"][slot], run_rc=rc, run_valid=ok,
                                     invalid_reasons=";".join(failed), window_cycles=m.pmu["npu_pmu_window_cycles"],
                                     cycle_valid=m.pmu["npu_pmu_cycle_valid"], valid_flags=m.valid_flags,
                                     golden_crc=(f"0x{golden_crc:08x}" if isinstance(golden_crc, int) else golden_crc),
                                     vendor_rc=tr[1], ofm_mismatch_count=tr[4], ofm_max_abs_diff=tr[5], **prov))
                vrc = m.trailing[1] if len(m.trailing) >= 2 else None
                st = (hex(m.trailing[2]), m.trailing[3]) if len(m.trailing) >= 4 else None
                mm = tuple(m.trailing[4:7]) if len(m.trailing) >= 7 else None
                print(f"set {set_id:2d} rep {rep} rc={rc} vendor_rc={vrc} seam_status/qread={st} ofm_mismatch(count,maxdiff,first)={mm} valid={ok} {failed or ''}", flush=True)
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
    mm = sorted({tuple(x["ofm_mismatch"][:2]) for x in raw if x.get("ofm_mismatch")})
    summ = dict(keep_model=a.keep_model, validity=a.validity, ofm_mismatch_observed=[list(t) for t in mm], requested_ids=(sorted(set(ids)) if ids else "all"), provenance=prov, runs=len(raw) - 1, rows=len(rows), refusal=refusal,
                consistency=E.consistency(rows), verdict_counts={v: sum(1 for p in per if p["verdict"] == v) for v in E.VERDICTS})
    try:
        E.check_coverage(by, ids); summ["coverage"] = "COMPLETE" if ids is None else f"COMPLETE_SUBSET({len(set(ids))})"
    except E.Refusal as e:
        summ["coverage"] = str(e)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str))
    print(json.dumps({k: summ[k] for k in ("runs", "coverage", "consistency", "verdict_counts", "refusal")}, indent=1))
    return 1 if refusal else 0


if __name__ == "__main__":
    sys.exit(main())
