#!/usr/bin/env python3
"""Print read-only counts and artifact refs for one literal sealed Harness run."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON evidence must be one object: {path.name}")
    return document


def _receipt_module() -> ModuleType:
    path = HARNESS / "scripts/generate-receipt.py"
    spec = importlib.util.spec_from_file_location("qi_generate_receipt_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load generate-receipt.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _live_artifact_refs(live: Mapping[str, Any]) -> set[str]:
    refs: set[str] = {
        "artifacts/current-four-manifest.json",
        "artifacts/human-verdict.json",
        "live-run-evidence.json",
    }
    design = live.get("design_qa")
    if isinstance(design, Mapping):
        for name in ("implementation_capture_ref", "comparison_capture_ref"):
            value = design.get(name)
            if isinstance(value, str):
                refs.add(value)
    samples = live.get("samples")
    if not isinstance(samples, list):
        return refs
    for sample in samples:
        if not isinstance(sample, Mapping):
            continue
        process = sample.get("process")
        review = sample.get("review")
        consistency = sample.get("consistency")
        for section, name in (
            (process, "prepare_log_ref"),
            (review, "evidence_ref"),
            (consistency, "evidence_ref"),
        ):
            if isinstance(section, Mapping) and isinstance(section.get(name), str):
                refs.add(section[name])
        for section_name in ("balloons", "export"):
            section = sample.get(section_name)
            browser = section.get("browser") if isinstance(section, Mapping) else None
            if not isinstance(browser, Mapping):
                continue
            for name in ("report_ref", "result_ref"):
                value = browser.get(name)
                if isinstance(value, str):
                    refs.add(value)
            screenshots = browser.get("screenshot_refs")
            if isinstance(screenshots, list):
                refs.update(ref for ref in screenshots if isinstance(ref, str))
    return refs


def summary_lines(
    root: Path,
    run_id: str,
    receipt: Mapping[str, Any],
) -> list[str]:
    receipt_module = _receipt_module()
    if not receipt_module.RUN_ID_RE.fullmatch(run_id):
        raise ValueError("--run-id requires one literal generated run ID")
    run_dir = root / ".agent/harness/runs" / run_id
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ValueError(f"run directory does not exist: {run_id}")
    results_document = _load_json(run_dir / "contract-results.json")
    live = _load_json(run_dir / "live-run-evidence.json")
    manifest = _load_json(run_dir / "artifacts/current-four-manifest.json")
    results = results_document.get("results")
    samples = live.get("samples")
    entries = manifest.get("entries")
    if (
        receipt.get("run_id") != run_id
        or results_document.get("run_id") != run_id
        or live.get("run_id") != run_id
        or not isinstance(results, list)
        or not isinstance(samples, list)
        or not isinstance(entries, list)
    ):
        raise ValueError("summary evidence is incomplete or run-spliced")

    counts = receipt.get("result_counts")
    freshness = receipt.get("freshness")
    if not isinstance(counts, Mapping) or not isinstance(freshness, Mapping):
        raise ValueError("receipt counts or freshness are missing")
    artifact_counts = []
    for sample in samples:
        export = sample.get("export") if isinstance(sample, Mapping) else None
        kinds = export.get("artifact_kinds") if isinstance(export, Mapping) else None
        artifact_counts.append(len(kinds) if isinstance(kinds, list) else 0)
    artifacts_per_sample = (
        artifact_counts[0]
        if artifact_counts and len(set(artifact_counts)) == 1
        else 0
    )
    reasons = freshness.get("reasons")
    stale = 0 if freshness.get("fresh") is True else len(reasons or [])
    lines = [
        f"contracts={len(results)}",
        f"passed={counts.get('passed', 0)}",
        f"failed={counts.get('failed', 0)}",
        f"blocked={counts.get('blocked', 0)}",
        f"not_run={counts.get('not_run', 0)}",
        f"stale={stale}",
        f"current_four={len(entries)}",
        f"artifacts_per_sample={artifacts_per_sample}",
        f"overall_verdict={receipt.get('overall_verdict')}",
    ]
    refs = _live_artifact_refs(live)
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("contract result must be one object")
        artifact_refs = result.get("artifact_refs")
        if not isinstance(artifact_refs, list):
            raise ValueError("contract result artifact_refs are missing")
        refs.update(ref for ref in artifact_refs if isinstance(ref, str))
    lines.extend(f"artifact_ref={ref}" for ref in sorted(refs))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        receipt = _receipt_module().check_run(args.run_id, ROOT)
        lines = summary_lines(ROOT, args.run_id, receipt)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"summarize-run: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
