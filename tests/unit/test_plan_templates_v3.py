from research_navigator.plans.service import build_plan_items


def test_reading_template_is_reading_focused() -> None:
    items = build_plan_items(plan_kind="reading", objective="读懂这篇论文")
    categories = [item["category"] for item in items]
    assert categories == [
        "reading_question",
        "reading_triage",
        "core_reading",
        "evidence_notes",
        "direction_link",
        "reading_output",
    ]
    assert "minimal_experiment" not in categories
    assert "risk_check" not in categories


def test_exploration_template_contains_counter_search() -> None:
    items = build_plan_items(plan_kind="exploration", objective="验证一个研究问题")
    categories = [item["category"] for item in items]
    assert categories == [
        "exploration_question",
        "support_search",
        "counter_search",
        "neighbor_comparison",
        "minimal_validation",
        "decision_gate",
    ]


def test_reading_and_exploration_templates_are_substantively_different() -> None:
    reading = build_plan_items(plan_kind="reading", objective="同一目标")
    exploration = build_plan_items(plan_kind="exploration", objective="同一目标")
    assert [item["category"] for item in reading] != [item["category"] for item in exploration]
    assert [item["title"] for item in reading] != [item["title"] for item in exploration]
    assert [item["expected_output"] for item in reading] != [
        item["expected_output"] for item in exploration
    ]


def test_confirmed_gap_template_preserves_rigorous_steps() -> None:
    categories = [
        item["category"]
        for item in build_plan_items(
            plan_kind="confirmed_gap", objective="验证已确认缺口", gap_claim="缺口主张"
        )
    ]
    for category in (
        "reproduction",
        "dataset_preparation",
        "minimal_experiment",
        "risk_check",
        "milestone",
    ):
        assert category in categories


def test_manual_template_has_one_editable_action() -> None:
    items = build_plan_items(plan_kind="manual", objective="联系合作者")
    assert len(items) == 1
    assert items[0]["category"] == "manual_action"
