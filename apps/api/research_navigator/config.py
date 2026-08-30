"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _as_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with local-first defaults."""

    data_dir: Path
    database_url: str
    upload_dir: Path
    vector_dir: Path
    backup_dir: Path
    allowed_origins: tuple[str, ...]
    enable_fixture_source: bool
    enable_openalex: bool
    enable_crossref: bool
    enable_arxiv: bool
    enable_semantic_scholar: bool
    semantic_scholar_api_key: str | None
    unpaywall_email: str | None
    crossref_mailto: str | None
    llm_base_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    max_pdf_bytes: int
    session_ttl_hours: int
    environment: str
    openalex_api_key: str | None = None
    analysis_provider: str = "deterministic"
    analysis_prompt_version: str = "paper-analysis-v2"
    llm_timeout_seconds: float = 20.0
    llm_max_attempts: int = 2
    public_demo_mode: bool = False
    public_demo_max_users: int = 50
    public_demo_max_upload_mb: int = 10
    public_demo_max_active_jobs: int = 5
    public_demo_max_query_length: int = 200
    public_demo_max_job_payload_bytes: int = 16_384

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("RN_DATA_DIR", "runtime")).expanduser().resolve()
        database_url = os.getenv(
            "RN_DATABASE_URL",
            f"sqlite+pysqlite:///{(data_dir / 'research_navigator.db').as_posix()}",
        )
        return cls(
            data_dir=data_dir,
            database_url=database_url,
            upload_dir=Path(os.getenv("RN_UPLOAD_DIR", data_dir / "uploads"))
            .expanduser()
            .resolve(),
            vector_dir=Path(os.getenv("RN_VECTOR_DIR", data_dir / "vector_index"))
            .expanduser()
            .resolve(),
            backup_dir=Path(os.getenv("RN_BACKUP_DIR", data_dir / "backups"))
            .expanduser()
            .resolve(),
            allowed_origins=_as_csv(
                os.getenv("RN_CORS_ALLOWED_ORIGINS", os.getenv("RN_ALLOWED_ORIGINS")),
                ("http://localhost:5173", "http://127.0.0.1:5173"),
            ),
            enable_fixture_source=_as_bool(os.getenv("RN_ENABLE_FIXTURE_SOURCE"), True),
            enable_openalex=_as_bool(os.getenv("RN_ENABLE_OPENALEX"), True),
            enable_crossref=_as_bool(os.getenv("RN_ENABLE_CROSSREF"), True),
            enable_arxiv=_as_bool(os.getenv("RN_ENABLE_ARXIV"), True),
            enable_semantic_scholar=_as_bool(os.getenv("RN_ENABLE_SEMANTIC_SCHOLAR"), True),
            semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None,
            unpaywall_email=os.getenv("UNPAYWALL_EMAIL") or None,
            crossref_mailto=os.getenv("CROSSREF_MAILTO") or None,
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_model=os.getenv("LLM_MODEL") or None,
            max_pdf_bytes=int(os.getenv("RN_MAX_PDF_BYTES", str(25 * 1024 * 1024))),
            session_ttl_hours=int(os.getenv("RN_SESSION_TTL_HOURS", "168")),
            environment=os.getenv("RN_ENVIRONMENT", "development"),
            openalex_api_key=os.getenv("OPENALEX_API_KEY") or None,
            analysis_provider=os.getenv("RN_ANALYSIS_PROVIDER", "deterministic").strip().lower(),
            analysis_prompt_version=os.getenv("RN_ANALYSIS_PROMPT_VERSION", "paper-analysis-v2"),
            llm_timeout_seconds=float(os.getenv("RN_LLM_TIMEOUT_SECONDS", "20")),
            llm_max_attempts=int(os.getenv("RN_LLM_MAX_ATTEMPTS", "2")),
            public_demo_mode=_as_bool(os.getenv("RN_PUBLIC_DEMO_MODE"), False),
            public_demo_max_users=int(os.getenv("RN_PUBLIC_DEMO_MAX_USERS", "50")),
            public_demo_max_upload_mb=int(os.getenv("RN_PUBLIC_DEMO_MAX_UPLOAD_MB", "10")),
            public_demo_max_active_jobs=int(
                os.getenv("RN_PUBLIC_DEMO_MAX_ACTIVE_JOBS", "5")
            ),
            public_demo_max_query_length=int(
                os.getenv("RN_PUBLIC_DEMO_MAX_QUERY_LENGTH", "200")
            ),
            public_demo_max_job_payload_bytes=int(
                os.getenv("RN_PUBLIC_DEMO_MAX_JOB_PAYLOAD_BYTES", "16384")
            ),
        )

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.vector_dir, self.backup_dir):
            path.mkdir(parents=True, exist_ok=True)
