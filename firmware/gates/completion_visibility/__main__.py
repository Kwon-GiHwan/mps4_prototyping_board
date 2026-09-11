"""Run the development checker with an explicit successor identity in its output."""

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from firmware.gates.completion_visibility.cli import main
else:
    from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
