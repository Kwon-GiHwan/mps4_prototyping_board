#!/usr/bin/env python3
"""Figure 1 (Stage 6C F1, F2, F4, F5): raw-data table, Fig 1-A (MACs per MAC_ACTIVE cycle by shape),
Fig 1-B (F1/F2 representative vs control: MAC_ACTIVE and NPU_ACTIVE in cycles) and the shape table.

Inputs: results/fi101_stage6c/stage6c_summary.json (TA profile 1, EXT RLATENCY 500, image 14077be, placement 0) and
the Vela shape facts already in that summary; operator geometry from results/fi101_stage4/stage4_operator_inventory.csv
for the representatives, the controls are the same mapping with the channel count changed (evidence/stage6c/contract.md).

  python3 fig1_stage6c.py <out dir>        (needs matplotlib)
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402,F401
from matplotlib import font_manager  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
SUM = REPO / "results/fi101_stage6c/stage6c_summary.json"
COND = "TA profile 1 (EXT RLATENCY 500), runner image 14077be, placement 0, pass A/B 측정 RUN 중앙값"
# label, key, source operator, geometry (Ho x Wo, Cin, Cout, kernel, stride) — representatives from the stage4 inventory
SHAPES = [
    ("F1 대표", "s6c_f1_rep", "yolo op9 Conv2D 1×1", "96×96", 4, 24, "1×1", "1×1"),
    ("F1 통제", "s6c_f1_cin16", "F1, Cin 16", "96×96", 16, 24, "1×1", "1×1"),
    ("F2 대표", "s6c_f2_rep", "yolo op3 DW 3×3", "96×96", 8, 8, "3×3", "1×1"),
    ("F2 통제", "s6c_f2_c16", "F2, C 16", "96×96", 16, 16, "3×3", "1×1"),
    ("F4", "s6c_f4_rep", "w2l op17 Conv2D 1×32", "1×148", 250, 2000, "1×32", "1×1"),
    ("F5", "s6c_f5_rep", "kws op0 Conv2D 10×4", "49×10", 1, 140, "10×4", "1×1"),
]
PEAK = 1024
BLUE, ORANGE = "#2a78d6", "#eb6834"            # dataviz reference categorical slots 1, 2 (validated, light)
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


KFONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def style():
    font_manager.fontManager.addfont(KFONT)
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=KFONT).get_name(), "axes.unicode_minus": False, "font.size": 10, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                         "savefig.facecolor": SURF, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
                         "grid.linewidth": 0.8, "axes.axisbelow": True})


def rows(s: dict) -> list[dict]:
    out = []
    for label, key, src, sp, cin, cout, k, st in SHAPES:
        r = s["results"][key]
        assert r["status"] == "VALID", key
        m, t, v = r["metrics"], r["traffic"], s["shapes"][key]["vela"]
        out.append(dict(shape=label, key=key, source=src, status=r["status"], ofm_spatial=sp, cin=cin, cout=cout,
                        kernel=k, stride=st, traversal=v["traversal"], ofm_block=v["ofm_block"], ofm_ublock=v["ofm_ublock"],
                        n_mac=m["n_mac"], npu_active=m["npu_active"], npu_active_range=m["npu_active_range"],
                        mac_active=m["mac_active"], mac_dpu_active=m["mac_dpu_active"], ao_active=m["ao_active"],
                        wd_active=m["wd_active"], wd_stalled=m["wd_stalled"],
                        macs_per_mac_cycle=m["n_mac"] / m["mac_active"],
                        sram_rd_beats=t["sram_rd_beats"], sram_wr_beats=t["sram_wr_beats"],
                        ext_rd_beats=t["ext_rd_beats"], ext_wr_beats=t["ext_wr_beats"],
                        ext_rd_trans=t["ext_rd_trans"], ext_rd_req_stalled=t["ext_rd_req_stalled"],
                        vela_op_cycles=v["op_cycles"], condition=COND))
    return out


def fig_a(rs: list[dict], out: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    x = range(len(rs))
    vals = [r["macs_per_mac_cycle"] for r in rs]
    ax.bar(x, vals, width=0.62, color=BLUE, edgecolor=SURF, linewidth=2)
    ax.axhline(PEAK, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(-0.4, PEAK + 15, f"피크 {PEAK} MAC/cycle", ha="left", va="bottom", color=INK2, fontsize=9)
    for i, v in zip(x, vals):
        if v > 0.85 * PEAK:                                   # inside the bar, clear of the peak line
            ax.text(i, v - 25, f"{v:,.0f}", ha="center", va="top", color=SURF, fontsize=9)
        else:
            ax.text(i, v + 15, f"{v:,.0f}", ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_xticks(list(x), [f"{r['shape']}\n{r['traversal']}" for r in rs], fontsize=9)
    ax.set_ylim(0, 1150)
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    ax.set_ylabel("MAC / MAC_ACTIVE cycle (TFLite N_MAC 기준)")
    ax.set_title("그림 1-A. 연산 형상별 유효 MAC 처리율", loc="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, f"Stage 6C. {COND}.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out / "fig1a_mac_per_cycle.png", dpi=200)
    plt.close(fig)


def fig_b(rs: list[dict], out: pathlib.Path) -> None:
    pairs = [("F1 (1×1 PartKernel)", rs[0], rs[1]), ("F2 (Depthwise 3×3)", rs[2], rs[3])]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.0))
    w = 0.36
    for ax, (title, rep, ctl) in zip(axes, pairs):
        for j, r in enumerate((rep, ctl)):
            ax.bar(j - w / 2, r["mac_active"], w, color=BLUE, edgecolor=SURF, linewidth=2,
                   label="MAC_ACTIVE" if j == 0 else None)
            ax.bar(j + w / 2, r["npu_active"], w, color=ORANGE, edgecolor=SURF, linewidth=2,
                   label="NPU_ACTIVE" if j == 0 else None)
            top = max(rep["npu_active"], ctl["npu_active"])
            ax.text(j - w / 2, r["mac_active"] + 0.015 * top, f"{r['mac_active']:,.0f}", ha="center", va="bottom",
                    fontsize=8.5, color=INK)
            ax.text(j + w / 2, r["npu_active"] + 0.015 * top, f"{r['npu_active']:,.0f}\n(range {r['npu_active_range']:,})",
                    ha="center", va="bottom", fontsize=8, color=INK)
        ax.set_xticks([0, 1], [f"대표\nCin {rep['cin']} → Cout {rep['cout']}", f"통제\nCin {ctl['cin']} → Cout {ctl['cout']}"],
                      fontsize=9)
        ax.set_ylim(0, max(rep["npu_active"], ctl["npu_active"]) * 1.22)
        ax.set_title(title, loc="left", fontsize=10, color=INK)
        ax.set_ylabel("cycles")
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, loc="upper left", bbox_to_anchor=(0.01, 0.93), ncol=2, fontsize=9)
    fig.suptitle("그림 1-B. 대표/통제 쌍의 MAC_ACTIVE와 NPU_ACTIVE (같은 cycle 단위, 패널별 축 범위)", x=0.01,
                 ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, f"Stage 6C. {COND}. 각 Unit ACTIVE의 증가를 병목의 직접 원인으로 해석하지 않는다.",
             fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.88))
    fig.savefig(out / "fig1b_mac_vs_npu_active.png", dpi=200)
    plt.close(fig)


def fig_table(rs: list[dict], out: pathlib.Path) -> None:
    cols = ["형상", "출처 연산", "Traversal", "OFM Block", "ublock", "Cin", "Cout", "Kernel", "Stride", "OFM 공간 크기",
            "N_MAC (TFLite)"]
    cells = [[r["shape"], r["source"], r["traversal"], r["ofm_block"], r["ofm_ublock"], r["cin"], r["cout"], r["kernel"],
              r["stride"], r["ofm_spatial"], f"{r['n_mac']:,}"] for r in rs]
    fig, ax = plt.subplots(figsize=(10.5, 2.5))
    ax.axis("off")
    t = ax.table(cellText=cells, colLabels=cols, loc="center", cellLoc="center")
    t.auto_set_font_size(False)
    t.set_fontsize(8.5)
    t.scale(1, 1.45)
    t.auto_set_column_width(list(range(len(cols))))
    for (i, _), c in t.get_celld().items():
        c.set_edgecolor(GRID)
        c.set_facecolor("#efeeea" if i == 0 else SURF)
    ax.set_title("그림 1 보조 표. 형상별 실행 구성 (Vela 5.0.0, MLEK 옵션)", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(out / "fig1_shape_table.png", dpi=200)
    plt.close(fig)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rs = rows(json.loads(SUM.read_text()))
    with (out / "fig1_raw_data.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rs)
    style()
    fig_a(rs, out)
    fig_b(rs, out)
    fig_table(rs, out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
