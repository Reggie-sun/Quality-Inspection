#!/usr/bin/env python3
"""Record per-sample, non-overwriting quality-operator verdict stages."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import jsonschema


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"
RUNS = HARNESS / "runs"
SCHEMA_PATH = HARNESS / "schemas/human-verdict.schema.json"
ARTIFACT_PATH = Path("artifacts/human-verdict.json")
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
STAGE_KEYS = {
    "item-set": (
        "automatic_candidates_are_actionable",
        "candidates_are_editable",
        "operator_confirmed_item_set_is_complete",
        "not_false_success",
    ),
    "balloons": (
        "all_required_balloons_visible",
        "hard_collisions_resolved",
    ),
}
MERGE_SPLIT_DISPOSITIONS = ("merge", "split", "not_applicable")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(document: Mapping[str, Any]) -> None:
    schema = _load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(document)


def _atomic_write(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def record_stage(
    run_dir: Path,
    *,
    order: int,
    project_id: str,
    stage: str,
    operator_id: str,
    note: str,
    merge_split_disposition: str | None,
    merge_split_note: str | None,
    answers: Mapping[str, bool],
) -> dict[str, Any]:
    if stage not in STAGE_KEYS:
        raise ValueError("stage must be item-set or balloons")
    if not RUN_ID_RE.fullmatch(run_dir.name):
        raise ValueError("run directory must use one literal run ID")
    clean_operator = operator_id.strip()
    clean_note = note.strip()
    clean_project = project_id.strip()
    if order not in {1, 2, 3, 4}:
        raise ValueError("sample order must be between 1 and 4")
    if not clean_operator or not clean_note or not clean_project:
        raise ValueError("operator ID, project ID and note must be non-empty")
    if stage == "item-set":
        clean_disposition = (merge_split_disposition or "").strip()
        clean_merge_note = (merge_split_note or "").strip()
        if clean_disposition not in MERGE_SPLIT_DISPOSITIONS or not clean_merge_note:
            raise ValueError(
                "item-set verdict requires an explicit merge/split disposition and note"
            )
    elif merge_split_disposition is not None or merge_split_note is not None:
        raise ValueError("merge/split evidence belongs only to the item-set stage")
    expected = set(STAGE_KEYS[stage])
    if set(answers) != expected:
        raise ValueError(f"{stage} answers must be explicit and exact")
    if any(type(value) is not bool for value in answers.values()):
        raise TypeError(f"{stage} answers must be booleans")

    artifact = run_dir / ARTIFACT_PATH
    if artifact.exists():
        document = _load_json(artifact)
        _validate(document)
        if document.get("run_id") != run_dir.name:
            raise ValueError("human verdict run identity mismatch")
    else:
        document = {
            "schema_version": "human-verdict/1",
            "run_id": run_dir.name,
            "samples": [],
        }

    samples = document["samples"]
    sample = next((item for item in samples if item["order"] == order), None)
    if sample is None:
        if any(item["project_id"] == clean_project for item in samples):
            raise ValueError("human verdict project identity is already bound")
        sample = {
            "order": order,
            "project_id": clean_project,
            "item_set": None,
            "balloons": None,
            "merged_verdict": None,
        }
        samples.append(sample)
        samples.sort(key=lambda item: item["order"])
    elif sample["project_id"] != clean_project:
        raise ValueError("human verdict project identity mismatch")

    recorded_operators = {
        write["operator_id"]
        for item in samples
        for write in (item.get("item_set"), item.get("balloons"))
        if isinstance(write, Mapping)
    }
    if recorded_operators and recorded_operators != {clean_operator}:
        raise ValueError("all verdict stages must use the same operator")

    field = "item_set" if stage == "item-set" else "balloons"
    if sample[field] is not None:
        raise ValueError(f"{stage} verdict was already recorded")
    if stage == "balloons" and sample["item_set"] is None:
        raise ValueError("balloons verdict requires the bound item-set verdict first")
    write = {
        "operator_id": clean_operator,
        "note": clean_note,
        "recorded_at": _iso_now(),
        "answers": {key: answers[key] for key in STAGE_KEYS[stage]},
    }
    if stage == "item-set":
        write.update(
            {
                "merge_split_disposition": clean_disposition,
                "merge_split_note": clean_merge_note,
            }
        )
    sample[field] = write
    if sample["item_set"] is not None and sample["balloons"] is not None:
        sample["merged_verdict"] = {
            **sample["item_set"]["answers"],
            **sample["balloons"]["answers"],
        }
    _validate(document)
    _atomic_write(artifact, document)
    return document


def all_affirmative(document: Mapping[str, Any]) -> bool:
    samples = document.get("samples")
    return isinstance(samples, list) and bool(samples) and all(
        isinstance(sample.get("merged_verdict"), Mapping)
        and bool(sample["merged_verdict"])
        and all(value is True for value in sample["merged_verdict"].values())
        for sample in samples
    )


def _validate_target(
    run_dir: Path,
    *,
    order: int,
    project_id: str,
    operator_id: str,
    stage: str,
) -> None:
    run = _load_json(run_dir / "run.json")
    if (
        run.get("mode") != "live"
        or run.get("scope") != "full-p0"
        or run.get("execution_state") not in {"running", "visual_qa_pending"}
        or run.get("completed_at") is not None
    ):
        raise ValueError("human verdict requires one open full-p0 live run")
    live_identity = run.get("live_identity")
    if not isinstance(live_identity, Mapping) or (
        live_identity.get("operator_id") != operator_id.strip()
    ):
        raise ValueError("human verdict operator differs from the bound live run")
    live = _load_json(run_dir / "live-run-evidence.json")
    samples = live.get("samples")
    sample = next(
        (
            entry
            for entry in samples
            if isinstance(entry, Mapping)
            and entry.get("order") == order
            and entry.get("project_id") == project_id.strip()
        ),
        None,
    ) if isinstance(samples, list) else None
    if sample is None:
        raise ValueError("human verdict sample/project is not registered in this run")
    if stage == "balloons":
        balloons = sample.get("balloons")
        browser = balloons.get("browser") if isinstance(balloons, Mapping) else None
        if not isinstance(browser, Mapping) or browser.get("passed") is not True:
            raise ValueError(
                "balloons verdict requires post-action pre-export browser evidence"
            )


def _answer(value: str | None, name: str) -> bool:
    if value is None:
        raise ValueError(f"--{name.replace('_', '-')} is required for this stage")
    return value == "yes"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sample-order", required=True, type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--stage", required=True, choices=tuple(STAGE_KEYS))
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument(
        "--merge-split-disposition",
        choices=MERGE_SPLIT_DISPOSITIONS,
    )
    parser.add_argument("--merge-split-note")
    for key in (*STAGE_KEYS["item-set"], *STAGE_KEYS["balloons"]):
        parser.add_argument(f"--{key.replace('_', '-')}", choices=("yes", "no"))
    args = parser.parse_args(argv)
    try:
        if not RUN_ID_RE.fullmatch(args.run_id):
            raise ValueError("--run-id must be one literal run ID")
        run_dir = RUNS / args.run_id
        _validate_target(
            run_dir,
            order=args.sample_order,
            project_id=args.project_id,
            operator_id=args.operator_id,
            stage=args.stage,
        )
        answers = {
            key: _answer(getattr(args, key), key)
            for key in STAGE_KEYS[args.stage]
        }
        document = record_stage(
            run_dir,
            order=args.sample_order,
            project_id=args.project_id,
            stage=args.stage,
            operator_id=args.operator_id,
            note=args.note,
            merge_split_disposition=args.merge_split_disposition,
            merge_split_note=args.merge_split_note,
            answers=answers,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        jsonschema.ValidationError,
    ) as exc:
        print(f"record-human-verdict: {exc}", file=sys.stderr)
        return 2
    print(
        f"run_id={args.run_id} sample={args.sample_order} stage={args.stage} "
        f"merged={int(any(sample['order'] == args.sample_order and sample['merged_verdict'] is not None for sample in document['samples']))} "
        f"all_affirmative={int(all_affirmative(document))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
