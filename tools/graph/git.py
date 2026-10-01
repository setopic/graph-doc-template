"""gitをサブプロセスで呼ぶための、最小限のヘルパ。

外部パッケージは増やさない（`subprocess`は標準ライブラリにある）。
gitが無いかリポジトリでない場合は`None`を返し、どうするかは呼び出し側に判断させる。
例外を投げないのは、gitに依存する機能が任意だからである。
検証（`check`）は、gitが無くても動かなければならない。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 30


def run(root: Path, args: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """`git -C <root> <args>`を実行し、標準出力を返す。失敗したらNoneを返す。"""
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
