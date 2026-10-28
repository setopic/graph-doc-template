"""SVGの図（render --format svg）のテスト。

READMEの図は、層を列に並べたSVGを既定にした（#203）。配置・箱・線・クラス名だけを
renderが出し、見た目はテーマのCSSで決める。ここでは、次の性質を固定する。

- 同じ入力から同じバイト列を出す（make readme-checkがバイト列で比べるため）
- 層の大きい種別ほど左の列に置き、層のルールの対象外の種別は上下の帯に置く
- depends_onの線に動き（SMIL）を付け、graph.tomlの[render]で消したり周期を変えたりできる
- G018は、SVGでは警告だけを出す
"""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from tools.graph import cli, render, schema, svg
from tools.graph.model import WARN

from tests.helpers import make_graph
from tests.test_render_mermaid import edge, node

ROOT = Path(__file__).resolve().parents[1]
CSS = ".edge { stroke: red; }"


def sample():
    return make_graph(
        [
            node("ADR-0001", "adr", edges=[edge("ADR-0001", "ARCH-01", "decides")]),
            node(
                "CON-01",
                "contract",
                status="draft",
                edges=[edge("CON-01", "UC-01"), edge("CON-01", "DOM-01")],
            ),
            node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
            node("DOM-01", "domain", edges=[edge("DOM-01", "ARCH-01")]),
            node("ARCH-01", "architecture"),
            node("ARCH-02", "architecture", edges=[edge("ARCH-02", "ARCH-01", "refines")]),
            node("META-01", "meta", edges=[edge("META-01", "META-02", "related")]),
            node("META-02", "meta", edges=[edge("META-02", "META-01", "related")]),
        ]
    )


def box_xy(out: str, node_id: str) -> tuple[float, float]:
    match = re.search(
        rf'data-id="{re.escape(node_id)}">\n<rect class="box" x="([\d.]+)" y="([\d.]+)"', out
    )
    assert match, node_id
    return float(match.group(1)), float(match.group(2))


class LayoutTest(unittest.TestCase):
    def test_same_input_gives_same_bytes(self) -> None:
        self.assertEqual(svg.to_svg(sample(), css=CSS), svg.to_svg(sample(), css=CSS))

    def test_layers_are_columns_from_left(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        xs = [box_xy(out, i)[0] for i in ("CON-01", "UC-01", "DOM-01", "ARCH-01")]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(len(set(xs)), 4)

    def test_exempt_types_go_to_bands(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        adr_y = box_xy(out, "ADR-0001")[1]
        meta_y = box_xy(out, "META-01")[1]
        for node_id in ("CON-01", "UC-01", "DOM-01", "ARCH-01", "ARCH-02"):
            y = box_xy(out, node_id)[1]
            self.assertLess(adr_y, y)
            self.assertGreater(meta_y, y)

    def test_crossing_is_reduced(self) -> None:
        """A1→B2とA2→B1は、並べ替えで交差しない並びになる。"""
        graph = make_graph(
            [
                node("UC-01", "usecase", edges=[edge("UC-01", "DOM-02")]),
                node("UC-02", "usecase", edges=[edge("UC-02", "DOM-01")]),
                node("DOM-01", "domain"),
                node("DOM-02", "domain"),
            ]
        )
        out = svg.to_svg(graph, css=CSS)
        uc = box_xy(out, "UC-01")[1] < box_xy(out, "UC-02")[1]
        dom = box_xy(out, "DOM-02")[1] < box_xy(out, "DOM-01")[1]
        self.assertEqual(uc, dom)

    def test_long_title_is_wrapped_and_cut(self) -> None:
        graph = make_graph(
            [
                node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
                node("DOM-01", "domain"),
            ]
        )
        graph.nodes["UC-01"].title = "とても長い題" * 20
        out = svg.to_svg(graph, css=CSS)
        title = re.search(r'data-id="UC-01">.*?<text class="node-title">(.*?)</text>', out, re.S)
        spans = re.findall(r"<tspan[^>]*>(.*?)</tspan>", title.group(1))
        self.assertEqual(len(spans), 2)
        self.assertTrue(spans[-1].endswith("…"))
        for span in spans:
            self.assertLessEqual(svg.text_width(span, svg.TITLE_FONT), svg.BOX_MAX_W - 2 * svg.PAD_X)

    def test_text_is_escaped(self) -> None:
        graph = make_graph(
            [
                node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
                node("DOM-01", "domain"),
            ]
        )
        graph.nodes["UC-01"].title = "A&B <c>"
        out = svg.to_svg(graph, css=CSS)
        self.assertIn("A&amp;B &lt;c&gt;", out)


class ClassTest(unittest.TestCase):
    def test_node_classes(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        self.assertIn('<g class="node t-contract s-draft" data-id="CON-01">', out)

    def test_edge_classes(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        self.assertRegex(out, r'class="edge k-depends_on" d="[^"]+" marker-end="url\(#arrow-depends_on\)"')
        # relatedは向きが無いので、矢印を付けず、往復を1本にする
        self.assertEqual(out.count('class="edge k-related undirected"'), 1)

    def test_css_is_embedded(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        self.assertIn(f"<style><![CDATA[\n{CSS}\n]]></style>", out)

    def test_default_theme_is_used_without_config(self) -> None:
        schema.reset()
        self.assertEqual(svg.load_theme(ROOT), svg.DEFAULT_THEME.read_text(encoding="utf-8"))

    def test_focus_class(self) -> None:
        out = svg.to_svg(sample(), css=CSS, focus={"DOM-01"})
        self.assertIn('<g class="node t-domain s-stable focus" data-id="DOM-01">', out)


class FlowTest(unittest.TestCase):
    def test_depends_on_edges_have_dots(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        # depends_onは4本。点はdepends_onにだけ付く
        self.assertEqual(out.count('<circle class="flow-dot k-depends_on"'), 4)
        self.assertIn('dur="6s"', out)

    def test_period(self) -> None:
        out = svg.to_svg(sample(), css=CSS, period=3)
        self.assertIn('dur="3s"', out)
        self.assertNotIn('dur="6s"', out)

    def test_no_animation(self) -> None:
        out = svg.to_svg(sample(), css=CSS, animate=False)
        self.assertNotIn("<animate", out)
        self.assertNotIn('class="flow"', out)

    def test_glow_on_destination(self) -> None:
        out = svg.to_svg(sample(), css=CSS)
        self.assertIn('<rect class="glow"', out)


class VariantsTest(unittest.TestCase):
    def test_aggregate(self) -> None:
        out = svg.to_svg(sample(), css=CSS, aggregate=True)
        self.assertIn('data-id="UC"', out)
        self.assertNotIn('data-id="UC-01"', out)
        # 型の組ごとに本数を書く。メタ / 規約どうしのrelatedは、往復の2本を数える
        self.assertIn(">related 2</text>", out)

    def test_types(self) -> None:
        out = svg.to_svg(sample(), css=CSS, types={"domain"})
        self.assertIn('data-id="DOM-01"', out)
        self.assertIn('class="node group t-usecase" data-id="UC"', out)
        self.assertNotIn('data-id="UC-01"', out)

    def test_note_reduced_goes_to_desc(self) -> None:
        out = render.note_reduced(svg.to_svg(sample(), css=CSS), "svg", 2)
        self.assertIn("<desc>ほかのdepends_onを辿れば分かる依存を2本省いた（render --reduce）</desc>", out)
        self.assertNotIn("<!--", out)


def crowded(adrs: int, contracts: int = 0):
    """決定記録がadrs個あり、それぞれがARCH-01・DOM-01・UC-01をdecidesで指すグラフ。
    契約はcontracts個あり、それぞれがARCH-01へdepends_onで2列以上をまたぐ。"""
    nodes = [
        node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
        node("DOM-01", "domain", edges=[edge("DOM-01", "ARCH-01")]),
        node("ARCH-01", "architecture"),
    ]
    for i in range(1, adrs + 1):
        adr = f"ADR-{i:04d}"
        nodes.append(
            node(adr, "adr", edges=[edge(adr, t, "decides") for t in ("ARCH-01", "DOM-01", "UC-01")])
        )
    for i in range(1, contracts + 1):
        con = f"CON-{i:02d}"
        nodes.append(node(con, "contract", edges=[edge(con, "UC-01"), edge(con, "ARCH-01")]))
    return make_graph(nodes)


class CrowdedTest(unittest.TestCase):
    """線の多い図でも、線の名前と通り道が重ならないようにする。"""

    def test_band_label_once_per_box_and_kind(self) -> None:
        out = svg.to_svg(crowded(5), css=CSS)
        labels = re.findall(r'<text class="edge-label k-decides"[^>]*>decides</text>', out)
        self.assertEqual(len(labels), 5)

    def test_corridor_grows_with_lines(self) -> None:
        def gap(graph) -> float:
            boxes, lines = svg._parts_plain(graph, False, set())
            lay = svg._layout(boxes, lines)
            band_bottom = max(b.y + b.h for b in lay.boxes.values() if b.type == "adr")
            return min(y for _, _, y, _, _ in lay.lanes) - band_bottom

        self.assertEqual(gap(crowded(1)), svg.BAND_GAP)
        many = gap(crowded(10))
        self.assertGreaterEqual(many, svg.CORRIDOR_STEP * 30)

    def test_dummies_are_packed(self) -> None:
        boxes, lines = svg._parts_plain(crowded(0, contracts=6), False, set())
        lay = svg._layout(boxes, lines)
        dummies = [d for ds in lay.dummies.values() for d in ds if d.type == "usecase"]
        self.assertEqual(len(dummies), 6)
        column = sorted(dummies + [lay.boxes["UC-01"]], key=lambda b: b.y)
        # 続けて並ぶ通り道どうしは、DUMMY_GAPだけ空けて詰める
        steps = {round(b.y - a.y, 1) for a, b in zip(column, column[1:]) if not a.head and not b.head}
        self.assertEqual(steps, {svg.DUMMY_H + svg.DUMMY_GAP})

    def test_same_input_gives_same_bytes(self) -> None:
        self.assertEqual(svg.to_svg(crowded(10, 6), css=CSS), svg.to_svg(crowded(10, 6), css=CSS))


def superseded(adrs: int):
    """決定記録がadrs個あり、それぞれが1つ前の決定記録をsupersedesで置き換え、
    いずれかの層の箱をdecidesで指すグラフ。題の長さを変えて、箱の幅をばらつかせる。"""
    titles = ["予約", "在庫の引き当て", "とても長い題の文書で折り返しが要るかを確かめる"]
    targets = ["ARCH-01", "DOM-01", "UC-01"]
    nodes = [
        node("UC-01", "usecase", edges=[edge("UC-01", "DOM-01")]),
        node("DOM-01", "domain", edges=[edge("DOM-01", "ARCH-01")]),
        node("ARCH-01", "architecture"),
    ]
    for i in range(1, adrs + 1):
        adr = f"ADR-{i:04d}"
        edges = [edge(adr, targets[i % 3], "decides")]
        if i > 1:
            edges.append(edge(adr, f"ADR-{i - 1:04d}", "supersedes"))
        n = node(adr, "adr", edges=edges)
        n.title = titles[(i * 7) % 3]
        nodes.append(n)
    return make_graph(nodes)


def drawn_boxes(out: str) -> list[tuple[float, float, float, float]]:
    found = re.findall(r'<rect class="box" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', out)
    return [(float(x), float(y), float(x) + float(w), float(y) + float(h)) for x, y, w, h in found]


def drawn_labels(out: str, kinds: set[str]) -> list[tuple[str, tuple[float, float, float, float]]]:
    """図に書いた線の名前と、その矩形の見積もり。kindsの種類の名前だけを返す。"""
    found = re.findall(
        r'<text class="edge-label k-(\w+)[^"]*" x="([\d.]+)" y="([\d.]+)" text-anchor="(\w+)">([^<]*)</text>', out
    )
    return [
        (text, svg.label_rect(text, (float(x), float(y) + 4), anchor))
        for kind, x, y, anchor, text in found
        if kind in kinds
    ]


class BandLabelTest(unittest.TestCase):
    """上の段で決定記録どうしを結ぶ線の名前が、箱に隠れたり、ほかの名前に重なったりしない。"""

    def setUp(self) -> None:
        self.out = svg.to_svg(superseded(14), css=CSS)

    def test_labels_do_not_hit_boxes(self) -> None:
        boxes = drawn_boxes(self.out)
        labels = drawn_labels(self.out, {"supersedes", "decides"})
        self.assertTrue(labels)
        for text, rect in labels:
            for box in boxes:
                self.assertFalse(svg._meets(rect, box), (text, rect, box))

    def test_labels_do_not_meet_each_other(self) -> None:
        labels = drawn_labels(self.out, {"supersedes", "decides"})
        for k, (text, rect) in enumerate(labels):
            for other, rect2 in labels[k + 1 :]:
                self.assertFalse(svg._meets(rect, rect2), (text, rect, other, rect2))

    def test_every_line_keeps_its_name(self) -> None:
        # 図に書けなかった名前は、線のツールチップに回す。どの線も名前を失わない
        shown = len(drawn_labels(self.out, {"supersedes"}))
        tooltips = self.out.count("<title>supersedes</title>")
        self.assertEqual(shown + tooltips, 13)

    def test_adjacent_boxes_leave_room_for_the_name(self) -> None:
        boxes, lines = svg._parts_plain(superseded(2), False, set())
        lay = svg._layout(boxes, lines)
        a, b = sorted((lay.boxes[k] for k in ("ADR-0001", "ADR-0002")), key=lambda x: x.x)
        self.assertEqual(a.y, b.y)
        need = svg.text_width("supersedes", svg.EDGE_LABEL_FONT) + 2 * svg.LABEL_PAD
        self.assertGreaterEqual(round(b.x - (a.x + a.w), 1), round(need, 1))

    def test_same_input_gives_same_bytes(self) -> None:
        self.assertEqual(self.out, svg.to_svg(superseded(14), css=CSS))


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(root), "render", *args])
    return code, out.getvalue(), err.getvalue()


class IntoReadmeTest(unittest.TestCase):
    """render --format svg --intoは、SVGをファイルに書き、READMEには画像への参照を書く。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "index.md").write_text(
            "---\nid: IDX-01\ntype: index\ntitle: 目次\nstatus: stable\n---\n\n# 目次\n",
            encoding="utf-8",
        )
        (self.tmp / "README.md").write_text(
            f"# 題\n\n{schema.DIAGRAM_BLOCK_START}\n{schema.DIAGRAM_BLOCK_END}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        schema.reset()

    def test_writes_svg_and_reference(self) -> None:
        code, out, _ = run(self.tmp, "--format", "svg", "--into", "README.md")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / "docs" / "graph.svg").is_file())
        readme = (self.tmp / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"![{render.SVG_ALT}](docs/graph.svg)", readme)
        self.assertNotIn("```mermaid", readme)

    def test_check_finds_stale_svg(self) -> None:
        run(self.tmp, "--format", "svg", "--into", "README.md")
        code, _, _ = run(self.tmp, "--format", "svg", "--into", "README.md", "--check")
        self.assertEqual(code, 0)
        (self.tmp / "docs" / "graph.svg").write_text("<svg/>\n", encoding="utf-8")
        code, out, _ = run(self.tmp, "--format", "svg", "--into", "README.md", "--check")
        self.assertEqual(code, 1)
        self.assertIn("図が古くなっている", out)
        # --checkは書き換えない
        self.assertEqual((self.tmp / "docs" / "graph.svg").read_text(encoding="utf-8"), "<svg/>\n")

    def test_out_sets_the_svg_path(self) -> None:
        code, _, _ = run(self.tmp, "--format", "svg", "--into", "README.md", "--out", "img/g.svg")
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "img" / "g.svg").is_file())
        self.assertIn("](img/g.svg)", (self.tmp / "README.md").read_text(encoding="utf-8"))

    def test_render_config_is_used(self) -> None:
        (self.tmp / "theme.css").write_text(".x { fill: blue; }\n", encoding="utf-8")
        (self.tmp / "graph.toml").write_text(
            '[render]\ntheme = "theme.css"\nanimate = false\n', encoding="utf-8"
        )
        code, _, _ = run(self.tmp, "--format", "svg", "--into", "README.md")
        self.assertEqual(code, 0)
        out = (self.tmp / "docs" / "graph.svg").read_text(encoding="utf-8")
        self.assertIn(".x { fill: blue; }", out)
        self.assertNotIn("<animate", out)


class RenderConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        schema.reset()

    def configure(self, text: str) -> None:
        (self.tmp / "graph.toml").write_text(text, encoding="utf-8")
        schema.configure(self.tmp)

    def test_defaults(self) -> None:
        schema.configure(self.tmp)
        self.assertIsNone(schema.RENDER_THEME)
        self.assertTrue(schema.RENDER_ANIMATE)
        self.assertEqual(schema.RENDER_PERIOD, 6.0)

    def test_values(self) -> None:
        (self.tmp / "t.css").write_text("", encoding="utf-8")
        self.configure('[render]\ntheme = "t.css"\nanimate = false\nperiod = 4\n')
        self.assertEqual(schema.RENDER_THEME, "t.css")
        self.assertFalse(schema.RENDER_ANIMATE)
        self.assertEqual(schema.RENDER_PERIOD, 4.0)

    def test_reset_returns_to_defaults(self) -> None:
        self.configure("[render]\nanimate = false\n")
        (self.tmp / "graph.toml").unlink()
        schema.configure(self.tmp)
        self.assertTrue(schema.RENDER_ANIMATE)

    def test_errors(self) -> None:
        for text in (
            '[render]\ntheme = "missing.css"\n',
            '[render]\ntheme = "../t.css"\n',
            '[render]\nanimate = "yes"\n',
            "[render]\nperiod = 0\n",
            "[render]\nperiod = true\n",
            "[render]\ncolor = 1\n",
        ):
            with self.subTest(text=text), self.assertRaises(schema.ConfigError):
                self.configure(text)


class G018SvgTest(unittest.TestCase):
    def _issues(self, edges: int) -> list:
        from tools.graph.rules import rule_g018_diagram_size

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            paths = "\n".join(f'<path id="e{i}" class="edge k-depends_on" d="M0,0"/>' for i in range(edges))
            (root / "docs" / "graph.svg").write_text(f"<svg>\n{paths}\n</svg>\n", encoding="utf-8")
            (root / "README.md").write_text(
                f"{schema.DIAGRAM_BLOCK_START}\n\n![g](docs/graph.svg)\n\n{schema.DIAGRAM_BLOCK_END}\n",
                encoding="utf-8",
            )
            graph = make_graph([node("UC-01", "usecase")])
            graph.root = root
            return rule_g018_diagram_size(graph)

    def test_counts_edges_in_the_svg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "g.svg").write_text(
                '<svg>\n<path id="e0" class="edge k-related undirected" d="M0,0"/>\n'
                '<path class="arrow-head k-depends_on" d="M0,0"/>\n</svg>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                f"{schema.DIAGRAM_BLOCK_START}\n![g](g.svg)\n{schema.DIAGRAM_BLOCK_END}\n",
                encoding="utf-8",
            )
            self.assertEqual(render.diagram_in_markdown(root / "README.md"), ("svg", 1))

    def test_silent_under_threshold(self) -> None:
        self.assertEqual(self._issues(10), [])

    def test_only_warns_over_the_mermaid_limit(self) -> None:
        issues = self._issues(schema.MERMAID_MAX_EDGES + 10)
        self.assertEqual([i.severity for i in issues], [WARN])
        self.assertIn("SVG", issues[0].message)
        self.assertIn("graph.mk", issues[0].message)


if __name__ == "__main__":
    unittest.main()
