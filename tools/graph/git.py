"""git をサブプロセスで呼ぶための最小のヘルパ。

外部パッケージは増やさない（`subprocess` は標準ライブラリ）。
git が無い・リポジトリでない場合は `None` を返し、呼び出し側で判断させる。
例外を投げないのは、git に依存する機能が**任意**だから。
検証（`check`）は git が無くても動かなければならない。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 30


def run(root: Path, args: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """`git -C <root> <args>` を実行し、標準出力を返す。失敗したら None。"""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout
