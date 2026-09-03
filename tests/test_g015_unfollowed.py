"""G015（依存先が変わったのに追従していない）のテスト。

**このルールだけはグラフの状態ではなく変更の状態を見る。**
そのため一時ディレクトリに本物の git リポジトリを作る。
git が無い環境では丸ごと飛ばす（`check` は git 無しでも動かなければならない）。
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.graph import cli

from .test_strict_mode import build_docs

DOMAIN_PATH = "docs/20-domain/dom-01-booking.md"
USECASE_PATH = "docs/30-usecases/uc-01-confirm-booking.md"


def git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=True,
        timeout=30,
    )


def run_check(root: Path, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--root", str(root), "check", *extra])
    return code, out.getvalue()


@unittest.skipUnless(git_available(), "git が無い")
class UnfollowedChanges(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)

        git(self.tmp, "init", "-q")
        # 実行環境の設定に依存させない（署名も名前も入っていないことがある）
        git(self.tmp, "config", "user.email", "test@example.invalid")
        git(self.tmp, "config", "user.name", "test")
        git(self.tmp, "config", "commit.gpgsign", "false")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "初期")

    def edit(self, rel: str, old: str, new: str) -> None:
        path = self.tmp / rel
        body = path.read_text(encoding="utf-8")
        self.assertIn(old, body)
        path.write_text(body.replace(old, new), encoding="utf-8")

    def test_clean_tree_says_nothing(self):
        code, output = run_check(self.tmp)
        self.assertEqual(code, 0)
        self.assertNotIn("G015", output)

    def test_changing_a_dependency_flags_the_dependent(self):
        self.edit(DOMAIN_PATH, "席を押さえた記録。", "席と時間帯を押さえた記録。")

        code, output = run_check(self.tmp)
        self.assertEqual(code, 0, "G015 は警告なので通常の check は通る")
        self.assertIn("G015", output)
        self.assertIn("uc-01-confirm-booking.md", output)
        self.assertIn("DOM-01", output)

    def test_following_up_clears_it(self):
        """依存元も一緒に変えたなら何も言わない。"""
        self.edit(DOMAIN_PATH, "席を押さえた記録。", "席と時間帯を押さえた記録。")
        self.edit(USECASE_PATH, "仮予約を確定にする。", "仮予約を確定にする（時間帯つき）。")

        _, output = run_check(self.tmp)
        self.assertNotIn("G015", output)

    def test_auto_block_only_change_is_not_a_change(self):
        """sync が書き換えたブロックだけでは、依存元に追従の余地が無い。"""
        path = self.tmp / DOMAIN_PATH
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n<!-- graph:auto:start -->\n書き換え\n<!-- graph:auto:end -->\n",
            encoding="utf-8",
        )
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "自動ブロックを足す")

        path.write_text(
            path.read_text(encoding="utf-8").replace("書き換え", "別の中身"),
            encoding="utf-8",
        )

        _, output = run_check(self.tmp)
        self.assertNotIn("G015", output)

    def test_strict_turns_it_into_a_failure(self):
        self.edit(DOMAIN_PATH, "席を押さえた記録。", "席と時間帯を押さえた記録。")
        self.assertEqual(run_check(self.tmp, "--strict")[0], 1)

    def test_no_history_skips_it(self):
        self.edit(DOMAIN_PATH, "席を押さえた記録。", "席と時間帯を押さえた記録。")
        _, output = run_check(self.tmp, "--no-history")
        self.assertNotIn("G015", output)

    def test_since_looks_at_committed_changes(self):
        """コミット済みの変更は、窓を指定したときだけ見える。"""
        self.edit(DOMAIN_PATH, "席を押さえた記録。", "席と時間帯を押さえた記録。")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "DOM-01 を直す")

        _, without = run_check(self.tmp)
        self.assertNotIn("G015", without, "窓が無ければコミット済みの変更は見ない")

        _, within = run_check(self.tmp, "--since", "HEAD~1")
        self.assertIn("G015", within)


class WithoutGit(unittest.TestCase):
    """git リポジトリでなくても check は動く。"""

    def test_check_still_runs(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        build_docs(tmp)

        code, output = run_check(tmp)
        self.assertEqual(code, 0)
        self.assertNotIn("G015", output)


if __name__ == "__main__":
    unittest.main()
