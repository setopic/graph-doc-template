"""個別のノードの図（render --format mermaid）のテスト。

`related`の往復を1本の線にまとめることと、線の無いノードを描かないことを固定する。
どちらも、READMEの図が線の数のわりに絡まって読みにくかったことから入れた（#169）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph import render
from tools.graph.model import Edge, Node

from tests.helpers import make_graph


def node(
    node_id: str,
    node_type: str,
    *,
    edges: list[Edge] | None = None,
    status: str = "stable",
) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        title=f"{node_id} の題",
        status=status,
        tags=[],
        path=Path(f"/tmp/{node_id}.md"),
        rel=f"docs/{node_id}.md",
        meta={},
        body="",
        edges=edges or [],
    )


def edge(src: str, dst: str, kind: str = "depends_on") -> Edge:
    return Edge(src=src, dst=dst, kind=kind, origin="frontmatter", resolved=True)


def edge_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if render.EDGE_LINE_RE.match(line)]


class RelatedOnceTest(unittest.TestCase):
    """`related`は向きの無い関係なので、ノードの組ごとに矢印の無い線1本で描く。"""

    def test_round_trip_becomes_one_line(self) -> None:
        graph = make_graph(
            [
                node("META-01", "meta", edges=[edge("META-01", "META-02", "related")]),
                node("META-02", "meta", edges=[edge("META-02", "META-01", "related")]),
            ]
        )
        out = render.to_mermaid(graph)
        self.assertEqual(edge_lines(out), ["  META-01 -.-|related| META-02"])

    def test_one_way_related_has_no_arrow(self) -> None:
        graph = make_graph(
            [
                node("META-01", "meta", edges=[edge("META-01", "META-02", "related")]),
                node("META-02", "meta"),
            ]
        )
        out = render.to_mermaid(graph)
        self.assertEqual(edge_lines(out), ["  META-01 -.-|related| META-02"])

    def test_directed_kinds_keep_both_directions(self) -> None:
        """向きのある種別は、まとめない。往復していれば、そのまま2本を描く。"""
        graph = make_graph(
            [
                node("DOM-01", "domain", edges=[edge("DOM-01", "DOM-02", "depends_on")]),
                node("DOM-02", "domain", edges=[edge("DOM-02", "DOM-01", "depends_on")]),
            ]
        )
        out = render.to_mermaid(graph)
        self.assertEqual(
            edge_lines(out),
            ["  DOM-01 -->|depends_on| DOM-02", "  DOM-02 -->|depends_on| DOM-01"],
        )

    def test_aggregate_is_unchanged(self) -> None:
        """集約図は、往復を2本として数えたまま、矢印で描く。"""
        graph = make_graph(
            [
                node("META-01", "meta", edges=[edge("META-01", "META-02", "related")]),
                node("META-02", "meta", edges=[edge("META-02", "META-01", "related")]),
            ]
        )
        out = render.to_mermaid_aggregate(graph)
        self.assertIn("META -.->|related 2| META", out)


class UnlinkedNodesTest(unittest.TestCase):
    """線を1本も持たないノードは、図に出さない。"""

    def _graph(self) -> list[Node]:
        return [
            node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
            node("DOM-01", "domain"),
            node("DOM-02", "domain", status="draft"),
            node("IDX-ROOT", "index"),
        ]

    def test_unlinked_node_is_left_out(self) -> None:
        out = render.to_mermaid(make_graph(self._graph()))
        self.assertIn("DOM-01[", out)
        self.assertNotIn("DOM-02", out)

    def test_subgraph_without_nodes_is_left_out(self) -> None:
        out = render.to_mermaid(make_graph(self._graph()))
        self.assertNotIn("subgraph index", out)
        self.assertEqual(out.count("subgraph "), out.count("  end\n"))

    def test_status_class_skips_unlinked_nodes(self) -> None:
        """描かないノードを`class`に挙げると、Mermaidがそのノードを作ってしまう。"""
        out = render.to_mermaid(make_graph(self._graph()))
        self.assertNotIn("draft;", out.replace("classDef draft", ""))

    def test_focus_node_stays_without_lines(self) -> None:
        out = render.to_mermaid(make_graph(self._graph()), focus={"IDX-ROOT"})
        self.assertIn("subgraph index", out)
        self.assertIn("IDX-ROOT[", out)
        self.assertIn("class IDX-ROOT focus;", out)
        self.assertNotIn("DOM-02", out)


if __name__ == "__main__":
    unittest.main()
