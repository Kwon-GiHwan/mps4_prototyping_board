# Historical host code

`bringup/` contains the former `host/bringup/` scripts, preserved byte for byte.
They capture one board’s historical serial ports, paths and manual recovery
procedures. They are not campaign backends and must not be imported or batch-run.
Some require `PYTHONPATH=host`, as before the move.

`patches/` contains the already archived one-off source rewriting scripts.

Historical documents and `environment/host/serial-bindings.yaml` intentionally
retain the original paths: translate `host/bringup/X` to
`host/legacy/bringup/X` when locating that snapshot today. Their recorded line
numbers and script bytes are unchanged.

The maintained MLEK matrix entry point is `python3 -m host.campaigns`.
`host/experiments/` and the root PMU/protocol tools are diagnostic/reference
paths with live dependencies and frozen qualification contracts. V15 is a
specific S5 boundary diagnostic, not a replacement for the stock MLEK runner.
Those paths are retained until their consumers and qualification evidence can
be migrated; a smaller version number alone does not make code unused.

Frozen experimental scripts within `docs/`, `evidence/` and `provenance/`, and
the build container snapshot under `environment/build/archive/`, remain
historical reproduction inputs. The campaign runtime does not import them.
