"""H3-R figures, regenerated from the evidence CSVs (plan A8 / GO section 10). Nothing is typed in by hand here.

    ~/.venvs/h3r-tf/bin/python h3r_plots.py        # writes plots/*.png

  fig1_r_by_shape_<metric>.png   r = C512/C256 per shape, one panel per op, base vs equalized (+ bridge for DW)
  fig2_cycles_by_shape.png       256 and 512 cycles per shape, base vs equalized, one panel per op (TOTAL)
  fig3_h3_vs_h3r_base.png        Q1: legacy H3 base r vs H3-R base r per shape
  fig4_dw_bridge.png             Q3: DW legacy relaxed / bridge / equalized r per shape
The shape order is the plan's (1x36 ... 36x1). A missing (gate-refused) point is left empty, never interpolated.
"""
import csv, json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PLOTS = os.path.join(HERE, "plots")
SHAPES = [(1, 36), (2, 18), (3, 12), (4, 9), (6, 6), (9, 4), (12, 3), (18, 2), (36, 1)]
LABELS = ["%dx%d" % s for s in SHAPES]
OPS = [("conv1x1", "1x1 Conv"), ("conv3x3", "3x3 Conv SAME"), ("dw3x3", "3x3 DWConv SAME")]
COND = {"base": ("tab:blue", "o", "base (MAC profile TA)"), "equalized": ("tab:red", "s", "equalized (identical applied TA)"),
        "bridge_legacy_relaxed": ("tab:green", "^", "bridge (legacy relaxed TA)")}


def rows(name):
    with open(os.path.join(HERE, name)) as f:
        lines = [l for l in f if not l.startswith("#")]
    return list(csv.DictReader(lines))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def series(data, key):
    return [num(data.get(s, {}).get(key)) for s in SHAPES]


def plot_series(ax, ys, color, marker, label, order=0, n=1):
    """Coincident series are the point of several of these figures, so later series are drawn with a smaller,
    hollow marker and a dashed line: three curves lying exactly on top of each other stay visibly three."""
    xs = [i for i, y in enumerate(ys) if y is not None]
    vs = [y for y in ys if y is not None]
    style = [("-", 11, "none", 2.6), ("--", 7, "none", 1.8), (":", 4, color, 1.2)][min(order, 2)] if n > 1 else ("-", 5, color, 1.6)
    ls, ms, mfc, lw = style
    ax.plot(xs, vs, color=color, marker=marker, label=label, linewidth=lw, markersize=ms,
            markerfacecolor=mfc, markeredgecolor=color, markeredgewidth=1.4, linestyle=ls)


def axis(ax, title, ylabel):
    ax.set_title(title, fontsize=11)
    ax.set_xticks(range(len(LABELS))); ax.set_xticklabels(LABELS, rotation=45, fontsize=8)
    ax.set_xlabel("shape H x W (area 36)", fontsize=9); ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(alpha=0.3, linewidth=0.5)


def main():
    os.makedirs(PLOTS, exist_ok=True)
    metrics = rows("h3r_models_conditions_metrics.csv")
    # r is carried on the 256 row of each (model, arm)
    by = {}
    for r in metrics:
        if r["gate"] == "PASS" and int(r["mac"]) == 256:
            by.setdefault((r["op"], r["arm"]), {})[(int(r["H"]), int(r["W"]))] = r

    for metric, col in (("TOTAL", "r_TOTAL_512_over_256"), ("ACTIVE", "r_ACTIVE_512_over_256")):
        fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
        for ax, (op, name) in zip(axes, OPS):
            present = [(cond, v) for cond, v in COND.items() if by.get((op, cond))]
            for order, (cond, (c, m, lab)) in enumerate(present):
                plot_series(ax, series(by[(op, cond)], col), c, m, lab, order, len(present))
            ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
            axis(ax, name, "r = C512 / C256 (%s)" % metric)
        axes[0].legend(fontsize=8)
        fig.suptitle("H3-R: scaling ratio by shape, common quantisation (%s cycles)" % metric, fontsize=12)
        fig.tight_layout()
        fig.savefig(os.path.join(PLOTS, "fig1_r_by_shape_%s.png" % metric.lower()), dpi=150)
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, (op, name) in zip(axes, OPS):
        for cond, (c, m, lab) in COND.items():
            for mac, ls in ((256, "-"), (512, ":")):
                d = {(int(r["H"]), int(r["W"])): r for r in metrics if r["op"] == op and r["arm"] == cond and int(r["mac"]) == mac and r["gate"] == "PASS"}
                if not d:
                    continue
                ys = series(d, "TOTAL")
                xs = [i for i, y in enumerate(ys) if y is not None]
                ax.plot(xs, [y for y in ys if y is not None], color=c, marker=m, linestyle=ls, linewidth=1.4,
                        markersize=4, label="%s %d" % (cond.split("_")[0], mac))
        axis(ax, name, "NPU TOTAL cycles")
    axes[0].legend(fontsize=7)
    fig.suptitle("H3-R: TOTAL cycles by shape, per MAC and TA condition", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(PLOTS, "fig2_cycles_by_shape.png"), dpi=150); plt.close(fig)

    q1 = {(r["op"], (int(r["H"]), int(r["W"]))): r for r in rows("h3_vs_h3r_base.csv")}
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, (op, name) in zip(axes, OPS):
        d = {s: q1.get((op, s), {}) for s in SHAPES}
        plot_series(ax, series(d, "legacy_r_TOTAL"), "tab:gray", "o", "H3 base (per-shape quantisation)", 0, 2)
        plot_series(ax, series(d, "h3r_r_TOTAL"), "tab:blue", "s", "H3-R base (common quantisation)", 1, 2)
        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
        axis(ax, name, "r = C512 / C256 (TOTAL)")
    axes[0].legend(fontsize=8)
    fig.suptitle("Q1: H3 base and H3-R base coincide exactly at every shape (TOTAL; ACTIVE likewise)", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(PLOTS, "fig3_h3_vs_h3r_base.png"), dpi=150); plt.close(fig)

    q3 = {(int(r["H"]), int(r["W"])): r for r in rows("dw_bridge_vs_equalized.csv")}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, metric in zip(axes, ("TOTAL", "ACTIVE")):
        plot_series(ax, series(q3, "legacy_r_%s_relaxed" % metric), "tab:gray", "o", "H3 relaxed (per-shape quantisation)", 0, 3)
        plot_series(ax, series(q3, "h3r_r_%s_bridge_legacy_relaxed" % metric), "tab:green", "^", "bridge (common quantisation, legacy relaxed TA)", 1, 3)
        plot_series(ax, series(q3, "h3r_r_%s_equalized" % metric), "tab:red", "s", "equalized (common quantisation, identical applied TA)", 2, 3)
        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8)
        axis(ax, "3x3 DWConv, %s" % metric, "r = C512 / C256")
    axes[0].legend(fontsize=8)
    fig.suptitle("Q3: DW bridge control -- the three curves coincide exactly at every shape and both metrics", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(PLOTS, "fig4_dw_bridge.png"), dpi=150); plt.close(fig)
    print("wrote", sorted(os.listdir(PLOTS)))


if __name__ == "__main__":
    main()
