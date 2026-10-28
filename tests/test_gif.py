"""SVGの図からGIFを作るコマンド（python -m tools.graph gif）のテスト。

ブラウザとPillowはCIに無いので、実際には撮らない。コマの時刻の決め方と、
足りないものがあるときに何が要るかを示して終わることを固定する（#203）。
"""

from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.graph import cli, gif, schema

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200" width="300" height="200">\n'
    '<circle r="4"><animateMotion dur="6s" begin="0s" repeatCount="indefinite"/></circle>\n'
    "</svg>\n"
)


class FrameTest(unittest.TestCase):
    def test_size_and_period(self) -> None:
        self.assertEqual(gif.svg_size(SVG), (300, 200))
        self.assertEqual(gif.svg_period(SVG), 6.0)
        self.assertIsNone(gif.svg_period("<svg width=\"1\" height=\"1\"></svg>"))

    def test_size_is_required(self) -> None:
        with self.assertRaises(gif.GifError):
            gif.svg_size("<svg></svg>")

    def test_frames_cover_one_period_without_repeating_the_start(self) -> None:
        times = gif.frame_times(6.0, 10)
        self.assertEqual(len(times), 60)
        self.assertEqual(times[0], 0.0)
        self.assertLess(times[-1], 6.0)

    def test_one_frame_without_animation(self) -> None:
        self.assertEqual(gif.frame_times(None, 10), [0.0])

    def test_html_stops_the_animation_at_the_time(self) -> None:
        html = gif.frame_html(SVG, 1.5)
        self.assertIn(SVG, html)
        self.assertIn("s.pauseAnimations();s.setCurrentTime(1.5);", html)


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(root), "gif", *args])
    return code, out.getvalue(), err.getvalue()


class MissingTest(unittest.TestCase):
    """ブラウザかPillowが無ければ、何が要るかを示して、終了コード1で終わる。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # 根を渡さないと、リポジトリの根のgraph.tomlで語彙が差し替わったまま残る
        self.addCleanup(schema.reset)
        (self.tmp / "g.svg").write_text(SVG, encoding="utf-8")

    def test_no_browser(self) -> None:
        with mock.patch.object(gif, "find_browser", return_value=None), mock.patch.object(
            gif, "load_pillow", return_value=object()
        ):
            code, _, err = run(self.tmp, "--svg", str(self.tmp / "g.svg"), "--out", str(self.tmp / "g.gif"))
        self.assertEqual(code, 1)
        self.assertIn("EdgeかChrome", err)
        self.assertNotIn("Pillow", err)
        self.assertFalse((self.tmp / "g.gif").exists())

    def test_no_pillow(self) -> None:
        with mock.patch.object(gif, "find_browser", return_value="msedge"), mock.patch.object(
            gif, "load_pillow", return_value=None
        ):
            code, _, err = run(self.tmp, "--svg", str(self.tmp / "g.svg"), "--out", str(self.tmp / "g.gif"))
        self.assertEqual(code, 1)
        self.assertIn("pip install Pillow", err)
        self.assertNotIn("EdgeかChrome", err)

    def test_missing_svg(self) -> None:
        with mock.patch.object(gif, "find_browser", return_value="msedge"), mock.patch.object(
            gif, "load_pillow", return_value=object()
        ):
            code, _, err = run(self.tmp, "--svg", str(self.tmp / "none.svg"), "--out", str(self.tmp / "g.gif"))
        self.assertEqual(code, 1)
        self.assertIn("make readme", err)

    def test_explicit_browser_that_does_not_exist(self) -> None:
        self.assertIsNone(gif.find_browser(str(self.tmp / "no-such-browser.exe")))


class WaitTest(unittest.TestCase):
    def test_waits_until_the_file_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "f.png"
            png.write_bytes(b"\x89PNG")
            self.assertTrue(gif._wait_for(png, timeout=2))

    def test_gives_up_without_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(gif._wait_for(Path(tmp) / "f.png", timeout=0.3))


if __name__ == "__main__":
    unittest.main()
