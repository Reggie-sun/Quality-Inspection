#!/usr/bin/env python3
"""Validate sanitized Provider fixtures and run fixture-only contract tests."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
FIXTURE_RELATIVE_PATHS = (
    Path(".agent/harness/fixtures/providers/tencent-ocr/general-accurate-v1.json"),
    Path(".agent/harness/fixtures/providers/qwen-vl/candidate-review-v1.json"),
    Path(".agent/harness/fixtures/providers/qwen-vl/visual-symbol-review-v2.json"),
)
FIXTURE_PATHS = tuple(ROOT / path for path in FIXTURE_RELATIVE_PATHS)
TEST_PATHS = (
    "backend/tests/contract/test_tencent_ocr_provider.py",
    "backend/tests/contract/test_qwen_vl_provider.py",
    "backend/tests/contract/test_qwen_symbol_provider.py",
    "backend/tests/contract/test_provider_call_records.py",
)
FORBIDDEN_KEY_RE = re.compile(
    r"authorization|api[_-]?key|secret|base64",
    re.IGNORECASE,
)
BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location(
        "qi_generate_receipt_for_provider_contracts",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate-receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_sanitized_payload(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if FORBIDDEN_KEY_RE.search(str(key)):
                raise ValueError(f"forbidden fixture key: {key}")
            validate_sanitized_payload(nested)
        return
    if isinstance(value, list):
        for nested in value:
            validate_sanitized_payload(nested)
        return
    if isinstance(value, str) and len(value) >= 64 and BASE64_RE.fullmatch(value):
        raise ValueError("fixture contains a full base64-like payload")


def _validated_fixture_path(path: Path) -> Path:
    repository = ROOT.absolute()
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(repository)
    except ValueError as exc:
        raise ValueError("Provider fixture escapes repository root") from exc
    if relative not in FIXTURE_RELATIVE_PATHS:
        raise ValueError("Provider fixture is not in the fixed D2-T2 allowlist")
    current = repository
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Provider fixture path contains a symlink")
    if not candidate.is_file():
        raise ValueError(f"Provider fixture is missing: {candidate.name}")
    try:
        candidate.resolve(strict=True).relative_to(repository.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError("Provider fixture escapes repository root") from exc
    return candidate


def load_fixture(path: Path) -> dict[str, Any]:
    fixture_path = _validated_fixture_path(path)
    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    _receipt_module().validate_schema(
        document,
        "provider-fixture.schema.json",
        ROOT,
    )
    validate_sanitized_payload(document["payload"])
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fixture",))
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    try:
        if args.task != "D2-T2":
            raise ValueError("Provider contract runner accepts only D2-T2")
        receipt_module = _receipt_module()
        if receipt_module.provider_network_enabled():
            raise ValueError("fixture Provider contracts reject network-enabled controls")
        for path in FIXTURE_PATHS:
            load_fixture(path)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"run-provider-contracts: {exc}", file=sys.stderr)
        return 2

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *TEST_PATHS, "-q"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        return result.returncode
    print(
        f"fixtures={len(FIXTURE_PATHS)} external_calls=0 "
        f"task={args.task} provider_contracts=passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
