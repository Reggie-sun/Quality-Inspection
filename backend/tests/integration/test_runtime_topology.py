import json
import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "compose.yaml"
QA_COMPOSE_FILE = ROOT / "compose.qa-dev.yaml"
SERVER_COMPOSE_FILE = ROOT / "compose.server.yaml"
TEST_COMPOSE_FILE = ROOT / "compose.test.yaml"


def _rendered_compose_config(project_name: str | None = None) -> dict:
    assert COMPOSE_FILE.is_file(), f"missing compose file: {COMPOSE_FILE}"
    environment = dict(os.environ)
    if project_name is not None:
        environment["COMPOSE_PROJECT_NAME"] = project_name
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
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _rendered_qa_compose_config(project_name: str) -> dict:
    assert QA_COMPOSE_FILE.is_file(), f"missing compose file: {QA_COMPOSE_FILE}"
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project_name
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "-f",
            str(QA_COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
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


def _rendered_server_compose_config(project_name: str) -> dict:
    assert SERVER_COMPOSE_FILE.is_file(), f"missing compose file: {SERVER_COMPOSE_FILE}"
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project_name
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "-f",
            str(SERVER_COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _rendered_qa_compose_config(project_name: str) -> dict:
    assert QA_COMPOSE_FILE.is_file(), f"missing compose file: {QA_COMPOSE_FILE}"
    environment = dict(os.environ)
    environment["COMPOSE_PROJECT_NAME"] = project_name
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "-f",
            str(QA_COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
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

    assert set(services) == {"postgres", "redis", "api", "worker", "frontend"}

    worker_command = services["worker"]["command"]
    if isinstance(worker_command, list):
        worker_command = " ".join(worker_command)
    assert "--concurrency=1" in worker_command

    assert _data_volume_source(services["api"]) == "qi_storage"
    assert _data_volume_source(services["worker"]) == "qi_storage"


def test_repo_compose_runtimes_explicitly_promote_production_symbol_routing() -> None:
    """Base, QA, and server consumers must not inherit a routing fallback."""
    rendered_configs = (
        _rendered_compose_config("quality-inspection-main"),
        _rendered_qa_compose_config("quality-inspection-qa"),
        _rendered_server_compose_config("quality-inspection-server"),
    )

    for config in rendered_configs:
        for service_name in ("api", "worker"):
            assert config["services"][service_name]["environment"][
                "QI_SYMBOL_RECOGNITION_MODE"
            ] == "production_uncertainty"


def test_api_and_worker_bind_mount_the_current_backend_source() -> None:
    """Development runtime must execute the selected worktree's backend source."""
    services = _rendered_compose_config()["services"]

    for service_name in ("api", "worker"):
        assert services[service_name]["environment"][
            "PYTHONDONTWRITEBYTECODE"
        ] == "1"
        source_mounts = [
            mount
            for mount in services[service_name].get("volumes", [])
            if mount.get("type") == "bind" and mount.get("target") == "/app"
        ]
        assert source_mounts == [
            {
                "type": "bind",
                "source": str(ROOT / "backend"),
                "target": "/app",
                "bind": {},
            }
        ]


def test_api_reloads_when_mounted_backend_source_changes() -> None:
    """The development API process must watch its bind-mounted source."""
    api_command = _rendered_compose_config()["services"]["api"]["command"]

    assert "--reload" in api_command


def test_compose_project_and_data_volumes_are_worktree_scoped() -> None:
    """Default Compose resources must not share one fixed cross-worktree owner."""
    source = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    assert "name" not in source

    main = _rendered_compose_config("quality-inspection-main")
    feature = _rendered_compose_config("quality-inspection-feature")

    assert main["name"] == "quality-inspection-main"
    assert feature["name"] == "quality-inspection-feature"
    assert main["networks"]["default"]["name"] == "quality-inspection-main_default"
    assert feature["networks"]["default"]["name"] == (
        "quality-inspection-feature_default"
    )
    for volume, suffix in (
        ("qi_postgres", "postgres_dev"),
        ("qi_storage", "storage_dev"),
    ):
        main_name = main["volumes"][volume]["name"]
        feature_name = feature["volumes"][volume]["name"]
        assert main_name == f"quality-inspection-main_{suffix}"
        assert feature_name == f"quality-inspection-feature_{suffix}"
        assert main_name != feature_name


def test_make_runtime_entries_use_worktree_scoped_projects() -> None:
    """Standard runtime entrypoints explicitly preserve the selected worktree."""
    for target, expected_project in (
        ("dev-local-api", "feature-a"),
        ("qa-dev-config", "feature-a-qa"),
    ):
        result = subprocess.run(
            [
                "make",
                "--dry-run",
                "QI_COMPOSE_PROJECT=feature-a",
                target,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"docker compose -p {expected_project}" in result.stdout
        assert "fuser -k" not in result.stdout

    frontend = subprocess.run(
        [
            "make",
            "--dry-run",
            "QI_COMPOSE_PROJECT=feature-a",
            "dev-local-frontend",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert frontend.returncode == 0, frontend.stdout + frontend.stderr
    assert "fuser -k" not in frontend.stdout
    assert "--strictPort" in frontend.stdout


def test_deploy_main_requires_a_live_worker_ping_before_success() -> None:
    """A deployment cannot complete until the rebuilt Celery worker replies."""
    result = subprocess.run(
        ["make", "--dry-run", "deploy-main"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    command = result.stdout
    assert "inspect ping --timeout=5" in command
    assert 'case "$worker_ping_output" in *pong*)' in command
    assert "Worker readiness check failed" in command
    assert "| grep -q" not in command
    assert "| rg -q" not in command
    assert command.index("up -d --remove-orphans") < command.index("inspect ping")
    assert command.index("inspect ping") < command.index("Deployment complete")


def _deploy_worker_gate_shell() -> str:
    result = subprocess.run(
        ["make", "--dry-run", "deploy-main"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    start = result.stdout.index("worker_attempt=0;")
    end = result.stdout.index("\n\tattempt=0;", start)
    return result.stdout[start:end] + "true\n"


def _run_deploy_worker_gate(
    tmp_path: Path,
    *,
    mode: str,
) -> tuple[subprocess.CompletedProcess[str], int]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "docker-attempts"
    state.write_text("0\n", encoding="utf-8")
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        'attempt=$(cat "$FAKE_DOCKER_STATE")\n'
        "attempt=$((attempt + 1))\n"
        'printf "%s\\n" "$attempt" >"$FAKE_DOCKER_STATE"\n'
        'case "$FAKE_DOCKER_MODE" in\n'
        "  pong-after-three)\n"
        '    if [ "$attempt" -ge 3 ]; then\n'
        '      printf "%s\\n" "-> celery@worker: OK" "        pong"\n'
        "      exit 0\n"
        "    fi\n"
        "    exit 69\n"
        "    ;;\n"
        "  zero-without-pong)\n"
        '    printf "%s\\n" "1 node online."\n'
        "    exit 0\n"
        "    ;;\n"
        "  always-fail) exit 69 ;;\n"
        "esac\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    fake_sleep = bin_dir / "sleep"
    fake_sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_sleep.chmod(0o755)
    environment = dict(os.environ)
    environment.update(
        {
            "FAKE_DOCKER_MODE": mode,
            "FAKE_DOCKER_STATE": str(state),
            "PATH": f"{bin_dir}:{environment['PATH']}",
        }
    )
    result = subprocess.run(
        ["sh", "-c", _deploy_worker_gate_shell()],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result, int(state.read_text(encoding="utf-8").strip())


def test_deploy_worker_gate_retries_until_a_worker_replies(tmp_path: Path) -> None:
    result, attempts = _run_deploy_worker_gate(tmp_path, mode="pong-after-three")

    assert result.returncode == 0, result.stdout + result.stderr
    assert attempts == 3
    assert "pong" in result.stdout


def test_deploy_worker_gate_fails_closed_without_a_pong(tmp_path: Path) -> None:
    for mode in ("always-fail", "zero-without-pong"):
        case_path = tmp_path / mode
        case_path.mkdir()
        result, attempts = _run_deploy_worker_gate(case_path, mode=mode)

        assert result.returncode == 1
        assert attempts == 30
        assert "Worker readiness check failed" in result.stderr


def test_qa_compose_volumes_are_worktree_scoped() -> None:
    """QA-dev data and dependency volumes follow its isolated project owner."""
    main = _rendered_qa_compose_config("quality-inspection-main-qa")
    feature = _rendered_qa_compose_config("quality-inspection-feature-qa")

    for volume, suffix in (
        ("qi_postgres", "postgres_qa_dev"),
        ("qi_storage", "storage_qa_dev"),
        ("qi_frontend_node_modules", "frontend_node_modules_qa_dev"),
    ):
        main_name = main["volumes"][volume]["name"]
        feature_name = feature["volumes"][volume]["name"]
        assert main_name == f"quality-inspection-main-qa_{suffix}"
        assert feature_name == f"quality-inspection-feature-qa_{suffix}"
        assert main_name != feature_name


def test_legacy_qa_runtime_has_a_non_destructive_cleanup_target() -> None:
    """The old fixed QA project can be retired without deleting its volumes."""
    result = subprocess.run(
        ["make", "--dry-run", "qa-dev-down-legacy"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "docker compose -p quality-inspection-qa" in result.stdout
    assert "down --remove-orphans" in result.stdout
    assert "--volumes" not in result.stdout


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
