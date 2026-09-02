import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PARITY_DIR = ROOT / "deployment" / "cloud" / "parity"
sys.path.insert(0, str(PARITY_DIR))

import run_evidence_workflow_parity as parity  # noqa: E402


SHA = "a" * 40


def test_source_commit_fails_closed_without_env_or_git(monkeypatch):
    monkeypatch.delenv("RN_SOURCE_COMMIT", raising=False)
    monkeypatch.setattr(parity.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Source commit unavailable"):
        parity.resolve_source_commit()


def test_source_commit_uses_valid_host_value_without_git(monkeypatch):
    monkeypatch.setenv("RN_SOURCE_COMMIT", SHA)
    monkeypatch.setattr(parity.shutil, "which", lambda _: None)
    assert parity.resolve_source_commit() == SHA


def test_source_commit_rejects_malformed_host_value(monkeypatch):
    monkeypatch.setenv("RN_SOURCE_COMMIT", "not-a-sha")
    monkeypatch.setattr(parity.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="invalid"):
        parity.resolve_source_commit()


def test_source_commit_falls_back_to_git(monkeypatch):
    monkeypatch.delenv("RN_SOURCE_COMMIT", raising=False)
    monkeypatch.setattr(parity.shutil, "which", lambda _: "git")
    monkeypatch.setattr(parity.subprocess, "check_output", lambda *args, **kwargs: SHA + "\n")
    assert parity.resolve_source_commit() == SHA


def test_receipt_records_exact_commit_and_source_without_secrets(monkeypatch):
    monkeypatch.setenv("RN_SOURCE_COMMIT", SHA)
    monkeypatch.setenv("RN_SOURCE_COMMIT_SOURCE", "HOST_CONTEXT_GUARD")
    receipt = parity._safe_receipt("synthetic-execution")
    assert receipt["source_commit"] == SHA
    assert receipt["source_commit_source"] == "HOST_CONTEXT_GUARD"
    serialized = str(receipt)
    assert "TURSO_AUTH_TOKEN" not in serialized
    assert "R2_SECRET_ACCESS_KEY" not in serialized
    assert "Authorization" not in serialized
