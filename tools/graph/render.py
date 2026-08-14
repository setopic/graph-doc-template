"""グラフを Mermaid / JSON / DOT に書き出す。"""

from __future__ import annotations

import json

from . import schema
from .model import Graph

_ARROW = {
    "refines": "-->",
    "depends_on": "-->",
    "related": "-.->",
    "supersedes": "==>",
    "decides": "-.->",
    schema.BODY_EDGE_KIND: "-.->",
}


def _edges(graph: Graph, include_mentions: bool):
    seen: set[tuple[str, str, str]] = set()
    for node in graph.sorted_nodes():
        for edge in node.edges:
            if not edge.resolved:
                continue
            if edge.kind == schema.BODY_EDGE_KIND and not include_mentions:
                continue
            key = (edge.src, edge.dst, edge.kind)
            if key in seen:
                continue
            seen.add(key)
            yield edge


def _escape(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ")


def to_mermaid(graph: Graph, include_mentions: bool = False) -> str:
    lines = ["graph LR"]

    for type_name, spec in schema.NODE_TYPES.items():
        nodes = graph.by_type(type_name)
        if not nodes:
            continue
        lines.append(f'  subgraph {type_name}["{spec["label"]}"]')
        for node in nodes:
            lines.append(f'    {node.id}["{_escape(node.id)}<br/>{_escape(node.title)}"]')
        lines.append("  end")

    for edge in _edges(graph, include_mentions):
        arrow = _ARROW.get(edge.kind, "-->")
        lines.append(f"  {edge.src} {arrow}|{edge.kind}| {edge.dst}")

    # status で色を分ける
    draft = [n.id for n in graph.sorted_nodes() if n.status == "draft"]
    deprecated = [n.id for n in graph.sorted_nodes() if n.status == "deprecated"]
    lines.append("  classDef draft stroke-dasharray: 4 3;")
    lines.append("  classDef deprecated opacity:0.5;")
    if draft:
        lines.append(f"  class {','.join(draft)} draft;")
    if deprecated:
        lines.append(f"  class {','.join(deprecated)} deprecated;")

    return "\n".join(lines) + "\n"


def to_json(graph: Graph, include_mentions: bool = True) -> str:
    payload = {
        "nodes": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "status": n.status,
                "tags": n.tags,
                "path": n.rel,
            }
            for n in graph.sorted_nodes()
        ],
        "edges": [
            {"src": e.src, "dst": e.dst, "kind": e.kind, "origin": e.origin}
            for e in _edges(graph, include_mentions)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def to_dot(graph: Graph, include_mentions: bool = False) -> str:
    lines = ["digraph docs {", "  rankdir=LR;", '  node [shape=box, fontname="sans-serif"];']
    for node in graph.sorted_nodes():
        lines.append(f'  "{node.id}" [label="{_escape(node.id)}\\n{_escape(node.title)}"];')
    for edge in _edges(graph, include_mentions):
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.kind}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def summary(graph: Graph) -> str:
    lines = ["ノード数:"]
    for type_name, spec in schema.NODE_TYPES.items():
        nodes = graph.by_type(type_name)
        if nodes:
            lines.append(f"  {spec['label']:<16} {len(nodes):>3}")

    kinds: dict[str, int] = {}
    for edge in graph.edges():
        if edge.resolved:
            kinds[edge.kind] = kinds.get(edge.kind, 0) + 1
    lines.append("エッジ数:")
    for kind, count in sorted(kinds.items()):
        lines.append(f"  {kind:<16} {count:>3}")

    statuses: dict[str, int] = {}
    for node in graph.sorted_nodes():
        statuses[node.status] = statuses.get(node.status, 0) + 1
    lines.append("status:")
    for status in schema.STATUSES:
        if status in statuses:
            lines.append(f"  {status:<16} {statuses[status]:>3}")

    return "\n".join(lines) + "\n"
