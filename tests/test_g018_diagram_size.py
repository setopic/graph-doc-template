"""G018（README の図が GitHub の描画上限に近い）と、集約図のテスト。

**数えるのはグラフではなく README に入っている図そのもの**という性質を固定する。
ここを取り違えると、`--aggregate` で間引いているリポジトリが誤検知で落ちる。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.graph import render, schema
from tools.graph.model import ERROR, WARN, Edge, Graph, Node

from .helpers import make_graph


def node(node_id: str, node_type: str, *, edges: list[Edge] | None = None) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        title=f"{node_id} の題",
        status="stable",
        tags=[],
        path=Path(f"/tmp/{node_id}.md"),
        rel=f"docs/{node_id}.md",
        meta={},
        body="",
        edges=edges or [],
    )


def edge(src: str, dst: str, kind: str = "depends_on") -> Edge:
    return Edge(src=src, dst=dst, kind=kind, origin="frontmatter", resolved=True)


def readme_with(diagram_lines: list[str]) -> str:
    """マーカーで囲んだ Mermaid 図を持つ README の中身を作る。"""
    return "\n".join(
        [
            "# 題",
            "",
            schema.DIAGRAM_BLOCK_START,
            "```mermaid",
            "graph LR",
            *diagram_lines,
            "```",
            schema.DIAGRAM_BLOCK_END,
            "",
        ]
    )


def edge_lines(count: int) -> list[str]:
    return [f"  N{i} -->|depends_on| N{i + 1}" for i in range(count)]


class CountEdgesTest(unittest.TestCase):
    """count_edges_in_markdown が図の中のエッジ行だけを数えること。"""

    def test_counts_only_edge_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                readme_with(
                    [
                        '  subgraph usecase["ユースケース"]',
                        '    UC-01["UC-01<br/>題"]',
                        "  end",
                        "  UC-01 -->|depends_on| DOM-01",
                        "  UC-01 -.->|related| DOM-02",
                        "  ADR-01 ==>|supersedes| ADR-02",
                        "  classDef draft stroke-dasharray: 4\\,3;",
                        "  class UC-01 draft;",
                    ]
                ),
                encoding="utf-8",
            )
            # ノード行・subgraph・classDef・class は数えない
            self.assertEqual(render.count_edges_in_markdown(readme), 3)

    def test_no_marker_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text("# 図のない README\n", encoding="utf-8")
            self.assertIsNone(render.count_edges_in_markdown(readme))

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(render.count_edges_in_markdown(Path(tmp) / "README.md"))


class RuleG018Test(unittest.TestCase):
    def _issues(self, count: int | None) -> list:
        from tools.graph.rules import rule_g018_diagram_size

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if count is not None:
                (root / "README.md").write_text(
                    readme_with(edge_lines(count)), encoding="utf-8"
                )
            graph = make_graph([node("UC-01", "usecase")])
            graph.root = root
            return rule_g018_diagram_size(graph)

    def test_silent_when_root_unknown(self) -> None:
        from tools.graph.rules import rule_g018_diagram_size

        graph = make_graph([node("UC-01", "usecase")])
        graph.root = None
        self.assertEqual(rule_g018_diagram_size(graph), [])

    def test_silent_without_readme(self) -> None:
        self.assertEqual(self._issues(None), [])

    def test_silent_well_under_limit(self) -> None:
        self.assertEqual(self._issues(10), [])

    def test_silent_just_below_warn(self) -> None:
        self.assertEqual(self._issues(schema.MERMAID_WARN_EDGES - 1), [])

    def test_warns_when_approaching(self) -> None:
        issues = self._issues(schema.MERMAID_WARN_EDGES)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G018")
        self.assertEqual(issues[0].severity, WARN)

    def test_warns_just_below_limit(self) -> None:
        issues = self._issues(schema.MERMAID_MAX_EDGES - 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, WARN)

    def test_errors_at_the_limit(self) -> None:
        """**ちょうど上限で既に落ちている。** GitHub の文言が
        「500 edges found, but the limit is 500」で、その時点で図が消えている。"""
        issues = self._issues(schema.MERMAID_MAX_EDGES)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, ERROR)

    def test_errors_when_over_limit(self) -> None:
        issues = self._issues(schema.MERMAID_MAX_EDGES + 1)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G018")
        self.assertEqual(issues[0].severity, ERROR)
        self.assertIn("--aggregate", issues[0].message)

    def test_error_points_to_graph_mk(self) -> None:
        """置き場所はgraph.mkである。テンプレートはMakefileを配るので、Makefileに足すと取り込みで競合する。"""
        issues = self._issues(schema.MERMAID_MAX_EDGES)
        self.assertIn("graph.mk", issues[0].message)
        self.assertNotIn("Makefile", issues[0].message)


class AggregateRenderTest(unittest.TestCase):
    def _graph(self, usecase_count: int) -> Graph:
        nodes = [node("DOM-01", "domain")]
        for i in range(1, usecase_count + 1):
            nodes.append(
                node(f"UC-{i:02d}", "usecase", edges=[edge(f"UC-{i:02d}", "DOM-01")])
            )
        return make_graph(nodes)

    def test_one_box_per_type(self) -> None:
        out = render.to_mermaid_aggregate(self._graph(3))
        self.assertIn('UC["ユースケース<br/>3 件"]', out)
        self.assertIn('DOM["ドメイン<br/>1 件"]', out)
        # 個別のノードは出さない
        self.assertNotIn("UC-01[", out)

    def test_edges_are_folded_with_counts(self) -> None:
        out = render.to_mermaid_aggregate(self._graph(3))
        self.assertIn("UC -->|depends_on 3| DOM", out)

    def test_diagram_does_not_grow_with_nodes(self) -> None:
        """**これが集約を入れる理由。** ノードが増えても図の行数が変わらない。"""
        small = render.to_mermaid_aggregate(self._graph(3))
        large = render.to_mermaid_aggregate(self._graph(300))
        self.assertEqual(
            len(small.splitlines()),
            len(large.splitlines()),
            "ノードを増やしても集約図の行数は変わらないはず",
        )

    def test_edge_kinds_stay_separate(self) -> None:
        graph = make_graph(
            [
                node("DOM-01", "domain"),
                node(
                    "UC-01",
                    "usecase",
                    edges=[
                        edge("UC-01", "DOM-01", "depends_on"),
                        edge("UC-01", "DOM-01", "related"),
                    ],
                ),
            ]
        )
        out = render.to_mermaid_aggregate(graph)
        self.assertIn("UC -->|depends_on 1| DOM", out)
        self.assertIn("UC -.->|related 1| DOM", out)

    def test_unresolved_edges_are_skipped(self) -> None:
        broken = Edge(
            src="UC-01", dst="DOM-99", kind="depends_on", origin="frontmatter",
            resolved=False,
        )
        graph = make_graph([node("UC-01", "usecase", edges=[broken])])
        out = render.to_mermaid_aggregate(graph)
        self.assertNotIn("DOM", out)


if __name__ == "__main__":
    unittest.main()
