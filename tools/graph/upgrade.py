"""テンプレートとの差を調べる。

**何も書き込まない。** 取り込みは、META-08（docs/00-meta/template-upgrade.md）の手順（`make update`ほか）に沿って
人が行う。このモジュールが答えるのは、次の1つだけである。

    「自分は遅れているか。遅れているなら、何が変わり、移行作業は要るか」

これが分からないと、派生プロジェクトは、気づかないうちに古くなる。マージし忘れても
何も起きないので、気づく機会が無い。

テンプレートは層を重ねられる（graph-doc-templateの上にgraph-project-templateを
重ねるなど）。版と変更履歴は層ごとに持ち、層ごとに比べる（setopic/graph-doc-template#125）。
下の層の版だけを比べると、上の層だけの変更を「取り込むものは無い」と誤って伝える。

- 下の層（graph-doc-template）の版は`tools/graph/version.py`、変更履歴は`TEMPLATE_CHANGELOG.md`
- 上の層は、`tools/graph/layers/<層の名前>.toml`を1つ置き、版と変更履歴の場所を書く

上の層のファイルは層ごとに名前が違うので、層を重ねても取り込みで競合しない。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .git import run as git_run

REMOTE = "template"
BRANCH = "main"
VERSION_PATH = "tools/graph/version.py"
CHANGELOG_PATH = "TEMPLATE_CHANGELOG.md"

# 下の層。版と変更履歴の場所は、上の層の宣言より前から決まっているので、ここに書く
BASE_LAYER = "graph-doc-template"
BASE_REPOSITORY = "https://github.com/setopic/graph-doc-template.git"

# 上の層の宣言を置くディレクトリ。1つの層につき、`<層の名前>.toml`を1つ置く
LAYERS_DIR = "tools/graph/layers"
LAYER_KEYS = ("name", "label", "below", "version", "changelog", "repository")
# 取り込みのブランチ名に入るので、英小文字と数字だけにする
LABEL_RE = re.compile(r"^[a-z][a-z0-9]*$")

VERSION_RE = re.compile(r'TEMPLATE_VERSION\s*=\s*["\']([^"\']+)["\']')
# 変更履歴の見出しの形（例: "## 1.2.0（2026-08-14）"）。版の後ろは問わない。
# 1.43.2までの見出しは版と日付をダッシュでつないでいた。上の層や派生の変更履歴には残っているので、どちらも読む
ENTRY_RE = re.compile(r"^##\s+(\d+\.\d+\.\d+)\b(.*)$")

# check-attrに一度に渡す経路の数。多すぎると、コマンド行の長さの上限に当たる
# （初回のマージの前は、差がツリー全体になり、数百件になりうる）
ATTR_CHUNK = 100


@dataclass(frozen=True)
class Layer:
    """テンプレートの1つの層。版は、読めなければNoneにする。"""

    name: str
    version: str | None
    changelog: str
    repository: str
    # 取り込みのブランチ名で、版の前に付ける名前。下の層は付けない（`chore/template-<版>`のまま）
    label: str | None = None
    below: str | None = None
    # PRの題（squashのコミット）に版を求めるか。上の層は、tomlの`versioned_title`で選ぶ（META-07）
    versioned_title: bool = False


class UpgradeError(RuntimeError):
    pass


def _ref() -> str:
    return f"{REMOTE}/{BRANCH}"


def parse_version(text: str) -> tuple[int, ...] | None:
    """"1.2.3"を(1, 2, 3)にする。数字以外が混ざっていたら、Noneを返す。"""
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except ValueError:
        return None


def read_remote_file(root: Path, path: str) -> str | None:
    return git_run(root, ["show", f"{_ref()}:{path}"])


def changelog_entries(text: str, newer_than: tuple[int, ...]) -> list[tuple[str, str]]:
    """`newer_than`より新しい版の項目を、新しい順に返す。"""
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

    # 項目の末尾に付く区切り線は、表示に要らない
    entries = [(version, text.rstrip("- \n")) for version, text in entries]

    return [
        (version, text)
        for version, text in entries
        if (parsed := parse_version(version)) is not None and parsed > newer_than
    ]


def merge_ours(root: Path, paths: list[str]) -> set[str]:
    """`.gitattributes`が`merge=ours`にしている経路を返す。

    判定できなければ、空集合を返す。変更されるファイルを多めに出すのは害が小さいが、
    判定できないまま一覧から落とすと、変わるものを「変わらない」と誤って伝えることになる。
    """
    # 取り込みは`make update`で行い、そのときだけドライバを効かせる。だから、
    # クローンにドライバが常設されているかどうかは見ない（setopic/graph-doc-template#36）。
    # `make update`を使わずに取り込むと、この一覧と実際の結果がずれる。

    found: set[str] = set()
    for start in range(0, len(paths), ATTR_CHUNK):
        chunk = paths[start : start + ATTR_CHUNK]
        # -zなら、経路も値もNUL区切りで返る。引用符もエスケープも入らない
        out = git_run(root, ["check-attr", "-z", "merge", "--", *chunk])
        if out is None:
            return set()
        # <経路> NUL <属性> NUL <値>の3つで1組
        fields = out.split("\0")
        for i in range(0, len(fields) - 2, 3):
            if fields[i + 1] == "merge" and fields[i + 2] == "ours":
                found.add(fields[i])
    return found


def _parse_layer(text: str, source: str) -> Layer:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise UpgradeError(f"{source}を読めない: {exc}") from exc
    missing = [key for key in LAYER_KEYS if not isinstance(data.get(key), str)]
    if missing:
        raise UpgradeError(f"{source}に{'・'.join(missing)}が無い")
    if not LABEL_RE.match(data["label"]):
        raise UpgradeError(f"{source}のlabelは、英小文字で始まる英小文字と数字にする")
    versioned_title = data.get("versioned_title", False)
    if not isinstance(versioned_title, bool):
        raise UpgradeError(f"{source}のversioned_titleは、trueかfalseにする")
    return Layer(
        name=data["name"],
        version=data["version"],
        changelog=data["changelog"],
        repository=data["repository"],
        label=data["label"],
        below=data["below"],
        versioned_title=versioned_title,
    )


def _order(base: Layer, upper: list[Layer]) -> list[Layer]:
    """下の層から順に並べる。`below`でたどれない層は、名前の順に最後に置く。"""
    ordered = [base]
    rest = sorted(upper, key=lambda layer: layer.name)
    while True:
        above = next((layer for layer in rest if layer.below == ordered[-1].name), None)
        if above is None:
            break
        ordered.append(above)
        rest.remove(above)
    return ordered + rest


def read_layers(read: Callable[[str], str | None], names: list[str]) -> list[Layer]:
    """層を、下の層から順に返す。

    `read`は、リポジトリの根からの経路を受け取って中身を返す（無ければNone）。
    `names`は、`LAYERS_DIR`にある宣言のファイル名である。手元の作業ツリーと
    テンプレートの側（`git show`）を同じ関数で読めるように、読み方を外から渡す。
    """
    version_text = read(VERSION_PATH)
    found = VERSION_RE.search(version_text) if version_text else None
    base = Layer(
        name=BASE_LAYER,
        version=found.group(1) if found else None,
        changelog=CHANGELOG_PATH,
        repository=BASE_REPOSITORY,
        versioned_title=True,
    )
    upper = []
    for name in names:
        path = f"{LAYERS_DIR}/{name}"
        text = read(path)
        if text is not None:
            upper.append(_parse_layer(text, path))
    return _order(base, upper)


def local_layers(root: Path) -> list[Layer]:
    """手元の作業ツリーにある層を、下の層から順に返す。"""

    def read(path: str) -> str | None:
        target = root / path
        return target.read_text(encoding="utf-8") if target.is_file() else None

    directory = root / LAYERS_DIR
    names = sorted(p.name for p in directory.glob("*.toml")) if directory.is_dir() else []
    return read_layers(read, names)


def remote_layers(root: Path) -> list[Layer]:
    """テンプレートの側（`template/main`）にある層を、下の層から順に返す。fetchはしない。"""
    # ディレクトリが無ければ失敗してNoneが返る。上の層が無いだけなので、空として扱う
    listing = git_run(root, ["ls-tree", "--name-only", f"{_ref()}:{LAYERS_DIR}"])
    names = sorted(line for line in (listing or "").splitlines() if line.endswith(".toml"))
    return read_layers(lambda path: read_remote_file(root, path), names)


def compare(root: Path) -> list[dict]:
    """テンプレートの側にある層ごとに、手元の版と比べる。下の層から順に返す。

    手元にしか無い層は比べない。層のテンプレート本体（graph-project-templateなど）では、
    自分の層は手元にしか無く、`template`は1つ下の層を指しているからである。
    """
    local = {layer.name: layer for layer in local_layers(root)}
    result = []
    for theirs in remote_layers(root):
        remote = parse_version(theirs.version) if theirs.version else None
        if remote is None:
            raise UpgradeError(f"テンプレートの{theirs.name}の版を読み取れなかった")
        ours = local.get(theirs.name)
        local_text = ours.version if ours else None
        current = parse_version(local_text) if local_text else None
        if ours is not None and current is None:
            raise UpgradeError(f"手元の{theirs.name}の版を読み取れなかった")

        # 手元に無い層は、まだ一度も取り込んでいない。遅れているとして扱い、
        # 変更履歴は全部を出さない（版の宣言より前の項目まで並んでしまう）
        behind = current is None or remote > current
        entries: list[tuple[str, str]] = []
        if current is not None and remote > current:
            changelog = read_remote_file(root, theirs.changelog)
            if changelog:
                entries = changelog_entries(changelog, current)

        result.append(
            {
                "name": theirs.name,
                "label": theirs.label,
                "local": local_text,
                "remote": theirs.version,
                "behind": behind,
                "ahead": current is not None and current > remote,
                # majorが上がっていれば、移行作業が要る
                "breaking": current is not None and remote > current and remote[0] > current[0],
                "entries": entries,
            }
        )
    return result


def label(layers: list[dict]) -> str:
    """取り込みのブランチ名とマージのメッセージに入れる版。遅れている層だけを、下から並べる。

    下の層は版だけ（`1.38.0`）、上の層は名前を前に付ける（`project-0.14.0`）。
    両方が遅れていれば`1.38.0-project-0.14.0`になる。遅れている層が無ければ空にする。
    """
    parts = []
    for layer in layers:
        if not layer["behind"]:
            continue
        prefix = f"{layer['label']}-" if layer["label"] else ""
        parts.append(f"{prefix}{layer['remote']}")
    return "-".join(parts)


def _require_remote(root: Path) -> None:
    remotes = git_run(root, ["remote"])
    if remotes is None:
        raise UpgradeError("gitのリポジトリではないか、gitを実行できない")
    if REMOTE not in remotes.split():
        # いちばん上の層が、このリポジトリの取り込み元である
        top = local_layers(root)[-1]
        raise UpgradeError(
            f"リモート{REMOTE!r}が無い。最初に一度だけ、次のように設定する。\n"
            f"  git remote add {REMOTE} {top.repository}"
        )


def inspect_label(root: Path) -> str:
    """取り込みの版（`label`）だけを返す。fetchはしない。`make update`が先に済ませる。"""
    _require_remote(root)
    return label(compare(root))


def inspect(root: Path) -> dict:
    """テンプレートとの差を調べる。書き込みは行わない。"""
    _require_remote(root)

    if git_run(root, ["fetch", REMOTE]) is None:
        raise UpgradeError(f"git fetch {REMOTE}に失敗した（ネットワークを確かめる）")

    layers = compare(root)
    behind = any(layer["behind"] for layer in layers)

    # ドットは3つにする。2つだとツリー全体の差になり、テンプレートには無い
    # プロジェクト固有のノードまで、変更されるように見えてしまう。
    # 知りたいのは、分岐したあとにテンプレート側が変えた分だけである。
    diff = git_run(root, ["diff", "--name-only", f"HEAD...{_ref()}"])
    if diff is None:
        # 共通の祖先が無い（初回のマージの前）。全体の差で代用する
        diff = git_run(root, ["diff", "--name-only", "HEAD", _ref()])
    files = [line for line in (diff or "").splitlines() if line.strip()]

    # `merge=ours`のものは、差があってもマージでは変わらない（プロジェクト側が残る）。
    # 差分にはそのまま出てくるので、落とさないと、変わらないものを「変更される」と誤って伝える。
    ours = merge_ours(root, files)
    files = [path for path in files if path not in ours]

    return {
        "layers": layers,
        "behind": behind,
        "ahead": not behind and any(layer["ahead"] for layer in layers),
        "breaking": any(layer["breaking"] for layer in layers),
        "label": label(layers),
        "files": files,
    }
