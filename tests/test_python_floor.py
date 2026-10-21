"""宣言したPythonの下限が、実際に回している版と合っているかを見る。

READMEには前から`Python 3.10+`と書いてあったが、**CIは3.12しか
回していなかった。** 宣言は書いた瞬間から腐りはじめる。ここで3つを
突き合わせて、ずれたら落とす。

  1. `version.py`の`MIN_PYTHON`
  2. `graph-check.yml`の`python-version`
  3. READMEの「外部依存なし（Python X.Y+ …）」

**下限は「試している中で最も古い版」であって、願望ではない。**
開発機・CI・本番ホストがすべて3.12に揃っているので、3.12が下限になる。
これより古い版で動くかどうかは、誰も試していないので分からない。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tools.graph.version import MIN_PYTHON

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "graph-check.yml"
README = ROOT / "README.md"


class PythonFloorTest(unittest.TestCase):
    def test_floor_is_a_version_pair(self) -> None:
        self.assertRegex(MIN_PYTHON, r"^\d+\.\d+$")

    def test_workflow_pins_the_declared_floor(self) -> None:
        """CIが`MIN_PYTHON`以上しか回していないか。

        **最も低い版が下限のはず**なので、最小を取って突き合わせる。
        版を増やしたときも、いちばん下が宣言と一致していれば正しい。
        """
        if not WORKFLOW.exists():
            self.skipTest("graph-check.ymlが無い（派生側で差し替えている）")
        found = re.findall(
            r'python-version:\s*"(\d+\.\d+)"', WORKFLOW.read_text(encoding="utf-8")
        )
        self.assertTrue(found, "python-versionの指定が読み取れない")
        lowest = min(found, key=lambda v: tuple(int(part) for part in v.split(".")))
        self.assertEqual(
            lowest,
            MIN_PYTHON,
            f"CIが回す最も低い版{lowest}とMIN_PYTHON {MIN_PYTHON}がずれている",
        )

    def test_readme_states_the_declared_floor(self) -> None:
        """READMEの記載も同じ版か。人が最初に読む場所なので合わせる。"""
        if not README.exists():
            self.skipTest("README.mdが無い")
        match = re.search(r"Python (\d+\.\d+)\+", README.read_text(encoding="utf-8"))
        if match is None:
            self.skipTest("READMEにPythonの下限の記載が無い（派生側で書き換えている）")
        self.assertEqual(
            match.group(1),
            MIN_PYTHON,
            f"READMEの{match.group(1)}+とMIN_PYTHON {MIN_PYTHON}がずれている",
        )


if __name__ == "__main__":
    unittest.main()
