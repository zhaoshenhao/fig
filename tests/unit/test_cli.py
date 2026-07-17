from __future__ import annotations

import sys
from pathlib import Path

import yaml

_proj_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj_root))


def _make_product_dir(tmp_path: Path, name: str, nodes: list[dict]) -> Path:
    product_dir = tmp_path / name
    nodes_dir = product_dir / "nodes"
    nodes_dir.mkdir(parents=True)

    (product_dir / "workflow.yaml").write_text(
        yaml.dump(
            {
                "name": name,
                "collections": ["default"],
                "return_mode": "full",
                "nodes": nodes,
            }
        ),
        encoding="utf-8",
    )

    for node in nodes:
        node_name = node.get("name", "")
        if node_name:
            (nodes_dir / f"{node_name}.yaml").write_text(
                yaml.dump({"tool": "mock_echo", "message": node_name}),
                encoding="utf-8",
            )

    return product_dir


class TestValidateWorkflow:
    """Tests for src/cli/validate_workflow.py"""

    def test_validate_workflow_file_path(self, tmp_path):
        nodes = [{"name": "a", "next_type": "one", "next": ""}]
        product_dir = _make_product_dir(tmp_path, "test_wf", nodes)
        wf_file = product_dir / "workflow.yaml"

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(wf_file))
        assert errors == []

    def test_validate_workflow_directory(self, tmp_path):
        nodes = [{"name": "a", "next_type": "one", "next": ""}]
        product_dir = _make_product_dir(tmp_path, "test_wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert errors == []

    def test_validate_workflow_not_found(self, tmp_path):
        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(tmp_path / "nonexistent"))
        assert len(errors) >= 1
        assert any("not found" in e.lower() for e in errors)

    def test_validate_no_nodes(self, tmp_path):
        product_dir = tmp_path / "empty"
        nodes_dir = product_dir / "nodes"
        nodes_dir.mkdir(parents=True)
        (product_dir / "workflow.yaml").write_text(
            yaml.dump({"name": "empty_wf", "nodes": []}),
            encoding="utf-8",
        )

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert len(errors) >= 1
        assert any("no nodes" in e.lower() for e in errors)

    def test_validate_duplicate_node_names(self, tmp_path):
        nodes = [
            {"name": "dup", "next_type": "one", "next": ""},
            {"name": "dup", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("duplicate" in e.lower() for e in errors)

    def test_validate_invalid_next_type(self, tmp_path):
        nodes = [{"name": "a", "next_type": "invalid_type_xyz", "next": ""}]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("invalid next_type" in e.lower() for e in errors)

    def test_validate_one_next_string(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
            {"name": "b", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert errors == []

    def test_validate_one_next_non_string(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "one", "next": ["should", "be", "string"]}
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("should be string" in e.lower() for e in errors)

    def test_validate_one_next_int(self, tmp_path):
        nodes = [{"name": "a", "next_type": "one", "next": 42}]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("should be string" in e.lower() for e in errors)

    def test_validate_if_then_list(self, tmp_path):
        nodes = [
            {"name": "r", "next_type": "if-then", "next": ["a", "b"]},
            {"name": "a", "next_type": "one", "next": ""},
            {"name": "b", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert errors == []

    def test_validate_if_then_non_list(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "if-then", "next": "not-a-list"}
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("should be list" in e.lower() for e in errors)

    def test_validate_switch_empty_list(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "switch", "next": []}
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("empty" in e.lower() for e in errors)

    def test_validate_switch_list(self, tmp_path):
        nodes = [
            {"name": "dispatcher", "next_type": "switch", "next": ["a", "b"], "parallel": False},
            {"name": "a", "next_type": "one", "next": ""},
            {"name": "b", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert errors == []

    def test_validate_missing_node_config(self, tmp_path):
        product_dir = tmp_path / "orphan"
        nodes_dir = product_dir / "nodes"
        nodes_dir.mkdir(parents=True)
        (product_dir / "workflow.yaml").write_text(
            yaml.dump(
                {
                    "name": "orphan_wf",
                    "nodes": [
                        {"name": "orphan", "next_type": "one", "next": ""}
                    ],
                }
            ),
            encoding="utf-8",
        )

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("not found" in e.lower() for e in errors)

    def test_validate_next_not_found(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "one", "next": "nonexistent_node"}
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("not found" in e.lower() for e in errors)

    def test_validate_branch_not_found(self, tmp_path):
        nodes = [
            {"name": "r", "next_type": "if-then", "next": ["valid", "nonexistent"]},
            {"name": "valid", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("branch" in e.lower() for e in errors)

    def test_validate_unreachable_nodes(self, tmp_path):
        nodes = [
            {"name": "start", "next_type": "one", "next": ""},
            {"name": "isolated", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("unreachable" in e.lower() for e in errors)

    def test_validate_dead_ends(self, tmp_path):
        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
        ]
        product_dir = _make_product_dir(tmp_path, "wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert any("not converging" in e.lower() for e in errors)

    def test_validate_ok(self, tmp_path):
        nodes = [
            {"name": "retrieve", "next_type": "one", "next": "generate"},
            {"name": "generate", "next_type": "one", "next": ""},
        ]
        product_dir = _make_product_dir(tmp_path, "full_wf", nodes)

        from src.cli.validate_workflow import validate_workflow

        errors = validate_workflow(str(product_dir))
        assert errors == []

    def test_main_verbose(self, tmp_path, capsys):
        nodes = [{"name": "a", "next_type": "one", "next": ""}]
        product_dir = _make_product_dir(tmp_path, "test_wf", nodes)

        import sys as _sys

        from src.cli.validate_workflow import main as cli_main

        _sys.argv = ["validate", str(product_dir), "--verbose"]
        try:
            rc = cli_main()
            assert rc == 0
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "adjacency" in captured.out.lower()


class TestBuildGraph:
    def test_build_graph_has_input_output(self):
        nodes = [
            {"name": "a", "next_type": "one", "next": "b"},
            {"name": "b", "next_type": "one", "next": ""},
        ]

        from src.cli.validate_workflow import _build_graph

        adj, all_nodes = _build_graph(nodes)
        assert "input" in all_nodes
        assert "output" in all_nodes
        assert adj["input"] == {"a"}
        assert "output" in adj["b"]

    def test_build_graph_if_then(self):
        nodes = [
            {"name": "r", "next_type": "if-then", "next": ["a", "b"]},
            {"name": "a", "next_type": "one", "next": ""},
            {"name": "b", "next_type": "one", "next": ""},
        ]

        from src.cli.validate_workflow import _build_graph

        adj, _ = _build_graph(nodes)
        assert adj["r"] == {"a", "b"}
        assert adj["r"] == {"a", "b"}

    def test_build_graph_switch_parallel(self):
        nodes = [
            {"name": "d", "next_type": "switch", "next": ["x", "y"], "parallel": True},
            {"name": "x", "next_type": "one", "next": ""},
            {"name": "y", "next_type": "one", "next": ""},
        ]

        from src.cli.validate_workflow import _build_graph

        adj, _ = _build_graph(nodes)
        assert adj["d"] == {"x", "y"}
        assert "output" in adj["x"]
        assert "output" in adj["y"]


class TestBFS:
    def test_bfs_covers_all_reachable(self):
        adj = {
            "a": {"b", "c"},
            "b": {"d"},
            "c": {"d"},
            "d": set(),
        }

        from src.cli.validate_workflow import _bfs

        visited = _bfs(adj, "a")
        assert visited == {"a", "b", "c", "d"}

    def test_bfs_skips_disconnected(self):
        adj = {
            "a": {"b"},
            "b": set(),
            "c": {"d"},
            "d": set(),
        }

        from src.cli.validate_workflow import _bfs

        visited = _bfs(adj, "a")
        assert visited == {"a", "b"}
