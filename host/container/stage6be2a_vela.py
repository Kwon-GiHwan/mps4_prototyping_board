#!/usr/bin/env python3
"""Stage 6B-E2A (evidence/stage6b/stage6be2a/contract.md §1, §2, §8): Vela facts only, no comparison.

For every target (tflite with its recorded sha256s) and every system-config variant: compile with the packer's MLEK Vela
options (only --system-config differs for a variant), record the Vela output, command stream, constant and IO digests,
the summary CSV row and the debug-DB performance tables (perf_debug, perf_debug_main, perf_debug_wd).
`models` records the seven original MLEK models with the base options (summary only).

  stage6be2a_vela.py targets <targets.json> <out.json>
  stage6be2a_vela.py models <out.json>
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
from pack_vela_workload import MLEK_INI, VELA_OPTIONS, inspect_vela  # noqa: E402
from vela_op_map import tables  # noqa: E402

BASE_SECTION = "Ethos_U85_SYS_DRAM_Mid_1024"
# contract §8: one line changed, x0.5 and x2 of the base value (ints rounded); ports_used only to 1
VARIANTS = [(k, f) for k in ("Dram_clock_scale", "Dram_read_latency", "Dram_write_latency", "Dram_max_reads",
                             "Dram_max_writes", "Dram_burst_length", "Sram_clock_scale", "Sram_read_latency",
                             "Sram_write_latency", "Sram_max_reads", "Sram_max_writes", "Sram_burst_length")
            for f in (0.5, 2.0)] + [("Dram_ports_used", None), ("Sram_ports_used", None)]
DB_TABLES = ("perf", "perf_debug", "perf_debug_main", "perf_debug_wd")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def base_section(ini: str) -> list[str]:
    lines, on = [], False
    for ln in ini.splitlines():
        if ln.startswith("["):
            on = ln.strip() == f"[System_Config.{BASE_SECTION}]"
            continue
        if on and "=" in ln:
            lines.append(ln.strip())
    return lines


def variant_value(key: str, base: str, factor: float | None) -> str:
    if factor is None:
        return "1"
    v = float(base) * factor
    return repr(v) if "clock_scale" in key else str(int(round(v)))


def variant_inis(ini: str) -> dict[str, tuple[str, dict]]:
    """{name: (ini text, change)}; 'base' is the MLEK ini unchanged."""
    sec = base_section(ini)
    assert len(sec) == 17, sec
    kv = dict(ln.split("=", 1) for ln in sec)
    out = {"base": (ini, {})}
    for key, f in VARIANTS:
        new = variant_value(key, kv[key], f)
        name = f"E2A_{key}_{new.replace('.', 'p')}"
        body = [f"{k}={new if k == key else v}" for k, v in kv.items()]
        out[name] = (ini + f"\n[System_Config.{name}]\n" + "\n".join(body) + "\n",
                     dict(parameter=key, base=kv[key], value=new, factor=f))
    return out


def compile_one(tfl: str, ini_text: str, sysname: str, debug: bool) -> dict:
    opts = list(VELA_OPTIONS)
    with tempfile.TemporaryDirectory() as d:
        if sysname != BASE_SECTION:                   # the base compile is the packer's exact call (MLEK ini path)
            ini_p = os.path.join(d, "e2a.ini")
            pathlib.Path(ini_p).write_text(ini_text)
            opts[opts.index("--config") + 1] = ini_p
            opts[opts.index("--system-config") + 1] = sysname
        out_d = os.path.join(d, "out")
        r = subprocess.run(["vela", tfl, *opts, "--output-dir", out_d, *(["--enable-debug-db"] if debug else [])],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return dict(ok=False, why=f"vela rc {r.returncode}", stderr_tail=r.stderr[-800:])
        vt = glob.glob(os.path.join(out_d, "*_vela.tflite"))[0]
        res = dict(ok=True, vela_sha256=sha(open(vt, "rb").read()),
                   summary=next(csv.DictReader(open(glob.glob(os.path.join(out_d, "*_summary_*.csv"))[0]))))
        try:
            info = inspect_vela(vt)
            res.update(cms_sha256=sha(info["cms"]), const_sha256=sha(info["const"]), arena_size=info["arena_size"],
                       fast_size=info["fast_size"], inputs=info["inputs"], outputs=info["outputs"])
        except SystemExit as e:                       # more than one ethos-u op (original models): no digests
            res.update(inspect_error=str(e))
        if debug:
            t = tables(glob.glob(os.path.join(out_d, "*_debug.xml"))[0])
            res["db"] = {k: t.get(k, []) for k in DB_TABLES}
        return res


def cmd_targets(targets_p: str, out_p: str) -> None:
    targets = json.loads(pathlib.Path(targets_p).read_text())
    ini = pathlib.Path(MLEK_INI).read_text()
    inis = variant_inis(ini)
    res = dict(vela_options=list(VELA_OPTIONS), mlek_ini_sha256=sha(ini.encode()), variants={}, targets={})
    for name, (_, change) in inis.items():
        res["variants"][name] = change
    for t in targets:
        src = pathlib.Path(t["tflite"]).read_bytes()
        entry = dict(record=t, model_sha256=sha(src), model_equals_record=sha(src) == t["model_sha256"], by_variant={})
        for name, (text, _) in inis.items():
            entry["by_variant"][name] = compile_one(t["tflite"], text, BASE_SECTION if name == "base" else name, True)
        b = entry["by_variant"]["base"]
        entry["vela_equals_record"] = b.get("vela_sha256") == t["vela_sha256"]
        entry["cms_equals_record"] = b.get("cms_sha256") == t["cms_sha256"]
        res["targets"][t["id"]] = entry
        print(t["id"], entry["model_equals_record"], entry["vela_equals_record"], entry["cms_equals_record"], flush=True)
    pathlib.Path(out_p).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(out_p, sha(pathlib.Path(out_p).read_bytes()))


def cmd_models(out_p: str) -> None:
    from stage6b_models import MLEK, SOURCES
    from stage6m_models import MODELS
    ini = pathlib.Path(MLEK_INI).read_text()
    res = {}
    for m in MODELS:
        src = MLEK / SOURCES[m] / f"{m}.tflite"
        c = compile_one(str(src), ini, BASE_SECTION, False)
        res[m] = dict(model_sha256=sha(src.read_bytes()), vela_sha256=c.get("vela_sha256"), summary=c.get("summary"), ok=c["ok"])
        print(m, c["ok"], flush=True)
    pathlib.Path(out_p).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(out_p, sha(pathlib.Path(out_p).read_bytes()))


if __name__ == "__main__":
    {"targets": lambda: cmd_targets(sys.argv[2], sys.argv[3]), "models": lambda: cmd_models(sys.argv[2])}[sys.argv[1]]()
