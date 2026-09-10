"""Explicit synthetic cited materials for positive lifecycle tests; SQLite only."""

from fastapi import FastAPI
from sqlalchemy import select

from research_navigator.analysis.structured import CitationLocator, PaperAnalysisOutput
from research_navigator.models import Paper, PaperAnalysisRecord, ResearchProject


def add_cited_materials(app: FastAPI, project_id: int, paper_ids: list[int]) -> None:
    with app.state.database.session() as session:
        assert session.bind.dialect.name == "sqlite"
        project = session.get(ResearchProject, project_id)
        assert project is not None
        direction = project.broad_direction or project.name
        for paper_id in paper_ids:
            paper = session.get(Paper, paper_id)
            assert paper is not None
            problem = f"This synthetic study investigates {direction}."
            limitation = "This synthetic evaluation is limited to a single laboratory dataset."
            future = "The authors propose testing transfer to an independent dataset."
            paper.abstract = " ".join([problem, limitation, future])
            fields = {
                "research_problem": problem,
                "limitations_author_stated": limitation,
                "future_work_explicit": future,
            }
            output = PaperAnalysisOutput(
                paper_id=paper_id,
                evidence_level="abstract_only",
                summary=problem,
                executive_summary=problem,
                research_problem=problem,
                limitations_author_stated=[limitation],
                future_work_explicit=[future],
                field_states={field: "evidenced" for field in fields},
                field_citations={
                    field: [
                        CitationLocator(
                            source_type="abstract", section="Abstract", supporting_text=text
                        )
                    ]
                    for field, text in fields.items()
                },
            )
            row = session.scalar(
                select(PaperAnalysisRecord)
                .where(
                    PaperAnalysisRecord.paper_id == paper_id,
                    PaperAnalysisRecord.user_id == project.user_id,
                    PaperAnalysisRecord.project_id == project_id,
                )
                .order_by(PaperAnalysisRecord.created_at.desc(), PaperAnalysisRecord.id.desc())
            )
            if row is None:
                row = PaperAnalysisRecord(
                    user_id=project.user_id,
                    paper_id=paper_id,
                    project_id=project_id,
                    evidence_level="abstract_only",
                    analysis_version="structured-v3",
                    direction_similarity_json="{}",
                    reproduction_assessment_json="{}",
                )
                session.add(row)
            row.analysis_json = output.model_dump_json()
        session.commit()
