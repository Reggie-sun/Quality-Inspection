#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


TASK_ID = "D6-T3"
TESTS = (
    "backend/tests/unit/exports/test_manifest.py",
    "backend/tests/integration/test_export_consistency.py",
    "backend/tests/integration/test_export_atomicity.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the offline D6-T3 export consistency contract."
    )
    parser.add_argument("mode", choices=("fixture",))
    parser.add_argument("--task", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.task != TASK_ID:
        print(f"error: --task must be {TASK_ID}", file=sys.stderr)
        return 2

    repository_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q"],
        cwd=repository_root,
        check=False,
    )
    if result.returncode != 0:
        return result.returncode
    print(f"task={TASK_ID} export_consistency=passed external_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
