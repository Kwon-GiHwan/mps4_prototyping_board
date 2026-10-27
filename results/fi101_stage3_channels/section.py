"""Print the README section of one model from channels.csv / channel_verdicts.csv (read side only; write side is
not interpretable, see README).  python3 section.py <results dir> <model> <boots>"""
import csv, sys, pathlib
D, model, boots = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
ver = {r["model"]: r["verdict"] for r in csv.DictReader(open(D / "channel_verdicts.csv"))}[model]
rows = [r for r in csv.DictReader(open(D / "channels.csv")) if r["model"] == model]
get = lambda ch, e: next((float(r["channel_median"]) for r in rows if r["channel"] == ch and int(r["ev_type"]) == e), None)
unf = lambda e: next(float(r["unfiltered_median"]) for r in rows if int(r["ev_type"]) == e)
pct = lambda v, u: f"{100 * v / u:.1f} %" if u else "—"
print(f"\n## {model} (boots {boots}) — `{ver}`\n")
print("| channel | EXT rd beats | share | SRAM rd beats | share | EXT rd trans | SRAM rd trans |")
print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
print(f"| unfiltered | {unf(386):,.0f} | — | {unf(130):,.0f} | — | {unf(384):,.0f} | {unf(128):,.0f} |")
se = ss = 0
for ch, lab in (("rd_weights", "rd_weights"), ("rd_ifm", "rd_ifm"), ("rd_mem2mem", "rd_mem2mem (DMA)")):
    e, s = get(ch, 386), get(ch, 130)
    se += e; ss += s
    print(f"| {lab} | {e:,.0f} | {pct(e, unf(386))} | {s:,.0f} | {pct(s, unf(130))} | {get(ch, 384):,.0f} | {get(ch, 128):,.0f} |")
print(f"| sum of the three | {se:,.0f} | {pct(se, unf(386))} | {ss:,.0f} | {pct(ss, unf(130))} | | |")
w, wt = get("wr_ofm", 135), get("wr_ofm", 132)
print(f"\nwr_ofm: SRAM wr beats {w:,.0f} (unfiltered {unf(135):,.0f}), SRAM wr trans {wt:,.0f} (unfiltered {unf(132):,.0f}).")
