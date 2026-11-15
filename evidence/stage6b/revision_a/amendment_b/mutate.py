"""Mutation test of the Stage 6B Revision A Amendment B judge (evidence/stage6b/revision_a/amendment_b/amendment_b_contract.md).
Each mutation neuters one rule in host/analysis/stage6b_amendment_b.py, runs test_stage6b_amendment_b, requires RED, and
restores the file by sha256.

    python3 evidence/stage6b/revision_a/amendment_b/mutate.py
"""
import hashlib
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
A = "host/analysis/stage6b_amendment_b.py"
T = ["test_stage6b_amendment_b"]

MUTATIONS = [
    ('F1: original activation rows', A, 'if oacts != ([ACT_OP[act]] if act in ACT_OP else []):', 'if False:'),
    ('F2: tflite_activation', A, 'if row.get("tflite_activation") != oconv.get("tflite_activation"):', 'if False:'),
    ('F2: activation registers', A, 'for k in ACT_REGS if a.get(k) != b.get(k)})', 'for k in () if a.get(k) != b.get(k)})'),
    ('F2: activation min/max', A, 'ACT_REGS = ("activation", "activation_min", "activation_max", "ofm_zero_point", "ofm_scale")', 'ACT_REGS = ("activation", "ofm_zero_point", "ofm_scale")'),
    ('F2: ofm scale and zero point', A, 'ACT_REGS = ("activation", "activation_min", "activation_max", "ofm_zero_point", "ofm_scale")', 'ACT_REGS = ("activation", "activation_min", "activation_max")'),
    ('F3: conv registers', A, 'diffs += [f"F3 {k}" for k in d]', 'pass'),
    ('F4: dead activation row', A, 'if not all(is_dead(r) for r in act_rows(inv_rows) + act_rows(form["rows"])):', 'if False:'),
    ('F4: dead = no cms offset', A, 'return not str(r.get("cms_offsets") or "").strip() and', 'return'),
    ('F4: dead = no cycles', A, 'and str(r.get("vela_op_cycles")) == "0"', ''),
    ('F4: kernel types', A, 'if ff["kernel_types"] != expected_kernels(label, len(orig["conv_act"])):', 'if False:'),
    ('F6: rows from the original activation', A, 'conv = ["Conv2D"] + list(oacts)', 'conv = ["Conv2D"] + [ACT_OP[a] for a in ACT_OP][:len(oacts)]'),
    ('F6: logical rows', A, 'if form.get("npu_ops") != ops or [int(r["tflite_op_index"]) for r in form["rows"]] != idx:', 'if form.get("npu_ops") != ops:'),
    ('F6: logical op list', A, 'if form.get("npu_ops") != ops or [int(r["tflite_op_index"]) for r in form["rows"]] != idx:', 'if [int(r["tflite_op_index"]) for r in form["rows"]] != idx:'),
    ('F6: cpu ops', A, 'if form.get("cpu_rows"):', 'if False:'),
    ('F6: fused names', A, 'if any(str(r.get("fused_names")) != "1" for r in form["rows"]):', 'if False:'),
    ('F6: conv output tensor', A, 'if row.get("name") != RA.CONV_OUT_NAME[label]:', 'if False:'),
    ('unverified: original compile', A, 'if not orig.get("vela_sha256", "").startswith(man["inventory_vela_sha256"]) or orig.get("n_ethosu_ops") != 1:', 'if False:'),
    ('unverified: original registers', A, 'if not orig.get("conv_act") or any(k is None for k in orig["conv_act"]):', 'if False:'),
    ('unverified: form registers', A, 'if not ff or not ff.get("conv_act") or any(k is None for k in ff["conv_act"]):', 'if not ff:'),
    ('unverified: stream digest', A, 'if ff and ff.get("cms_sha256") != form.get("cms_sha256"):\n        missing.append', 'if False:\n        missing.append'),
    ('unverified: logical rows', A, 'if not form.get("rows") or not inv_rows:', 'if False:'),
    ('gate: only PRESERVED passes', A, 'return dict(status=RA.FAIL if diffs else RA.PASS, cls=CHANGED if diffs else PRESERVED, diffs=diffs)', 'return dict(status=RA.PASS, cls=CHANGED if diffs else PRESERVED, diffs=diffs)'),
    ('eligible: amended gate used', A, 'checks = dict(j["checks"], fusion=dict(status=fg["status"], diffs=fg["diffs"]))', 'checks = dict(j["checks"])'),
    ('eligible: all gates', A, 'ok = j["cls"] == "EXACT_A" and all(c["status"] == RA.PASS for c in checks.values())', 'ok = j["cls"] == "EXACT_A" and checks["fusion"]["status"] == RA.PASS'),
    ('V2: conv input', A, 'if not fx["conv_in_equals_x"]:', 'if False:'),
    ('V3: model conv output', A, 'if fx["conv_out_vs_model_mismatch"] != 0:', 'if False:'),
    ('V4: numpy', A, 'if fx["numpy_vs_ref_max_abs"] > RA.NUMPY_MAX_ABS:', 'if False:'),
    ('V5: self-ADD', A, 'if fx["final_vs_conv_out_max_abs"] > RA.SELF_ADD_MAX_ABS:', 'if False:'),
    ('V6: conv_out 10 %', A, 'if fx["conv_out_informative"] < RA.INFORMATIVE_MIN:', 'if False:'),
    ('V6: final 10 %', A, 'if fx["final_informative"] < RA.INFORMATIVE_MIN:', 'if False:'),
    ('V6: threshold not lowered', A, 'if fx["conv_out_informative"] < RA.INFORMATIVE_MIN:', 'if fx["conv_out_informative"] < 0.05:'),
    ('V7: repacked compile', A, 'if fx["pack_rc"] != 0 or not fx.get("vela_equals_record") or not fx.get("cms_equals_record"):', 'if fx["pack_rc"] != 0:'),
    ('V1: digest -> UNRESOLVED', A, 'if not fx["input_digest_ok"]:', 'if False:'),
    ('V1: shape -> UNRESOLVED', A, 'if fx.get("x_shape") != fx.get("conv_ifm_shape"):', 'if False:'),
    ('fixture: incomplete -> UNRESOLVED', A, 'if any(fx.get(k) is None for k in need):', 'if False:'),
    ('fixture: missing -> UNRESOLVED', A, 'if not fx or fx.get("missing") or "input_digest_ok" not in fx:', 'if not fx:'),
    ('extra: fixed groups only', A, 'fg = fixture_gate(fx) if man["group"] in FIXTURE_GROUPS else None', 'fg = fixture_gate(fx)'),
    ('extra: fixture PASS required', A, 'extra = board is None and fg is not None and fg["status"] == RA.PASS and saturation_only(forms["A2"])', 'extra = board is None and fg is not None and saturation_only(forms["A2"])'),
    ('extra: saturation diffs only', A, 'and set(ref["diffs"]) <= SATURATION_DIFFS', ''),
    ('extra: other gates pass', A, 'others = all(c["status"] == RA.PASS for k, c in fj["checks"].items() if k != "reference")', 'others = True'),
    ('extra: EXACT_A required', A, 'return fj["cls"] == "EXACT_A" and others and', 'return others and'),
    ('extra: apart from board_eligible', A, 'return dict(forms=forms, form=best, cls=forms[best]["cls"], board_form=board, board_eligible=board is not None,', 'return dict(forms=forms, form=best, cls=forms[best]["cls"], board_form=board, board_eligible=board is not None or extra,'),
    ('prov: fact stream', A, 'if ff and ff.get("cms_sha256") != form.get("cms_sha256"):\n                err.append', 'if False:\n                err.append'),
    ('prov: missing facts', A, 'err.append(f"{c[\'group\']}: no fusion facts"); continue', 'continue'),
    ('estimates: graph sum', A, 'graph_op_cycles_sum=sum(num(r.get("vela_op_cycles")) or 0 for r in form.get("rows") or []),', 'graph_op_cycles_sum=num(cr.get("vela_op_cycles")),'),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def green():
    for d in REPO.glob("host/**/__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    return all(subprocess.run([sys.executable, "-B", "-W", "ignore", "-m", "unittest", f"host.tests.{m}"], cwd=REPO,
                              capture_output=True).returncode == 0 for m in T)


def main():
    if not green():
        print("baseline not GREEN"); return 1
    lines, bad = [], 0
    for mid, rel, old, new in MUTATIONS:
        p = REPO / rel
        before, text = sha(p), p.read_text()
        if text.count(old) != 1:
            lines.append(f"NOT_APPLIED  {mid}  ({rel}: pattern found {text.count(old)}x)"); bad += 1; print(lines[-1]); continue
        p.write_text(text.replace(old, new))
        try:
            g = green()
        finally:
            p.write_text(text)
        restored = sha(p) == before
        bad += g or not restored
        lines.append(f"{'SURVIVED' if g else 'KILLED':12s} {mid}  ({rel}; restored by sha256: {restored})")
        print(lines[-1], flush=True)
    g = green()
    lines.append(f"after restore: {'GREEN' if g else 'RED'}")
    (pathlib.Path(__file__).parent / "mutation.txt").write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 1 if bad or not g else 0


if __name__ == "__main__":
    sys.exit(main())
