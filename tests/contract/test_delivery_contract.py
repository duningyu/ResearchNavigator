import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_required_product_technical_and_deployment_artifacts_exist() -> None:
    required = [
        ".env.example",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "infra/docker-compose.yml",
        "infra/api.Dockerfile",
        "infra/web.Dockerfile",
        "docs/PRD.md",
        "docs/TECHDOC_INDEX.md",
        "docs/architecture.md",
        "docs/database-design.md",
        "docs/api-design.md",
        "docs/mcp-design.md",
        "docs/rag-design.md",
        "docs/agent-workflow.md",
        "docs/research-gap-method.md",
        "docs/data-source-contracts.md",
        "docs/security-and-compliance.md",
        "docs/evaluation-plan.md",
        "docs/deployment-runbook.md",
        "docs/claim-boundary.md",
        "docs/requirement-traceability.md",
        "docs/releases/V1.0.0.md",
        "docs/releases/V2.0.0.md",
        "docs/releases/V2.1.0.md",
        "docs/releases/V2.2.0.md",
        "scripts/backup.py",
        "scripts/restore.py",
        "scripts/export_workspace.py",
        "scripts/export_openapi.py",
        "scripts/verify_delivery.py",
        "AGENTS.md",
        "CODEX_AUDIT_AND_COMPLETION_PROMPT.md",
        "delivery/README.md",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    assert not missing, f"Missing delivery artifacts: {missing}"


def test_compose_has_persistent_runtime_and_separate_web_api_worker_services() -> None:
    compose = yaml.safe_load((ROOT / "infra/docker-compose.yml").read_text())
    services = compose["services"]
    assert {"web", "api", "worker"} <= set(services)
    assert any("runtime" in str(volume) for volume in services["api"].get("volumes", []))
    assert any("runtime" in str(volume) for volume in services["worker"].get("volumes", []))


def test_example_configuration_contains_no_committed_real_secret() -> None:
    content = (ROOT / ".env.example").read_text()
    forbidden = ("sk-", "Bearer eyJ", "BEGIN PRIVATE KEY", "password=research")
    assert not any(token in content for token in forbidden)
    assert "LLM_API_KEY=" in content
    assert "SEMANTIC_SCHOLAR_API_KEY=" in content


def test_openapi_contract_includes_v1_v2_and_completion_endpoints() -> None:
    from research_navigator.config import Settings
    from research_navigator.main import create_app

    state = ROOT / ".pytest-openapi-state"
    settings = Settings(
        data_dir=state,
        database_url=f"sqlite+pysqlite:///{(state / 'contract.db').as_posix()}",
        upload_dir=state / "uploads",
        vector_dir=state / "vectors",
        backup_dir=state / "backups",
        allowed_origins=("http://localhost:5173",),
        enable_fixture_source=True,
        enable_openalex=False,
        enable_crossref=False,
        enable_arxiv=False,
        enable_semantic_scholar=False,
        semantic_scholar_api_key=None,
        unpaywall_email=None,
        crossref_mailto=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
        max_pdf_bytes=1_000_000,
        session_ttl_hours=24,
        environment="contract",
    )
    paths = create_app(settings).openapi()["paths"]
    required = {
        "/api/search/papers",
        "/api/search/sessions/{session_id}",
        "/api/search/sessions/{session_id}/papers",
        "/api/search/sessions/{session_id}/rerun",
        "/api/papers/resolve",
        "/api/papers/{paper_id}/related",
        "/api/papers/{paper_id}/analyze",
        "/api/papers/{paper_id}/documents",
        "/api/paper-sets",
        "/api/paper-sets/{paper_set_id}",
        "/api/comparisons",
        "/api/comparisons/{comparison_id}",
        "/api/gaps/generate",
        "/api/gaps/{gap_id}/challenge",
        "/api/gaps/{gap_id}/confirm",
        "/api/jobs",
        "/api/jobs/{job_id}/cancel",
        "/api/sources/{source_name}/test",
        "/api/settings/me",
        "/api/admin/runtime-config",
        "/api/admin/backups",
        "/api/admin/backups/{name}/stage-restore",
        "/api/workspace/export",
        "/api/documents/{document_id}",
        "/api/papers/{paper_id}/evidence-workflows",
        "/api/evidence-workflows/{job_id}",
        "/api/admin/backfills/abstract-provenance",
        "/api/papers/{paper_id}/authors",
        "/api/papers/{paper_id}/datasets",
        "/api/projects/{project_id}/direction-clusters",
        "/api/direction-clusters/{run_id}",
        "/api/evaluations/studies",
    }
    assert required <= set(paths)
    assert (ROOT / "scripts/export_openapi.py").is_file()


def test_feedback_closure_traceability_matrix_covers_page_api_storage_and_evidence() -> None:
    content = (ROOT / "docs/requirement-traceability.md").read_text(encoding="utf-8")
    required_markers = {
        "Page—API—Storage—Evidence",
        "PaperSet",
        "Gap Explanation",
        "PDF 上传/解析/检索/删除",
        "Settings",
        "Admin",
        "备份恢复",
        "任务取消",
        "来源主动测试",
        "HTTP-first",
        "simulated_human_confirmation",
        "Playwright",
        "BLOCKED",
        "SKIPPED",
    }
    missing = sorted(marker for marker in required_markers if marker not in content)
    assert not missing, f"Traceability matrix missing feedback-closure markers: {missing}"


def test_release_scripts_are_directly_invokable() -> None:
    for script in ("scripts/verify_delivery.py", "scripts/package_release.py"):
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{script} direct invocation failed: {result.stderr}"
