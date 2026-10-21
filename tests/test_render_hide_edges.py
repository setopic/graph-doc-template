"""render --hide-edgesのテスト。

挙げた種類の線を描かないことと、その線しか持たないノードが図から外れることを固定する。
派生のREADMEの図が、ADRから出るdecidesの線で読めない大きさになったことから入れた（#171）。
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from tools.graph import cli, render

from tests.helpers import make_graph
from tests.test_render_mermaid import edge, edge_lines, node

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return make_graph(
        [
            node(
                "ADR-0001",
                "adr",
                edges=[
                    edge("ADR-0001", "DOM-01", "decides"),
                    edge("ADR-0001", "ARCH-01", "decides"),
                ],
            ),
            node("DOM-01", "domain", edges=[edge("DOM-01", "ARCH-01")]),
            node("ARCH-01", "architecture"),
        ]
    )


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(ROOT), "render", *args])
    return code, out.getvalue(), err.getvalue()


class WithoutKindsTest(unittest.TestCase):
    def test_hidden_kind_is_not_drawn(self) -> None:
        out = render.to_mermaid(sample().without_kinds({"decides"}))
        self.assertEqual(edge_lines(out), ["  DOM-01 -->|depends_on| ARCH-01"])

    def test_node_with_only_hidden_edges_is_dropped(self) -> None:
        out = render.to_mermaid(sample().without_kinds({"decides"}))
        self.assertNotIn("ADR-0001", out)
        self.assertIn("DOM-01", out)

    def test_focus_node_is_kept(self) -> None:
        graph = sample().without_kinds({"decides"})
        out = render.to_mermaid(graph, focus={"ADR-0001"})
        self.assertIn('ADR-0001["', out)

    def test_nodes_are_kept_in_graph(self) -> None:
        graph = sample().without_kinds({"decides"})
        self.assertEqual(set(graph.nodes), {"ADR-0001", "DOM-01", "ARCH-01"})


class CliTest(unittest.TestCase):
    def test_unknown_kind_is_error(self) -> None:
        code, _, err = run("--hide-edges", "decide")
        self.assertEqual(code, 1)
        self.assertIn("decide", err)

    def test_json_has_no_hidden_edges(self) -> None:
        code, out, _ = run("--format", "json", "--hide-edges", "decides,related")
        self.assertEqual(code, 0)
        kinds = {e["kind"] for e in json.loads(out)["edges"]}
        self.assertTrue(kinds)
        self.assertFalse(kinds & {"decides", "related"})

    def test_aggregate_has_no_hidden_edges(self) -> None:
        code, out, _ = run("--aggregate", "--hide-edges", "related")
        self.assertEqual(code, 0)
        self.assertNotIn("|related", out)


if __name__ == "__main__":
    unittest.main()
