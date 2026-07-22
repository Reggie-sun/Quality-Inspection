#!/usr/bin/env python3
"""Generate the executable P0 contract mirror from its only Markdown source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TRACE = ROOT / "docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md"
GLOBAL = ROOT / "docs/contracts/MAIN_CONTRACT_MATRIX.md"
OUTPUT = ROOT / ".agent/harness/contracts/p0-contracts.json"

TRACE_SOURCE = str(TRACE.relative_to(ROOT))
GLOBAL_SOURCE = str(GLOBAL.relative_to(ROOT))
P0_SECTION = "## P0 Contract Rows"
GLOBAL_ID_RE = re.compile(r"^[A-Z]+-[0-9]{3}$")
P0_ID_RE = re.compile(r"^P0-[A-Z]+-[0-9]{3}[A-Z]?$")

COLUMN_KEYS = (
    "p0_contract_id",
    "global_contract_id",
    "implementation_only",
    "related_global_contract_ids",
    "stable_p0_requirement",
    "owner",
    "task_id",
    "tier",
    "verification_selector",
    "blocking_level",
    "current_status",
    "implementation_reason",
)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise ValueError(f"not a Markdown table row: {line!r}")
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _strip_outer_code(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def _p0_table_lines(markdown: str) -> list[str]:
    in_section = False
    lines: list[str] = []
    for line in markdown.splitlines():
        if line == P0_SECTION:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            lines.append(line)
    if not in_section:
        raise ValueError(f"missing section {P0_SECTION!r}")
    return lines


def _related_ids(value: str) -> list[str]:
    raw = _strip_outer_code(value)
    if raw == "[]":
        return []
    if not raw.startswith("[") or not raw.endswith("]"):
        raise ValueError(f"invalid related global ID list: {value!r}")
    ids = [_strip_outer_code(part) for part in raw[1:-1].split(",") if part.strip()]
    if any(not GLOBAL_ID_RE.fullmatch(item) for item in ids):
        raise ValueError(f"invalid related global ID list: {value!r}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate related global ID: {value!r}")
    return sorted(ids)


def parse_p0_contracts(markdown: str) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for line in _p0_table_lines(markdown):
        if not line.lstrip().startswith("|"):
            continue
        cells = _table_cells(line)
        first = _strip_outer_code(cells[0]) if cells else ""
        if not P0_ID_RE.fullmatch(first):
            continue
        if len(cells) != len(COLUMN_KEYS):
            raise ValueError(f"{first}: expected 12 columns, got {len(cells)}")

        global_id_raw = _strip_outer_code(cells[1])
        implementation_only_raw = _strip_outer_code(cells[2])
        if implementation_only_raw not in {"true", "false"}:
            raise ValueError(f"{first}: invalid implementation_only value")
        global_id = None if global_id_raw == "null" else global_id_raw
        if global_id is not None and not GLOBAL_ID_RE.fullmatch(global_id):
            raise ValueError(f"{first}: invalid global_contract_id {global_id!r}")

        contract = {
            "p0_contract_id": first,
            "global_contract_id": global_id,
            "implementation_only": implementation_only_raw == "true",
            "related_global_contract_ids": _related_ids(cells[3]),
            "stable_p0_requirement": _strip_outer_code(cells[4]),
            "owner": _strip_outer_code(cells[5]),
            "task_id": _strip_outer_code(cells[6]),
            "tier": _strip_outer_code(cells[7]),
            "verification_selector": _strip_outer_code(cells[8]),
            "blocking_level": _strip_outer_code(cells[9]),
            "current_status": _strip_outer_code(cells[10]),
            "implementation_reason": _strip_outer_code(cells[11]),
        }
        contracts.append(contract)
    return sorted(contracts, key=lambda row: row["p0_contract_id"])


def parse_global_contracts(markdown: str) -> dict[str, dict[str, str]]:
    contracts: dict[str, dict[str, str]] = {}
    for line in markdown.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _table_cells(line)
        if len(cells) != 11:
            continue
        contract_id = _strip_outer_code(cells[0])
        if not GLOBAL_ID_RE.fullmatch(contract_id):
            continue
        if contract_id in contracts:
            raise ValueError(f"duplicate global contract ID: {contract_id}")
        contracts[contract_id] = {
            "global_contract_id": contract_id,
            "current_enforcement_stage": _strip_outer_code(cells[10]),
        }
    return contracts


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def contract_definition_hash(contracts: list[dict[str, Any]]) -> str:
    definition = [
        {key: row[key] for key in COLUMN_KEYS if key != "current_status"}
        for row in contracts
    ]
    return _digest(definition)


def status_projection_hash(contracts: list[dict[str, Any]]) -> str:
    projection = [
        {
            "p0_contract_id": row["p0_contract_id"],
            "current_status": row["current_status"],
        }
        for row in contracts
    ]
    return _digest(projection)


def build_mirror() -> dict[str, Any]:
    contracts = parse_p0_contracts(TRACE.read_text(encoding="utf-8"))
    global_contracts = parse_global_contracts(GLOBAL.read_text(encoding="utf-8"))
    referenced = {
        global_id
        for row in contracts
        for global_id in ([row["global_contract_id"]] + row["related_global_contract_ids"])
        if global_id is not None
    }
    unknown = sorted(referenced - set(global_contracts))
    if unknown:
        raise ValueError(f"unknown global contract IDs: {', '.join(unknown)}")
    return {
        "schema_version": "p0-contracts/1",
        "source": TRACE_SOURCE,
        "global_source": GLOBAL_SOURCE,
        "contract_definition_hash": contract_definition_hash(contracts),
        "status_projection_hash": status_projection_hash(contracts),
        "contracts": contracts,
    }


def generated_bytes() -> bytes:
    return (
        json.dumps(build_mirror(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temp_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare exact generated bytes without writing",
    )
    args = parser.parse_args(argv)
    try:
        content = generated_bytes()
        if args.check:
            if not OUTPUT.exists() or OUTPUT.read_bytes() != content:
                print("mirror drift: regenerate p0-contracts.json", file=sys.stderr)
                return 1
            return 0
        _atomic_write(OUTPUT, content)
        print(f"generated={OUTPUT.relative_to(ROOT)}")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"generate-contract-mirror: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
