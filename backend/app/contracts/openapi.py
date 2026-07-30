from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def find_breaking_changes(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    changes: list[str] = []
    baseline_paths = baseline.get("paths", {})
    current_paths = current.get("paths", {})

    for path, baseline_path in baseline_paths.items():
        current_path = current_paths.get(path, {})
        for method, baseline_operation in baseline_path.items():
            if method not in HTTP_METHODS:
                continue
            location = f"{method.upper()} {path}"
            current_operation = current_path.get(method)
            if current_operation is None:
                changes.append(f"{location}: operation removed")
                continue
            if baseline_operation.get("operationId") != current_operation.get(
                "operationId"
            ):
                changes.append(f"{location}: operationId changed")
            _compare_statuses(
                baseline_operation,
                current_operation,
                location,
                changes,
            )
            _compare_request_body(
                baseline_operation,
                current_operation,
                location,
                changes,
            )
            _compare_parameters(
                baseline_operation,
                current_operation,
                location,
                baseline,
                current,
                changes,
            )
            _compare_content_schema(
                baseline_operation.get("requestBody", {}).get("content", {}),
                current_operation.get("requestBody", {}).get("content", {}),
                f"{location} request",
                baseline,
                current,
                changes,
            )
            for status, baseline_response in baseline_operation.get(
                "responses", {}
            ).items():
                current_response = current_operation.get("responses", {}).get(status)
                if current_response is None:
                    continue
                _compare_content_schema(
                    baseline_response.get("content", {}),
                    current_response.get("content", {}),
                    f"{location} response {status}",
                    baseline,
                    current,
                    changes,
                )

    baseline_schemas = baseline.get("components", {}).get("schemas", {})
    current_schemas = current.get("components", {}).get("schemas", {})
    for name, baseline_schema in baseline_schemas.items():
        current_schema = current_schemas.get(name)
        if current_schema is None:
            changes.append(f"schema {name}: schema removed")
            continue
        _compare_schema(
            baseline_schema,
            current_schema,
            f"schema {name}",
            baseline,
            current,
            changes,
            set(),
        )
    return changes


def _compare_statuses(
    baseline_operation: dict[str, Any],
    current_operation: dict[str, Any],
    location: str,
    changes: list[str],
) -> None:
    baseline_statuses = set(baseline_operation.get("responses", {}))
    current_statuses = set(current_operation.get("responses", {}))
    removed = sorted(baseline_statuses - current_statuses)
    if removed:
        changes.append(f"{location}: response statuses removed: {removed}")
    for status in sorted(baseline_statuses & current_statuses):
        baseline_codes = set(
            baseline_operation["responses"][status].get(
                "x-stable-error-codes",
                [],
            )
        )
        current_codes = set(
            current_operation["responses"][status].get(
                "x-stable-error-codes",
                [],
            )
        )
        removed_codes = sorted(baseline_codes - current_codes)
        if removed_codes:
            changes.append(
                f"{location} response {status}: "
                f"stable error codes removed: {removed_codes}"
            )


def _compare_request_body(
    baseline_operation: dict[str, Any],
    current_operation: dict[str, Any],
    location: str,
    changes: list[str],
) -> None:
    baseline_required = baseline_operation.get("requestBody", {}).get(
        "required",
        False,
    )
    current_required = current_operation.get("requestBody", {}).get(
        "required",
        False,
    )
    if baseline_required != current_required:
        changes.append(
            f"{location} request body: required changed from "
            f"{baseline_required} to {current_required}"
        )


def _compare_parameters(
    baseline_operation: dict[str, Any],
    current_operation: dict[str, Any],
    location: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
    changes: list[str],
) -> None:
    current_parameters = {
        (parameter.get("in"), parameter.get("name")): parameter
        for parameter in current_operation.get("parameters", [])
    }
    baseline_parameter_keys = {
        (parameter.get("in"), parameter.get("name"))
        for parameter in baseline_operation.get("parameters", [])
    }
    for key, current_parameter in current_parameters.items():
        if (
            key not in baseline_parameter_keys
            and current_parameter.get("required", False)
        ):
            changes.append(f"{location} parameter {key}: required parameter added")
    for baseline_parameter in baseline_operation.get("parameters", []):
        key = (
            baseline_parameter.get("in"),
            baseline_parameter.get("name"),
        )
        current_parameter = current_parameters.get(key)
        if current_parameter is None:
            changes.append(f"{location} parameter {key}: parameter removed")
            continue
        if baseline_parameter.get("required", False) != current_parameter.get(
            "required", False
        ):
            changes.append(f"{location} parameter {key}: required changed")
        _compare_schema(
            baseline_parameter.get("schema", {}),
            current_parameter.get("schema", {}),
            f"{location} parameter {key}",
            baseline,
            current,
            changes,
            set(),
        )


def _compare_content_schema(
    baseline_content: dict[str, Any],
    current_content: dict[str, Any],
    location: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
    changes: list[str],
) -> None:
    for media_type, baseline_media in baseline_content.items():
        current_media = current_content.get(media_type)
        if current_media is None:
            changes.append(f"{location}: media type removed: {media_type}")
            continue
        _compare_schema(
            baseline_media.get("schema", {}),
            current_media.get("schema", {}),
            f"{location} {media_type}",
            baseline,
            current,
            changes,
            set(),
        )


def _compare_schema(
    baseline_schema: dict[str, Any],
    current_schema: dict[str, Any],
    location: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
    changes: list[str],
    seen: set[tuple[str, str]],
) -> None:
    pair = (
        str(baseline_schema.get("$ref", id(baseline_schema))),
        str(current_schema.get("$ref", id(current_schema))),
    )
    if pair in seen:
        return
    seen.add(pair)
    baseline_schema = _resolve_schema(baseline_schema, baseline)
    current_schema = _resolve_schema(current_schema, current)

    baseline_type = _normalized_type(baseline_schema)
    current_type = _normalized_type(current_schema)
    if baseline_type != current_type:
        changes.append(
            f"{location}: type changed from {baseline_type} to {current_type}"
        )
        return

    baseline_required = set(baseline_schema.get("required", []))
    current_required = set(current_schema.get("required", []))
    if baseline_required != current_required:
        changes.append(
            f"{location}: required changed from "
            f"{sorted(baseline_required)} to {sorted(current_required)}"
        )

    removed_enum = set(baseline_schema.get("enum", [])) - set(
        current_schema.get("enum", [])
    )
    if removed_enum:
        changes.append(
            f"{location}: enum values removed: {sorted(removed_enum, key=str)}"
        )

    if (
        "const" in baseline_schema or "const" in current_schema
    ) and baseline_schema.get("const") != current_schema.get("const"):
        changes.append(
            f"{location}: const changed from "
            f"{baseline_schema.get('const')!r} to {current_schema.get('const')!r}"
        )

    baseline_properties = baseline_schema.get("properties", {})
    current_properties = current_schema.get("properties", {})
    for name, baseline_property in baseline_properties.items():
        current_property = current_properties.get(name)
        if current_property is None:
            changes.append(f"{location}.{name}: property removed")
            continue
        _compare_schema(
            baseline_property,
            current_property,
            f"{location}.{name}",
            baseline,
            current,
            changes,
            seen,
        )

    if "items" in baseline_schema:
        if "items" not in current_schema:
            changes.append(f"{location}: array items schema removed")
        else:
            _compare_schema(
                baseline_schema["items"],
                current_schema["items"],
                f"{location}[]",
                baseline,
                current,
                changes,
                seen,
            )

    for keyword in ("allOf", "anyOf", "oneOf"):
        baseline_variants = baseline_schema.get(keyword, [])
        if not baseline_variants:
            continue
        current_variants = current_schema.get(keyword, [])
        current_signatures = {_schema_signature(item) for item in current_variants}
        removed_variants = [
            item
            for item in baseline_variants
            if _schema_signature(item) not in current_signatures
        ]
        if removed_variants:
            changes.append(f"{location}: {keyword} variants removed or changed")


def _resolve_schema(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith(
        "#/components/schemas/"
    ):
        return schema
    name = reference.rsplit("/", 1)[-1]
    return document.get("components", {}).get("schemas", {}).get(name, {})


def _normalized_type(schema: dict[str, Any]) -> tuple[str, ...]:
    value = schema.get("type")
    if isinstance(value, list):
        return tuple(sorted(str(item) for item in value))
    if isinstance(value, str):
        return (value,)
    if any(key in schema for key in ("allOf", "anyOf", "oneOf")):
        return ("composed",)
    if "$ref" in schema:
        return ("reference",)
    return ("unspecified",)


def _schema_signature(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the current FastAPI OpenAPI projection as the baseline.",
    )
    parser.add_argument(
        "--baseline-ref",
        help=(
            "Git revision containing the prior approved snapshot. "
            "Required for breaking checks so the current change cannot "
            "rewrite its own baseline."
        ),
    )
    args = parser.parse_args()

    from app.main import app

    current = app.openapi()
    if args.write:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(f"openapi_snapshot_written={args.baseline}")
        return 0

    if not args.baseline_ref:
        parser.error("--baseline-ref is required unless --write is used")
    baseline = _baseline_from_git(args.baseline, args.baseline_ref)
    changes = find_breaking_changes(baseline, current)
    if changes:
        for change in changes:
            print(f"BREAKING: {change}")
        return 1
    print("openapi_breaking_changes=0")
    return 0


def _baseline_from_git(path: Path, revision: str) -> dict[str, Any]:
    repository = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relative = path.resolve().relative_to(Path(repository).resolve())
    content = subprocess.run(
        ["git", "show", f"{revision}:{relative.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(content)


if __name__ == "__main__":
    raise SystemExit(main())
