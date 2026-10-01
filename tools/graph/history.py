"""gitの履歴から、各ファイルの最終更新日を得る。

いつからdraftのままかを知る手段が要るが、フロントマターに日付を
手で書かせると、必ず実態とずれる。履歴はgitが正確に持っているので、そちらを使う。

gitが無い、リポジトリでない、履歴が浅いのいずれかの場合は、何も返さない。
日付が取れないときは、誤検知するより、検査を飛ばすほうを選ぶ。
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .git import run as _run

# 出力側の区切り。引数にはASCIIの"%x00"を渡し、gitにNULへ展開させる。
# NUL文字そのものを引数に含めると、Windowsでプロセスを起動できない。
SEPARATOR = "\x00"
COMMIT_FORMAT = "--format=%x00%cI"


def is_usable(root: Path) -> bool:
    """履歴が信頼できるか。浅いクローンでは、全ファイルが同じ日付になる。"""
    inside = _run(root, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return False
    shallow = _run(root, ["rev-parse", "--is-shallow-repository"])
    if shallow is None or shallow.strip() != "false":
        return False
    return True


def last_commit_dates(root: Path) -> dict[str, date]:
    """`{リポジトリからの相対パス: 最終コミット日}`を返す。取れなければ空を返す。"""
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
        # git logは新しい順なので、最初に現れたものが最終更新
        dates.setdefault(path, current)

    return dates
