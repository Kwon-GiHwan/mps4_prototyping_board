#!/usr/bin/env python3
"""Stage 6B-E1-R (evidence/stage6b/stage6be1r/contract.md): the E1 generator and Vela facts with the revised grid only
(OFM 24..40 square, prefix e1r_); facts only, every rule is in host/analysis/stage6be1r.py.

  stage6be1r_models.py grid     <out.json>                 static facts of all 680 grid candidates (Vela only)
  stage6be1r_models.py build    <out dir> <name>...        two independent builds per name (stage6be1_models.build)
  stage6be1r_models.py compiler <out.json>                 Vela version and sha256 of every installed Vela package file
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stage6be1_models as E1M  # noqa: E402

E1M.HWS = tuple((n, n) for n in range(24, 41))
E1M.name_of = lambda cin, h, w, cout: f"e1r_c{cin}_h{h}w{w}_o{cout}"


def compiler(out: str) -> None:
    import ethosu.vela as v
    from importlib.metadata import version
    root = pathlib.Path(v.__file__).resolve().parent
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    digest = hashlib.sha256("".join(f"{k} {h}\n" for k, h in files.items()).encode()).hexdigest()
    pathlib.Path(out).write_text(json.dumps(dict(vela_version=version("ethos-u-vela"), package_root=str(root),
                                                 n_files=len(files), package_digest=digest, files=files), indent=1))
    print(version("ethos-u-vela"), len(files), digest)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "grid":
        E1M.grid(sys.argv[2])
    elif cmd == "build":
        E1M.build(sys.argv[2], sys.argv[3:])
    elif cmd == "compiler":
        compiler(sys.argv[2])
    else:
        raise SystemExit(__doc__)
