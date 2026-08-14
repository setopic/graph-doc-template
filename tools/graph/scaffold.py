"""テンプレートから新しいノードを起こす。

作った直後に孤立ノード（G005）にならないよう、対応する index.md の
一覧ブロックにもリンクを追加する。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from . import schema

TEMPLATE_DIR = "00-meta/templates"
CHILDREN_START = "<!-- graph:children:start -->"
CHILDREN_END = "<!-- graph:children:end -->"


class ScaffoldError(RuntimeError):
    pass


def create(
    root: Path,
    *,
    node_type: str,
    node_id: str,
    title: str,
    slug: str | None = None,
    status: str = "draft",
) -> Path:
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

    docs = root / schema.DOCS_DIR
    template_path = docs / TEMPLATE_DIR / f"{node_type}.md"
    if not template_path.is_file():
        raise ScaffoldError(f"テンプレートがありません: {template_path}")

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

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")

    _register_in_index(docs / target_dir_name / "index.md", node_id, title, target)
    return target


def _register_in_index(index_path: Path, node_id: str, title: str, target: Path) -> None:
    if not index_path.is_file():
        return

    text = index_path.read_text(encoding="utf-8")
    if CHILDREN_START not in text or CHILDREN_END not in text:
        return

    entry = f"- [{node_id} {title}](./{target.name})"
    if entry in text:
        return

    head, _, rest = text.partition(CHILDREN_END)
    updated = head.rstrip("\n") + "\n" + entry + "\n" + CHILDREN_END + rest
    index_path.write_text(updated, encoding="utf-8", newline="\n")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)
