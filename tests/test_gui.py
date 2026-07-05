from __future__ import annotations

import sys
from pathlib import Path

_proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_proj_root))


class TestDagLevels:
    def test_simple_chain(self):
        from src.gui.utils import _dag_levels

        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
            {"name": "b", "next_type": "one", "next": ""},
        ]
        levels = _dag_levels(nodes)
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]

    def test_if_then_branch(self):
        from src.gui.utils import _dag_levels

        nodes = [
            {"name": "router", "next_type": "if-then", "next": ["greet", "farewell"]},
            {"name": "greet", "next_type": "one", "next": ""},
            {"name": "farewell", "next_type": "one", "next": ""},
        ]
        levels = _dag_levels(nodes)
        assert levels[0] == ["router"]
        assert set(levels[1]) == {"greet", "farewell"}

    def test_switch(self):
        from src.gui.utils import _dag_levels

        nodes = [
            {"name": "d", "next_type": "switch", "next": ["x", "y"]},
            {"name": "x", "next_type": "one", "next": ""},
            {"name": "y", "next_type": "one", "next": ""},
        ]
        levels = _dag_levels(nodes)
        assert levels[0] == ["d"]
        assert set(levels[1]) == {"x", "y"}

    def test_empty_nodes(self):
        from src.gui.utils import _dag_levels

        assert _dag_levels([]) == [[]]

    def test_single_node(self):
        from src.gui.utils import _dag_levels

        nodes = [{"name": "solo", "next_type": "one", "next": ""}]
        levels = _dag_levels(nodes)
        assert levels == [["solo"]]

    def test_multi_level_chain(self):
        from src.gui.utils import _dag_levels

        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
            {"name": "b", "next_type": "one", "next": "c"},
            {"name": "c", "next_type": "one", "next": ""},
        ]
        levels = _dag_levels(nodes)
        assert levels == [["a"], ["b"], ["c"]]

    def test_disconnected_node(self):
        from src.gui.utils import _dag_levels

        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
            {"name": "b", "next_type": "one", "next": ""},
            {"name": "orphan", "next_type": "one", "next": ""},
        ]
        levels = _dag_levels(nodes)
        assert "orphan" in levels[-1] or "orphan" in levels[0] or "orphan" in levels[1]
        assert len(levels) >= 2


class TestHighlightTerm:
    def test_basic_match(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("hello world", "world")
        assert "<mark>world</mark>" in result
        assert "hello" in result

    def test_case_insensitive(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("Hello World", "hello")
        assert "<mark>Hello</mark>" in result

    def test_empty_term(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("hello world", "")
        assert result == "hello world"

    def test_no_match(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("hello world", "xyz")
        assert result == "hello world"

    def test_multiple_matches(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("foo bar foo", "foo")
        assert result.count("<mark>foo</mark>") == 2

    def test_special_regex_chars(self):
        from src.gui.utils import _highlight_term

        result = _highlight_term("a + b = c", "+")
        assert "<mark>+</mark>" in result


class TestPrettyDisplayJson:
    def test_valid_json_dict(self):
        from src.gui.utils import _pretty_display_json

        result = _pretty_display_json('{"a": 1}')
        assert result == {"a": 1}

    def test_valid_json_list(self):
        from src.gui.utils import _pretty_display_json

        result = _pretty_display_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_invalid_json_returns_none(self):
        from src.gui.utils import _pretty_display_json

        assert _pretty_display_json("not json") is None

    def test_empty_string(self):
        from src.gui.utils import _pretty_display_json

        assert _pretty_display_json("") is None

    def test_json_string_returns_none(self):
        from src.gui.utils import _pretty_display_json

        assert _pretty_display_json('"just a string"') is None

    def test_json_number_returns_none(self):
        from src.gui.utils import _pretty_display_json

        assert _pretty_display_json("42") is None

    def test_nested_json(self):
        from src.gui.utils import _pretty_display_json

        result = _pretty_display_json('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}
