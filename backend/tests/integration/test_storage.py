import json
import subprocess
from pathlib import Path

from sqlalchemy import inspect

from app.db import engine
from app.storage.models import StoredFile


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"


def _storage_volume(service: dict) -> str:
    mounts = [
        mount
        for mount in service.get("volumes", [])
        if mount.get("type") == "volume" and mount.get("target") == "/data"
    ]
    assert len(mounts) == 1
    return mounts[0]["source"]


def test_api_and_worker_share_storage_root() -> None:
    """P0-RUN-002A binds API and Worker to one controlled storage root."""
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    services = json.loads(rendered.stdout)["services"]

    assert _storage_volume(services["api"]) == _storage_volume(services["worker"])


def test_database_persists_only_file_metadata() -> None:
    """P0-RUN-002E keeps file bytes out of PostgreSQL metadata rows."""
    columns = {
        column["name"]
        for column in inspect(engine).get_columns(StoredFile.__tablename__)
    }

    assert columns == {
        "id",
        "resource_ref",
        "sha256",
        "size_bytes",
        "mime_type",
        "created_at",
    }
    assert "path" not in columns
    assert "content" not in columns
