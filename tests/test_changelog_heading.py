"""変更履歴の見出しの形を変えても、upgradeがバージョンを読めることのテスト（setopic/graph-doc-template#135）。

1.43.3で、見出しをバージョンと日付をダッシュでつなぐ形から`## 1.2.3（2026-10-21）`の形に改めた。
上の層や派生の変更履歴は古い形のまま取り込まれることがあるので、upgradeは新旧どちらの形も読む。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph import upgrade
from tools.graph.version import TEMPLATE_VERSION

ROOT = Path(__file__).resolve().parent.parent

OLD = "\N{EM DASH}"


def old_heading(version: str) -> str:
    return f"## {version} {OLD} 2026-10-21"


def new_heading(version: str) -> str:
    return f"## {version}（2026-10-21）"


def changelog(*headings: str) -> str:
    return "# 変更履歴\n\n" + "".join(f"{h}\n\n変更\n\n---\n\n" for h in headings)


class ChangelogEntriesTest(unittest.TestCase):
    def test_new_heading_is_read(self) -> None:
        text = changelog(new_heading("1.1.0"), new_heading("1.0.1"), new_heading("1.0.0"))
        entries = upgrade.changelog_entries(text, (1, 0, 0))
        self.assertEqual(entries, [("1.1.0", "変更"), ("1.0.1", "変更")])

    def test_old_heading_is_still_read(self) -> None:
        # 上の層や派生が、古い形のままの変更履歴を持っていても読める
        text = changelog(old_heading("0.2.0"), old_heading("0.1.0"))
        entries = upgrade.changelog_entries(text, (0, 1, 0))
        self.assertEqual(entries, [("0.2.0", "変更")])

    def test_mixed_headings_keep_version_order(self) -> None:
        # 新しいバージョンだけを新しい形にし、古いバージョンは古い形のまま残した変更履歴
        text = changelog(new_heading("1.10.0"), new_heading("1.9.1"), old_heading("1.9.0"), old_heading("1.2.0"))
        versions = [version for version, _ in upgrade.changelog_entries(text, (1, 2, 0))]
        self.assertEqual(versions, ["1.10.0", "1.9.1", "1.9.0"])

    def test_rewriting_headings_does_not_change_comparison(self) -> None:
        versions = ["1.43.3", "1.43.2", "1.10.0", "1.9.9", "1.0.0"]
        before = upgrade.changelog_entries(changelog(*map(old_heading, versions)), (1, 9, 9))
        after = upgrade.changelog_entries(changelog(*map(new_heading, versions)), (1, 9, 9))
        self.assertEqual([v for v, _ in before], [v for v, _ in after])
        self.assertEqual([v for v, _ in after], ["1.43.3", "1.43.2", "1.10.0"])


class TemplateChangelogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / upgrade.CHANGELOG_PATH).read_text(encoding="utf-8")
        self.headings = [line for line in self.text.splitlines() if upgrade.ENTRY_RE.match(line)]

    def test_headings_have_no_dash(self) -> None:
        self.assertEqual([h for h in self.headings if OLD in h], [])

    def test_top_entry_is_current_version(self) -> None:
        entries = upgrade.changelog_entries(self.text, (0, 0, 0))
        self.assertEqual(entries[0][0], TEMPLATE_VERSION)

    def test_versions_are_strictly_descending(self) -> None:
        # 見出しを書き換えた後も、新しい順に並び、バージョンの比較が崩れていない
        versions = [upgrade.parse_version(v) for v, _ in upgrade.changelog_entries(self.text, (0, 0, 0))]
        self.assertNotIn(None, versions)
        self.assertEqual(versions, sorted(versions, reverse=True))
        self.assertEqual(len(versions), len(set(versions)))
        self.assertEqual(len(versions), len(self.headings))


if __name__ == "__main__":
    unittest.main()
