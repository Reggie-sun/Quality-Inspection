from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / ".agent/harness"


def _provider_contract_module() -> ModuleType:
    path = HARNESS / "scripts/run-provider-contracts.py"
    spec = importlib.util.spec_from_file_location("test_run_provider_contracts", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def provider_contract_network_tripwire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture Provider contract tests must never open a network connection."""

    def blocked_network(*_args, **_kwargs):
        raise AssertionError("fixture Provider contract attempted network access")

    monkeypatch.setattr(socket, "create_connection", blocked_network)
    monkeypatch.setattr(socket.socket, "connect", blocked_network)


@pytest.fixture
def tencent_fixture() -> dict:
    document = _provider_contract_module().load_fixture(
        HARNESS / "fixtures/providers/tencent-ocr/general-accurate-v1.json"
    )
    return document["payload"]


@pytest.fixture
def qwen_fixture() -> dict:
    document = _provider_contract_module().load_fixture(
        HARNESS / "fixtures/providers/qwen-vl/candidate-review-v1.json"
    )
    return document["payload"]
