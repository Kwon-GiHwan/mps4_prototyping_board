# h3r_analyze.py mutation log

analyzer sha256 (unchanged before/after): `98456064f86ff0d796425c6e766bfc35a21a0cfe479be3d49b01d89f83605f03`

| # | mutation | original | mutated | suite |
|---|---|---|---|---|
| 1 | RUN status | `any(r["status"] != "SUCCESS" for r in a["runs"])` | `False` | RED |
| 2 | RUN missing counter | `if missing:` | `if False:` | RED |
| 3 | REPS differ | `if len({vec(r["measurement"]) for r in a["runs"]}) != 1:` | `if False:` | RED |
| 4 | TA header | `if not a["header_ok"] or any(a["header"].get(k) != req.get(k) for k in TA_KEYS):` | `if False:` | RED |
| 5 | TA cache | `if a["cache"] is not None and any(a["cache"].get(k) != req.get(k) for k in TA_KEYS):` | `if False:` | RED |
| 6 | ARTIFACT identity | `if len(shas) > 1:` | `if False:` | RED |
| 7 | G1PRIME flag | `if m is None or m.get("g1prime_pass") is not True:` | `if m is None:` | RED |
| 8 | OUTPUT no verify | `if v.get("status") == "SUCCESS" and v.get("dump_sha256"):` | `if True:` | RED |
| 9 | OUTPUT incomplete | `if bad:` | `if False:` | RED |
| 10 | OUTPUT differ | `if len({str(d) for d in dumps.values()}) > 1:` | `if False:` | RED |
| 11 | OUTPUT bytes vs digest | `return data\n` | `return v["dump_sha256"]\n` | RED |
| 12 | EQUALIZED applied across MACs | `if len(eq) == 2 and eq[256] != eq[512]:` | `if False:` | RED |
| 13 | applied mask | `(v & TA_MASK[k.split("_", 1)[1]])` | `v` | RED |
| 14 | PRESERVATION | `if changed:` | `if False:` | RED |
| 15 | ratio direction | `r[(model, cond)] = cyc[(model, cond, 512)][key] / float(m[key])` | `r[(model, cond)] = float(m[key]) / cyc[(model, cond, 512)][key]` | RED |
| 16 | SHAPE_EFFECT threshold | `"holds": spread[(op, cond)]["spread"] >= SHAPE_T` | `"holds": spread[(op, cond)]["spread"] > SHAPE_T` | RED |
| 17 | MSI factor | `e["spread"] < MSI_FACTOR * b["spread"]` | `e["spread"] <= MSI_FACTOR * b["spread"]` | RED |
| 18 | TYPE_DEPENDENT threshold | `round(max(ms) - min(ms), 4) >= TYPE_T` | `round(max(ms) - min(ms), 4) > TYPE_T` | RED |
| 19 | METRIC_DEPENDENT label | `elif t["holds"] == a["holds"]:` | `elif True:` | RED |
| 20 | refused arm excluded | `ok.pop((cell, a), None)` | `pass` | RED |

survived: none

note: an earlier `b["spread"] > 0 and` guard in MEMORY_SHAPE_INTERACTION survived as an equivalent mutant (a spread is never negative, so it could not change any outcome); the redundant guard was removed instead of keeping an untestable branch.
