#!/usr/bin/env python3
"""Generate the manuscript figures from frozen derived data.

Phase-2 action 7 (`EXISTING_DATA_ONLY`). Every value plotted is read from a
frozen CSV; no transformation is applied that the frozen analysis does not
already define, and no new metric is introduced. There is no spreadsheet step —
this script is the provenance record, and it re-derives each figure from source
on every run.

Output is SVG written by hand rather than through a plotting library: no new
dependency, deterministic byte-for-byte output, and every number in the figure
is greppable in the file.

    python3 docs/paper/figures/make_figures.py        # writes docs/paper/figures/*.svg

Refusals encoded here, not left to the caller:
  - no figure places raw cycles from two platforms on one axis;
  - no figure plots FVP-versus-board error, ratio or accuracy;
  - no figure labels an operation as the cause of the whole-model change.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)

# ---- palette (colour-blind safe, prints legibly in greyscale) -------------
INK, MUTE, GRID = "#1a1a1a", "#6b6b6b", "#d8d8d8"
SER = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#8c564b"]
NEGC, POSC, SAMEC = "#0072b2", "#d55e00", "#9a9a9a"
FONT = ("font-family=\"Helvetica,Arial,sans-serif\"")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class SVG:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=11, anchor="start", fill=INK, weight="normal"):
        self.add('<text x="%.1f" y="%.1f" %s font-size="%s" font-weight="%s" '
                 'text-anchor="%s" fill="%s">%s</text>'
                 % (x, y, FONT, size, weight, anchor, fill, esc(s)))

    def para(self, x, y, s_, size=10, width=None, fill=MUTE, leading=16):
        """Wrap a caption to the canvas width; returns the y after the block."""
        width = width or (self.w - x - 40)
        words, line, out = s_.split(), "", []
        for wd in words:
            trial = (line + " " + wd).strip()
            if len(trial) * size * 0.55 > width and line:
                out.append(line); line = wd
            else:
                line = trial
        if line:
            out.append(line)
        for i, ln in enumerate(out):
            self.text(x, y + i * leading, ln, size=size, fill=fill)
        return y + len(out) * leading

    def line(self, x1, y1, x2, y2, stroke=GRID, w=1, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                 'stroke-width="%s"%s/>' % (x1, y1, x2, y2, stroke, w, d))

    def rect(self, x, y, w, h, fill, op=1.0):
        self.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" '
                 'opacity="%s"/>' % (x, y, max(w, 0), max(h, 0), fill, op))

    def path(self, pts, stroke, w=1.8):
        d = " ".join(("M" if i == 0 else "L") + "%.1f %.1f" % p
                     for i, p in enumerate(pts))
        self.add('<path d="%s" fill="none" stroke="%s" stroke-width="%s" '
                 'stroke-linejoin="round"/>' % (d, stroke, w))

    def dot(self, x, y, r, fill):
        self.add('<circle cx="%.1f" cy="%.1f" r="%s" fill="%s"/>' % (x, y, r, fill))

    def save(self, path):
        body = "\n".join(self.parts)
        out = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
               'viewBox="0 0 %d %d"><rect width="%d" height="%d" fill="#ffffff"/>\n'
               '%s\n</svg>\n' % (self.w, self.h, self.w, self.h, self.w, self.h, body))
        with open(path, "w") as fh:
            fh.write(out)
        return path


def rd(rel):
    with open(os.path.join(PAPER, rel)) as fh:
        return list(csv.DictReader(fh))


SHORT = {"rnnoise_INT8": "rnnoise", "kws_micronet_m": "kws_micronet",
         "ad_medium_int8": "ad_medium", "vww4_128_128_INT8": "vww4",
         "yolo-fastest_192_face_v4": "yolo-fastest",
         "mobilenet_v2_1.0_224_INT8": "mobilenet_v2",
         "wav2letter_pruned_int8": "wav2letter"}

PROV = []


def prov(**kw):
    PROV.append(kw)


# =========================================================================
# Figure 1 — MAC scaling, separated panels, normalized within each panel
# =========================================================================
def fig_scaling():
    rows = [r for r in rd("analysis/scaling.csv") if r["status"] == "EXECUTABLE"]
    panels = [("SSE-300", "ethos-u55"), ("SSE-300", "ethos-u65"),
              ("SSE-320", "ethos-u85")]
    panels = [p for p in panels if any((r["platform"], r["npu"]) == p for r in rows)]
    pw, ph, pad, top = 250, 210, 62, 66
    s = SVG(pad + len(panels) * pw + 150, top + ph + 96)
    s.text(pad - 44, 26, "Cumulative scaling efficiency within each platform / NPU",
           size=14, weight="bold")
    s.text(pad - 44, 45,
           "Each panel is normalized to its own MAC baseline. Panels share no "
           "absolute axis and must not be read across.", size=10.5, fill=MUTE)
    wls = sorted({r["workload"] for r in rows})
    colour = {w: SER[i % len(SER)] for i, w in enumerate(wls)}
    for pi, (plat, npu) in enumerate(panels):
        x0 = pad + pi * pw
        sub = [r for r in rows if r["platform"] == plat and r["npu"] == npu]
        macs = sorted({int(r["mac"]) for r in sub})
        s.text(x0, top - 12, "%s / %s" % (plat, npu.replace("ethos-", "Ethos-")),
               size=11.5, weight="bold")
        for gy in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = top + ph - gy * ph
            s.line(x0, y, x0 + pw - 34, y, GRID if gy else MUTE)
            if pi == 0:
                s.text(x0 - 8, y + 3.5, "%.2f" % gy, size=9.5, anchor="end", fill=MUTE)
        s.line(x0, top + ph - 0.75 * ph, x0 + pw - 34, top + ph - 0.75 * ph,
               MUTE, 1, "3,3")
        xs = {mm: x0 + (pw - 46) * (i / max(len(macs) - 1, 1))
              for i, mm in enumerate(macs)}
        for mm in macs:
            s.text(xs[mm], top + ph + 16, str(mm), size=9.5, anchor="middle", fill=MUTE)
        s.text(x0 + (pw - 46) / 2, top + ph + 34, "MAC configuration",
               size=10, anchor="middle", fill=MUTE)
        for w in sorted({r["workload"] for r in sub}):
            pts = [(xs[int(r["mac"])],
                    top + ph - min(float(r["cumulative_efficiency"]), 1.15) * ph)
                   for r in sorted(sub, key=lambda r: int(r["mac"]))
                   if r["workload"] == w]
            if len(pts) < 2:
                continue
            s.path(pts, colour[w])
            for p in pts:
                s.dot(p[0], p[1], 2.4, colour[w])
    lx = pad + len(panels) * pw + 4
    s.text(lx, top - 12, "workload", size=10.5, weight="bold")
    for i, w in enumerate(wls):
        y = top + 6 + i * 17
        s.line(lx, y - 4, lx + 16, y - 4, colour[w], 2.6)
        s.text(lx + 21, y, SHORT.get(w, w), size=10)
    s.text(pad - 44, top + ph + 62,
           "Dashed line: the frozen 0.75 STRONG threshold. Only "
           "timing-adapter-enabled platforms appear.", size=10, fill=MUTE)
    s.text(pad - 44, top + ph + 78,
           "Cumulative efficiency = (cycles(baseline)/cycles(M)) / "
           "(M/baseline MAC); 1.0 is ideal proportional scaling.",
           size=10, fill=MUTE)
    prov(figure="fig1_mac_scaling", source_tag="paper-fvp-analysis-results-frozen",
         source="docs/paper/analysis/scaling.csv",
         columns="platform, npu, workload, mac, status, cumulative_efficiency",
         transformation="filter status==EXECUTABLE; plot the frozen "
                        "cumulative_efficiency column as-is, one panel per "
                        "(platform, NPU); no recomputation",
         metric="cumulative efficiency, frozen definition "
                "(cycles(baseline)/cycles(M))/(M/baseline)",
         claim="scaling is workload-dependent and mostly sub-proportional "
               "within each platform (Section 4.1)",
         forbidden="reading values across panels as a cross-generation "
                   "performance comparison; panels share no absolute axis")
    return s.save(os.path.join(HERE, "fig1_mac_scaling.svg"))


# =========================================================================
# Figure 2 — U85 256->512, rnnoise: where the +19,060 cycles come from
# =========================================================================
def fig_mechanism():
    rows = [r for r in rd("mechanism/U85_GROUP_DIFFERENTIAL.csv")
            if r["workload"] == "rnnoise_INT8" and r["binding_pair"] == "B-frozen"]
    rows.sort(key=lambda r: int(r["delta"]))
    total = sum(int(r["delta"]) for r in rows)
    bh, gap, top, lab = 17, 7, 96, 250
    s = SVG(940, top + len(rows) * (bh + gap) + 132)
    s.text(40, 26, "Ethos-U85 256 → 512 MACs: per-operation-group cycle "
                   "change for rnnoise", size=14, weight="bold")
    s.text(40, 45, "Ten groups regress, one improves, three are unchanged; the "
                   "whole-model change is +%s cycles." % format(total, ","),
           size=10.5, fill=MUTE)
    s.text(40, 62, "No single group accounts for the reversal — the largest "
                   "is about a fifth of it.", size=10.5, fill=MUTE)
    mx = max(abs(int(r["delta"])) for r in rows) or 1
    zero, half = lab + 250, 250.0
    s.line(zero, top - 10, zero, top + len(rows) * (bh + gap) - gap + 4, MUTE)
    for r in rows:
        i = rows.index(r)
        y = top + i * (bh + gap)
        d = int(r["delta"])
        w = abs(d) / mx * half
        c = {"REGRESS": POSC, "IMPROVE": NEGC}.get(r["direction"], SAMEC)
        s.rect(zero if d >= 0 else zero - w, y, w, bh, c, 0.92)
        types = r["member_types"].replace(" ", "/")
        s.text(lab - 8, y + bh - 4.5,
               "%s  (%s op%s)" % (types[:34], r["n_ops"],
                                  "" if r["n_ops"] == "1" else "s"),
               size=10, anchor="end")
        s.text(zero + (w + 8 if d >= 0 else -w - 8), y + bh - 4.5,
               "%+d" % d, size=10, anchor="start" if d >= 0 else "end", fill=MUTE)
    ly = top + len(rows) * (bh + gap) + 22
    for i, (c, t) in enumerate(((POSC, "regress (slower at 512)"),
                                (NEGC, "improve (faster at 512)"),
                                (SAMEC, "unchanged"))):
        s.rect(lab - 8 + i * 210, ly, 13, 11, c)
        s.text(lab + 10 + i * 210, ly + 10, t, size=10)
    s.para(40, ly + 40,
           "Groups are the frozen common attribution partition: where small "
           "operations merge into one interrupt-service window, only the group "
           "effect is evaluable, not per-operation cause. Bars show where cycles "
           "moved, not why \u2014 no group is claimed as the cause of the "
           "whole-model reversal.")
    prov(figure="fig2_u85_group_delta", source_tag="paper-u85-mechanism-derived-frozen",
         source="docs/paper/mechanism/U85_GROUP_DIFFERENTIAL.csv",
         columns="workload, binding_pair, n_ops, member_types, delta, direction",
         transformation="filter workload==rnnoise_INT8 and binding_pair==B-frozen "
                        "(14 groups); sort by frozen delta; plot delta as-is",
         metric="per-group cycle delta, 512 minus 256, frozen",
         claim="the reversal is distributed across operation groups "
               "(Section 6.3 / 7.3)",
         forbidden="reading any single bar as the cause of the whole-model "
                   "regression; per-operation attribution inside a merged group")
    return s.save(os.path.join(HERE, "fig2_u85_group_delta.svg"))


# =========================================================================
# Figure 3 — the same groups recur under every tested memory configuration
# =========================================================================
def fig_memory():
    rows = [r for r in rd("mechanism/U85_P1B_CROSSMODE_GROUPS.csv")
            if r["workload"] == "rnnoise_INT8"]
    modes = [("SO", "Sram_Only"), ("SH", "Shared_Sram"), ("DS", "Dedicated_Sram")]
    moving = [r for r in rows if any(int(r[k + "_delta"]) for k, _ in modes)]
    moving.sort(key=lambda r: -int(r["DS_delta"]))
    consistent = sum(1 for r in rows
                     if len({r["SO_dir"], r["SH_dir"], r["DS_dir"]}) == 1)
    gh, gap, top, lab = 15, 26, 104, 268
    s = SVG(940, top + len(moving) * (3 * gh + gap) + 116)
    s.text(40, 26, "rnnoise under three memory configurations: the same groups "
                   "regress every time", size=14, weight="bold")
    s.text(40, 45, "Whole-model totals: Sram_Only +%s, Shared_Sram +%s, "
                   "Dedicated_Sram +%s cycles."
           % tuple(format(sum(int(r[k + "_delta"]) for r in rows), ",")
                   for k, _ in modes), size=10.5, fill=MUTE)
    s.text(40, 62, "%d of %d groups keep the same direction in all three modes; "
                   "no group flips between improvement and regression."
           % (consistent, len(rows)), size=10.5, fill=MUTE)
    mx = max(abs(int(r[k + "_delta"])) for r in moving for k, _ in modes) or 1
    zero, half = lab + 270, 270.0
    for gi, r in enumerate(moving):
        y0 = top + gi * (3 * gh + gap)
        types = r["member_types"].replace(" ", "/")
        s.text(lab - 10, y0 + gh + 4,
               "%s (%s ops)" % (types[:30], r["n_ops"]), size=10, anchor="end")
        for mi, (k, name) in enumerate(modes):
            y = y0 + mi * gh
            d = int(r[k + "_delta"])
            w = abs(d) / mx * half
            c = POSC if d > 0 else (NEGC if d < 0 else SAMEC)
            s.rect(zero if d >= 0 else zero - w, y + 2, w, gh - 4, c,
                   0.55 + 0.2 * mi)
            s.text(zero + w + 8 if d >= 0 else zero - w - 8, y + gh - 3.5,
                   "%s %+d" % (name, d), size=9,
                   anchor="start" if d >= 0 else "end", fill=MUTE)
        s.line(zero, y0, zero, y0 + 3 * gh, MUTE)
    ly = top + len(moving) * (3 * gh + gap) + 12
    s.para(40, ly + 12,
           "Bar shade darkens from Sram_Only to Dedicated_Sram. Only groups that "
           "move in at least one configuration are drawn. Every memory mode "
           "compiles to a different artifact, so memory-system behaviour and "
           "compiler-generated program change remain NOT_SEPARATED: this is a "
           "configuration intervention, not a bandwidth intervention.")
    prov(figure="fig3_u85_memory_robustness", source_tag="paper-u85-p1b-frozen",
         source="docs/paper/mechanism/U85_P1B_CROSSMODE_GROUPS.csv",
         columns="workload, n_ops, member_types, SO_delta, SH_delta, DS_delta, "
                 "SO_dir, SH_dir, DS_dir",
         transformation="filter workload==rnnoise_INT8; drop groups whose delta "
                        "is zero in all three modes; sort by frozen DS_delta; "
                        "plot the frozen deltas as-is",
         metric="per-group cycle delta, 512 minus 256, per memory configuration",
         claim="direction is invariant across tested memory configurations while "
               "magnitude is not (Section 6.4 / 7.4)",
         forbidden="attributing the modulation to memory bandwidth; the modes "
                   "are different artifacts")
    return s.save(os.path.join(HERE, "fig3_u85_memory_robustness.svg"))


# =========================================================================
# Figure 4 — board: independently normalized relative cost, never an error plot
# =========================================================================
def fig_board():
    rows = rd("analysis/board_rq3/normalized_relative_cost.csv")
    rank = rd("analysis/board_rq3/fvp_board_ranking.csv")
    order = sorted(rows, key=lambda r: float(r["fvp_normalized_cost"]))
    bh, gap, top, lab = 15, 24, 104, 178
    s = SVG(900, top + len(order) * (2 * bh + gap) + 128)
    s.text(40, 26, "Simulated and physical relative workload cost, each "
                   "normalized within its own domain", size=14, weight="bold")
    s.text(40, 45, "Ranking is preserved exactly: Spearman rho = 1.0, zero rank "
                   "inversions across all seven workloads.", size=10.5, fill=MUTE)
    s.text(40, 62, "Each domain is divided by its own geometric mean, so the two "
                   "bars are shapes to compare, not magnitudes.", size=10.5,
           fill=MUTE)
    mx = max(float(r["board_normalized_cost"]) for r in order)
    span = 560.0
    for i, r in enumerate(order):
        y0 = top + i * (2 * bh + gap)
        s.text(lab - 10, y0 + bh + 2, SHORT.get(r["workload"], r["workload"]),
               size=10.5, anchor="end")
        for j, (k, name, c) in enumerate((("fvp_normalized_cost", "FVP", SER[0]),
                                          ("board_normalized_cost", "board", SER[1]))):
            v = float(r[k])
            s.rect(lab, y0 + j * bh + 2, v / mx * span, bh - 4, c, 0.9)
            s.text(lab + v / mx * span + 7, y0 + j * bh + bh - 4.5,
                   "%s %.4f" % (name, v), size=9, fill=MUTE)
    ly = top + len(order) * (2 * bh + gap)
    yy = s.para(40, ly + 16,
                "No aggregate deviation statistic is shown: L1, L2, RMSE, MAPE "
                "and the board/FVP ratio were never preregistered, and choosing "
                "one with both vectors visible would be selecting a statistic to "
                "fit the result. Absolute simulation-versus-hardware comparison "
                "is refused by construction: the two builds are target-specific.")
    s.para(40, yy + 6, "One physical configuration only \u2014 Corstone-320 / "
                       "Ethos-U85 @ 1024 MACs, 21 formal samples.")
    prov(figure="fig4_board_relative_cost",
         source_tag="paper-board-rq3-analysis-results-frozen",
         source="docs/paper/analysis/board_rq3/normalized_relative_cost.csv "
                "(+ fvp_board_ranking.csv for the ordering claim)",
         columns="workload, fvp_normalized_cost, board_normalized_cost",
         transformation="sort by the frozen fvp_normalized_cost; plot both frozen "
                        "columns as-is. No ratio, difference or error is computed",
         metric="geometric-mean-normalized relative cost, computed within each "
                "domain separately (frozen)",
         claim="ordinal structure and relative cost shape transfer to the one "
               "measurable hardware configuration (Section 6 / 7.2)",
         forbidden="any error, accuracy, ratio or deviation reading between the "
                   "two bars; absolute cycle comparison",
         cross_check="row count and ranking cross-checked against "
                     "fvp_board_ranking.csv: %d workloads, %d inversions"
                     % (len(rank), sum(1 for r in rank
                                       if r.get("fvp_rank") != r.get("board_rank"))))
    return s.save(os.path.join(HERE, "fig4_board_relative_cost.svg"))


# =========================================================================
# Figure 5 — which structural metrics survived a platform change
# =========================================================================
def fig_platform():
    rows = rd("platform_sensitivity/X3_METRIC_QUALIFICATION.csv")
    metrics = ["workload_ranking", "mac_step_direction", "saturation_verdict",
               "normalized_workload_ordering", "scaling_class"]
    pretty = {"workload_ranking": "workload ranking",
              "mac_step_direction": "MAC-step direction",
              "saturation_verdict": "saturation verdict",
              "normalized_workload_ordering": "normalized workload ordering",
              "scaling_class": "threshold scaling class"}
    by = {}
    for r in rows:
        if r["metric"] in metrics and r["class"] in ("A", "B"):
            by[(r["metric"], r["class"])] = r
    top, lab, rowh, barw = 108, 232, 44, 200
    s = SVG(900, top + len(metrics) * rowh + 168)
    s.text(40, 26, "Which structural metrics survived a change of Corstone "
                   "platform", size=14, weight="bold")
    s.text(40, 45, "Same NPU, same MAC configuration, byte-identical Vela "
                   "artifact; only the host platform changes.", size=10.5, fill=MUTE)
    s.text(40, 62, "CLASS A holds timing-adapter state constant (SSE-310 ↔ "
                   "SSE-315). CLASS B does not. The classes are never pooled.",
           size=10.5, fill=MUTE)
    for ci, (cls, cx) in enumerate((("A", lab), ("B", lab + barw + 118))):
        s.text(cx, top - 14, "CLASS %s  (%s)" % (cls, "TA state constant" if cls == "A"
                                                 else "TA state differs"),
               size=10.5, weight="bold")
    for mi, met in enumerate(metrics):
        y = top + mi * rowh
        s.text(lab - 12, y + 15, pretty[met], size=10.5, anchor="end")
        for ci, (cls, cx) in enumerate((("A", lab), ("B", lab + barw + 118))):
            r = by.get((met, cls))
            if not r:
                continue
            tot = int(r["tested_universe"]); ag = int(r["agreement"])
            dis = int(r["disagreement"])
            w = barw * (ag / tot) if tot else 0
            s.rect(cx, y, w, 17, SER[2] if not dis else SER[2], 0.85)
            if dis:
                s.rect(cx + w, y, barw * (dis / tot), 17, SER[1], 0.9)
            s.text(cx + barw + 10, y + 13, "%d/%d" % (ag, tot), size=10, fill=MUTE)
            s.text(cx, y + 31, r["qualification"].replace("_", " ").lower(),
                   size=9, fill=MUTE)
    ly = top + len(metrics) * rowh + 10
    for i, (c, t) in enumerate(((SER[2], "agreed across the platform pair"),
                                (SER[1], "disagreed"))):
        s.rect(lab - 12 + i * 250, ly, 13, 11, c, 0.88)
        s.text(lab + 6 + i * 250, ly + 10, t, size=10)
    yy = s.para(40, ly + 36,
                "The only disagreements are eight threshold scaling-class labels, "
                "all in CLASS B, every one PARTIAL on the TA_ON side and STRONG "
                "on the TA_OFF side \u2014 crossings of the frozen 0.75 cut "
                "point. No ranking, direction or saturation verdict changed "
                "anywhere.")
    s.para(40, yy + 6,
           "In CLASS B the timing-adapter state, the subsystem and the Fast "
           "Models implementation change together: the disagreements are "
           "ASSOCIATED_WITH those comparisons, never attributed to one factor.")
    prov(figure="fig5_platform_sensitivity",
         source_tag="paper-platform-sensitivity-x3-results-frozen",
         source="docs/paper/platform_sensitivity/X3_METRIC_QUALIFICATION.csv",
         columns="metric, class, tested_universe, agreement, disagreement, "
                 "qualification",
         transformation="plot the frozen agreement/tested_universe counts per "
                        "metric per class; classes drawn separately and never "
                        "pooled into one rate",
         metric="agreement counts under the frozen X1 comparison universe",
         claim="ordinal and directional metrics were robust across the tested "
               "pairs; thresholded classes were TA-state sensitive "
               "(Section 5 / 7.5)",
         forbidden="pooling CLASS A with CLASS B; reading the bars as a "
                   "platform-performance ranking; any raw-cycle comparison")
    return s.save(os.path.join(HERE, "fig5_platform_sensitivity.svg"))


def main():
    made = [fig_scaling(), fig_mechanism(), fig_memory(), fig_board(),
            fig_platform()]
    with open(os.path.join(HERE, "FIGURE_PROVENANCE.json"), "w") as fh:
        json.dump({"generated_by": "docs/paper/figures/make_figures.py",
                   "class": "EXISTING_DATA_ONLY",
                   "rule": "no metric, threshold or transformation is introduced "
                           "here that the frozen analysis does not already define",
                   "figures": PROV}, fh, indent=1)
    for p in made:
        print("wrote", os.path.relpath(p, PAPER))
    print("wrote FIGURE_PROVENANCE.json (%d records)" % len(PROV))
    return 0


if __name__ == "__main__":
    sys.exit(main())
