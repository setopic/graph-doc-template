"""グラフを、Mermaid・JSON・DOTの形式で書き出す。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import schema
from .model import Graph, Node

DIAGRAM_BLOCK_RE = re.compile(
    re.escape(schema.DIAGRAM_BLOCK_START) + r".*?" + re.escape(schema.DIAGRAM_BLOCK_END),
    re.DOTALL,
)

_ARROW = {
    "refines": "-->",
    "depends_on": "-->",
    "related": "-.->",
    "supersedes": "==>",
    "decides": "-.->",
    schema.BODY_EDGE_KIND: "-.->",
}

# 向きの無いエッジの種別。個別のノードの図では、A→BとB→Aを1本にまとめ、
# 矢印の無い線で描く。相互に書く決まり（G010）なので、矢印にすると関係1つが2本になる。
_UNDIRECTED = {"related": "-.-"}


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


def _diagram_edges(graph: Graph, include_mentions: bool):
    """個別のノードの図に描くエッジ。向きの無い種別は、ノードの組ごとに1本にする。"""
    pairs: set[tuple[frozenset[str], str]] = set()
    for edge in _edges(graph, include_mentions):
        if edge.kind in _UNDIRECTED:
            key = (frozenset((edge.src, edge.dst)), edge.kind)
            if key in pairs:
                continue
            pairs.add(key)
        yield edge


def _escape(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ")


def to_mermaid(
    graph: Graph,
    include_mentions: bool = False,
    focus: set[str] | None = None,
) -> str:
    lines = ["graph LR"]

    edges = list(_diagram_edges(graph, include_mentions))
    # 線を1本も持たないノードは描かない。場所を取るだけで、何も伝えないからである。
    # focusのノードは、線が無くても残す。何を中心にした図かが分からなくなる。
    drawn = {e.src for e in edges} | {e.dst for e in edges} | (focus or set())

    for type_name, spec in schema.NODE_TYPES.items():
        nodes = [n for n in graph.by_type(type_name) if n.id in drawn]
        if not nodes:
            continue
        lines.append(f'  subgraph {type_name}["{spec["label"]}"]')
        for node in nodes:
            lines.append(f'    {node.id}["{_escape(node.id)}<br/>{_escape(node.title)}"]')
        lines.append("  end")

    for edge in edges:
        arrow = _UNDIRECTED.get(edge.kind) or _ARROW.get(edge.kind, "-->")
        lines.append(f"  {edge.src} {arrow}|{edge.kind}| {edge.dst}")

    _status_classes(lines, [n for n in graph.sorted_nodes() if n.id in drawn])

    if focus:
        marked = [n.id for n in graph.sorted_nodes() if n.id in focus]
        if marked:
            lines.append("  classDef focus stroke-width:3px;")
            lines.append(f"  class {','.join(marked)} focus;")

    return "\n".join(lines) + "\n"


def _status_classes(lines: list[str], shown: list[Node]) -> None:
    """statusで色を分ける。描かないノードを挙げると、Mermaidがそのノードを作ってしまう"""
    draft = [n.id for n in shown if n.status == "draft"]
    deprecated = [n.id for n in shown if n.status == "deprecated"]
    # mermaidのstyleの定義はカンマ区切りなので、値に含めるカンマは\,と書く。
    # 空白区切り（"4 3"）は仕様で定義されておらず、描画されないことがある。
    lines.append("  classDef draft stroke-dasharray: 4\\,3;")
    lines.append("  classDef deprecated opacity:0.5;")
    if draft:
        lines.append(f"  class {','.join(draft)} draft;")
    if deprecated:
        lines.append(f"  class {','.join(deprecated)} deprecated;")


def to_mermaid_types(
    graph: Graph,
    types: set[str],
    include_mentions: bool = False,
) -> str:
    """`types`の種別のノードだけを個別に描き、ほかの種別は型ごとに1つの箱へまとめる。

    層の中の依存の形と、その層がどの層とつながっているかを1枚で見るための図である。
    箱は`--aggregate`と同じ形で、箱との間の線には、ノード × 種別 × 型ごとの本数を書く。
    箱の数はほかの種別の数までしか増えない。
    """
    lines = ["graph LR"]
    inside = {n.id for n in graph.nodes.values() if n.type in types}

    inner = []
    # (始点, 種別, 終点)ごとの本数。層の外の側は、型の接頭辞に置き換える
    totals: dict[tuple[str, str, str], int] = {}
    for edge in _diagram_edges(graph, include_mentions):
        src_in, dst_in = edge.src in inside, edge.dst in inside
        if src_in and dst_in:
            inner.append(edge)
            continue
        if not src_in and not dst_in:
            continue
        src = graph.nodes.get(edge.src)
        dst = graph.nodes.get(edge.dst)
        if src is None or dst is None:
            continue
        outer = dst if src_in else src
        if outer.type not in schema.NODE_TYPES:
            continue  # 型の誤りはG003が指摘する。ここでは何も言わずに飛ばす
        prefix = schema.NODE_TYPES[outer.type]["prefix"]
        if src_in or edge.kind in _UNDIRECTED:
            # 向きの無い線は、層の中のノードの側から描く
            key = (edge.src if src_in else edge.dst, edge.kind, prefix)
        else:
            key = (prefix, edge.kind, edge.dst)
        totals[key] = totals.get(key, 0) + 1

    # 線を1本も持たないノードは、to_mermaidと同じく描かない
    drawn = {e.src for e in inner} | {e.dst for e in inner}
    drawn |= {k for src, _, dst in totals for k in (src, dst) if k in inside}

    for type_name, spec in schema.NODE_TYPES.items():
        if type_name in types:
            nodes = [n for n in graph.by_type(type_name) if n.id in drawn]
            if not nodes:
                continue
            lines.append(f'  subgraph {type_name}["{spec["label"]}"]')
            for node in nodes:
                lines.append(f'    {node.id}["{_escape(node.id)}<br/>{_escape(node.title)}"]')
            lines.append("  end")
        elif any(spec["prefix"] in (src, dst) for src, _, dst in totals):
            label = _escape(spec["label"])
            count = len(graph.by_type(type_name))
            lines.append(f'  {spec["prefix"]}["{label}<br/>{count} 件"]')

    for edge in inner:
        arrow = _UNDIRECTED.get(edge.kind) or _ARROW.get(edge.kind, "-->")
        lines.append(f"  {edge.src} {arrow}|{edge.kind}| {edge.dst}")
    for (src, kind, dst), count in sorted(totals.items()):
        arrow = _UNDIRECTED.get(kind) or _ARROW.get(kind, "-->")
        lines.append(f"  {src} {arrow}|{kind} {count}| {dst}")

    _status_classes(lines, [n for n in graph.sorted_nodes() if n.id in drawn])
    return "\n".join(lines) + "\n"


def to_mermaid_aggregate(graph: Graph, include_mentions: bool = False) -> str:
    """型ごとに1つの箱へまとめた図を、書き出す。

    ノードが何件あっても、箱は型の数だけ、エッジは「型 × 種別 × 型」の組み合わせの数
    だけになる。**ノードが増えても図は大きくならない**ので、GitHubの描画上限
    （エッジ500本。G018）に当たらない。

    その代わり、個別のノードは見えなくなる。上限に近づいたリポジトリだけで
    使うこと。小さいリポジトリで使うと、図を縮める必要が無いのに、情報だけを失う。
    """
    lines = ["graph LR"]

    present = [
        (spec, graph.by_type(name)) for name, spec in schema.NODE_TYPES.items()
    ]
    present = [(spec, nodes) for spec, nodes in present if nodes]

    for spec, nodes in present:
        label = _escape(spec["label"])
        lines.append(f'  {spec["prefix"]}["{label}<br/>{len(nodes)} 件"]')

    # (始点の型, 種別, 終点の型)ごとに、本数を数える
    totals: dict[tuple[str, str, str], int] = {}
    for edge in _edges(graph, include_mentions):
        src = graph.nodes.get(edge.src)
        dst = graph.nodes.get(edge.dst)
        if src is None or dst is None:
            continue
        if src.type not in schema.NODE_TYPES or dst.type not in schema.NODE_TYPES:
            continue  # 型の誤りはG003が指摘する。ここでは何も言わずに飛ばす
        key = (src.type, edge.kind, dst.type)
        totals[key] = totals.get(key, 0) + 1

    # 本数の多い順に並べる。同じ数なら組み合わせの名前の順にして、出力を安定させる
    for (src_type, kind, dst_type), count in sorted(
        totals.items(), key=lambda item: (-item[1], item[0])
    ):
        arrow = _ARROW.get(kind, "-->")
        src_prefix = schema.NODE_TYPES[src_type]["prefix"]
        dst_prefix = schema.NODE_TYPES[dst_type]["prefix"]
        lines.append(f"  {src_prefix} {arrow}|{kind} {count}| {dst_prefix}")

    return "\n".join(lines) + "\n"


# 図の中でエッジを表している行。`A --> B`・`A -.-> B`・`A -.- B`・`A ==> B`に当たる。
EDGE_LINE_RE = re.compile(r"^\s*[A-Za-z][\w-]*\s+(?:-->|-\.->|-\.-|==>)")


def count_edges_in_markdown(path: Path) -> int | None:
    """Markdownのマーカーの中にある図の、エッジの本数を数える。

    **グラフからではなく、書き込まれた図そのものを数える。** そうしないと、
    `--aggregate`や`--focus`で減らしている場合に、実態とずれる。GitHubが
    描こうとするのは、あくまでREADMEに入っている図だからである。

    マーカーかファイルが無ければ、Noneを返す（数えようがない）。
    """
    if not path.is_file():
        return None
    match = DIAGRAM_BLOCK_RE.search(path.read_text(encoding="utf-8"))
    if not match:
        return None
    return sum(1 for line in match.group(0).splitlines() if EDGE_LINE_RE.match(line))


def to_json(
    graph: Graph,
    include_mentions: bool = True,
    *,
    omitted: list[Node] | None = None,
) -> str:
    """`chars`は自動生成ブロックを除いた本文の文字数。読む前に量を見積もるためのもの。

    `omitted`は、`render --budget`が予算で外したノード。中身は読まずに済むよう、
    名前と場所だけを出す。
    """
    payload = {
        "nodes": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "status": n.status,
                "tags": n.tags,
                "path": n.rel,
                "chars": len(n.body),
            }
            for n in graph.sorted_nodes()
        ],
        "edges": [
            {"src": e.src, "dst": e.dst, "kind": e.kind, "origin": e.origin}
            for e in _edges(graph, include_mentions)
        ],
    }
    if omitted is not None:
        payload["omitted"] = [
            {"id": n.id, "title": n.title, "path": n.rel, "chars": len(n.body)}
            for n in omitted
        ]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def to_dot(graph: Graph, include_mentions: bool = False) -> str:
    lines = ["digraph docs {", "  rankdir=LR;", '  node [shape=box, fontname="sans-serif"];']
    for node in graph.sorted_nodes():
        lines.append(f'  "{node.id}" [label="{_escape(node.id)}\\n{_escape(node.title)}"];')
    for edge in _edges(graph, include_mentions):
        lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.kind}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def note_reduced(output: str, fmt: str, count: int) -> str:
    """`render --reduce`で省いた本数を、図のコメントとして1行目の後ろに書く。描画には現れない。"""
    mark = "%%" if fmt == "mermaid" else "//"
    head, _, rest = output.partition("\n")
    return f"{head}\n  {mark} ほかのdepends_onを辿れば分かる依存を{count}本省いた（render --reduce）\n{rest}"


class InjectError(RuntimeError):
    pass


def inject(path: Path, diagram: str, *, dry_run: bool = False) -> bool:
    """マーカーで囲まれた範囲に、図を書き込む。更新が必要ならTrueを返す。

    READMEに図を貼ると必ず実態とずれるので、`sync`と同じくマーカーで囲む方式にして、
    最新かどうかをCIで検証できるようにする。
    """
    if not path.is_file():
        raise InjectError(f"ファイルが無い: {path}")

    original = path.read_text(encoding="utf-8")
    if not DIAGRAM_BLOCK_RE.search(original):
        raise InjectError(
            f"{path.name}に書き込み先が無い。"
            f"次の2行を並べて置く。\n"
            f"  {schema.DIAGRAM_BLOCK_START}\n  {schema.DIAGRAM_BLOCK_END}"
        )

    block = "\n".join(
        [
            schema.DIAGRAM_BLOCK_START,
            "",
            "<!-- この図は render --into が生成する。手で編集しない -->",
            "",
            "```mermaid",
            diagram.rstrip("\n"),
            "```",
            "",
            schema.DIAGRAM_BLOCK_END,
        ]
    )

    updated = DIAGRAM_BLOCK_RE.sub(lambda _: block, original, count=1)
    if updated == original:
        return False

    if not dry_run:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return True


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
