from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.providers.pricing import load_pricing_snapshot
from app.providers.usage_ledger import ProviderUsageLedger


CYCLE_ID = "gdt10d-classified-live-20260802"
RUN_ID = "20260802T000000000000Z-fixture"


def _hashed(document: dict[str, object]) -> dict[str, object]:
    payload = dict(document)
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(content).hexdigest()
    return payload


def _write_fact(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text(
        json.dumps(_hashed(document), sort_keys=True),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def create_cycle_authorization(
    root: Path,
    *,
    project_ids: tuple[str, ...],
) -> Path:
    root.mkdir(mode=0o700)
    pricing = load_pricing_snapshot()
    _write_fact(
        root / "issuance.json",
        {
            "schema_version": "provider-cycle-issuance/1",
            "cycle_id": CYCLE_ID,
            "expires_at": "2099-08-02T23:59:59+00:00",
            "head_revision": "a" * 40,
            "plan_sha256": "b" * 64,
            "pricing_sha256": pricing.content_sha256,
            "runtime_closure_sha256": "c" * 64,
            "current_four_sha256": "d" * 64,
            "backend_image_id": "sha256:" + "9" * 64,
            "compose_project": "quality_inspection-qa",
            "expected_db_revision": "0014",
            "max_total_cny": "50.000000",
        },
    )
    issuance = json.loads((root / "issuance.json").read_text(encoding="utf-8"))
    _write_fact(
        root / "consumption.json",
        {
            "schema_version": "provider-cycle-consumption/1",
            "cycle_id": CYCLE_ID,
            "issuance_sha256": issuance["content_sha256"],
            "invocation_id": "e" * 64,
            "consumed_at": "2026-08-02T00:00:00+00:00",
        },
    )
    consumption = json.loads(
        (root / "consumption.json").read_text(encoding="utf-8")
    )
    _write_fact(
        root / "run.json",
        {
            "schema_version": "provider-cycle-run/1",
            "cycle_id": CYCLE_ID,
            "run_id": RUN_ID,
            "consumption_sha256": consumption["content_sha256"],
        },
    )
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    for order, project_id in enumerate(project_ids, start=1):
        _write_fact(
            root / "projects" / f"{order:04d}.json",
            {
                "schema_version": "provider-cycle-project/1",
                "cycle_id": CYCLE_ID,
                "run_id": RUN_ID,
                "project_id": project_id,
                "project_order": order,
                "source_sha256": hashlib.sha256(
                    f"fixture-source-{order}".encode()
                ).hexdigest(),
                "run_sha256": run["content_sha256"],
            },
        )
    return root


def open_cycle_ledger(
    tmp_path: Path,
    *,
    project_id: str,
) -> ProviderUsageLedger:
    authorization_root = create_cycle_authorization(
        tmp_path / "authorization",
        project_ids=(project_id,),
    )
    return ProviderUsageLedger.open(
        cycle_id=CYCLE_ID,
        storage_root=tmp_path / "storage",
        authorization_root=authorization_root,
        project_id=project_id,
    )
