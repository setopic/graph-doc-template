"""グラフの語彙の定義。

このテンプレートで、最初に書き換える場所がここである。ノード種別・IDの接頭辞・
置き場所のディレクトリ・層の高さ・エッジ種別を1つのファイルに集めてあるので、
プロジェクトの語彙に合わせて調整する。
"""

from __future__ import annotations

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


def is_immutable_record(node_type: str, status: str) -> bool:
    """確定した記録かどうか。確定前（`draft`・`review`）は書き換えてよいので、Falseを返す。"""
    return node_type in IMMUTABLE_RECORD_TYPES and status not in STALE_STATUSES

# G012: depends_onで、これより多く参照されているノードは、概念が混ざっている疑いがある。
#       変更したときの影響範囲が広くなりすぎる前に、分割を検討する。
MAX_INCOMING_DEPENDENCIES = 8

# ドメインノードの「用語」表。G013・G022・用語の一覧・reviewのA003が読む。
# 見出しと列名は文書の言語に依存するので、ここで差し替えられるようにしてある。
TERM_SECTION_HEADING = "用語"
TERM_COLUMN = "用語"
TERM_MEANING_COLUMN = "意味"

# G013: 「旧称」の列に挙げた語（改名して使わなくなった語）が、そのノードに依存している
#       文書で使われていないかを見る。言い換えは並べない。同じ意味なら、同じ用語を使う。
TERM_OLD_NAME_COLUMN = "旧称"
# 1.19までの列名。**読み続ける。** 見出しが合わない表は用語表として読まないので、
# 読むのをやめると、それを取り込んだ派生で、気づかないうちにG013が止まる。
TERM_FORBIDDEN_COLUMN = "使ってはいけない言い換え"
TERM_OLD_NAME_COLUMNS = (TERM_OLD_NAME_COLUMN, TERM_FORBIDDEN_COLUMN)

# 短すぎる語は本文のどこにでも現れるので、対象から外す（誤検知の害が、検知の益を上回る）。
TERM_MIN_LENGTH = 2

# G014: テンプレートの必須の節。typeごとに、それが無いと文書として成立しない節を挙げる。
#
# **雛形の全節を並べないこと。** 雛形には、書くことがあれば書く節も含まれている。
# 全節を必須にすると、意図して省いた節まで警告になる（実際のデータで35%が該当した）。
# ここに挙げるのは、既存のノードのほぼすべてが実際に持っている節だけにする。
#
# 見出しは、`## `の直後の文字列と完全に一致するかで照合する。文書の言語に依存するので、
# プロジェクトの語彙に合わせて書き換えてよい。空のタプルにすれば、そのtypeは検査しない。
#
# テンプレートを取り込む（git merge template/main）ときに、この行が競合したら、
# **こちら側の値を残す。** 節の名前はプロジェクトごとに違う。
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
DOCS_DIR = "docs"
ROOT_NODE_ID = "IDX-ROOT"

# グラフに含めないパス（docsからの相対、前方一致）
EXCLUDE_PREFIXES = ("00-meta/templates",)

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
# 関係しない。ソースファイルはノードではなく、グラフの外にある指し先である。
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
