"""Write the shared V14/V15 declared-artifact manifest format."""

import argparse
import hashlib
import json
from pathlib import Path


def write_manifest(
    build: Path,
    variant: str,
    build_id: str,
    frozen_evidence: Path,
    output: Path,
    declared: list[str],
) -> None:
    missing = [name for name in declared if not (build / name).is_file()]
    if missing:
        raise ValueError("declared artifact missing: %s" % missing)
    table = {
        name: {
            "sha256": hashlib.sha256((build / name).read_bytes()).hexdigest(),
            "bytes": (build / name).stat().st_size,
        }
        for name in declared
    }
    frozen = json.loads(frozen_evidence.read_text(encoding="utf-8"))["frozen_inputs"]
    document = {
        "variant": variant,
        "schema_version": 14,
        "build_id": build_id,
        "canonical_json": "v14-canonical-json-v1",
        "frozen_input_sha256": frozen,
        "declared_artifacts": table,
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    document["manifest_self_hash"] = hashlib.sha256(canonical).hexdigest()
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--frozen-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("declared", nargs="+")
    args = parser.parse_args()
    try:
        write_manifest(
            args.build, args.variant, args.build_id, args.frozen_evidence,
            args.output, args.declared,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, "%s\n" % exc)


if __name__ == "__main__":
    main()
