# h3r_analyze.py mutation log

analyzer sha256 (unchanged before/after): `4a61390e80050e399cba48eaa5bd9202f13a03afdff3f6aba84111ec0437c5f9`

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
| 14 | applied mask | `(v & TA_MASK[k.split("_", 1)[1]])` | `v` | RED |
| 15 | PRESERVATION | `if changed:` | `if False:` | RED |
| 16 | ratio direction | `r[(model, cond)] = cyc[(model, cond, 512)][key] / float(m[key])` | `r[(model, cond)] = float(m[key]) / cyc[(model, cond, 512)][key]` | RED |
| 17 | SHAPE_EFFECT threshold | `"holds": spread[(op, cond)]["spread"] >= SHAPE_T` | `"holds": spread[(op, cond)]["spread"] > SHAPE_T` | RED |
| 18 | MSI factor | `e["spread"] < MSI_FACTOR * b["spread"]` | `e["spread"] <= MSI_FACTOR * b["spread"]` | RED |
| 19 | TYPE_DEPENDENT threshold | `round(max(ms) - min(ms), 4) >= TYPE_T` | `round(max(ms) - min(ms), 4) > TYPE_T` | RED |
| 20 | METRIC_DEPENDENT label | `elif t["holds"] == a["holds"]:` | `elif True:` | RED |
| 21 | refused arm excluded | `ok.pop((cell, a), None)` | `pass` | RED |

survived: none

note: an earlier `b["spread"] > 0 and` guard in MEMORY_SHAPE_INTERACTION survived as an equivalent mutant (a spread is never negative, so it could not change any outcome); the redundant guard was removed instead of keeping an untestable branch.
