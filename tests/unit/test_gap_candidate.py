from research_navigator.gaps.candidate import generate_challenge_queries, make_gap_candidate


def test_gap_candidate_is_bounded_and_never_claims_novelty_proof() -> None:
    candidate = make_gap_candidate(
        project_direction="未来窗口异常风险排序",
        paper_ids=[1, 2],
        evidence_matrix=[
            {
                "paper_id": paper_id,
                "title": f"Synthetic study {paper_id}",
                "research_problem": "未来窗口异常风险排序",
                "limitations_author_stated": ["仅在单一数据集验证"],
                "field_states": {
                    "research_problem": "evidenced",
                    "limitations_author_stated": "evidenced",
                },
                "field_citations": {
                    field: [
                        {
                            "source_type": "abstract",
                            "section": "Abstract",
                            "supporting_text": text,
                            "material_verified": True,
                        }
                    ]
                    for field, text in [
                        ("research_problem", "未来窗口异常风险排序"),
                        ("limitations_author_stated", "仅在单一数据集验证"),
                    ]
                },
            }
            for paper_id in [1, 2]
        ],
    )

    assert candidate.not_novelty_proof is True
    assert "本次检索范围" in candidate.claim
    assert "从未" not in candidate.claim
    assert candidate.status == "generated"


def test_challenge_queries_expand_task_synonyms_and_counter_evidence_routes() -> None:
    queries = generate_challenge_queries("历史窗口到未来 Horizon 的异常风险排序与固定告警预算")

    assert len(queries) >= 5
    assert any("early warning" in query.lower() for query in queries)
    assert any("failure prediction" in query.lower() for query in queries)
    assert len(set(queries)) == len(queries)
