"""各ノードの末尾に「関連ドキュメント」ブロックを再生成する。

手で書いたリンク（フロントマターと本文）を正とし、その逆引き（誰から参照
されているか）だけを自動で埋める。ブロックはマーカーで囲まれていて、
loader が読み込み時に取り除くのでグラフの入力にはならない。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .loader import AUTO_BLOCK_RE
from .model import Graph, Node


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
            continue  # 目次は手で書いた一覧が正

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
