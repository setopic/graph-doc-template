"""テスト用の小さな組み立て道具。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.model import Graph, Node


def make_graph(nodes: list[Node]) -> Graph:
    graph = Graph()
    for node in nodes:
        graph.add(node)
    return graph


def _doc(node_id: str, node_type: str, title: str, edges: str = "") -> str:
    return f"---\nid: {node_id}\ntype: {node_type}\ntitle: {title}\nstatus: stable\ntags: []\n{edges}---\n\n# {title}\n"


# 既定の種別だけで組んだ、小さな文書のグラフ。metaどうしのrelated、ADRのdecides、
# 辿れば分かるdepends_on（DOM-01→DOM-02→ARCH-01と、DOM-01→ARCH-01）を含む
SAMPLE_DOCS = {
    "docs/index.md": _doc("IDX-ROOT", "index", "目次"),
    "docs/00-meta/graph-rules.md": _doc("META-01", "meta", "グラフの規約", "related:\n  - META-02\n"),
    "docs/00-meta/node-types.md": _doc("META-02", "meta", "ノード種別", "related:\n  - META-01\n"),
    "docs/10-architecture/arch-01-base.md": _doc("ARCH-01", "architecture", "土台"),
    "docs/20-domain/dom-01-booking.md": _doc(
        "DOM-01", "domain", "予約", "depends_on:\n  - DOM-02\n  - ARCH-01\nrelated:\n  - DOM-03\n"
    ),
    "docs/20-domain/dom-02-slot.md": _doc("DOM-02", "domain", "枠", "depends_on:\n  - ARCH-01\n"),
    "docs/20-domain/dom-03-guest.md": _doc("DOM-03", "domain", "客"),
    "docs/50-adr/adr-0001-graph.md": _doc(
        "ADR-0001", "adr", "グラフで管理する", "decides:\n  - META-01\n  - ARCH-01\n"
    ),
}


def sample_root(case: unittest.TestCase) -> Path:
    """SAMPLE_DOCSを置いた一時ディレクトリを作り、テストの終わりに消す。

    CLIのテストで`--root`にリポジトリの根を渡すと、根の`graph.toml`と文書に結果が左右される。
    種別を差し替えた派生では、既定の種別を前提にしたテストが落ちる。`cli.main`は
    `schema.configure`で語彙を差し替えるので、終わったら既定の語彙に戻す。
    """
    root = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, root, True)
    case.addCleanup(schema.reset)
    for rel, text in SAMPLE_DOCS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root
