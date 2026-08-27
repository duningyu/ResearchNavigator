"""Authenticated client for MCP tools to call the local ResearchNavigator API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


class MCPConfigurationError(RuntimeError):
    pass


class ResearchNavigatorClient:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (
            base_url or os.getenv("RN_API_BASE_URL") or "http://127.0.0.1:8000/api"
        ).rstrip("/")
        self.token = token or os.getenv("RN_MCP_ACCESS_TOKEN")
        timeout_seconds = self._timeout_seconds("RN_MCP_TIMEOUT_SECONDS", default=30.0)
        upload_timeout_seconds = self._timeout_seconds(
            "RN_MCP_UPLOAD_TIMEOUT_SECONDS", default=60.0
        )
        self.timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
        self.upload_timeout = httpx.Timeout(
            upload_timeout_seconds, connect=min(10.0, upload_timeout_seconds)
        )

    @staticmethod
    def _timeout_seconds(name: str, *, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = float(raw)
        except ValueError as exc:
            raise MCPConfigurationError(f"{name} must be a number") from exc
        if not 0.1 <= value <= 120.0:
            raise MCPConfigurationError(f"{name} must be between 0.1 and 120 seconds")
        return value

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            raise MCPConfigurationError(
                "RN_MCP_ACCESS_TOKEN is required; MCP workspace calls are user-scoped."
            )
        return {"Authorization": f"Bearer {self.token}"}

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.request(method, path, headers=self.headers, **kwargs)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {"status": "ok", "http_status": response.status_code}
            return response.json()

    async def request_object(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        payload = await self.request(method, path, **kwargs)
        if not isinstance(payload, dict):
            raise TypeError("ResearchNavigator API response must be a JSON object")
        return payload

    async def upload_pdf(
        self, paper_id: int, file_path: str, *, rights_confirmed: bool
    ) -> dict[str, Any]:
        if not rights_confirmed:
            raise ValueError("rights_confirmed must be true")
        path = Path(file_path).expanduser().resolve()
        allowed_root = Path(os.getenv("RN_MCP_ALLOWED_UPLOAD_ROOT", Path.cwd())).resolve()
        if path != allowed_root and allowed_root not in path.parents:
            raise ValueError("file_path is outside RN_MCP_ALLOWED_UPLOAD_ROOT")
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("file_path must reference an existing PDF")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.upload_timeout) as client:
            with path.open("rb") as handle:
                response = await client.post(
                    f"/papers/{paper_id}/upload",
                    headers=self.headers,
                    files={"file": (path.name, handle, "application/pdf")},
                    data={"rights_confirmed": "true"},
                )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {"status": "ok", "http_status": response.status_code}
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("ResearchNavigator API response must be a JSON object")
            return payload
