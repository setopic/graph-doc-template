"""make updateのマージコミットのメッセージのテスト（setopic/graph-doc-template#116）。

`make update`がメッセージを渡さないと、gitの既定の英語の文
（Merge remote-tracking branch 'template/main'）が付く。コミットメッセージも
日本語の書き方の対象なので、「テンプレートの<版>を取り込む」を渡す。
版は、取り込む側のテンプレートの`tools/graph/version.py`から読む。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def run(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8", env=ENV
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@unittest.skipUnless(shutil.which("git") and shutil.which("make"), "gitかmakeが無い")
class MakeUpdateMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.upstream = base / "upstream"
        self.derived = base / "derived"

        run(base, "git", "init", "-q", "-b", "main", str(self.upstream))
        shutil.copy(ROOT / "Makefile", self.upstream / "Makefile")
        write(self.upstream / "tools/graph/version.py", 'TEMPLATE_VERSION = "1.0.0"\n')
        write(self.upstream / "x.txt", "base\n")
        run(self.upstream, "git", "add", ".")
        run(self.upstream, "git", "commit", "-q", "-m", "init")

        run(base, "git", "clone", "-q", "-o", "template", str(self.upstream), str(self.derived))

    def make_update(self) -> subprocess.CompletedProcess[str]:
        python = Path(sys.executable).as_posix()
        return run(self.derived, "make", "-s", "update", f"PYTHON={python}", check=False)

    def bump_upstream(self, version: str, x: str) -> None:
        # 版の行の後ろに日本語を置き、version.pyをUTF-8で読めているかも確かめる。
        write(self.upstream / "tools/graph/version.py", f'TEMPLATE_VERSION = "{version}"\n# 版\n')
        write(self.upstream / "x.txt", x)
        run(self.upstream, "git", "commit", "-q", "-am", "up")

    def test_merge_commit_message_names_the_version(self) -> None:
        """取り込んだテンプレートの版を、日本語のメッセージに入れる。"""
        write(self.derived / "local.txt", "local\n")
        run(self.derived, "git", "add", ".")
        run(self.derived, "git", "commit", "-q", "-m", "local")
        self.bump_upstream("1.2.3", "base\n")

        result = self.make_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        subject = run(self.derived, "git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(subject, "テンプレートの1.2.3を取り込む")

    def test_conflict_keeps_the_message(self) -> None:
        """競合したときも、続きのgit commitが同じメッセージを使う。"""
        write(self.derived / "x.txt", "local\n")
        run(self.derived, "git", "commit", "-q", "-am", "local")
        self.bump_upstream("1.2.4", "template\n")

        result = self.make_update()
        self.assertNotEqual(result.returncode, 0)
        write(self.derived / "x.txt", "resolved\n")
        run(self.derived, "git", "add", "x.txt")
        run(self.derived, "git", "commit", "-q", "--no-edit")
        subject = run(self.derived, "git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(subject, "テンプレートの1.2.4を取り込む")


if __name__ == "__main__":
    unittest.main()
