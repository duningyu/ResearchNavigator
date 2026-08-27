#!/usr/bin/env python3
"""Export one user's local workspace without secrets or password hashes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from research_navigator.db import Database
from research_navigator.models import (
    Favorite,
    GapCandidate,
    Note,
    PlanItem,
    ResearchPlan,
    ResearchProfile,
    ResearchProject,
    User,
)


def row_dict(row: object, fields: tuple[str, ...]) -> dict[str, object]:
    return {field: getattr(row, field) for field in fields}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("runtime/research_navigator.db"))
    parser.add_argument("--email", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database = Database.from_url(f"sqlite+pysqlite:///{args.database.resolve().as_posix()}")
    with database.session() as session:
        user = session.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            raise SystemExit("User not found")
        profile = session.scalar(select(ResearchProfile).where(ResearchProfile.user_id == user.id))
        projects = list(
            session.scalars(select(ResearchProject).where(ResearchProject.user_id == user.id))
        )
        plans = list(session.scalars(select(ResearchPlan).where(ResearchPlan.user_id == user.id)))
        payload = {
            "format_version": 1,
            "user": row_dict(user, ("id", "email", "display_name")),
            "profile": None
            if profile is None
            else row_dict(
                profile,
                (
                    "stage",
                    "major",
                    "broad_direction",
                    "keywords_json",
                    "excluded_terms_json",
                    "preferences_json",
                    "compute_constraints",
                ),
            ),
            "projects": [
                row_dict(
                    row,
                    (
                        "id",
                        "name",
                        "description",
                        "broad_direction",
                        "status",
                        "created_at",
                        "updated_at",
                    ),
                )
                for row in projects
            ],
            "favorites": [
                row_dict(row, ("paper_id", "created_at"))
                for row in session.scalars(select(Favorite).where(Favorite.user_id == user.id))
            ],
            "notes": [
                row_dict(row, ("paper_id", "content", "note_type", "created_at", "updated_at"))
                for row in session.scalars(select(Note).where(Note.user_id == user.id))
            ],
            "gaps": [
                row_dict(
                    row,
                    (
                        "id",
                        "project_id",
                        "claim",
                        "status",
                        "evidence_matrix_json",
                        "counter_evidence_json",
                        "challenge_queries_json",
                        "not_novelty_proof",
                        "created_at",
                    ),
                )
                for row in session.scalars(
                    select(GapCandidate).where(GapCandidate.user_id == user.id)
                )
            ],
            "plans": [
                {
                    **row_dict(
                        plan,
                        (
                            "id",
                            "project_id",
                            "gap_id",
                            "title",
                            "objective",
                            "status",
                            "created_at",
                        ),
                    ),
                    "items": [
                        row_dict(
                            item,
                            (
                                "id",
                                "category",
                                "title",
                                "description",
                                "sequence",
                                "status",
                                "notes",
                            ),
                        )
                        for item in session.scalars(
                            select(PlanItem)
                            .where(PlanItem.plan_id == plan.id)
                            .order_by(PlanItem.sequence)
                        )
                    ],
                }
                for plan in plans
            ],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
