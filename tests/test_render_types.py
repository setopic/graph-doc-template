"""render --typeのテスト。

挙げた種別のノードだけを個別に描き、ほかの種別を型ごとの箱にまとめることを固定する。
全体図と1つのノードの近傍の間に、1つの層の中を見る図が無かったことから入れた（#172）。
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from tools.graph import cli, render

from tests.helpers import make_graph, sample_root
from tests.test_render_mermaid import edge, edge_lines, node


def sample():
    return make_graph(
        [
            node(
                "ADR-0001",
                "adr",
                edges=[
                    edge("ADR-0001", "DOM-01", "decides"),
                    edge("ADR-0001", "DOM-02", "decides"),
                ],
            ),
            node(
                "DOM-01",
                "domain",
                edges=[edge("DOM-01", "DOM-02"), edge("DOM-01", "ARCH-01")],
            ),
            node("DOM-02", "domain", edges=[edge("DOM-02", "ARCH-01")]),
            node("DOM-03", "domain"),
            node("ARCH-01", "architecture"),
            node("ARCH-02", "architecture"),
        ]
    )


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(root), "render", *args])
    return code, out.getvalue(), err.getvalue()


class ToMermaidTypesTest(unittest.TestCase):
    def test_inside_edges_are_drawn_one_by_one(self) -> None:
        out = render.to_mermaid_types(sample(), {"domain"})
        self.assertIn("  DOM-01 -->|depends_on| DOM-02", edge_lines(out))

    def test_outside_nodes_become_type_boxes(self) -> None:
        out = render.to_mermaid_types(sample(), {"domain"})
        self.assertIn('  ARCH["アーキテクチャ<br/>2 件"]', out)
        self.assertNotIn("ARCH-01", out)
        self.assertNotIn("ADR-0001", out)

    def test_box_edges_are_counted_per_node(self) -> None:
        out = render.to_mermaid_types(sample(), {"domain"})
        lines = edge_lines(out)
        self.assertIn("  DOM-01 -->|depends_on 1| ARCH", lines)
        self.assertIn("  ADR -.->|decides 1| DOM-01", lines)
        self.assertEqual(len(lines), 5)

    def test_node_without_edges_is_not_drawn(self) -> None:
        out = render.to_mermaid_types(sample(), {"domain"})
        self.assertNotIn("DOM-03", out)

    def test_related_to_outside_starts_from_inside(self) -> None:
        graph = make_graph(
            [
                node("ARCH-01", "architecture", edges=[edge("ARCH-01", "DOM-01", "related")]),
                node("DOM-01", "domain", edges=[edge("DOM-01", "ARCH-01", "related")]),
            ]
        )
        out = render.to_mermaid_types(graph, {"domain"})
        self.assertEqual(edge_lines(out), ["  DOM-01 -.-|related 1| ARCH"])


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_root(self)

    def test_unknown_type_is_error(self) -> None:
        code, _, err = run(self.root, "--type", "domian")
        self.assertEqual(code, 1)
        self.assertIn("domian", err)

    def test_with_focus_is_error(self) -> None:
        code, _, _ = run(self.root, "--type", "meta", "--focus", "META-01")
        self.assertEqual(code, 1)

    def test_with_aggregate_is_error(self) -> None:
        code, _, _ = run(self.root, "--type", "meta", "--aggregate")
        self.assertEqual(code, 1)

    def test_json_has_only_listed_types(self) -> None:
        code, out, _ = run(self.root, "--format", "json", "--type", "meta")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["nodes"])
        self.assertEqual({n["type"] for n in payload["nodes"]}, {"meta"})
        ids = {n["id"] for n in payload["nodes"]}
        for e in payload["edges"]:
            self.assertIn(e["src"], ids)
            self.assertIn(e["dst"], ids)

    def test_hidden_edges_are_not_counted(self) -> None:
        code, out, _ = run(self.root, "--type", "meta", "--hide-edges", "related")
        self.assertEqual(code, 0)
        self.assertNotIn("|related", out)


if __name__ == "__main__":
    unittest.main()
