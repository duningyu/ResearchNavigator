from pathlib import Path


def test_public_demo_migrations_use_the_isolated_database() -> None:
    script = Path("scripts/deployment/start_public_demo.ps1").read_text(encoding="utf-8")

    assert "$env:RN_DATABASE_URL" in script
    assert "research_navigator.db" in script


def test_public_demo_stop_script_does_not_overwrite_powershell_pid() -> None:
    script = Path("scripts/deployment/stop_public_demo.ps1").read_text(encoding="utf-8")

    assert "foreach ($pid " not in script.lower()
    assert "foreach ($ownedpid " in script.lower()
