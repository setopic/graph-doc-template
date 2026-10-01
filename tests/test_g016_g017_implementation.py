"""G016 / G017（implemented_by）のテスト。

**宣言が無ければ何も起きない**ことを最初に固定する。文書だけのリポジトリに
この機能を配っても影響が出ないことが、テンプレートを配る前提になっている。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph.loader import load

from .test_g015_unfollowed import git, git_available, run_check
from .test_strict_mode import build_docs

DOMAIN_PATH = "docs/20-domain/dom-01-booking.md"
USECASE_PATH = "docs/30-usecases/uc-01-confirm-booking.md"
SOURCE_PATH = "src/booking.py"


def declare(root: Path, rel: str, *targets: str) -> None:
    """フロントマターの末尾に implemented_by を足す。"""
    path = root / rel
    body = path.read_text(encoding="utf-8")
    block = "implemented_by:\n" + "".join(f"  - {t}\n" for t in targets)
    head, sep, rest = body.partition("---\n")
    front, sep2, tail = rest.partition("---\n")
    path.write_text(head + sep + front + block + sep2 + tail, encoding="utf-8")


class WithoutDeclaration(unittest.TestCase):
    """文書だけのリポジトリでは 1 件も出ない。"""

    def test_nothing_fires(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        build_docs(tmp)

        code, output = run_check(tmp)
        self.assertEqual(code, 0)
        self.assertNotIn("G016", output)
        self.assertNotIn("G017", output)


class TargetExists(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)
        (self.tmp / "src").mkdir()
        (self.tmp / SOURCE_PATH).write_text("# 予約\n", encoding="utf-8")

    def test_existing_target_passes(self):
        declare(self.tmp, DOMAIN_PATH, SOURCE_PATH)
        code, output = run_check(self.tmp, "--no-history")
        self.assertEqual(code, 0)
        self.assertNotIn("G016", output)

    def test_missing_target_is_an_error(self):
        declare(self.tmp, DOMAIN_PATH, "src/nowhere.py")
        code, output = run_check(self.tmp, "--no-history")
        self.assertEqual(code, 1, "指し先が無いのはエラー（警告ではない）")
        self.assertIn("G016", output)
        self.assertIn("nowhere.py", output)

    def test_a_directory_is_a_valid_target(self):
        declare(self.tmp, DOMAIN_PATH, "src")
        code, output = run_check(self.tmp, "--no-history")
        self.assertEqual(code, 0)
        self.assertNotIn("G016", output)

    def test_graph_without_root_says_nothing(self):
        """ルートが分からなければ確かめられないので落とさない。"""
        declare(self.tmp, DOMAIN_PATH, "src/nowhere.py")
        graph = load(self.tmp)
        graph.root = None
        from tools.graph import rules

        self.assertEqual(rules.rule_g016_implementation_exists(graph), [])


@unittest.skipUnless(git_available(), "git が無い")
class Drift(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)
        (self.tmp / "src").mkdir()
        (self.tmp / SOURCE_PATH).write_text("# 予約\n", encoding="utf-8")
        declare(self.tmp, DOMAIN_PATH, SOURCE_PATH)

        git(self.tmp, "init", "-q")
        git(self.tmp, "config", "user.email", "test@example.invalid")
        git(self.tmp, "config", "user.name", "test")
        git(self.tmp, "config", "commit.gpgsign", "false")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "初期")

    def touch(self, rel: str, text: str) -> None:
        path = self.tmp / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def test_clean_tree_says_nothing(self):
        _, output = run_check(self.tmp)
        self.assertNotIn("G017", output)

    def test_implementation_moved_alone(self):
        self.touch(SOURCE_PATH, "def confirm():\n    pass\n")
        code, output = run_check(self.tmp)
        self.assertEqual(code, 0, "G017 は警告")
        self.assertIn("G017", output)
        self.assertIn("実装が変わった", output)
        self.assertIn("dom-01-booking.md", output)

    def test_document_moved_alone(self):
        self.touch(DOMAIN_PATH, "\n席は 1 つずつ押さえる。\n")
        _, output = run_check(self.tmp)
        self.assertIn("G017", output)
        self.assertIn("実装は動いていない", output)

    def test_both_moved_is_silent(self):
        self.touch(SOURCE_PATH, "def confirm():\n    pass\n")
        self.touch(DOMAIN_PATH, "\n席は 1 つずつ押さえる。\n")
        _, output = run_check(self.tmp)
        self.assertNotIn("G017", output)

    def test_a_file_under_a_declared_directory_counts(self):
        declare(self.tmp, USECASE_PATH, "src")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "ディレクトリを指す")

        (self.tmp / "src" / "views.py").write_text("# 画面\n", encoding="utf-8")
        _, output = run_check(self.tmp)
        self.assertIn("uc-01-confirm-booking.md", output)


if __name__ == "__main__":
    unittest.main()
