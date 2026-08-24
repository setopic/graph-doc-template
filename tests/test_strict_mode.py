"""strict モードのテスト。

**警告とエラーで終了コードの扱いが違う**ことを固定する。
ここが崩れると CI が黙って通るようになる。
"""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.graph import cli

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_check(root: Path, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--root", str(root), "check", "--no-history", *extra])
    return code, out.getvalue()


class StrictMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO_ROOT / "docs", self.tmp / "docs")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_clean_repository_passes_both_ways(self):
        self.assertEqual(run_check(self.tmp)[0], 0)
        self.assertEqual(run_check(self.tmp, "--strict")[0], 0)

    def test_a_warning_only_fails_under_strict(self):
        """G014 を 1 件起こして、通常と strict の差を見る。"""
        target = self.tmp / "docs" / "20-domain" / "dom-01-booking.md"
        body = target.read_text(encoding="utf-8")
        self.assertIn("## 用語", body)
        target.write_text(body.replace("## 用語", "## 語彙"), encoding="utf-8")

        code, output = run_check(self.tmp)
        self.assertEqual(code, 0, "警告だけなら check は通る")
        self.assertIn("G014", output)

        code, _ = run_check(self.tmp, "--strict")
        self.assertEqual(code, 1, "--strict では警告も失敗になる")

    def test_an_error_fails_even_without_strict(self):
        """リンク切れ（G004）は警告ではなくエラー。"""
        target = self.tmp / "docs" / "30-usecases" / "uc-01-confirm-booking.md"
        body = target.read_text(encoding="utf-8")
        self.assertIn("[[DOM-01]]", body)
        target.write_text(body.replace("[[DOM-01]]", "[[DOM-99]]"), encoding="utf-8")

        code, output = run_check(self.tmp)
        self.assertEqual(code, 1, "エラーは strict でなくても失敗する")
        self.assertIn("G004", output)


if __name__ == "__main__":
    unittest.main()
