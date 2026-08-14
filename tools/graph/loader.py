"""docs/ を走査してグラフを組み立てる。"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .frontmatter import FrontmatterError, as_list, split
from .model import ERROR, Edge, Graph, Issue, Node

# [[UC-01]] / [[UC-01|表示名]]
WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+?)(?:\|[^\]]*?)?\]\]")
# [表示名](../20-domain/dom-01.md)
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
AUTO_BLOCK_RE = re.compile(
    re.escape(schema.AUTO_BLOCK_START) + r".*?" + re.escape(schema.AUTO_BLOCK_END),
    re.DOTALL,
)
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_non_prose(text: str) -> str:
    """リンクとして数えない部分を取り除く。

    - コードブロック / コードスパン: 規約やテンプレートの説明には
      `[[ID]]` のような記法の「例」が出てくる。これをリンクとして数えると、
      書き方を説明しただけでリンク切れになる
    - HTML コメント: 雛形の記入案内が入っている。案内文に書いた例や、
      コメントアウトした記述をエッジにしない
    """
    return INLINE_CODE_RE.sub(
        " ", FENCED_CODE_RE.sub(" ", HTML_COMMENT_RE.sub(" ", text))
    )


def strip_auto_block(text: str) -> str:
    """sync が生成したブロックを取り除く。

    自動生成されたバックリンクをエッジとして数えてしまうと、
    到達可能性も循環検出も自作自演で成立してしまうため必ず除外する。
    """
    return AUTO_BLOCK_RE.sub("", text)


def load(root: Path) -> Graph:
    """リポジトリルートを受け取り、グラフを返す。"""
    docs_root = root / schema.DOCS_DIR
    graph = Graph()

    if not docs_root.is_dir():
        graph.load_issues.append(
            Issue("G000", ERROR, f"{schema.DOCS_DIR}/ が見つかりません", str(docs_root))
        )
        return graph

    pending: list[tuple[Node, list[str], list[str]]] = []  # (node, wikilinks, mdlinks)
    by_path: dict[Path, Node] = {}

    for path in sorted(docs_root.rglob("*.md")):
        rel_to_docs = path.relative_to(docs_root).as_posix()
        if any(rel_to_docs.startswith(p) for p in schema.EXCLUDE_PREFIXES):
            continue

        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")

        try:
            meta, body = split(text)
        except FrontmatterError as exc:
            graph.load_issues.append(Issue("G001", ERROR, str(exc), rel))
            continue

        missing = [k for k in schema.REQUIRED_KEYS if not str(meta.get(k, "")).strip()]
        if missing:
            graph.load_issues.append(
                Issue("G001", ERROR, f"必須キーがありません: {', '.join(missing)}", rel)
            )
            continue

        node_id = str(meta["id"]).strip()
        if node_id in graph.nodes:
            graph.load_issues.append(
                Issue(
                    "G002",
                    ERROR,
                    f"id {node_id!r} が {graph.nodes[node_id].rel} と重複しています",
                    rel,
                )
            )
            continue

        clean_body = strip_auto_block(body)
        node = Node(
            id=node_id,
            type=str(meta["type"]).strip(),
            title=str(meta["title"]).strip(),
            status=str(meta["status"]).strip(),
            tags=as_list(meta.get("tags")),
            path=path,
            rel=rel,
            meta=meta,
            body=clean_body,
        )
        graph.add(node)
        by_path[path.resolve()] = node

        linkable = strip_non_prose(clean_body)
        wiki = WIKILINK_RE.findall(linkable)
        md = [
            href
            for href in MDLINK_RE.findall(linkable)
            if href.endswith(".md") and "://" not in href
        ]
        pending.append((node, wiki, md))

    for node, wiki, md in pending:
        _attach_frontmatter_edges(node, graph)
        _attach_body_edges(node, wiki, md, graph, by_path)

    return graph


def _attach_frontmatter_edges(node: Node, graph: Graph) -> None:
    for kind in schema.frontmatter_edge_kinds():
        for target in as_list(node.meta.get(kind)):
            node.edges.append(
                Edge(
                    src=node.id,
                    dst=target,
                    kind=kind,
                    origin="frontmatter",
                    resolved=target in graph.nodes,
                )
            )


def _attach_body_edges(
    node: Node,
    wiki: list[str],
    md: list[str],
    graph: Graph,
    by_path: dict[Path, Node],
) -> None:
    seen: set[str] = set()

    for raw in wiki:
        target = raw.strip()
        if not target or target in seen:
            continue
        seen.add(target)
        node.edges.append(
            Edge(
                src=node.id,
                dst=target,
                kind=schema.BODY_EDGE_KIND,
                origin="body",
                resolved=target in graph.nodes,
            )
        )

    for href in md:
        target_path = (node.path.parent / href).resolve()
        linked = by_path.get(target_path)
        if linked is not None:
            key = linked.id
            resolved = True
        else:
            key = href
            resolved = False
        if key in seen:
            continue
        seen.add(key)
        node.edges.append(
            Edge(
                src=node.id,
                dst=key,
                kind=schema.BODY_EDGE_KIND,
                origin="body",
                resolved=resolved,
            )
        )
