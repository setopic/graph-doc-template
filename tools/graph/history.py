"""git の履歴から、各ファイルの最終更新日を得る。

「いつから draft のままか」を知る手段が要るが、フロントマターに日付を
手で書かせると必ず腐る。履歴は git が正確に持っているのでそちらを使う。

git が無い・リポジトリでない・履歴が浅い場合は**何も返さない**。
日付が取れないときは誤検知するより検査を飛ばす。
"""

from __future__ import annotations

import subprocess
from datetime import date, datetime
from pathlib import Path

# 出力側の区切り。引数には ASCII の "%x00" を渡し、git に NUL へ展開させる。
# NUL 文字そのものを引数に含めると Windows でプロセスを起動できない。
SEPARATOR = "\x00"
COMMIT_FORMAT = "--format=%x00%cI"
TIMEOUT_SECONDS = 30


def _run(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def is_usable(root: Path) -> bool:
    """履歴が信頼できるか。浅いクローンでは全ファイルが同じ日付になる。"""
    inside = _run(root, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return False
    shallow = _run(root, ["rev-parse", "--is-shallow-repository"])
    if shallow is None or shallow.strip() != "false":
        return False
    return True


def last_commit_dates(root: Path) -> dict[str, date]:
    """`{リポジトリ相対パス: 最終コミット日}` を返す。取れなければ空。"""
    if not is_usable(root):
        return {}

    output = _run(
        root,
        ["log", "--no-merges", "--name-only", COMMIT_FORMAT],
    )
    if not output:
        return {}

    dates: dict[str, date] = {}
    current: date | None = None

    for line in output.splitlines():
        if line.startswith(SEPARATOR):
            stamp = line[len(SEPARATOR) :].strip()
            try:
                current = datetime.fromisoformat(stamp).date()
            except ValueError:
                current = None
            continue

        path = line.strip()
        if not path or current is None:
            continue
        # git log は新しい順なので、最初に現れたものが最終更新
        dates.setdefault(path, current)

    return dates
