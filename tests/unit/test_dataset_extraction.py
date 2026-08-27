from research_navigator.datasets.service import extract_split_evidence


def test_abstract_never_infers_dataset_splits() -> None:
    result = extract_split_evidence(
        evidence_level="abstract_only",
        protocol=["We use an 80/20 train/test split."],
    )
    assert result == {"train_split": None, "validation_split": None, "test_split": None}


def test_fulltext_preserves_explicit_split_sentences_only() -> None:
    result = extract_split_evidence(
        evidence_level="open_fulltext",
        protocol=[
            "The training split contains the first 80 percent.",
            "The validation split uses the next 10 percent.",
            "The test split uses the final 10 percent.",
        ],
    )
    assert result["train_split"].startswith("The training")
    assert result["validation_split"].startswith("The validation")
    assert result["test_split"].startswith("The test")
