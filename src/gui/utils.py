from __future__ import annotations

import json as _json
import re as _re
from collections import deque


def _dag_levels(nodes: list[dict]) -> list[list[str]]:
    """Compute topological levels of a DAG (list of node-name lists per level)."""
    adj: dict[str, list[str]] = {}
    for n in nodes:
        name = n["name"]
        adj[name] = []
        nt = n.get("next_type", "one")
        nxt = n.get("next", "")
        if nt == "one" and nxt:
            adj[name].append(nxt)
        elif nt in ("if-then", "switch") and isinstance(nxt, list):
            adj[name] = list(nxt)

    has_parent: set[str] = set()
    for targets in adj.values():
        has_parent.update(targets)
    roots = [n["name"] for n in nodes if n["name"] not in has_parent]
    if not roots and nodes:
        roots = [nodes[0]["name"]]

    levels: dict[str, int] = {}
    queue = deque((r, 0) for r in roots)
    while queue:
        node, lv = queue.popleft()
        if node in levels:
            continue
        levels[node] = lv
        for nb in adj.get(node, []):
            if nb not in levels:
                queue.append((nb, lv + 1))

    for n in nodes:
        if n["name"] not in levels:
            levels[n["name"]] = max(levels.values(), default=0) + 1

    max_lv = max(levels.values()) if levels else 0
    groups: list[list[str]] = [[] for _ in range(max(1, max_lv + 1))]
    for node, lv in levels.items():
        while lv >= len(groups):
            groups.append([])
        groups[lv].append(node)
    return groups


def _highlight_term(text: str, term: str) -> str:
    """Wrap occurrences of `term` in <mark> tags, case-insensitive."""
    if not term.strip():
        return text
    escaped = _re.escape(term.strip())
    return _re.sub(
        f"({escaped})", r"<mark>\1</mark>", text,
        flags=_re.IGNORECASE, count=20,
    )


def _pretty_display_json(text: str) -> dict | list | None:
    """Try to parse text as JSON. Returns parsed object or None."""
    if not text or not text.strip():
        return None
    try:
        data = _json.loads(text)
        if isinstance(data, (dict, list)):
            return data
    except (_json.JSONDecodeError, ValueError, TypeError):
        pass
    return None
