from pathlib import Path

WRAPPER = (
    Path(__file__).parents[2]
    / "scripts"
    / "deployment"
    / "run_preview_acceptance_fixture_controller.ps1"
)


def _audit_block() -> str:
    source = WRAPPER.read_text(encoding="utf-8")
    start = source.index("if ($Audit) {", source.index("$controller"))
    end = source.index("$manifestPath =", start)
    return source[start:end]


def test_audit_uses_verified_docker_runtime_without_host_python() -> None:
    audit = _audit_block()
    source = WRAPPER.read_text(encoding="utf-8")

    assert "Get-Command python" not in audit
    assert "Get-Command docker" in source
    assert "rn223-schema-audit:py312-libsql020" in source
    assert "$dockerImage" in audit
    assert "'--network', 'none'" in audit
    assert "preview_fixture_controller.py" in audit
    assert "'audit'" in audit
    assert "Read-Host" not in audit


def test_audit_mount_is_read_only_and_other_modes_keep_verified_contract() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    audit = _audit_block()

    assert "target=/workspace,readonly" in audit
    assert "'--workdir', '/workspace'" in audit
    assert "'dry-run'" in source
    assert "'execute'" in source
    assert "'verify'" in source
    assert "--manifest-sha256" in source
    assert "TURSO_AUTH_TOKEN" in source
    assert "R2_SECRET_ACCESS_KEY" in source
    assert "finally" in source
