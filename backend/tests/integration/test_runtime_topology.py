import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"
TEST_COMPOSE_FILE = ROOT / "compose.test.yaml"


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


def _rendered_test_compose_config() -> dict:
    assert TEST_COMPOSE_FILE.is_file(), f"missing test compose file: {TEST_COMPOSE_FILE}"
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(TEST_COMPOSE_FILE),
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


def test_backend_suite_uses_one_host_reachable_ephemeral_postgres() -> None:
    """The host test entry owns an isolated PostgreSQL lifecycle."""
    config = _rendered_test_compose_config()

    assert set(config["services"]) == {"postgres"}
    postgres = config["services"]["postgres"]
    assert postgres.get("volumes", []) == []
    assert postgres["tmpfs"] == ["/var/lib/postgresql/data"]
    assert postgres["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U qi -d qi",
    ]
    assert postgres["ports"] == [
        {
            "mode": "ingress",
            "target": 5432,
            "published": "0",
            "protocol": "tcp",
            "host_ip": "127.0.0.1",
        }
    ]


def test_backend_suite_make_target_migrates_tests_and_cleans_up() -> None:
    """The public target cleans its exact isolated project on every exit."""
    result = subprocess.run(
        ["make", "--dry-run", "test-backend"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    command = result.stdout
    assert "compose.test.yaml" in command
    assert 'test_project="quality-inspection-test-$$"' in command
    assert "up -d --wait" in command
    assert "port postgres 5432" in command
    assert "QI_DATABASE_URL=" in command
    assert "alembic -c alembic.ini upgrade head" in command
    assert "python -m pytest backend/tests -q" in command
    assert "down --volumes --remove-orphans" in command
    assert "trap 'exit 130' INT" in command
    assert "trap 'exit 143' TERM" in command


def test_backend_suite_preserves_test_failure_when_cleanup_also_fails(
    tmp_path: Path,
) -> None:
    """Cleanup diagnostics must not replace the pytest failure status."""
    compose_log = tmp_path / "compose.log"
    fake_compose = tmp_path / "fake-compose"
    fake_compose.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$FAKE_COMPOSE_LOG"\n'
        'case " $* " in\n'
        '  *" port postgres 5432 "*) echo "127.0.0.1:15432"; exit 0 ;;\n'
        '  *" down --volumes --remove-orphans "*) exit 1 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_compose.chmod(0o755)
    fake_micromamba = tmp_path / "micromamba"
    fake_micromamba.write_text(
        "#!/bin/sh\n"
        'case " $* " in\n'
        '  *" python -m pytest backend/tests -q "*) exit 7 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_micromamba.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{tmp_path}{os.pathsep}{environment['PATH']}"
    environment["FAKE_COMPOSE_LOG"] = str(compose_log)

    result = subprocess.run(
        [
            "make",
            f"TEST_BACKEND_COMPOSE={fake_compose}",
            "test-backend",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Error 7" in result.stderr, result.stdout + result.stderr
    assert "down --volumes --remove-orphans" in compose_log.read_text(
        encoding="utf-8"
    )
