"""リポジトリの根の`graph.toml`と文書に、共通のテストが左右されないことを確かめる。

種別を差し替えた派生にテンプレートを取り込むと、テストが落ちることがあった。CLIのテストが
`--root`にリポジトリの根を渡すと、`schema.configure`が根の`graph.toml`を読み、差し替えた
種別がプロセスに残る。後ろの、既定の種別を前提にしたテストが落ちる。根の文書に既定の
種別のノードがあることを前提にしたテストも、派生では落ちる。

ここでは、`tools/`と`tests/`を一時ディレクトリに写し、種別を差し替えた`graph.toml`を根に
置き、文書を置かずに、`cli.main`を呼ぶテストを別のプロセスで回す。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 既定の種別を1つも残さない、派生の例
GRAPH_TOML = """[node_types.chapter]
prefix = "CHP"
dir = "10-chapters"
layer = 10
label = "章"
"""

# cli.mainを呼ぶテストの後ろに回す、既定の種別を前提にしたテスト
DEFAULT_TYPE_MODULES = ("test_render_mermaid", "test_render_svg", "test_review")


def modules_calling_cli() -> list[str]:
    own = Path(__file__).stem
    return sorted(
        path.stem
        for path in (ROOT / "tests").glob("test_*.py")
        if path.stem != own and "cli.main(" in path.read_text(encoding="utf-8")
    )


class RootConfigIsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        ignore = shutil.ignore_patterns("__pycache__")
        shutil.copytree(ROOT / "tools", self.tmp / "tools", ignore=ignore)
        shutil.copytree(ROOT / "tests", self.tmp / "tests", ignore=ignore)
        (self.tmp / "graph.toml").write_text(GRAPH_TOML, encoding="utf-8", newline="\n")

    def test_tests_pass_with_replaced_types_at_the_root(self) -> None:
        modules = modules_calling_cli()
        self.assertIn("test_render_types", modules)
        names = [f"tests.{m}" for m in modules + [m for m in DEFAULT_TYPE_MODULES if m not in modules]]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *names],
            cwd=self.tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])


if __name__ == "__main__":
    unittest.main()
