from research_navigator.documents.retrieval import (
    HybridCandidate,
    cosine_similarity,
    hashing_vector,
    rank_hybrid,
)


def test_hashing_vector_is_deterministic_and_cosine_self_is_one() -> None:
    vector = hashing_vector("future horizon anomaly risk ranking")
    assert vector == hashing_vector("future horizon anomaly risk ranking")
    assert round(cosine_similarity(vector, vector), 8) == 1.0
    assert cosine_similarity(vector, hashing_vector("image segmentation")) < 0.5


def test_hybrid_ranking_uses_lexical_and_dense_evidence() -> None:
    candidates = [
        HybridCandidate(
            chunk_id=1,
            text="The model predicts future horizon anomaly risk under an alert budget.",
            section="Method",
            page_start=2,
            page_end=2,
            lexical_score=1.0,
            dense_score=0.9,
        ),
        HybridCandidate(
            chunk_id=2,
            text="This work studies image segmentation.",
            section="Method",
            page_start=3,
            page_end=3,
            lexical_score=0.0,
            dense_score=0.1,
        ),
    ]

    ranked = rank_hybrid(candidates, top_k=2)

    assert ranked[0].chunk_id == 1
    assert ranked[0].score > ranked[1].score
    assert ranked[0].citation["page_start"] == 2
