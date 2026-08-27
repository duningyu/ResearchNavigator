from datetime import date

from research_navigator.scholarly.crossref import _first_date


def test_first_date_skips_null_components_and_uses_next_valid_candidate() -> None:
    item = {
        "published-print": {"date-parts": [[None, None, None]]},
        "published-online": {"date-parts": [[2024, 7]]},
    }

    assert _first_date(item) == date(2024, 7, 1)


def test_first_date_treats_missing_month_and_day_as_first_day() -> None:
    assert _first_date({"issued": {"date-parts": [[2023]]}}) == date(2023, 1, 1)
