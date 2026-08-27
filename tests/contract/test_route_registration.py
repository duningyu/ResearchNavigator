from __future__ import annotations

from collections import Counter

from research_navigator.main import app


def test_each_http_method_and_path_is_registered_once() -> None:
    route_keys = [
        (method, route.path)
        for route in app.routes
        for method in sorted(getattr(route, "methods", set()) or set())
    ]
    duplicates = {key: count for key, count in Counter(route_keys).items() if count > 1}
    assert duplicates == {}
