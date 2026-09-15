# h3r_analyze.py mutation log

analyzer sha256 (unchanged before/after): `42b580eae5ce564872c4e0747b719d6cbd897669394cfb54692ee9a4e8697feb`

| # | mutation | original | mutated | suite |
|---|---|---|---|---|
| 1 | RUN status | `any(r["status"] != "SUCCESS" for r in a["runs"])` | `False` | RED |
| 2 | RUN missing counter | `if missing:` | `if False:` | RED |
| 3 | REPS differ | `if len({vec(r["measurement"]) for r in a["runs"]}) != 1:` | `if False:` | RED |
| 4 | TA header | `if not a["header_ok"] or any(a["header"].get(k) != req.get(k) for k in TA_KEYS):` | `if False:` | RED |
| 5 | TA cache | `if not a["cache"] or any(a["cache"].get(k) != req.get(k) for k in TA_KEYS):` | `if False:` | RED |
| 6 | TA cache presence | `if not a["cache"] or any` | `if a["cache"] and any` | RED |
| 7 | ARTIFACT identity | `if len(shas) > 1:` | `if False:` | RED |
| 8 | G1PRIME flag | `if m is None or m.get("g1prime_pass") is not True:` | `if m is None:` | RED |
| 9 | OUTPUT no verify | `if v.get("status") == "SUCCESS" and v.get("dump_sha256"):` | `if True:` | RED |
| 10 | OUTPUT incomplete | `if bad:` | `if False:` | RED |
| 11 | OUTPUT differ | `if len({str(d) for d in dumps.values()}) > 1:` | `if False:` | RED |
| 12 | OUTPUT bytes vs digest | `return data\n` | `return v["dump_sha256"]\n` | RED |
| 13 | EQUALIZED applied across MACs | `if len(eq) == 2 and eq[256] != eq[512]:` | `if False:` | RED |
| 14 | EQUALIZED compares all header fields | `applied_all(g[(c, a)]["header"])` | `applied(g[(c, a)]["header"])` | RED |
| 15 | applied_all mask | `(v & TA_MASK[suffix]) if suffix in TA_MASK else v` | `v` | RED |
| 16 | applied mask | `(v & TA_MASK[k.split("_", 1)[1]])` | `v` | RED |
| 17 | PRESERVATION | `if changed:` | `if False:` | RED |
| 18 | ratio direction | `r[(model, cond)] = cyc[(model, cond, 512)][key] / float(m[key])` | `r[(model, cond)] = float(m[key]) / cyc[(model, cond, 512)][key]` | RED |
| 19 | SHAPE_EFFECT threshold | `"holds": spread[(op, cond)]["spread"] >= SHAPE_T` | `"holds": spread[(op, cond)]["spread"] > SHAPE_T` | RED |
| 20 | MSI factor | `e["spread"] < MSI_FACTOR * b["spread"]` | `e["spread"] <= MSI_FACTOR * b["spread"]` | RED |
| 21 | TYPE_DEPENDENT threshold | `round(max(ms) - min(ms), 4) >= TYPE_T` | `round(max(ms) - min(ms), 4) > TYPE_T` | RED |
| 22 | METRIC_DEPENDENT label | `elif t["holds"] == a["holds"]:` | `elif True:` | RED |
| 23 | refused arm excluded | `ok.pop((cell, a), None)` | `pass` | RED |

survived: none

note: an earlier `b["spread"] > 0 and` guard in MEMORY_SHAPE_INTERACTION survived as an equivalent mutant (a spread is never negative, so it could not change any outcome); the redundant guard was removed instead of keeping an untestable branch.
