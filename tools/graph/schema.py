"""グラフの語彙の定義。

ノード種別・IDの接頭辞・置き場所のディレクトリ・層の高さ・エッジ種別と、
検査の既定値を1つのファイルに集めてある。このファイルは共通ファイルなので、
派生プロジェクトでは書き換えない。書き換えると、取り込みのたびに競合する。

派生プロジェクトは、ノード種別・しきい値・用語表の見出しと列名・必須の節を、
リポジトリの根の`graph.toml`で変える。書き方は、docs/00-meta/node-types.md
（META-02）の「プロジェクトごとの種別」の節と、docs/00-meta/graph-rules.md
（META-01）にある。
"""

from __future__ import annotations

import copy
import re
import tomllib
from pathlib import Path

# --------------------------------------------------------------------------
# ノード種別
# --------------------------------------------------------------------------
# layer: 抽象度の高さ。depends_onは、同じか、より小さいlayerしか指せない。
#        これで、ドメインがユースケースに依存するような層の逆流を、機械的に止める。
# dir:   そのノードを置くディレクトリ（docsからの相対）。Noneなら場所を問わない。
# exempt_layer: 層のルールの対象外（複数の層にまたがる決定記録など）。
NODE_TYPES: dict[str, dict] = {
    "index": {
        "prefix": "IDX",
        "dir": None,
        "layer": 0,
        "exempt_layer": True,
        "label": "目次",
    },
    "meta": {
        "prefix": "META",
        "dir": "00-meta",
        "layer": 0,
        "exempt_layer": True,
        "label": "メタ / 規約",
    },
    "architecture": {
        "prefix": "ARCH",
        "dir": "10-architecture",
        "layer": 10,
        "exempt_layer": False,
        "label": "アーキテクチャ",
    },
    "domain": {
        "prefix": "DOM",
        "dir": "20-domain",
        "layer": 20,
        "exempt_layer": False,
        "label": "ドメイン",
    },
    "usecase": {
        "prefix": "UC",
        "dir": "30-usecases",
        "layer": 30,
        "exempt_layer": False,
        "label": "ユースケース",
    },
    "contract": {
        "prefix": "CON",
        "dir": "40-contracts",
        "layer": 40,
        "exempt_layer": False,
        "label": "契約",
    },
    "adr": {
        "prefix": "ADR",
        "dir": "50-adr",
        "layer": 90,
        "exempt_layer": True,
        "label": "決定記録",
    },
}

# --------------------------------------------------------------------------
# エッジ種別（フロントマターのキー名が、そのままエッジ種別になる）
# --------------------------------------------------------------------------
# layered:   Trueなら、層のルール（G007）の対象
# same_type: Trueなら、同じtype同士しか結べない
# acyclic:   Trueなら、循環の検出（G006）の対象
# symmetric: Trueなら、相互にリンクすることを求める（片側だけならG010の警告）
# desc:      syncが関連ドキュメントのブロックに書く説明
EDGE_KINDS: dict[str, dict] = {
    "refines": {
        "layered": False,
        "same_type": True,
        "acyclic": True,
        "symmetric": False,
        "desc": "分割元のノード（1つの文書を分けたときだけ使う。前提はdepends_on）",
    },
    "depends_on": {
        "layered": True,
        "same_type": False,
        "acyclic": True,
        "symmetric": False,
        "desc": "この文書が成立するために前提となるノード",
    },
    "related": {
        "layered": False,
        "same_type": False,
        "acyclic": False,
        "symmetric": True,
        "desc": "依存はしないが、一緒に読むべきノード",
    },
    "supersedes": {
        "layered": False,
        "same_type": True,
        "acyclic": True,
        "symmetric": False,
        "desc": "この決定が置き換える過去の決定（ADR用）",
    },
    "decides": {
        "layered": False,
        "same_type": False,
        "acyclic": False,
        "symmetric": False,
        "desc": "この決定が影響を与えるノード（ADR用）",
    },
}

# 本文中の[[ID]]から生まれる、暗黙のエッジ種別。
# リンク切れは検出するが、層と循環のルールは当てない。
BODY_EDGE_KIND = "mentions"

# --------------------------------------------------------------------------
# フロントマターの必須キーと語彙
# --------------------------------------------------------------------------
REQUIRED_KEYS = ("id", "type", "title", "status")

# status: 成熟度。stableなノードが未確定のノードに依存していたら、警告する（G009）。
STATUSES = ("draft", "review", "stable", "deprecated")
UNSTABLE_STATUSES = ("draft", "deprecated")

# --------------------------------------------------------------------------
# 健全性のしきい値
# --------------------------------------------------------------------------
# G011: 確定していないstatusのまま、この日数だけ動きが無ければ警告する。
#       書きかけのまま放置された文書を見つけるためのもの。
STALE_AFTER_DAYS = 90
STALE_STATUSES = ("draft", "review")

# 確定したら書き換えない種別。決定を変えるときは、本文を直さず、新しいノードを起こす。
# 古いノードに要るのは後継へのリンクだけで、本文を保守する必要はない。
#
# 確定していない間（STALE_STATUSES）は、書き換えてよい。まだ決めている途中だからである。
#
# ここに挙げた種別には、本文を直させる検査（G020）を当てない。
# 直すこと自体がこの原則に反するので、**直しようのない指摘になる。**
IMMUTABLE_RECORD_TYPES = ("adr",)

# 用語表を語彙として集める種別。G022・用語の一覧・reviewのA003が、この種別のノードの
# 用語表を読む。G013は種別を問わず、用語表を持つノードすべてを読む。
TERM_TYPES = ("domain",)


def is_immutable_record(node_type: str, status: str) -> bool:
    """確定した記録かどうか。確定前（`draft`・`review`）は書き換えてよいので、Falseを返す。"""
    return node_type in IMMUTABLE_RECORD_TYPES and status not in STALE_STATUSES

# G012: depends_onで、これより多く参照されているノードは、概念が混ざっている疑いがある。
#       変更したときの影響範囲が広くなりすぎる前に、分割を検討する。
MAX_INCOMING_DEPENDENCIES = 8

# G012で数えない、依存元の種別。毎回同じノードに依存するのが当然な末端の種別
# （連載小説の各話が、主人公や都市に依存するなど）からの依存は、概念が混ざった印ではない。
# 既定の種別には無い。graph.tomlの`hub_exempt = true`で指定する。
HUB_EXEMPT_TYPES: tuple[str, ...] = ()

# ドメインノードの「用語」表。G013・G022・用語の一覧・reviewのA003が読む。
# 見出しと列名は文書の言語に依存するので、graph.tomlの`[terms]`で差し替えられる。
TERM_SECTION_HEADING = "用語"
TERM_COLUMN = "用語"
TERM_MEANING_COLUMN = "意味"

# G013: 「旧称」の列に挙げた語（改名して使わなくなった語）が、そのノードに依存している
#       文書で使われていないかを見る。言い換えは並べない。同じ意味なら、同じ用語を使う。
TERM_OLD_NAME_COLUMN = "旧称"
# 1.19までの列名。**読み続ける。** 見出しが合わない表は用語表として読まないので、
# 読むのをやめると、それを取り込んだ派生で、気づかないうちにG013が止まる。
TERM_FORBIDDEN_COLUMN = "使ってはいけない言い換え"
TERM_OLD_NAME_COLUMNS: tuple[str, ...] = (TERM_OLD_NAME_COLUMN, TERM_FORBIDDEN_COLUMN)

# 短すぎる語は本文のどこにでも現れるので、対象から外す（誤検知の害が、検知の益を上回る）。
TERM_MIN_LENGTH = 2

# G014: テンプレートの必須の節。typeごとに、それが無いと文書として成立しない節を挙げる。
#
# **雛形の全節を並べないこと。** 雛形には、書くことがあれば書く節も含まれている。
# 全節を必須にすると、意図して省いた節まで警告になる（実際のデータで35%が該当した）。
# ここに挙げるのは、既存のノードのほぼすべてが実際に持っている節だけにする。
#
# 見出しは、`## `の直後の文字列と完全に一致するかで照合する。文書の言語に依存するので、
# 派生ではgraph.tomlの`[required_sections]`で変える。空の配列にすれば、そのtypeは検査しない。
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "adr": ("背景", "決定", "理由", "却下した案", "影響", "見直しの条件"),
    # 「構成」は入れない。構成要素を持たず、方針だけを書くノードがある
    # （認証と権限など）。そこに要素の表を作らせると、中身の無い節が増える。
    "architecture": ("解決したい構造上の問題",),
    "domain": ("定義", "不変条件", "用語"),
    "usecase": ("概要", "事前条件"),
    # 契約には複数の形がある（HTTP・インタラクション・ファイル形式）。
    # 共通して現れる節が無いので、検査しない。形が固まったら足す。
    "contract": (),
    "index": (),
    "meta": (),
}

# refinesを持つノードは親から切り出したものなので、親が持つ節を繰り返さない。
# ここにtypeがあれば、そのノードにはREQUIRED_SECTIONSではなく、こちらを使う。
REQUIRED_SECTIONS_REFINED: dict[str, tuple[str, ...]] = {
    "domain": ("不変条件", "用語"),
    # architectureの必須の節は、「問題」と「構成」という枠組みそのものである。
    # 切り出した子がそれを繰り返すと、親と重複する。子に共通の形はまだ無いので、検査しない。
    "architecture": (),
}

# --------------------------------------------------------------------------
# グラフの走査対象
# --------------------------------------------------------------------------
# 検証する文書のフォルダ（リポジトリの根からの相対パス）。graph.tomlの一番上の
# `docs_dir`で変えられる。implemented_byのパスは、これとは関係なく根から数える。
DOCS_DIR = "docs"
ROOT_NODE_ID = "IDX-ROOT"

# グラフに含めないパス（docsからの相対、前方一致）
EXCLUDE_PREFIXES = ("00-meta/templates",)

# graph.tomlの一番上の`exclude`で足す、グラフに含めないパス（リポジトリの根からの相対）。
# EXCLUDE_PREFIXESは常に外し、これはそれに足す。ほかの道具から取り込んだMarkdownのように、
# 文書のフォルダにあってもノードではないファイルを外すのに使う。
EXCLUDE: tuple[str, ...] = ()

# graph.tomlの種別の`template`に書いた、種別ごとの雛形（種別の名前→リポジトリの根からの相対パス）。
# 書かなかった種別は、文書のフォルダの00-meta/templates/<種別>.mdを使う。
# 雛形はノードではないので、文書のフォルダの中に置いても、グラフに含めない。
TYPE_TEMPLATES: dict[str, str] = {}


def is_excluded(rel: str) -> bool:
    """リポジトリの根からの相対パス`rel`を、グラフに含めないか。"""
    prefix = DOCS_DIR + "/"
    if rel.startswith(prefix) and any(rel[len(prefix) :].startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    if rel in TYPE_TEMPLATES.values():
        return True
    return is_excluded_by_config(rel)


def is_excluded_by_config(rel: str) -> bool:
    """`rel`が`exclude`に書いたパスに当たるか。区切りの単位で合わせる。

    雛形（EXCLUDE_PREFIXES）は、グラフには含めないが、表の検査やlinkifyでは読む。
    `exclude`に書いたものは、取り込んだファイルを書き換えないよう、それらからも外す。
    """
    return any(rel == p or rel.startswith(p + "/") for p in EXCLUDE)

# --------------------------------------------------------------------------
# 実装との対応（文書と実装を同じリポジトリに置く場合だけ使う）
# --------------------------------------------------------------------------
# ノードのフロントマターに、その文書が規定している実装を書ける。
#
#     implemented_by:
#       - tournament/teams.py
#       - tournament/views.py
#
# 書かなければ何も起きない。文書だけのリポジトリでは1件も宣言されないので、
# G016もG017も出ない（用語表の「旧称」と同じ扱い）。
#
# これはエッジではない。層（G007）にも循環（G006）にも到達可能性（G005）にも
# 関係しない。ソースファイルはノードではなく、グラフの外にある参照先である。
#
# 指せるのは、同じリポジトリの中のパスだけである。ファイルでもディレクトリでもよい。
# 別のリポジトリの実装は指せない（G016が「存在しない」と言う）。
IMPLEMENTED_BY_KEY = "implemented_by"

# syncが本文の末尾に書き込むブロックの目印
AUTO_BLOCK_START = "<!-- graph:auto:start -->"
AUTO_BLOCK_END = "<!-- graph:auto:end -->"

# render --intoが図を書き込むブロックの目印
DIAGRAM_BLOCK_START = "<!-- graph:diagram:start -->"
DIAGRAM_BLOCK_END = "<!-- graph:diagram:end -->"

# --------------------------------------------------------------------------
# Mermaidの描画上限（G018）
# --------------------------------------------------------------------------
# GitHubは、Mermaidの図をエッジ500本までしか描かない。500ちょうどで、すでに描画されない
# （実際の文言は「500 edges found, but the limit is 500」）。図は丸ごと消え、
# 「Edge limit exceeded」という短い文言だけが残る。**図が消えたことに気づけるのは、
# GitHub上で見たときだけ**なので、上限の手前で警告して気づけるようにする。
#
# 上限そのものはGitHub側の設定（mermaid.initializeのmaxEdges）で、
# 図の中からは変えられない。自分でホストするHTMLなら引き上げられる。
MERMAID_MAX_EDGES = 500
MERMAID_WARN_EDGES = 450

# --------------------------------------------------------------------------
# SVGの図（render --format svg）
# --------------------------------------------------------------------------
# renderは配置・箱・線・クラス名だけを出し、色・フォント・線の太さ・動きは
# テーマのCSSで決める。CSSはSVGの中の<style>に埋め込む。GitHubはREADMEのSVGを
# imgで出すので、外部のCSSやフォントは読めないからである。
#
# RENDER_THEME:   テーマのCSS（リポジトリの根からの相対パス）。Noneなら既定のテーマ
#                 （tools/graph/themes/default.css）を使う
# RENDER_ANIMATE: depends_onの線の上を点が流れる動き（SMIL）を出すか
# RENDER_PERIOD:  動きの1周の秒数
RENDER_THEME: str | None = None
RENDER_ANIMATE = True
RENDER_PERIOD = 6.0

# 目次の一覧ブロックの目印。syncが中身を作り直す
CHILDREN_START = "<!-- graph:children:start -->"
CHILDREN_END = "<!-- graph:children:end -->"

# ドメインの目次（IDX-DOM）に、syncが作る用語の一覧の目印。
# 無ければ、syncが末尾に足す。index.mdは派生ではmerge=oursなので、
# テンプレートが目印を入れても、派生には届かない。
TERMS_START = "<!-- graph:terms:start -->"
TERMS_END = "<!-- graph:terms:end -->"


def prefix_of(node_type: str) -> str:
    return NODE_TYPES[node_type]["prefix"]


def type_of_prefix(prefix: str) -> str | None:
    for name, spec in NODE_TYPES.items():
        if spec["prefix"] == prefix:
            return name
    return None


def frontmatter_edge_kinds() -> tuple[str, ...]:
    return tuple(EDGE_KINDS.keys())


# --------------------------------------------------------------------------
# プロジェクトごとの語彙（graph.toml）
# --------------------------------------------------------------------------
# リポジトリの根に`graph.toml`を置くと、ノード種別をその内容に差し替える。
# テンプレートはこのファイルを配らない（graph.mkと同じ）。だから取り込みで競合しない。
# 無ければ、上の定義をそのまま使う。書き方はMETA-02（node-types.md）にある。
#
#     [node_types.character]
#     prefix = "CHR"
#     dir = "20-characters"
#     layer = 20
#     label = "人物"
#     terms = true
#     required_sections = ["人物像", "用語"]
#
# **種別を1つでも書いたら、書いたものが種別の全体になる。** テンプレートの種別と
# 混ぜると、使わない種別の雛形と規約が残り、どれが生きているのか分からなくなる。
# `index`と`meta`は、書かなくても常に残し、書き換えさせない。`index`は目次の仕組み
# そのもので、`meta`はテンプレートが配る規約文書（00-meta/）の種別だからである。
#
# 一番上に`extend_default_types = true`を置くと、既定の種別を残したまま、書いた種別を足す。
# 既定と同じ名前の種別は、書いたほうで丸ごと上書きする。置かなければ、全体を差し替える。
#
#     extend_default_types = true
#
#     [node_types.pdr]
#     prefix = "PDR"
#     dir = "50-pdr"
#     layer = 90
#     label = "製品の決定"
#     exempt_layer = true
#
# 種別の`template`には、`new`が使う雛形のパスを、リポジトリの根からの相対で書ける。
# 書かなければ、文書のフォルダの00-meta/templates/<種別>.mdを使う。
#
# `[commit]`の表には、ブランチ名とコミットの1行目に使う種類を足せる（META-07）。
#
#     [commit]
#     extra_types = ["episode"]
#
# `[terms]`の表には、用語表の見出しと列名を書ける。上のTERM_SECTION_HEADING・
# TERM_COLUMN・TERM_MEANING_COLUMN・TERM_OLD_NAME_COLUMNを差し替える。
# 1.19までの列名（TERM_FORBIDDEN_COLUMN）は、差し替えても読み続ける。
#
#     [terms]
#     section_heading = "Terms"
#     term_column = "Term"
#     meaning_column = "Meaning"
#     old_name_column = "Former names"
#
# `[required_sections]`と`[required_sections_refined]`の表には、既定の種別の
# 必須の節（G014）を書ける。書いた種別だけを差し替え、書かなかった種別は既定のままにする。
# 種別を差し替えたときは、[node_types]の各種別に書くので、この2つの表は使えない。
# extend_default_typesを置いたときは、[node_types]に書かなかった既定の種別にだけ使える。
#
#     [required_sections]
#     domain = ["定義", "用語"]
#
# `[render]`の表には、SVGの図（render --format svg）のテーマと動きを書ける。
# 上のRENDER_THEME・RENDER_ANIMATE・RENDER_PERIODを差し替える。
#
#     [render]
#     theme = "docs/graph-theme.css"
#     animate = true
#     period = 6
#
# `[thresholds]`の表には、健全性のしきい値を書ける。上のSTALE_AFTER_DAYS（G011）と
# MAX_INCOMING_DEPENDENCIES（G012）を、schema.pyを書き換えずに変えるためのものである。
# schema.pyは共通ファイルなので、書き換えると取り込みのたびに競合する。
#
#     [thresholds]
#     max_incoming_dependencies = 12
#     stale_after_days = 90
CONFIG_FILE = "graph.toml"

# ブランチ名とコミットの1行目に使う種類（META-07）。Conventional Commitsの語である
COMMIT_TYPES: tuple[str, ...] = ("feat", "fix", "docs", "refactor", "test", "ci", "chore")
_COMMIT_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]*$")

_PREFIX_RE = re.compile(r"^[A-Z]{2,5}$")
_TYPE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_TYPE_KEYS = {
    "prefix",
    "dir",
    "layer",
    "label",
    "exempt_layer",
    "terms",
    "immutable",
    "required_sections",
    "required_sections_refined",
    "hub_exempt",
    "template",
}
_THRESHOLD_KEYS = {"max_incoming_dependencies", "stale_after_days"}
_RENDER_KEYS = {"theme", "animate", "period"}
_TERMS_KEYS = {
    "section_heading": "TERM_SECTION_HEADING",
    "term_column": "TERM_COLUMN",
    "meaning_column": "TERM_MEANING_COLUMN",
    "old_name_column": "TERM_OLD_NAME_COLUMN",
}

# configureが何度呼ばれても同じ結果になるよう、テンプレートの定義を取っておく
# 差し替えても常に残す種別
BUILTIN_TYPES = ("index", "meta")

_DEFAULTS = {
    "NODE_TYPES": copy.deepcopy(NODE_TYPES),
    "REQUIRED_SECTIONS": dict(REQUIRED_SECTIONS),
    "REQUIRED_SECTIONS_REFINED": dict(REQUIRED_SECTIONS_REFINED),
    "IMMUTABLE_RECORD_TYPES": IMMUTABLE_RECORD_TYPES,
    "TERM_TYPES": TERM_TYPES,
    "HUB_EXEMPT_TYPES": HUB_EXEMPT_TYPES,
    "DOCS_DIR": DOCS_DIR,
    "EXCLUDE": EXCLUDE,
    "TYPE_TEMPLATES": dict(TYPE_TEMPLATES),
    "COMMIT_TYPES": COMMIT_TYPES,
    "MAX_INCOMING_DEPENDENCIES": MAX_INCOMING_DEPENDENCIES,
    "STALE_AFTER_DAYS": STALE_AFTER_DAYS,
    "TERM_SECTION_HEADING": TERM_SECTION_HEADING,
    "TERM_COLUMN": TERM_COLUMN,
    "TERM_MEANING_COLUMN": TERM_MEANING_COLUMN,
    "TERM_OLD_NAME_COLUMN": TERM_OLD_NAME_COLUMN,
    "RENDER_THEME": RENDER_THEME,
    "RENDER_ANIMATE": RENDER_ANIMATE,
    "RENDER_PERIOD": RENDER_PERIOD,
}


class ConfigError(ValueError):
    pass


def reset() -> None:
    """語彙をテンプレートの定義に戻す。"""
    global IMMUTABLE_RECORD_TYPES, TERM_TYPES, HUB_EXEMPT_TYPES, COMMIT_TYPES, DOCS_DIR, EXCLUDE
    global MAX_INCOMING_DEPENDENCIES, STALE_AFTER_DAYS
    global TERM_SECTION_HEADING, TERM_COLUMN, TERM_MEANING_COLUMN, TERM_OLD_NAME_COLUMN
    global TERM_OLD_NAME_COLUMNS
    global RENDER_THEME, RENDER_ANIMATE, RENDER_PERIOD
    # 辞書は中身を入れ替える。ほかのモジュールが同じ辞書を参照しているためである
    NODE_TYPES.clear()
    NODE_TYPES.update(copy.deepcopy(_DEFAULTS["NODE_TYPES"]))
    REQUIRED_SECTIONS.clear()
    REQUIRED_SECTIONS.update(_DEFAULTS["REQUIRED_SECTIONS"])
    REQUIRED_SECTIONS_REFINED.clear()
    REQUIRED_SECTIONS_REFINED.update(_DEFAULTS["REQUIRED_SECTIONS_REFINED"])
    TYPE_TEMPLATES.clear()
    TYPE_TEMPLATES.update(_DEFAULTS["TYPE_TEMPLATES"])
    IMMUTABLE_RECORD_TYPES = _DEFAULTS["IMMUTABLE_RECORD_TYPES"]
    TERM_TYPES = _DEFAULTS["TERM_TYPES"]
    HUB_EXEMPT_TYPES = _DEFAULTS["HUB_EXEMPT_TYPES"]
    COMMIT_TYPES = _DEFAULTS["COMMIT_TYPES"]
    DOCS_DIR = _DEFAULTS["DOCS_DIR"]
    EXCLUDE = _DEFAULTS["EXCLUDE"]
    MAX_INCOMING_DEPENDENCIES = _DEFAULTS["MAX_INCOMING_DEPENDENCIES"]
    STALE_AFTER_DAYS = _DEFAULTS["STALE_AFTER_DAYS"]
    TERM_SECTION_HEADING = _DEFAULTS["TERM_SECTION_HEADING"]
    TERM_COLUMN = _DEFAULTS["TERM_COLUMN"]
    TERM_MEANING_COLUMN = _DEFAULTS["TERM_MEANING_COLUMN"]
    TERM_OLD_NAME_COLUMN = _DEFAULTS["TERM_OLD_NAME_COLUMN"]
    TERM_OLD_NAME_COLUMNS = (TERM_OLD_NAME_COLUMN, TERM_FORBIDDEN_COLUMN)
    RENDER_THEME = _DEFAULTS["RENDER_THEME"]
    RENDER_ANIMATE = _DEFAULTS["RENDER_ANIMATE"]
    RENDER_PERIOD = _DEFAULTS["RENDER_PERIOD"]


def configure(root: Path) -> None:
    """`root`に`graph.toml`があれば、ノード種別をその内容に差し替える。

    無ければ、テンプレートの定義に戻すだけである。読めない・書き方が違うときは
    ConfigErrorを出す。黙って既定に戻すと、差し替えたつもりの種別が効かないまま
    検証が通ってしまう。
    """
    reset()
    path = root / CONFIG_FILE
    if not path.is_file():
        return
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_FILE}が読めない: {exc}") from exc

    unknown = set(data) - {
        "docs_dir",
        "extend_default_types",
        "exclude",
        "node_types",
        "commit",
        "thresholds",
        "terms",
        "required_sections",
        "required_sections_refined",
        "render",
    }
    if unknown:
        raise ConfigError(f"{CONFIG_FILE}に知らないキーがある: {', '.join(sorted(unknown))}")
    if "docs_dir" in data:
        _apply_docs_dir(data["docs_dir"])
    # docs_dirの後に読む。docs_dirの外を指していないかを、変えた後のフォルダで確かめる
    if "exclude" in data:
        _apply_exclude(data["exclude"])
    if "commit" in data:
        _apply_commit(data["commit"])
    if "thresholds" in data:
        _apply_thresholds(data["thresholds"])
    if "terms" in data:
        _apply_terms(data["terms"])
    if "render" in data:
        _apply_render(root, data["render"])
    extend = data.get("extend_default_types", False)
    if not isinstance(extend, bool):
        raise ConfigError(f"{CONFIG_FILE}のextend_default_types: trueかfalseにする")
    sections = (
        ("required_sections", REQUIRED_SECTIONS),
        ("required_sections_refined", REQUIRED_SECTIONS_REFINED),
    )
    types = data.get("node_types")
    if types is None:
        if extend:
            raise ConfigError(
                f"{CONFIG_FILE}にextend_default_typesを置いたのに、[node_types]が無い。足す種別を[node_types]に書く"
            )
        for key, target in sections:
            if key in data:
                _apply_default_sections(key, data[key], target)
        return
    if not extend:
        for key, _ in sections:
            if key in data:
                raise ConfigError(
                    f"{CONFIG_FILE}の[{key}]は、[node_types]と一緒には書けない。"
                    f"種別を差し替えたときは、[node_types]の各種別に{key}を書く"
                )
    if not isinstance(types, dict) or not types:
        raise ConfigError(f"{CONFIG_FILE}の[node_types]に、種別が1つも無い")
    _apply_node_types(root, types, extend)
    if not extend:
        return
    # 既定を残したときは、[node_types]に書かなかった既定の種別の必須の節を、この2つの表で変えられる。
    # [node_types]に書いた種別は、その種別の表に書く。2か所に書けると、どちらが効くのか分からない
    for key, target in sections:
        if key not in data:
            continue
        table = data[key]
        written = sorted(set(table) & set(types)) if isinstance(table, dict) else []
        if written:
            raise ConfigError(
                f"{CONFIG_FILE}の[{key}]: {', '.join(written)}は[node_types]に書いた種別なので、"
                f"[node_types.<名前>]の{key}に書く"
            )
        _apply_default_sections(key, table, target)


def _apply_node_types(root: Path, types: dict, extend: bool) -> None:
    """[node_types]の種別を読む。

    `extend`がFalseなら、書いた種別と`index`・`meta`だけを残す。Trueなら、既定の種別も残し、
    書いた種別を足す。既定と同じ名前の種別は、書いたほうで丸ごと上書きする。キーごとに
    混ぜると、書いていないキーが上流の値のまま残り、どの値が効いているのかを
    graph.tomlだけでは読めなくなるからである。
    """
    global IMMUTABLE_RECORD_TYPES, TERM_TYPES, HUB_EXEMPT_TYPES
    kept = [
        name
        for name in (_DEFAULTS["NODE_TYPES"] if extend else BUILTIN_TYPES)
        if name in BUILTIN_TYPES or name not in types
    ]
    node_types = {name: copy.deepcopy(_DEFAULTS["NODE_TYPES"][name]) for name in kept}
    required: dict[str, tuple[str, ...]] = {
        name: _DEFAULTS["REQUIRED_SECTIONS"].get(name, ()) for name in kept
    }
    refined: dict[str, tuple[str, ...]] = {
        name: _DEFAULTS["REQUIRED_SECTIONS_REFINED"][name]
        for name in kept
        if name in _DEFAULTS["REQUIRED_SECTIONS_REFINED"]
    }
    immutable = [name for name in _DEFAULTS["IMMUTABLE_RECORD_TYPES"] if name in node_types]
    terms = [name for name in _DEFAULTS["TERM_TYPES"] if name in node_types]
    hub_exempt = [name for name in _DEFAULTS["HUB_EXEMPT_TYPES"] if name in node_types]
    templates: dict[str, str] = {}
    prefixes = {spec["prefix"]: name for name, spec in node_types.items()}
    dirs = {spec["dir"]: name for name, spec in node_types.items() if spec["dir"]}

    for name, spec in types.items():
        where = f"{CONFIG_FILE}の[node_types.{name}]"
        if name in BUILTIN_TYPES:
            raise ConfigError(f"{where}: {name}はテンプレートの仕組みが使う種別なので、書き換えられない")
        if not _TYPE_NAME_RE.match(name):
            raise ConfigError(f"{where}: 種別の名前は英小文字で始まる英数字にする")
        if not isinstance(spec, dict):
            raise ConfigError(f"{where}: 表で書く")
        unknown = set(spec) - _TYPE_KEYS
        if unknown:
            raise ConfigError(f"{where}: 知らないキーがある: {', '.join(sorted(unknown))}")

        prefix = spec.get("prefix")
        if not isinstance(prefix, str) or not _PREFIX_RE.match(prefix):
            raise ConfigError(f"{where}: prefixは英大文字2〜5字にする（例: CHR）")
        if prefix in prefixes:
            raise ConfigError(f"{where}: prefix {prefix}は{prefixes[prefix]}と重なっている")
        prefixes[prefix] = name

        directory = spec.get("dir")
        if not isinstance(directory, str) or not directory or "/" in directory:
            raise ConfigError(f"{where}: dirは文書のフォルダの直下のディレクトリ名にする（例: 20-characters）")
        if directory in dirs:
            raise ConfigError(f"{where}: dir {directory}は{dirs[directory]}と重なっている")
        dirs[directory] = name

        layer = spec.get("layer")
        if not isinstance(layer, int) or isinstance(layer, bool):
            raise ConfigError(f"{where}: layerは整数にする")
        label = spec.get("label")
        if not isinstance(label, str) or not label:
            raise ConfigError(f"{where}: labelを書く")

        flags = {}
        for key in ("exempt_layer", "terms", "immutable", "hub_exempt"):
            value = spec.get(key, False)
            if not isinstance(value, bool):
                raise ConfigError(f"{where}: {key}はtrueかfalseにする")
            flags[key] = value

        node_types[name] = {
            "prefix": prefix,
            "dir": directory,
            "layer": layer,
            "exempt_layer": flags["exempt_layer"],
            "label": label,
        }
        required[name] = _sections(where, spec, "required_sections") or ()
        refined_sections = _sections(where, spec, "required_sections_refined")
        if refined_sections is not None:
            refined[name] = refined_sections
        if flags["immutable"]:
            immutable.append(name)
        if flags["terms"]:
            terms.append(name)
        if flags["hub_exempt"]:
            hub_exempt.append(name)
        if "template" in spec:
            templates[name] = _template_path(root, where, spec["template"])

    # 既定の種別は既定の順に並べ、足した種別をその後ろに置く。上書きした種別も、既定の位置に置く
    order = [name for name in _DEFAULTS["NODE_TYPES"] if name in node_types]
    order += [name for name in node_types if name not in order]
    NODE_TYPES.clear()
    NODE_TYPES.update({name: node_types[name] for name in order})
    REQUIRED_SECTIONS.clear()
    REQUIRED_SECTIONS.update(required)
    REQUIRED_SECTIONS_REFINED.clear()
    REQUIRED_SECTIONS_REFINED.update(refined)
    TYPE_TEMPLATES.clear()
    TYPE_TEMPLATES.update(templates)
    IMMUTABLE_RECORD_TYPES = tuple(immutable)
    TERM_TYPES = tuple(terms)
    HUB_EXEMPT_TYPES = tuple(hub_exempt)


def _apply_commit(table: object) -> None:
    global COMMIT_TYPES
    where = f"{CONFIG_FILE}の[commit]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: 表で書く")
    unknown = set(table) - {"extra_types"}
    if unknown:
        raise ConfigError(f"{where}: 知らないキーがある: {', '.join(sorted(unknown))}")
    extra = table.get("extra_types", [])
    if not isinstance(extra, list) or not all(isinstance(v, str) and _COMMIT_TYPE_RE.match(v) for v in extra):
        raise ConfigError(f"{where}: extra_typesは英小文字で始まる語の配列にする（例: [\"episode\"]）")
    taken = [v for v in extra if v in _DEFAULTS["COMMIT_TYPES"]]
    if taken:
        raise ConfigError(f"{where}: {', '.join(taken)}は標準の種類にすでにある")
    if len(set(extra)) != len(extra):
        raise ConfigError(f"{where}: extra_typesに同じ語が2つある")
    COMMIT_TYPES = _DEFAULTS["COMMIT_TYPES"] + tuple(extra)


def _apply_docs_dir(value: object) -> None:
    """検証する文書のフォルダを差し替える。

    リポジトリの根からの相対パスだけを受け付ける。根の外を検証させると、
    ほかのリポジトリの文書を、このリポジトリのグラフとして扱ってしまう。
    """
    global DOCS_DIR
    where = f"{CONFIG_FILE}のdocs_dir"
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: リポジトリの根からの相対パスを、空でない文字列で書く（例: design）")
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    if value.strip().startswith(("/", "\\")) or ":" in parts[0] or any(p in ("", ".", "..") for p in parts):
        raise ConfigError(f"{where}: リポジトリの根からの相対パスにする（/で始めない。.や..や空の区切りを使わない）: {value!r}")
    DOCS_DIR = "/".join(parts)


def _apply_exclude(value: object) -> None:
    """グラフに含めないパスを足す。

    docs_dirと同じく、リポジトリの根からの相対パスで書く。文書のフォルダの外を指す値は断る。
    docs_dirを変えたのにこちらを直し忘れると、何も外さないまま気づかないからである。
    """
    global EXCLUDE
    where = f"{CONFIG_FILE}のexclude"
    if not isinstance(value, list):
        raise ConfigError(f"{where}: パスの文字列の配列にする（例: [\"{DOCS_DIR}/vendor/\"]）")
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{where}: パスは空でない文字列にする: {item!r}")
        parts = item.strip().replace("\\", "/").strip("/").split("/")
        if item.strip().startswith(("/", "\\")) or ":" in parts[0] or any(p in ("", ".", "..") for p in parts):
            raise ConfigError(f"{where}: リポジトリの根からの相対パスにする（/で始めない。.や..や空の区切りを使わない）: {item!r}")
        path = "/".join(parts)
        if not path.startswith(DOCS_DIR + "/"):
            raise ConfigError(f"{where}: 文書のフォルダ（{DOCS_DIR}/）の下のパスにする: {item!r}")
        paths.append(path)
    EXCLUDE = tuple(paths)


def _template_path(root: Path, where: str, value: object) -> str:
    """種別の`template`を、リポジトリの根からの相対パスとして読む。

    excludeやimplemented_byと同じく根から数える。雛形を文書のフォルダの外にも置けるようにし、
    docs_dirを変えても書き直さずに済むようにするためである。指したファイルが無ければ断る。
    `new`で初めて気づくと、どの種別の書き方が違うのかを探すことになる。
    """
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: templateは雛形のファイルのパスを、空でない文字列で書く（例: \"templates/adr.md\"）")
    parts = value.strip().replace("\\", "/").strip("/").split("/")
    if value.strip().startswith(("/", "\\")) or ":" in parts[0] or any(p in ("", ".", "..") for p in parts):
        raise ConfigError(f"{where}: templateはリポジトリの根からの相対パスにする（/で始めない。.や..や空の区切りを使わない）: {value!r}")
    path = "/".join(parts)
    if not (root / path).is_file():
        raise ConfigError(f"{where}: templateに書いた雛形が無い: {path}（リポジトリの根から数える）")
    return path


def _apply_thresholds(table: object) -> None:
    global MAX_INCOMING_DEPENDENCIES, STALE_AFTER_DAYS
    where = f"{CONFIG_FILE}の[thresholds]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: 表で書く")
    unknown = set(table) - _THRESHOLD_KEYS
    if unknown:
        raise ConfigError(f"{where}: 知らないキーがある: {', '.join(sorted(unknown))}")
    for key, value in table.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ConfigError(f"{where}: {key}は1以上の整数にする")
    MAX_INCOMING_DEPENDENCIES = table.get("max_incoming_dependencies", MAX_INCOMING_DEPENDENCIES)
    STALE_AFTER_DAYS = table.get("stale_after_days", STALE_AFTER_DAYS)


def _apply_render(root: Path, table: object) -> None:
    """[render]の表を読む。テーマのCSSは、リポジトリの根の中にあるファイルだけを受け付ける。"""
    global RENDER_THEME, RENDER_ANIMATE, RENDER_PERIOD
    where = f"{CONFIG_FILE}の[render]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: 表で書く")
    unknown = set(table) - _RENDER_KEYS
    if unknown:
        raise ConfigError(f"{where}: 知らないキーがある: {', '.join(sorted(unknown))}")
    if "theme" in table:
        value = table["theme"]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where}: themeは、リポジトリの根からの相対パスを空でない文字列で書く（例: docs/graph-theme.css）")
        parts = value.strip().replace("\\", "/").split("/")
        if value.strip().startswith(("/", "\\")) or ":" in parts[0] or any(p in ("", ".", "..") for p in parts):
            raise ConfigError(f"{where}: themeは、リポジトリの根からの相対パスにする（/で始めない。.や..や空の区切りを使わない）: {value!r}")
        rel = "/".join(parts)
        if not (root / rel).is_file():
            raise ConfigError(f"{where}: themeのファイルが無い: {rel}")
        RENDER_THEME = rel
    if "animate" in table:
        if not isinstance(table["animate"], bool):
            raise ConfigError(f"{where}: animateはtrueかfalseにする")
        RENDER_ANIMATE = table["animate"]
    if "period" in table:
        period = table["period"]
        if isinstance(period, bool) or not isinstance(period, (int, float)) or not 0 < period <= 600:
            raise ConfigError(f"{where}: periodは、0より大きく600以下の秒数にする")
        RENDER_PERIOD = float(period)


def _apply_terms(table: object) -> None:
    global TERM_OLD_NAME_COLUMNS
    where = f"{CONFIG_FILE}の[terms]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: 表で書く")
    unknown = set(table) - set(_TERMS_KEYS)
    if unknown:
        raise ConfigError(f"{where}: 知らないキーがある: {', '.join(sorted(unknown))}")
    for key, value in table.items():
        if not isinstance(value, str) or not value.strip() or "|" in value:
            raise ConfigError(f"{where}: {key}は空でない文字列にする（|は使えない）")
        globals()[_TERMS_KEYS[key]] = value.strip()
    columns = [TERM_COLUMN, TERM_MEANING_COLUMN, TERM_OLD_NAME_COLUMN]
    if len(set(columns)) != len(columns):
        raise ConfigError(f"{where}: 列名が重なっている: {', '.join(columns)}")
    TERM_OLD_NAME_COLUMNS = (TERM_OLD_NAME_COLUMN, TERM_FORBIDDEN_COLUMN)


def _apply_default_sections(key: str, table: object, target: dict[str, tuple[str, ...]]) -> None:
    where = f"{CONFIG_FILE}の[{key}]"
    if not isinstance(table, dict):
        raise ConfigError(f"{where}: 表で書く")
    unknown = set(table) - set(NODE_TYPES)
    if unknown:
        raise ConfigError(f"{where}: 知らない種別がある: {', '.join(sorted(unknown))}")
    for name in table:
        target[name] = _sections(where, table, name)


def _sections(where: str, spec: dict, key: str) -> tuple[str, ...] | None:
    if key not in spec:
        return None
    value = spec[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ConfigError(f"{where}: {key}は見出しの文字列の配列にする")
    return tuple(value)
