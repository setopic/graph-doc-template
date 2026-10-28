"""render --reduceのテスト。

ほかのdepends_onを辿れば分かる依存を図から省くことと、検査の元になるグラフは変えないことを固定する。
派生のドメイン層の図が、層の中の線118本で読めない大きさになったことから入れた（#174）。
"""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from tools.graph import cli, render

from tests.helpers import make_graph, sample_root
from tests.test_render_mermaid import edge, edge_lines, node


def chain():
    """DOM-01→DOM-02→DOM-03と、辿れば分かるDOM-01→DOM-03"""
    return make_graph(
        [
            node(
                "DOM-01",
                "domain",
                edges=[
                    edge("DOM-01", "DOM-02"),
                    edge("DOM-01", "DOM-03"),
                    edge("DOM-01", "DOM-02", "related"),
                ],
            ),
            node(
                "DOM-02",
                "domain",
                edges=[edge("DOM-02", "DOM-03"), edge("DOM-02", "DOM-01", "related")],
            ),
            node("DOM-03", "domain"),
        ]
    )


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(root), "render", *args])
    return code, out.getvalue(), err.getvalue()


class WithoutImpliedTest(unittest.TestCase):
    def test_implied_edge_is_dropped(self) -> None:
        graph, count = chain().without_implied("depends_on")
        self.assertEqual(count, 1)
        self.assertEqual(
            [line for line in edge_lines(render.to_mermaid(graph)) if "depends_on" in line],
            ["  DOM-01 -->|depends_on| DOM-02", "  DOM-02 -->|depends_on| DOM-03"],
        )

    def test_other_kinds_are_kept(self) -> None:
        graph, _ = chain().without_implied("depends_on")
        self.assertIn("|related|", render.to_mermaid(graph))

    def test_original_graph_is_unchanged(self) -> None:
        graph = chain()
        graph.without_implied("depends_on")
        self.assertEqual(len(graph.nodes["DOM-01"].out_edges("depends_on")), 2)

    def test_path_outside_among_is_not_used(self) -> None:
        # DOM-01→ARCH-01→DOM-02のような経路は、描かないノードを通るので使わない
        graph = make_graph(
            [
                node(
                    "DOM-01",
                    "domain",
                    edges=[edge("DOM-01", "DOM-02"), edge("DOM-01", "UC-01")],
                ),
                node("UC-01", "usecase", edges=[edge("UC-01", "DOM-02")]),
                node("DOM-02", "domain"),
            ]
        )
        _, count = graph.without_implied("depends_on", {"DOM-01", "DOM-02"})
        self.assertEqual(count, 0)
        _, count = graph.without_implied("depends_on")
        self.assertEqual(count, 1)

    def test_cycle_keeps_reachability(self) -> None:
        # 循環はG006の誤りだが、図に描くときに辿れる範囲を変えない
        graph = make_graph(
            [
                node("DOM-01", "domain", edges=[edge("DOM-01", "DOM-02")]),
                node("DOM-02", "domain", edges=[edge("DOM-02", "DOM-01")]),
            ]
        )
        _, count = graph.without_implied("depends_on")
        self.assertEqual(count, 0)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_root(self)

    def test_comment_and_stderr(self) -> None:
        code, out, err = run(self.root, "--reduce")
        self.assertEqual(code, 0)
        self.assertIn("%% ほかのdepends_onを辿れば分かる依存を", out.splitlines()[1])
        self.assertIn("本省いた", err)

    def test_dot_comment(self) -> None:
        code, out, _ = run(self.root, "--reduce", "--format", "dot")
        self.assertEqual(code, 0)
        self.assertIn("// ", out.splitlines()[1])

    def test_with_type(self) -> None:
        code, _, _ = run(self.root, "--reduce", "--type", "domain")
        self.assertEqual(code, 0)

    def test_json_is_error(self) -> None:
        code, _, err = run(self.root, "--reduce", "--format", "json")
        self.assertEqual(code, 1)
        self.assertIn("--reduce", err)

    def test_aggregate_is_error(self) -> None:
        code, _, err = run(self.root, "--reduce", "--aggregate")
        self.assertEqual(code, 1)
        self.assertIn("--reduce", err)


if __name__ == "__main__":
    unittest.main()
