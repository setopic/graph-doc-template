"""render --outの書き出し先のテスト。

終わりの表示は、書き出し先を根からの相対で見せる。根の外のパスを渡すと、
相対にできずに例外が出ていた。外のパスでも、書いたうえで、そのパスを見せる。
"""

from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import cli, schema

from tests.helpers import sample_root


def run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--root", str(root), "render", *args])
    return code, out.getvalue(), err.getvalue()


class OutOutsideRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = sample_root(self)
        self.outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.outside, True)

    def test_out_outside_root(self) -> None:
        for fmt, name in (("json", "g.json"), ("mermaid", "g.mmd"), ("svg", "g.svg")):
            with self.subTest(fmt=fmt):
                path = self.outside / name
                code, out, err = run(self.root, "--format", fmt, "--out", str(path))
                self.assertEqual(code, 0, err)
                self.assertTrue(path.is_file())
                self.assertIn(f"書き出した: {path.as_posix()}", out)

    def test_out_inside_root_is_relative(self) -> None:
        code, out, err = run(self.root, "--format", "json", "--out", "docs/graph.json")
        self.assertEqual(code, 0, err)
        self.assertIn("書き出した: docs/graph.json", out)

    def test_svg_into_with_out_outside_root(self) -> None:
        (self.root / "README.md").write_text(
            f"# 題\n\n{schema.DIAGRAM_BLOCK_START}\n{schema.DIAGRAM_BLOCK_END}\n",
            encoding="utf-8",
            newline="\n",
        )
        path = self.outside / "g.svg"
        code, out, err = run(self.root, "--format", "svg", "--into", "README.md", "--out", str(path))
        self.assertEqual(code, 0, err)
        self.assertTrue(path.is_file())
        self.assertIn(f"図を更新した: README.md・{path.as_posix()}", out)


if __name__ == "__main__":
    unittest.main()
