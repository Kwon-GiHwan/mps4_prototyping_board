"""POST_HOC_DESCRIPTIVE (owner request 2026-11-11, no board run): MAC_ACTIVE of the Conv/DWConv configs of Stage 4 and
Stage 4C-1 against the number of OFM microblocks (ublocks) the kernels cover, from the compiled artifacts.

ublocks = sum over kernels of ceil(H / ub_h) * ceil(W / ub_w) * ceil(kernel OFM channel slice / ub_c); the ublock is Vela's
(debug database), the slices are the kernels' OFM depth in the command stream. cycles per ublock = MAC_ACTIVE / ublocks;
it is read from the data (not derived from documents), so agreement between configs of one operator is a description,
not a prediction.

  python3 results/fi101_stage4c1/mac_active_ublocks.py
"""
import csv, json, math, pathlib, statistics, sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "host/analysis"), str(REPO / "host/lib")]
import stage4 as S4  # noqa: E402
import stage4c1 as P  # noqa: E402

SRC = [("stage4", REPO / "evidence/stage4", c) for c in
       ("s4_conv_base", "s4_conv_cin15", "s4_conv_cout95", "s4_dw_base", "s4_dw_c143")] + \
      [("stage4c1", REPO / "evidence/stage4c1", c) for c in
       ("s4_conv_base", "s4c_conv_cout94", "s4c_conv_cout97", "s4_dw_base", "s4c_dw_c142", "s4c_dw_c145")]
rows = []
for src, ev, cfg in SRC:
    comp = json.loads((ev / "workloads" / f"{cfg}.compile.json").read_text())
    ks = P.kernels((ev / "workloads" / f"{cfg}.drwl.cms.bin").read_bytes())
    _, h, w, c = comp["ofm_shape"]
    uh, uw, uc = map(int, comp["ofm_ublock"].split("x"))
    slices = [k["ofm_depth_m1"] + 1 for k in ks]
    ub = sum(math.ceil(h / uh) * math.ceil(w / uw) * math.ceil(s / uc) for s in slices)
    runs = S4.load(ev / "raw" / "conds" / cfg / "wfe", 1)
    mac = [r["ev"][48] for r in runs[1]]
    dpu = [r["ev"][51] for r in runs[1]]
    rows.append(dict(source=src, config=cfg, channels=c, macs=comp["n_mac"], ofm_ublock=comp["ofm_ublock"],
                     ofm_block=comp["ofm_block"], ofm_slices="+".join(map(str, slices)), ublocks=ub,
                     mac_active=statistics.median(mac), mac_active_range=max(mac) - min(mac),
                     mac_dpu_active=statistics.median(dpu), cycles_per_ublock=statistics.median(mac) / ub,
                     macs_per_mac_active_cycle=round(comp["n_mac"] / statistics.median(mac), 2),
                     channels_rounded_up_to_16=16 * math.ceil(c / 16)))
with open(pathlib.Path(__file__).with_suffix(".csv"), "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); wr.writeheader(); wr.writerows(rows)
for r in rows:
    print(r)
