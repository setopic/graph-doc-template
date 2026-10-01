"""テンプレートに同梱したサンプルノードを、まとめて取り除く。

複製したテンプレートを実際のプロジェクトに使うとき、サンプルの撤去は
「ファイルの削除」「各index.mdの一覧からの削除」「残った参照の修正」の3つに分かれる。
最初の2つを自動で行い、3つ目は`check`に任せる（何を直すべきかは
リンク切れとして正確に出るので、機械的に消さないほうがよい）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import schema
from .frontmatter import FrontmatterError, as_list, split
from .model import Graph
from .scaffold import unregister_from_index

DEFAULT_TAG = "sample"


@dataclass
class TaggedFile:
    """削除の対象のファイル。グラフのノードとは別に、ファイルから直接読む。"""

    id: str
    title: str
    path: Path
    rel: str


def find_tagged(root: Path, tag: str) -> list[TaggedFile]:
    """`tags`に`tag`を持つファイルを、グラフを経由せずに探す。

    グラフから探すと、idが重複しているノードはloaderが読み込んでいないので、
    見つからない。テンプレートからマージした直後が、まさにその状態である
    （プロジェクト側とサンプルが同じidを持つ）。そのため、
    **撤去したいときに限って、見つからない**ことになる。
    """
    docs = root / schema.DOCS_DIR
    found: list[TaggedFile] = []

    if not docs.is_dir():
        return found

    for path in sorted(docs.rglob("*.md")):
        rel_to_docs = path.relative_to(docs).as_posix()
        if any(rel_to_docs.startswith(p) for p in schema.EXCLUDE_PREFIXES):
            continue

        try:
            meta, _ = split(path.read_text(encoding="utf-8"))
        except FrontmatterError:
            continue

        if tag not in as_list(meta.get("tags")):
            continue

        found.append(
            TaggedFile(
                id=str(meta.get("id", "")).strip(),
                title=str(meta.get("title", "")).strip(),
                path=path,
                rel=path.relative_to(root).as_posix(),
            )
        )

    return found


def referencing_nodes(graph: Graph, target_ids: set[str]) -> dict[str, list[str]]:
    """削除の対象を指しているノードを、`{削除の対象のid: [参照元]}`で返す。

    グラフから引くので、idが重複している場合は取りこぼすことがある。
    削除した後に`check`が確実に指摘するので、ここは参考の情報でよい。
    """
    result: dict[str, list[str]] = {}

    for node in graph.sorted_nodes():
        if node.id in target_ids:
            continue
        for edge in node.edges:
            if edge.resolved and edge.dst in target_ids:
                result.setdefault(edge.dst, []).append(f"{node.id} ({edge.kind})")

    return {k: sorted(set(v)) for k, v in result.items()}


def remove(root: Path, graph: Graph, tag: str, *, dry_run: bool) -> dict:
    """タグの付いたノードを削除し、index.mdの一覧からも外す。"""
    targets = find_tagged(root, tag)
    if not targets:
        return {"targets": [], "index_updated": [], "referenced_by": {}}

    referenced_by = referencing_nodes(graph, {t.id for t in targets if t.id})
    filenames = {target.path.name for target in targets}
    index_updated: list[str] = []

    if not dry_run:
        for target in targets:
            target.path.unlink()

        docs = root / schema.DOCS_DIR
        for index_path in sorted(docs.rglob("index.md")):
            if unregister_from_index(index_path, filenames):
                index_updated.append(index_path.relative_to(root).as_posix())

    return {
        "targets": targets,
        "index_updated": index_updated,
        "referenced_by": referenced_by,
    }
