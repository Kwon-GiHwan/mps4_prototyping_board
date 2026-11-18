#!/usr/bin/env python3
"""Stage 6G-X_LAT Phase 2 (docs/plan/stage6g_xlat_directive_chatgpt.txt §4): Vela 5.0.0 per-layer costs of the original
kws/ad MLEK models at Dram_read_latency 250 / 500 / 1000, everything else = MLEK options and ini.

Each latency is a copy of [System_Config.Ethos_U85_SYS_DRAM_Mid_1024] with one line changed (500 = unchanged copy), plus
the packer's exact base compile for reference. Kept per compile: vela tflite sha256, command stream sha256, summary row,
per-layer CSV (--verbose-performance writes it into the output dir).

  xlat_vela.py <out dir (new)>
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[0] / "lib"))
from pack_vela_workload import MLEK_INI, VELA_OPTIONS, inspect_vela  # noqa: E402

RES = "/opt/arm/ml-embedded-evaluation-kit/resources_downloaded"
MODELS = {"kws_micronet_m": f"{RES}/kws/kws_micronet_m.tflite", "ad_medium_int8": f"{RES}/ad/ad_medium_int8.tflite"}
BASE = "Ethos_U85_SYS_DRAM_Mid_1024"
LATENCIES = (250, 500, 1000)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def section(ini: str) -> list[str]:
    lines, on = [], False
    for ln in ini.splitlines():
        if ln.startswith("["):
            on = ln.strip() == f"[System_Config.{BASE}]"
            continue
        if on and "=" in ln:
            lines.append(ln.strip())
    return lines


def ini_for(ini: str, lat: int) -> tuple[str, str]:
    kv = dict(ln.split("=", 1) for ln in section(ini))
    if kv.get("Dram_read_latency") != "500":
        raise SystemExit(f"unexpected base Dram_read_latency {kv.get('Dram_read_latency')}")
    name = f"XLAT_Dram_read_latency_{lat}"
    body = [f"{k}={lat if k == 'Dram_read_latency' else v}" for k, v in kv.items()]
    return ini + f"\n[System_Config.{name}]\n" + "\n".join(body) + "\n", name


def compile_one(tfl: str, ini_text: str | None, sysname: str, keep: pathlib.Path) -> dict:
    opts = list(VELA_OPTIONS)
    with tempfile.TemporaryDirectory() as d:
        if ini_text is not None:
            p = os.path.join(d, "xlat.ini")
            pathlib.Path(p).write_text(ini_text)
            opts[opts.index("--config") + 1] = p
            opts[opts.index("--system-config") + 1] = sysname
        out = os.path.join(d, "out")
        r = subprocess.run(["vela", tfl, *opts, "--verbose-performance", "--output-dir", out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"vela rc {r.returncode}: {r.stderr[-800:]}")
        keep.mkdir(parents=True)
        for f in glob.glob(os.path.join(out, "*")):
            shutil.copy(f, keep)
        (keep / "stdout.txt").write_text(r.stdout)
        vt = glob.glob(os.path.join(out, "*_vela.tflite"))[0]
        info = inspect_vela(vt)
        return dict(vela_sha256=sha(open(vt, "rb").read()), cms_sha256=sha(info["cms"]), const_sha256=sha(info["const"]),
                    per_layer=os.path.basename(glob.glob(os.path.join(out, "*_per-layer.csv"))[0]),
                    summary=os.path.basename(glob.glob(os.path.join(out, "*_summary_*.csv"))[0]))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = pathlib.Path(argv[1])
    if out.exists():
        raise SystemExit(f"{out} exists")
    ini = pathlib.Path(MLEK_INI).read_text()
    res = dict(vela_options=VELA_OPTIONS, mlek_ini_sha256=sha(ini.encode()),
               vela_version=subprocess.run(["vela", "--version"], capture_output=True, text=True).stdout.strip(),
               models={})
    for m, tfl in MODELS.items():
        e = dict(tflite=tfl, tflite_sha256=sha(pathlib.Path(tfl).read_bytes()),
                 base=compile_one(tfl, None, BASE, out / m / "base"))
        for lat in LATENCIES:
            text, name = ini_for(ini, lat)
            e[f"L{lat}"] = dict(system_config=name, **compile_one(tfl, text, name, out / m / f"L{lat}"))
        res["models"][m] = e
        print(m, {k: v["vela_sha256"][:8] for k, v in e.items() if isinstance(v, dict)}, flush=True)
    (out / "xlat_vela.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
