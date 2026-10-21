"""PRのブランチ名・題・コミットの1行目が、META-07の決まりに合うかを確かめる。

決まりは、`<種類>(<ノードのid>): <日本語の1文>（#issue）`の1行目と、
`<種類>/<issueの番号>-<内容>`のブランチ名である。種類は`schema.COMMIT_TYPES`で、
派生は`graph.toml`の`[commit]`の表で足せる。

**次の2つは確かめない。** どちらも、書き手が選べないからである。

- `claude/`で始まるブランチ名。Claudeのクラウドのセッションが自動で付ける
- `chore/template-`のPRに入るコミット。決まりより前に書かれた上流のコミットが入る

テンプレートの層のうち版を求める層では、PRの題に版を求める。下の層（graph-doc-template）は
いつも求め、上の層は`tools/graph/layers/<層の名前>.toml`の`versioned_title`で選ぶ。
層の宣言は派生にも写るので、宣言の`repository`がPRのリポジトリと同じときだけ求める。
取り込みのPRの題には、版を求めない。

日本語の1文かどうかと、括弧のidが実在するかは見ない。idの実在は`check_refs.py`が、
PRの題と本文で確かめている。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.graph import schema  # noqa: E402
from tools.graph.upgrade import local_layers  # noqa: E402

SUBJECT = re.compile(r"^(?P<type>[a-z][a-z0-9-]*)(?:\([A-Z]{2,5}-\d{2,4}\))?: \S")
VERSIONED = re.compile(r"^[a-z][a-z0-9-]*(?:\([A-Z]{2,5}-\d{2,4}\))?: \d+\.\d+\.\d+ \S")
# `https://github.com/<owner>/<name>.git`や`git@github.com:<owner>/<name>.git`の`<owner>/<name>`
REPOSITORY_SLUG = re.compile(r"([^/:]+/[^/:]+?)(?:\.git)?/?$")
BRANCH = re.compile(r"^(?P<type>[a-z][a-z0-9-]*)/(?:\d+-)?[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
# 取り込みの版は、遅れている層の版を並べたもの（`1.38.0`、`<label>-0.14.0`、
# `1.38.0-<label>-0.14.0`）。上の層の版の前には層の宣言の`label`が付く（setopic/graph-doc-template#125）
TEMPLATE_BRANCH = re.compile(
    r"^chore/template-(?:[a-z][a-z0-9]*-)?\d+\.\d+\.\d+(?:-[a-z][a-z0-9]*-\d+\.\d+\.\d+)*$"
)
EXEMPT_BRANCH_PREFIX = "claude/"


def check_subject(subject: str, types: tuple[str, ...]) -> str | None:
    """コミットの1行目かPRの題を確かめ、合わなければその理由を返す。"""
    match = SUBJECT.match(subject)
    if not match:
        return "`<種類>(<ノードのid>): <日本語の1文>（#issue）`の形になっていない"
    if match.group("type") not in types:
        return f"種類`{match.group('type')}`は一覧に無い"
    return None


def check_title(title: str, types: tuple[str, ...], versioned: bool = False) -> str | None:
    """PRの題を確かめる。`versioned`なら、1文の前に版を求める。"""
    problem = check_subject(title, types)
    if problem is None and versioned and not VERSIONED.match(title):
        return "版を求める層の題は`<種類>(<ノードのid>): <版> <日本語の1文>（#issue）`にする"
    return problem


def check_branch(branch: str, types: tuple[str, ...]) -> str | None:
    if branch.startswith(EXEMPT_BRANCH_PREFIX) or TEMPLATE_BRANCH.match(branch):
        return None
    match = BRANCH.match(branch)
    if not match:
        return "`<種類>/<issueの番号>-<英小文字とハイフンの内容>`の形になっていない"
    if match.group("type") not in types:
        return f"種類`{match.group('type')}`は一覧に無い"
    return None


def versioned_repositories(root: Path) -> set[str]:
    """PRの題に版を求める層の`<owner>/<name>`。"""
    found = set()
    for layer in local_layers(root):
        match = REPOSITORY_SLUG.search(layer.repository)
        if layer.versioned_title and match:
            found.add(match.group(1))
    return found


def skips_commits(branch: str) -> bool:
    """テンプレートの取り込みのPRか。上流の古いコミットが入るので、コミットを確かめない。"""
    return bool(TEMPLATE_BRANCH.match(branch))


def commit_subjects(base: str, head: str) -> list[str]:
    """PRに含まれる、マージ以外のコミットの1行目。"""
    out = subprocess.run(
        ["git", "log", "--no-merges", "--format=%s", f"{base}..{head}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def run(
    branch: str,
    title: str,
    subjects: list[str],
    types: tuple[str, ...],
    versioned: bool = False,
) -> int:
    """終了コードを返す。`subjects`は、確かめるコミットの1行目である。

    `versioned`は、PRの題に版を求める層のリポジトリか。取り込みのPRでは求めない。
    """
    versioned = versioned and not TEMPLATE_BRANCH.match(branch)
    problems: list[str] = []
    if problem := check_branch(branch, types):
        problems.append(f"ブランチ名 {branch}: {problem}")
    if problem := check_title(title, types, versioned):
        problems.append(f"PRの題 {title}: {problem}")
    for subject in subjects:
        if problem := check_subject(subject, types):
            problems.append(f"コミット {subject}: {problem}")

    print("種類:", " ".join(types))
    if not problems:
        print("ブランチ名・PRの題・コミットの1行目は、決まりに合っている")
        return 0
    for line in problems:
        print(line)
    print("決まりは、META-07（docs/00-meta/issue-pr-flow.md）の「ブランチ名とコミットの1行目」にある。")
    return 1


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    schema.configure(root)  # graph.tomlの[commit]で足した種類を読む
    branch = os.environ.get("HEAD_REF", "")
    subjects = []
    if not skips_commits(branch):
        subjects = commit_subjects(os.environ["BASE_SHA"], os.environ["HEAD_SHA"])
    return run(
        branch,
        os.environ.get("PR_TITLE", ""),
        subjects,
        schema.COMMIT_TYPES,
        os.environ.get("GITHUB_REPOSITORY", "") in versioned_repositories(root),
    )


if __name__ == "__main__":
    raise SystemExit(main())
