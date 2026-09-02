"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from urllib.parse import urlsplit
from dataclasses import dataclass, field
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


def normalize_turso_database_url(provider_url: str) -> str:
    """Convert Turso's provider URL into the SQLAlchemy libsql URL shape."""
    value = provider_url.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "libsql" or not parsed.hostname:
        raise ValueError("TURSO_DATABASE_URL must be a libsql:// provider URL")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("TURSO_DATABASE_URL must not contain credentials or a port")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("TURSO_DATABASE_URL must not contain a path or query")
    return f"sqlite+libsql://{parsed.hostname}?secure=true"


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
    # Optional deployment seam fields keep legacy direct Settings(...) construction
    # local-SQLite compatible while from_env() supplies Turso values explicitly.
    database_backend: str = "sqlite"
    turso_database_url: str | None = None
    turso_auth_token: str | None = None
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
    storage_backend: str = "local"
    r2_bucket: str | None = None
    r2_account_id: str | None = None
    r2_access_key_id: str | None = field(default=None, repr=False)
    r2_secret_access_key: str | None = field(default=None, repr=False)
    r2_endpoint: str | None = None
    r2_region: str = "auto"

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("RN_DATA_DIR", "runtime")).expanduser().resolve()
        database_backend = os.getenv("DATABASE_BACKEND", "sqlite").strip().lower()
        turso_database_url = os.getenv("TURSO_DATABASE_URL") or None
        turso_auth_token = os.getenv("TURSO_AUTH_TOKEN") or None
        if database_backend == "turso":
            if not turso_database_url:
                raise ValueError("TURSO_DATABASE_URL is required for turso backend")
            if not turso_auth_token:
                raise ValueError("TURSO_AUTH_TOKEN is required for turso backend")
            database_url = os.getenv("RN_DATABASE_URL") or normalize_turso_database_url(
                turso_database_url
            )
        elif database_backend == "sqlite":
            database_url = os.getenv(
                "RN_DATABASE_URL",
                f"sqlite+pysqlite:///{(data_dir / 'research_navigator.db').as_posix()}",
            )
        else:
            raise ValueError(f"Unsupported database backend: {database_backend!r}")
        instance = cls(
            data_dir=data_dir,
            database_url=database_url,
            database_backend=database_backend,
            turso_database_url=turso_database_url,
            turso_auth_token=turso_auth_token,
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
            storage_backend=os.getenv("RN_STORAGE_BACKEND", "local").strip().lower(),
            r2_bucket=os.getenv("R2_BUCKET") or None,
            r2_account_id=os.getenv("R2_ACCOUNT_ID") or None,
            r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID") or None,
            r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY") or None,
            r2_endpoint=os.getenv("R2_ENDPOINT") or None,
            r2_region=os.getenv("R2_REGION", "auto"),
        )

        if instance.storage_backend == "r2":
            missing = [
                name for name, value in {
                    "R2_BUCKET": instance.r2_bucket,
                    "R2_ACCOUNT_ID": instance.r2_account_id,
                    "R2_ACCESS_KEY_ID": instance.r2_access_key_id,
                    "R2_SECRET_ACCESS_KEY": instance.r2_secret_access_key,
                }.items() if not value
            ]
            if missing:
                raise ValueError("R2 credentials/configuration required: " + ", ".join(missing))
        return instance

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.vector_dir, self.backup_dir):
            path.mkdir(parents=True, exist_ok=True)
