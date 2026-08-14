"""テンプレートから新しいノードを起こす。

作った直後に孤立ノード（G005）にならないよう、対応する index.md の
一覧ブロックにもリンクを追加する。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from . import schema
from .frontmatter import set_scalar

TEMPLATE_DIR = "00-meta/templates"
CHILDREN_START = "<!-- graph:children:start -->"
CHILDREN_END = "<!-- graph:children:end -->"

# 一括生成ファイルの区切り。タブは編集中に空白へ化けることがあるため使わない
BATCH_SEPARATOR = "|"
BATCH_COLUMNS = ("type", "id", "title", "slug", "status", "template")


ID_LINE_RE = re.compile(r"^id:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)


class ScaffoldError(RuntimeError):
    pass


def existing_ids(root: Path) -> set[str]:
    """既存ノードの id を集める。

    loader を使わないのは、他のファイルが壊れていても id の衝突だけは
    検出したいため。フロントマターの `id:` 行だけを軽く読む。
    """
    docs = root / schema.DOCS_DIR
    found: set[str] = set()
    if not docs.is_dir():
        return found

    for path in docs.rglob("*.md"):
        rel = path.relative_to(docs).as_posix()
        if any(rel.startswith(p) for p in schema.EXCLUDE_PREFIXES):
            continue
        head = path.read_text(encoding="utf-8")[:600]
        match = ID_LINE_RE.search(head)
        if match:
            found.add(match.group(1))

    return found


def create(
    root: Path,
    *,
    node_type: str,
    node_id: str,
    title: str,
    slug: str | None = None,
    status: str = "draft",
    template: str | None = None,
    known_ids: set[str] | None = None,
) -> Path:
    """1 ノードを作る。`template` を省略すると `<type>.md` の雛形を使う。

    `known_ids` は一括生成で既存 id の走査を 1 回に抑えるための引数。
    渡した集合には、作成した id が追加される。
    """
    spec = schema.NODE_TYPES.get(node_type)
    if spec is None:
        raise ScaffoldError(f"未知の type {node_type!r}（許可: {', '.join(schema.NODE_TYPES)}）")
    if status not in schema.STATUSES:
        raise ScaffoldError(f"未知の status {status!r}（許可: {', '.join(schema.STATUSES)}）")

    prefix = spec["prefix"]
    node_id = node_id.strip()
    if not node_id.startswith(prefix + "-"):
        raise ScaffoldError(f"type={node_type} の id は {prefix}- で始めてください（例: {prefix}-01）")

    target_dir_name = spec["dir"]
    if target_dir_name is None:
        raise ScaffoldError(f"type={node_type} は自動生成の対象外です")

    taken = existing_ids(root) if known_ids is None else known_ids
    if node_id in taken:
        raise ScaffoldError(f"id {node_id!r} はすでに使われています")

    docs = root / schema.DOCS_DIR
    template_name = template or node_type
    template_path = docs / TEMPLATE_DIR / f"{template_name}.md"
    if not template_path.is_file():
        available = ", ".join(sorted(p.stem for p in (docs / TEMPLATE_DIR).glob("*.md")))
        raise ScaffoldError(
            f"雛形がありません: {template_name}.md（利用できるもの: {available}）"
        )

    filename = f"{node_id.lower()}"
    resolved_slug = _slugify(slug or title)
    if resolved_slug:
        filename += f"-{resolved_slug}"
    target = docs / target_dir_name / f"{filename}.md"

    if target.exists():
        raise ScaffoldError(f"すでに存在します: {target}")

    content = template_path.read_text(encoding="utf-8")
    content = (
        content.replace("{{ID}}", node_id)
        .replace("{{TITLE}}", title)
        .replace("{{TYPE}}", node_type)
        .replace("{{STATUS}}", status)
        .replace("{{DATE}}", _dt.date.today().isoformat())
    )
    # 雛形に書かれた type を信用しない。--type で指定されたものを正とする。
    # 雛形はグラフの検査対象外なので、そこに古い type が残っていても気づけない
    # （層を改称したとき、実際に雛形の type だけ取り残された）。
    content = set_scalar(content, "type", node_type)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    taken.add(node_id)

    register_in_index(docs / target_dir_name / "index.md", node_id, title, target.name)
    return target


# --------------------------------------------------------------------------
# 一括生成
# --------------------------------------------------------------------------
def parse_batch(path: Path) -> list[dict]:
    """一括生成ファイルを読む。

    1 行 1 ノード。`|` 区切りで、前から
    `type | id | title | slug | status | template` の順。
    slug 以降は省略できる。`#` で始まる行と空行は読み飛ばす。

        # type    | id    | title              | slug
        usecase   | UC-02 | 予約をキャンセルする  | cancel-booking
    """
    if not path.is_file():
        raise ScaffoldError(f"一括生成ファイルがありません: {path}")

    entries: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        cells = [c.strip() for c in line.split(BATCH_SEPARATOR)]
        if len(cells) < 3:
            raise ScaffoldError(
                f"{path.name} {lineno} 行目: 列が足りません"
                f"（`type {BATCH_SEPARATOR} id {BATCH_SEPARATOR} title` は必須）-> {line!r}"
            )
        if len(cells) > len(BATCH_COLUMNS):
            raise ScaffoldError(
                f"{path.name} {lineno} 行目: 列が多すぎます"
                f"（{BATCH_SEPARATOR} で区切れるのは {len(BATCH_COLUMNS)} 列まで）-> {line!r}"
            )

        entry = dict(zip(BATCH_COLUMNS, cells))
        entries.append({k: v for k, v in entry.items() if v})

    if not entries:
        raise ScaffoldError(f"{path.name}: 生成対象がありません")
    return entries


def create_many(root: Path, entries: list[dict]) -> tuple[list[Path], list[str]]:
    """まとめて作る。`(作れたもの, エラーメッセージ)` を返す。

    1 件失敗しても残りは続行する。途中で止めると、
    どこまで作られたのか分からない状態になるため。
    """
    created: list[Path] = []
    errors: list[str] = []
    known_ids = existing_ids(root)

    for entry in entries:
        try:
            created.append(
                create(
                    root,
                    node_type=entry["type"],
                    node_id=entry["id"],
                    title=entry["title"],
                    slug=entry.get("slug"),
                    status=entry.get("status", "draft"),
                    template=entry.get("template"),
                    known_ids=known_ids,
                )
            )
        except ScaffoldError as exc:
            errors.append(f"{entry.get('id', '?')}: {exc}")

    return created, errors


# --------------------------------------------------------------------------
# index.md の一覧ブロック
# --------------------------------------------------------------------------
def register_in_index(index_path: Path, node_id: str, title: str, filename: str) -> None:
    if not index_path.is_file():
        return

    text = index_path.read_text(encoding="utf-8")
    if CHILDREN_START not in text or CHILDREN_END not in text:
        return

    entry = f"- [{node_id} {title}](./{filename})"
    if entry in text:
        return

    head, _, rest = text.partition(CHILDREN_END)
    updated = head.rstrip("\n") + "\n" + entry + "\n" + CHILDREN_END + rest
    index_path.write_text(updated, encoding="utf-8", newline="\n")


def unregister_from_index(index_path: Path, filenames: set[str]) -> bool:
    """一覧ブロックから、指定ファイルへのリンク行を取り除く。更新したら True。"""
    if not index_path.is_file():
        return False

    text = index_path.read_text(encoding="utf-8")
    if CHILDREN_START not in text or CHILDREN_END not in text:
        return False

    head, _, tail = text.partition(CHILDREN_START)
    block, _, rest = tail.partition(CHILDREN_END)

    kept = [
        line
        for line in block.splitlines()
        if not any(f"({name}" in line or f"(./{name}" in line for name in filenames)
    ]
    new_block = "\n".join(kept).strip("\n")
    rebuilt = (
        head
        + CHILDREN_START
        + ("\n" + new_block + "\n" if new_block else "\n")
        + CHILDREN_END
        + rest
    )

    if rebuilt == text:
        return False
    index_path.write_text(rebuilt, encoding="utf-8", newline="\n")
    return True


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)
