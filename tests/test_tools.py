from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestRouter:
    def test_exact_match(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [
                    {"value": "hello", "match": "exact", "branch": "greet"},
                ],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "  hello  "}}]}
        result = router(config, session)
        assert result == "greet"

    def test_contains_match(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [
                    {"value": "bye", "match": "contains", "branch": "farewell"},
                ],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "goodbye now"}}]}
        result = router(config, session)
        assert result == "farewell"

    def test_startswith_match(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [
                    {"value": "help", "match": "startswith", "branch": "assist"},
                ],
                "default": "fallback",
            }
        }
        session = {
            "nodes": [{"name": "input", "data": {"text": "help me please"}}]
        }
        result = router(config, session)
        assert result == "assist"

    def test_default_route(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [
                    {"value": "exact match", "match": "exact", "branch": "a"},
                ],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "no match here"}}]}
        result = router(config, session)
        assert result == "fallback"

    def test_no_rules_returns_default(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "hello"}}]}
        result = router(config, session)
        assert result == "fallback"

    def test_empty_session_returns_default(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [{"value": "x", "match": "exact", "branch": "x"}],
                "default": "fallback",
            }
        }
        session = {"nodes": []}
        result = router(config, session)
        assert result == "fallback"

    def test_case_insensitive(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "match_field": "text",
                "rules": [
                    {"value": "HELLO", "match": "exact", "branch": "greet"},
                ],
                "default": "fallback",
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "hello"}}]}
        result = router(config, session)
        assert result == "greet"

    def test_default_value_empty(self):
        from src.engine.tools.router import router

        config = {
            "router": {
                "rules": [{"value": "x", "match": "exact", "branch": "x"}],
            }
        }
        session = {"nodes": [{"name": "input", "data": {"text": "y"}}]}
        result = router(config, session)
        assert result == ""


class TestMergeBranches:
    def test_merges_two_branches(self):
        from src.engine.tools.merge import merge_branches

        session = {
            "nodes": [
                {"name": "switch", "data": {}, "timestamp": 1.0},
            ]
        }
        branches = {
            "b1": [
                {
                    "name": "n1",
                    "pre": "",
                    "data": {"text": "a"},
                    "timestamp": 2.0,
                    "metrics": {},
                },
            ],
            "b2": [
                {
                    "name": "n2",
                    "pre": "",
                    "data": {"text": "b"},
                    "timestamp": 3.0,
                    "metrics": {},
                },
            ],
        }
        merge_branches(session, 0, branches)

        assert len(session["nodes"]) > 1
        switch = session["nodes"][0]
        assert "branches" in switch
        assert set(switch["branches"].keys()) == {"b1", "b2"}

    def test_branch_pre_filled(self):
        from src.engine.tools.merge import merge_branches

        session = {
            "nodes": [
                {"name": "sw", "data": {}, "timestamp": 1.0},
            ]
        }
        branches = {
            "b1": [
                {
                    "name": "child",
                    "pre": "",
                    "data": {"text": "x"},
                    "timestamp": 2.0,
                    "metrics": {},
                },
            ],
        }
        merge_branches(session, 0, branches)

        child = [n for n in session["nodes"] if n["name"] == "child"]
        assert len(child) == 1
        assert child[0]["pre"] == "sw"

    def test_sort_by_timestamp(self):
        from src.engine.tools.merge import merge_branches

        session = {
            "nodes": [
                {"name": "sw", "data": {}, "timestamp": 1.0},
            ]
        }
        branches = {
            "b1": [
                {
                    "name": "late",
                    "pre": "",
                    "data": {"text": "late"},
                    "timestamp": 5.0,
                    "metrics": {},
                },
            ],
            "b2": [
                {
                    "name": "early",
                    "pre": "",
                    "data": {"text": "early"},
                    "timestamp": 2.0,
                    "metrics": {},
                },
            ],
        }
        merge_branches(session, 0, branches)

        merged_names = [n["name"] for n in session["nodes"][1:]]
        assert merged_names[0] == "early"
        assert merged_names[1] == "late"

    def test_empty_branch_ok(self):
        from src.engine.tools.merge import merge_branches

        session = {
            "nodes": [
                {"name": "sw", "data": {}, "timestamp": 1.0},
            ]
        }
        branches = {"b1": []}
        merge_branches(session, 0, branches)

        switch = session["nodes"][0]
        assert switch["branches"]["b1"]["start"] == switch["branches"]["b1"]["end"]
