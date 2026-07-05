import argparse
import sys
from collections import deque
from pathlib import Path

import yaml

NEXT_TYPES = {"one", "if-then", "switch"}


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_workflow(workflow_path: str) -> list[str]:
    wf_path = Path(workflow_path)

    if wf_path.is_file() and wf_path.name == "workflow.yaml":
        product_dir = wf_path.parent
    elif wf_path.is_dir():
        product_dir = wf_path
        wf_path = product_dir / "workflow.yaml"
    else:
        return [f"ERROR: workflow file not found: {workflow_path}"]

    if not wf_path.is_file():
        return [f"ERROR: workflow.yaml not found in {product_dir}"]

    data = _load_yaml(wf_path)
    return _validate(data, product_dir)


def _validate(data: dict, product_dir: Path) -> list[str]:
    errors: list[str] = []

    name = data.get("name", product_dir.name)
    nodes_raw = data.get("nodes", [])
    if not isinstance(nodes_raw, list) or not nodes_raw:
        errors.append(f"[{name}] ERROR: no nodes defined")
        return errors

    errors.extend(_check_existence(name, nodes_raw, product_dir))

    adj, all_nodes = _build_graph(nodes_raw)
    errors.extend(_check_connectivity(name, adj, all_nodes))
    errors.extend(_check_convergence(name, adj, all_nodes))

    return errors


def _check_existence(
    wf_name: str, nodes: list[dict], product_dir: Path
) -> list[str]:
    errors: list[str] = []
    node_names: set[str] = set()
    nodes_dir = product_dir / "nodes"

    for node in nodes:
        node_name = node.get("name", "")
        if not node_name:
            errors.append(f"[{wf_name}] ERROR: node missing 'name'")
            continue
        if node_name in node_names:
            errors.append(f"[{wf_name}] ERROR: duplicate node name '{node_name}'")
        node_names.add(node_name)

        nt = node.get("next_type", "one")
        if nt not in NEXT_TYPES:
            errors.append(f"[{wf_name}] ERROR: node '{node_name}' invalid next_type '{nt}'")

        nxt = node.get("next", "")
        if nt == "one":
            if not isinstance(nxt, str):
                errors.append(
                    f"[{wf_name}] ERROR: node '{node_name}' "
                    f"next should be string, got {type(nxt).__name__}"
                )
        elif nt in ("if-then", "switch"):
            if not isinstance(nxt, list):
                errors.append(
                    f"[{wf_name}] ERROR: node '{node_name}' "
                    f"next should be list, got {type(nxt).__name__}"
                )
            elif len(nxt) == 0:
                errors.append(f"[{wf_name}] ERROR: node '{node_name}' ({nt}) next list is empty")

        node_file = nodes_dir / f"{node_name}.yaml"
        if not node_file.is_file():
            errors.append(f"[{wf_name}] ERROR: node config not found: {node_file}")

    for node in nodes:
        node_name = node.get("name", "")
        nt = node.get("next_type", "one")
        nxt = node.get("next", "")
        if nt == "one" and nxt:
            if isinstance(nxt, str) and nxt not in node_names:
                errors.append(
                    f"[{wf_name}] ERROR: node '{node_name}' next='{nxt}' not found in workflow"
                )
        elif nt in ("if-then", "switch") and isinstance(nxt, list):
            for branch in nxt:
                if branch not in node_names:
                    errors.append(
                        f"[{wf_name}] ERROR: node '{node_name}' next branch '{branch}' not found"
                    )

    return errors


def _build_graph(nodes: list[dict]) -> tuple[dict[str, set[str]], set[str]]:
    adj: dict[str, set[str]] = {"input": set(), "output": set()}
    all_nodes: set[str] = set()

    for node in nodes:
        node_name = node["name"]
        all_nodes.add(node_name)
        adj.setdefault(node_name, set())

        nt = node.get("next_type", "one")
        nxt = node.get("next", "")

        if nt == "one" and nxt and isinstance(nxt, str):
            adj[node_name].add(nxt)
        elif nt in ("if-then", "switch") and isinstance(nxt, list):
            for branch in nxt:
                adj[node_name].add(branch)

    if nodes:
        adj["input"].add(nodes[0]["name"])

    for node in nodes:
        nt = node.get("next_type", "one")
        nxt = node.get("next", "")
        is_terminal = False
        if nt == "one" and nxt == "":
            is_terminal = True
        elif nt in ("if-then", "switch") and (not isinstance(nxt, list) or len(nxt) == 0):
            is_terminal = True

        if is_terminal:
            adj[node["name"]].add("output")

    all_nodes.add("output")
    all_nodes.add("input")
    adj.setdefault("output", set())
    adj.setdefault("input", set())

    return adj, all_nodes


def _check_connectivity(
    wf_name: str, adj: dict[str, set[str]], all_nodes: set[str]
) -> list[str]:
    errors: list[str] = []
    visited = _bfs(adj, "input")
    unreachable = all_nodes - visited
    if unreachable:
        errors.append(
            f"[{wf_name}] ERROR: unreachable from input: {sorted(unreachable)}"
        )
    return errors


def _check_convergence(
    wf_name: str, adj: dict[str, set[str]], all_nodes: set[str]
) -> list[str]:
    errors: list[str] = []
    rev_adj: dict[str, set[str]] = {n: set() for n in adj}
    for src, targets in adj.items():
        for tgt in targets:
            rev_adj.setdefault(tgt, set()).add(src)

    visited = _bfs(rev_adj, "output")
    dead_ends = all_nodes - visited
    if dead_ends:
        errors.append(
            f"[{wf_name}] ERROR: nodes not converging to output: {sorted(dead_ends)}"
        )
    return errors


def _bfs(adj: dict[str, set[str]], start: str) -> set[str]:
    visited: set[str] = set()
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a workflow product directory")
    parser.add_argument(
        "path",
        help="Path to workflow.yaml or product directory (e.g. config/workflows/default/)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    errors = validate_workflow(args.path)

    if errors:
        for e in errors:
            print(e)
        return 1

    wf_path = Path(args.path)
    if wf_path.is_file():
        product_dir = wf_path.parent
    else:
        product_dir = wf_path
        wf_path = product_dir / "workflow.yaml"

    data = _load_yaml(wf_path)
    name = data.get("name", product_dir.name)
    nodes = data.get("nodes", [])
    total = len(nodes) + 2
    collections = data.get("collections", ["default"])
    print(f"  [OK] workflow \"{name}\" passed")
    print(f"       product dir: {product_dir}")
    print(f"       nodes: {total} (input + {len(nodes)} tool + output)")
    print(f"       collections: {collections}")
    print("       connectivity: all nodes reachable")
    print("       convergence: all paths lead to output")

    if args.verbose:
        adj, _ = _build_graph(nodes)
        print("       adjacency:")
        for src, targets in sorted(adj.items()):
            if targets:
                print(f"         {src} -> {sorted(targets)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
