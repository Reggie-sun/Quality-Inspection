from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.providers.usage_ledger import ProviderUsageLedger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Close one paid Provider cycle under its durable ledger lock."
    )
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--status", choices=("completed", "failed", "aborted"), required=True)
    parser.add_argument("--quiescence-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.project_id is None:
            terminal = ProviderUsageLedger.close_without_project(
                cycle_id=args.cycle_id,
                storage_root=Path("/data"),
                authorization_root=Path("/auth"),
                run_id=args.run_id,
                status=args.status,
                quiescence_sha256=args.quiescence_sha256,
            )
        else:
            ledger = ProviderUsageLedger.open_for_close(
                cycle_id=args.cycle_id,
                storage_root=Path("/data"),
                authorization_root=Path("/auth"),
                project_id=args.project_id,
            )
            terminal = ledger.close_cycle(
                run_id=args.run_id,
                status=args.status,
                quiescence_sha256=args.quiescence_sha256,
            )
    except (OSError, ValueError) as exc:
        print(f"cycle_close_error={type(exc).__name__}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema_version": terminal["schema_version"],
                "cycle_id": terminal["cycle_id"],
                "run_id": terminal["run_id"],
                "status": terminal["status"],
                "quiescence_sha256": terminal["quiescence_sha256"],
                "run_sha256": terminal["run_sha256"],
                "content_sha256": terminal["content_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
