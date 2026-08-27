"""Federated lawful OA candidate resolution."""

from __future__ import annotations

from collections.abc import Iterable

from research_navigator.open_access.base import (
    OpenAccessCandidate,
    OpenAccessClient,
    OpenAccessResolution,
    PaperIdentity,
)
from research_navigator.open_access.policy import decide_access

_PRIORITY = {
    "auto_ingest": 0,
    "requires_user_confirmation": 1,
    "link_only": 2,
    "rejected": 3,
}


class OpenAccessResolver:
    def __init__(self, clients: Iterable[OpenAccessClient]) -> None:
        self.clients = list(clients)

    async def resolve(self, identity: PaperIdentity) -> OpenAccessResolution:
        candidates: list[OpenAccessCandidate] = []
        statuses: dict[str, str] = {}
        errors: dict[str, str] = {}
        seen: set[tuple[str, str | None, str | None]] = set()
        for client in self.clients:
            try:
                source_candidates = await client.resolve(identity)
                statuses[client.name] = "ok"
            except Exception as exc:
                statuses[client.name] = "error"
                errors[client.name] = f"{type(exc).__name__}: {exc}"
                continue
            for raw in source_candidates:
                evaluated = decide_access(raw)
                key = (evaluated.source, evaluated.pdf_url, evaluated.landing_url)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(evaluated)
        ordered = sorted(
            candidates,
            key=lambda item: (
                _PRIORITY[item.access_decision],
                item.source,
                item.pdf_url or item.landing_url or "",
            ),
        )
        selected = next(
            (item for item in ordered if item.access_decision != "rejected"), None
        )
        return OpenAccessResolution(
            candidates=ordered,
            selected=selected,
            source_status=statuses,
            errors=errors,
        )
