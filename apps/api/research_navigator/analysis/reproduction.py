"""Observable-evidence reproduction assessment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from research_navigator.analysis.structured import PaperAnalysisOutput
from research_navigator.models import Paper

DimensionStatus = Literal["verified", "partial", "unknown", "missing"]


class ReproductionDimension(BaseModel):
    name: str
    weight: float
    status: DimensionStatus
    score: float | None
    evidence: str
    source: str | None = None


class ReproductionAssessment(BaseModel):
    score: float
    evidence_coverage: float
    dimensions: list[ReproductionDimension]
    estimated_difficulty: str
    estimated_compute_level: str
    blocking_reasons: list[str]
    recommended_first_step: str
    score_version: str = "reproduction-v1"


def calculate_reproduction_assessment(
    dimensions: list[ReproductionDimension],
) -> ReproductionAssessment:
    known = [item for item in dimensions if item.status != "unknown"]
    available_weight = sum(item.weight for item in known)
    total_weight = sum(item.weight for item in dimensions)
    weighted = sum(item.weight * float(item.score or 0.0) for item in known)
    score = 0.0 if available_weight == 0 else 100 * weighted / available_weight
    blocking = [item.name for item in dimensions if item.status == "missing"]
    difficulty = "high" if blocking or score < 45 else "medium" if score < 75 else "low"
    return ReproductionAssessment(
        score=round(score, 2),
        evidence_coverage=round(available_weight / total_weight, 4) if total_weight else 0.0,
        dimensions=dimensions,
        estimated_difficulty=difficulty,
        estimated_compute_level="unknown",
        blocking_reasons=blocking,
        recommended_first_step=(
            "先解决缺失的数据、代码或协议阻断项。"
            if blocking
            else "先运行作者基线或最小公开数据集实验。"
        ),
    )


def assess_reproduction(paper: Paper, analysis: PaperAnalysisOutput) -> ReproductionAssessment:
    urls = " ".join(
        [paper.publisher_url or "", paper.pdf_url or "", paper.source_urls_json]
    ).lower()
    has_repo = "github.com" in urls or "gitlab.com" in urls
    fulltext = analysis.evidence_level in {
        "open_fulltext",
        "user_uploaded_fulltext",
        "publisher_authorized_fulltext",
    }
    dimensions = [
        ReproductionDimension(
            name="code_availability",
            weight=0.20,
            status="verified" if has_repo else "unknown",
            score=1.0 if has_repo else None,
            evidence="发现可验证代码仓库链接。" if has_repo else "当前来源未完成代码仓库核验。",
        ),
        ReproductionDimension(
            name="data_availability",
            weight=0.20,
            status="partial" if analysis.datasets else "unknown",
            score=0.5 if analysis.datasets else None,
            evidence="正文/摘要提及数据集，但未验证下载与许可。"
            if analysis.datasets
            else "未验证数据可用性。",
        ),
        ReproductionDimension(
            name="method_completeness",
            weight=0.15,
            status="verified"
            if fulltext and analysis.methods
            else "partial"
            if analysis.methods
            else "unknown",
            score=0.9 if fulltext and analysis.methods else 0.45 if analysis.methods else None,
            evidence="已访问全文方法证据。" if fulltext else "仅依据摘要或元数据。",
        ),
        ReproductionDimension(
            name="environment_documentation",
            weight=0.10,
            status="unknown",
            score=None,
            evidence="未检查环境锁定文件。",
        ),
        ReproductionDimension(
            name="hyperparameter_documentation",
            weight=0.10,
            status="partial" if fulltext else "unknown",
            score=0.5 if fulltext else None,
            evidence="全文可访问，但尚未进行参数完整性逐项审计。"
            if fulltext
            else "摘要不能支持参数审计。",
        ),
        ReproductionDimension(
            name="compute_fit",
            weight=0.10,
            status="unknown",
            score=None,
            evidence="未取得可信算力成本证据。",
        ),
        ReproductionDimension(
            name="evaluation_protocol",
            weight=0.10,
            status="partial" if analysis.metrics else "unknown",
            score=0.5 if analysis.metrics else None,
            evidence="发现评价指标，但尚未核验切分和实现协议。"
            if analysis.metrics
            else "未找到评价协议信息。",
        ),
        ReproductionDimension(
            name="license_clarity",
            weight=0.05,
            status="unknown",
            score=None,
            evidence="未核验代码和数据许可证。",
        ),
    ]
    return calculate_reproduction_assessment(dimensions)
