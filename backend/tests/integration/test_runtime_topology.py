import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"


def _rendered_compose_config() -> dict:
    assert COMPOSE_FILE.is_file(), f"missing compose file: {COMPOSE_FILE}"
    result = subprocess.run(
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
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _data_volume_source(service: dict) -> str:
    data_mounts = [
        volume
        for volume in service.get("volumes", [])
        if volume.get("type") == "volume" and volume.get("target") == "/data"
    ]
    assert len(data_mounts) == 1
    return data_mounts[0]["source"]


def test_compose_has_exact_p0_services() -> None:
    """P0-RUN-001 verifies the exact P0 Compose topology."""
    config = _rendered_compose_config()
    services = config["services"]

    assert config["name"] == "quality-inspection"
    assert set(services) == {"postgres", "redis", "api", "worker", "frontend"}

    worker_command = services["worker"]["command"]
    if isinstance(worker_command, list):
        worker_command = " ".join(worker_command)
    assert "--concurrency=1" in worker_command

    assert _data_volume_source(services["api"]) == "qi_storage"
    assert _data_volume_source(services["worker"]) == "qi_storage"
