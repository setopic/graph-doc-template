"""グラフの構造を読み、見直す候補を挙げる（`stats`と`path`が使う）。

ここで挙げるものは誤りとは限らないので、`check`のルールにはしない。
`G015`と同じく「見たか」を確かめる材料で、終了コードにも影響させない。
"""

from __future__ import annotations

from collections import deque

from . import schema
from .loader import strip_non_prose
from .model import Graph, Node
from .rules import _EMPHASIS_RE, _TERM_SECTION_RE, _prerequisites, term_rows

# depends_onの多い順に、上から何件を出すか
TOP_DEPENDED = 5

# pathが辿るエッジ。前提の向き（依存元から依存先へ）だけを見る
PATH_KINDS = ("depends_on", "refines")


def _layer(node: Node) -> int | None:
    """層のルール（`G007`）の対象なら、その層の番号を返す。対象外ならNone。"""
    spec = schema.NODE_TYPES.get(node.type)
    if spec is None or spec["exempt_layer"]:
        return None
    return spec["layer"]


def depended_counts(graph: Graph) -> list[tuple[str, int]]:
    """`depends_on`された数の多い順に並べる。数え方は`G012`と同じにする。"""
    counts: dict[str, int] = {}
    for node in graph.sorted_nodes():
        if node.type in schema.HUB_EXEMPT_TYPES:
            continue
        for edge in node.out_edges("depends_on"):
            if edge.resolved:
                counts[edge.dst] = counts.get(edge.dst, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def unused_nodes(graph: Graph) -> list[Node]:
    """どのノードからも前提にされていない、いちばん上の層より下のノード。

    いちばん上の層（既定では契約）は、ほかから依存されないのが普通なので外す。
    `G005`は目次から辿れるかだけを見るので、ここで挙げるノードは`check`を通る。
    """
    layers = {layer for n in graph.nodes.values() if (layer := _layer(n)) is not None}
    if not layers:
        return []
    top = max(layers)
    used = {
        e.dst
        for e in graph.edges()
        if e.resolved and e.kind in PATH_KINDS and e.src != e.dst
    }
    return [
        n
        for n in graph.sorted_nodes()
        if (layer := _layer(n)) is not None and layer < top and n.id not in used
    ]


def _prose(node: Node) -> str:
    return strip_non_prose(_TERM_SECTION_RE.sub(" ", node.body))


def unused_terms(graph: Graph) -> list[tuple[str, str]]:
    """用語表にあるのに、依存しているどのノードの本文にも出てこない用語。

    依存しているノードが1つも無いノードは外す。そのノード自体が`unused_nodes`に挙がるからである。
    """
    dependents: dict[str, list[Node]] = {}
    for node in graph.sorted_nodes():
        for owner_id in _prerequisites(graph, node.id):
            dependents.setdefault(owner_id, []).append(node)

    found: list[tuple[str, str]] = []
    for owner in graph.sorted_nodes():
        if owner.type not in schema.TERM_TYPES or owner.id not in dependents:
            continue
        texts = [_prose(n) for n in dependents[owner.id]]
        for row in term_rows(owner.body):
            term = _EMPHASIS_RE.sub("", row.get(schema.TERM_COLUMN, "")).strip()
            if term and not any(term in text for text in texts):
                found.append((owner.id, term))
    return found


def body_only_references(graph: Graph) -> list[tuple[Node, Node]]:
    """本文の`[[ID]]`でだけ指していて、前提として辿れない組。

    `depends_on`を書ける向き（同じか数字の小さい層）への参照だけを挙げる。
    上の層への参照は道案内にしかならないので、前提の書き忘れではない。
    本文のリンクは`G006`・`G007`にかからないので、前提を本文にだけ書くと見落とされる。
    """
    pairs: list[tuple[Node, Node]] = []
    for node in graph.sorted_nodes():
        src_layer = _layer(node)
        if src_layer is None:
            continue
        prerequisites = set(_prerequisites(graph, node.id))
        seen: set[str] = set()
        for edge in node.out_edges(schema.BODY_EDGE_KIND):
            if not edge.resolved or edge.dst in seen or edge.dst == node.id:
                continue
            seen.add(edge.dst)
            target = graph.nodes[edge.dst]
            dst_layer = _layer(target)
            if dst_layer is None or dst_layer > src_layer:
                continue
            if edge.dst not in prerequisites:
                pairs.append((node, target))
    return pairs


def report(graph: Graph) -> str:
    """`stats`の後半に出す、構造の見直しの候補。"""
    lines = [f"depends_onされている数（上位{TOP_DEPENDED}件。G012の上限は{schema.MAX_INCOMING_DEPENDENCIES}）:"]
    ranking = depended_counts(graph)[:TOP_DEPENDED]
    lines += [f"  {node_id:<16} {count:>3}" for node_id, count in ranking] or ["  なし"]

    lines.append("どこからも前提にされていないノード（いちばん上の層を除く）:")
    lines += [f"  {n.id:<16} {n.title}" for n in unused_nodes(graph)] or ["  なし"]

    lines.append("依存しているノードの本文に出てこない用語:")
    lines += [f"  {owner_id:<16} {term}" for owner_id, term in unused_terms(graph)] or ["  なし"]

    lines.append("本文でだけ参照していて、depends_onで辿れない組:")
    lines += [
        f"  {src.id} → {dst.id}（{dst.title}）" for src, dst in body_only_references(graph)
    ] or ["  なし"]

    return "\n".join(lines) + "\n"


def shortest_path(graph: Graph, src: str, dst: str) -> list[tuple[str, str]] | None:
    """`src`から`dst`へ、前提の向きに辿る最短の経路。

    `[(エッジ種別, ノードのid), ...]`を返す。先頭は`("", src)`。経路が無ければNone。
    """
    previous: dict[str, tuple[str, str]] = {src: ("", "")}
    queue = deque([src])
    while queue:
        current = queue.popleft()
        if current == dst:
            break
        node = graph.nodes.get(current)
        if node is None:
            continue
        for edge in sorted(node.edges, key=lambda e: (e.kind, e.dst)):
            if edge.resolved and edge.kind in PATH_KINDS and edge.dst not in previous:
                previous[edge.dst] = (edge.kind, current)
                queue.append(edge.dst)
    if dst not in previous:
        return None

    steps: list[tuple[str, str]] = []
    current = dst
    while current != src:
        kind, before = previous[current]
        steps.append((kind, current))
        current = before
    steps.append(("", src))
    return list(reversed(steps))
