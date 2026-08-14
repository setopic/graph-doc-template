"""テンプレート同梱のサンプルノードを一括で取り除く。

複製したテンプレートを実プロジェクトに転用するとき、サンプルの撤去は
「ファイル削除 + 各 index.md の一覧から削除 + 残った参照の修正」に分かれる。
最初の 2 つを自動化し、3 つ目は `check` に任せる（何を直すべきかは
リンク切れとして正確に出るため、機械的に消してしまわない方がよい）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .model import Graph, Node
from .scaffold import unregister_from_index

DEFAULT_TAG = "sample"


def find_tagged(graph: Graph, tag: str) -> list[Node]:
    return [n for n in graph.sorted_nodes() if tag in n.tags]


def referencing_nodes(graph: Graph, targets: list[Node]) -> dict[str, list[str]]:
    """削除対象を指しているノードを `{削除対象 id: [参照元 id]}` で返す。"""
    target_ids = {n.id for n in targets}
    result: dict[str, list[str]] = {}

    for node in graph.sorted_nodes():
        if node.id in target_ids:
            continue
        for edge in node.edges:
            if edge.resolved and edge.dst in target_ids:
                result.setdefault(edge.dst, []).append(f"{node.id} ({edge.kind})")

    return {k: sorted(set(v)) for k, v in result.items()}


def remove(root: Path, graph: Graph, tag: str, *, dry_run: bool) -> dict:
    """タグの付いたノードを削除し、index.md の一覧からも外す。"""
    targets = find_tagged(graph, tag)
    if not targets:
        return {"targets": [], "index_updated": [], "referenced_by": {}}

    referenced_by = referencing_nodes(graph, targets)
    filenames = {node.path.name for node in targets}
    index_updated: list[str] = []

    if not dry_run:
        for node in targets:
            node.path.unlink()

        docs = root / schema.DOCS_DIR
        for index_path in sorted(docs.rglob("index.md")):
            if unregister_from_index(index_path, filenames):
                index_updated.append(index_path.relative_to(root).as_posix())

    return {
        "targets": targets,
        "index_updated": index_updated,
        "referenced_by": referenced_by,
    }
