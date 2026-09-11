"""Plan and execute exhaustive MLEK campaigns from an explicit JSON config."""
import argparse
import json
from pathlib import Path
import sys

from .config import load_config, make_plan
from .errors import CellFailure
from .runner import run_campaign


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="expand every model/target/variant/MAC without executing")
    plan.add_argument("config", type=Path)
    plan.add_argument("--output", "-o", type=Path, help="new JSON file; default is stdout")
    run = commands.add_parser("run", help="execute cells and retain all success/failure records")
    run.add_argument("config", type=Path)
    run.add_argument("--output", "-o", type=Path, required=True, help="new campaign directory")
    run.add_argument("--resume", action="store_true", help="resume identical saved campaign without retrying terminal cells")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "plan":
            text = json.dumps(make_plan(config), indent=2, sort_keys=True, allow_nan=False) + "\n"
            if args.output is None:
                sys.stdout.write(text)
            else:
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(text)
            return 0
        result = run_campaign(config, args.output, resume=args.resume)
        print(json.dumps({"plan_id": result["plan_id"], "summary": result.get("summary", {}),
                          "results": str(args.output.resolve() / "results.json")}, sort_keys=True))
        return 0 if result["cells"] and all(cell["status"] == "SUCCESS" for cell in result["cells"]) else 1
    except KeyboardInterrupt:
        print("Campaign interrupted; inspect saved results and target state before resuming.", file=sys.stderr)
        return 130
    except (ValueError, KeyError, TypeError, OSError, CellFailure) as exc:
        print(f"Campaign configuration/state error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
