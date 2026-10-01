"""upgradeが、merge=oursのファイルを数えるときのテスト（setopic/graph-doc-template#36）。

テンプレートの取り込みは`make update`で行い、そのときだけ`-c merge.ours.driver=true`で
ドライバを効かせる。クローンにドライバを常設すると、取り込み以外のマージでも
merge=oursが効き、相手の変更が何も言わずに落ちる。

だから`upgrade`は、クローンにドライバが常設されているかどうかを見ずに、
merge=oursのファイルを「取り込んでも変わらない」側に数える。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.graph.upgrade import merge_ours


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "gitが無い")
class MergeOursTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        git(self.root, "init", "-q")
        (self.root / ".gitattributes").write_text(
            "README.md merge=ours\nindex.md  merge=ours\n", encoding="utf-8", newline="\n"
        )

    def test_counts_merge_ours_without_driver_config(self) -> None:
        """クローンにドライバが常設されていなくても、merge=oursのファイルを数える。"""
        found = merge_ours(self.root, ["README.md", "docs/index.md", "tools/graph/cli.py"])
        self.assertEqual(found, {"README.md", "docs/index.md"})

    def test_counts_merge_ours_with_old_driver_config(self) -> None:
        """以前のsetupが常設した設定が残っていても、結果は同じ。"""
        git(self.root, "config", "merge.ours.driver", "true")
        found = merge_ours(self.root, ["README.md", "tools/graph/cli.py"])
        self.assertEqual(found, {"README.md"})


if __name__ == "__main__":
    unittest.main()
