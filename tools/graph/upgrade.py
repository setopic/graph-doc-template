"""テンプレートとの差を調べる。

**何も書き込まない。** 取り込みは README の手順（`git merge template/main` ほか）で
人が行う。このモジュールが答えるのは 1 つだけ。

    「自分は遅れているか。遅れているなら、何が変わり、移行作業は要るか」

これが分からないと、派生リポジトリは静かに古くなる。マージし忘れても
何も起きないので、気づく機会が存在しない。
"""

from __future__ import annotations

import re
from pathlib import Path

from .git import run as git_run
from .version import TEMPLATE_VERSION

REMOTE = "template"
BRANCH = "main"
VERSION_PATH = "tools/graph/version.py"
CHANGELOG_PATH = "TEMPLATE_CHANGELOG.md"

VERSION_RE = re.compile(r'TEMPLATE_VERSION\s*=\s*["\']([^"\']+)["\']')
# 変更履歴の見出し: "## 1.2.0 — 2026-08-14"
ENTRY_RE = re.compile(r"^##\s+(\d+\.\d+\.\d+)\b(.*)$")


class UpgradeError(RuntimeError):
    pass


def _ref() -> str:
    return f"{REMOTE}/{BRANCH}"


def parse_version(text: str) -> tuple[int, ...] | None:
    """"1.2.3" を (1, 2, 3) にする。数字以外が混ざったら None。"""
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except ValueError:
        return None


def read_remote_file(root: Path, path: str) -> str | None:
    return git_run(root, ["show", f"{_ref()}:{path}"])


def changelog_entries(text: str, newer_than: tuple[int, ...]) -> list[tuple[str, str]]:
    """`newer_than` より新しい版の項目を、新しい順に返す。"""
    entries: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []

    for line in text.splitlines():
        match = ENTRY_RE.match(line)
        if match:
            if current is not None:
                entries.append((current, "\n".join(body).strip()))
            current = match.group(1)
            body = []
            continue
        if current is not None:
            body.append(line)

    if current is not None:
        entries.append((current, "\n".join(body).strip()))

    return [
        (version, text)
        for version, text in entries
        if (parsed := parse_version(version)) is not None and parsed > newer_than
    ]


def inspect(root: Path) -> dict:
    """テンプレートとの差を調べる。書き込みは行わない。"""
    remotes = git_run(root, ["remote"])
    if remotes is None:
        raise UpgradeError("git リポジトリではないか、git を実行できません")
    if REMOTE not in remotes.split():
        raise UpgradeError(
            f"リモート {REMOTE!r} がありません。最初に一度だけ設定してください:\n"
            f"  git remote add {REMOTE} https://github.com/setopic/graph-doc-template.git"
        )

    if git_run(root, ["fetch", REMOTE]) is None:
        raise UpgradeError(f"git fetch {REMOTE} に失敗しました（ネットワークを確認）")

    local = parse_version(TEMPLATE_VERSION)
    raw_remote = read_remote_file(root, VERSION_PATH)
    remote_text = None
    if raw_remote:
        found = VERSION_RE.search(raw_remote)
        remote_text = found.group(1) if found else None
    remote = parse_version(remote_text) if remote_text else None

    if local is None or remote is None:
        raise UpgradeError("版を読み取れませんでした")

    entries: list[tuple[str, str]] = []
    if remote > local:
        changelog = read_remote_file(root, CHANGELOG_PATH)
        if changelog:
            entries = changelog_entries(changelog, local)

    diff = git_run(root, ["diff", "--name-only", "HEAD", _ref()])
    files = [line for line in (diff or "").splitlines() if line.strip()]

    return {
        "local": TEMPLATE_VERSION,
        "remote": remote_text,
        "behind": remote > local,
        "ahead": local > remote,
        # major が上がっていれば移行作業が要る
        "breaking": remote > local and remote[0] > local[0],
        "entries": entries,
        "files": files,
    }
