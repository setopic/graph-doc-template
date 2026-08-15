"""各ノードの末尾に「関連ドキュメント」ブロックを再生成する。

手で書いたリンク（フロントマターと本文）を正とし、その逆引き（誰から参照
されているか）だけを自動で埋める。ブロックはマーカーで囲まれていて、
loader が読み込み時に取り除くのでグラフの入力にはならない。

目次ノードだけは扱いが違う。こちらは**一覧ブロックを丸ごと作り直す**。
中身は「同じディレクトリにあるノード」で機械的に決まり、
`<!-- graph:children:start -->` の外に書いた案内文には触らない。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .loader import AUTO_BLOCK_RE
from .model import Graph, Node

CHILDREN_RE = re.compile(
    re.escape(schema.CHILDREN_START) + r".*?" + re.escape(schema.CHILDREN_END),
    re.DOTALL,
)
# "DOM-01" を ("DOM", 1) にして、DOM-2 が DOM-10 より前に来るようにする
ID_RE = re.compile(r"^(.*?)-(\d+)$")


def _id_key(node_id: str) -> tuple[str, int, str]:
    match = ID_RE.match(node_id)
    if match:
        return (match.group(1), int(match.group(2)), "")
    return (node_id, 0, node_id)


def build_children_block(graph: Graph, index_node: Node) -> str:
    """目次の一覧ブロックを作る。同じディレクトリのノードを id 順に並べる。

    **手で書き足す必要をなくすためにある。** 登録漏れは `G005`（孤立ノード）
    として出るが、そもそも漏れようがないほうがよい。改題への追随も同じで、
    タイトルはフロントマターにあるのだから機械が拾えばよい。
    """
    directory = index_node.path.parent
    children = [
        node
        for node in graph.nodes.values()
        if node.type != "index" and node.path.parent == directory
    ]

    lines = [schema.CHILDREN_START]
    for child in sorted(children, key=lambda n: _id_key(n.id)):
        lines.append(f"- [{child.id} {child.title}](./{child.path.name})")
    lines.append(schema.CHILDREN_END)
    return "\n".join(lines)


def build_block(graph: Graph, node: Node) -> str:
    lines = [schema.AUTO_BLOCK_START, "", "## 関連ドキュメント（自動生成 / 手で編集しない）", ""]

    wrote_any = False

    for kind in schema.frontmatter_edge_kinds():
        targets = [e.dst for e in node.out_edges(kind) if e.resolved]
        if not targets:
            continue
        wrote_any = True
        lines.append(f"**{kind}** — {schema.EDGE_KINDS[kind]['desc']}")
        lines.append("")
        for target_id in sorted(set(targets)):
            target = graph.nodes[target_id]
            lines.append(f"- [{target.id} {target.title}]({_relpath(node, target)})")
        lines.append("")

    incoming: dict[str, set[str]] = {}
    for edge in graph.incoming(node.id):
        if edge.kind == schema.BODY_EDGE_KIND:
            continue
        incoming.setdefault(edge.kind, set()).add(edge.src)

    if incoming:
        wrote_any = True
        lines.append("**このノードを参照しているノード**")
        lines.append("")
        for kind in sorted(incoming):
            for source_id in sorted(incoming[kind]):
                source = graph.nodes[source_id]
                lines.append(
                    f"- ({kind}) [{source.id} {source.title}]({_relpath(node, source)})"
                )
        lines.append("")

    if not wrote_any:
        lines.append("_まだリンクがありません。孤立ノードのままにしないこと。_")
        lines.append("")

    lines.append(schema.AUTO_BLOCK_END)
    return "\n".join(lines)


def _relpath(source: Node, target: Node) -> str:
    import os

    rel = os.path.relpath(target.path, source.path.parent)
    rel = Path(rel).as_posix()
    return rel if rel.startswith(".") else "./" + rel


def sync(graph: Graph, *, dry_run: bool = False) -> list[str]:
    """更新されたファイルの相対パス一覧を返す。"""
    changed: list[str] = []

    for node in graph.sorted_nodes():
        if node.type == "index":
            # 目次は一覧ブロックだけを作り直す。案内文はそのまま
            original = node.path.read_text(encoding="utf-8")
            if not CHILDREN_RE.search(original):
                continue
            block = build_children_block(graph, node)
            updated = CHILDREN_RE.sub(lambda _: block, original, count=1)
            if updated != original:
                changed.append(node.rel)
                if not dry_run:
                    node.path.write_text(updated, encoding="utf-8", newline="\n")
            continue

        original = node.path.read_text(encoding="utf-8")
        block = build_block(graph, node)

        if AUTO_BLOCK_RE.search(original):
            updated = AUTO_BLOCK_RE.sub(lambda _: block, original, count=1)
        else:
            updated = original.rstrip("\n") + "\n\n---\n\n" + block + "\n"

        if updated != original:
            changed.append(node.rel)
            if not dry_run:
                node.path.write_text(updated, encoding="utf-8", newline="\n")

    return changed
