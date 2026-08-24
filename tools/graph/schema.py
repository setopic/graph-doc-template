"""グラフの語彙定義。

このテンプレートで**最初に書き換える場所**がここ。
ノード種別・ID 接頭辞・配置ディレクトリ・層の高さ・エッジ種別を
1 ファイルに集約してあるので、プロジェクトの語彙に合わせて調整する。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# ノード種別
# --------------------------------------------------------------------------
# layer: 抽象度の高さ。depends_on は「同じか、より小さい layer」しか指せない。
#        これで「ドメインがユースケースに依存する」ような層の逆流を機械的に止める。
# dir:   そのノードが置かれるべきディレクトリ（docs からの相対）。None は場所を問わない。
# exempt_layer: 層ルールの対象外（横断的な決定記録など）。
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
# エッジ種別（フロントマターのキー名がそのままエッジ種別になる）
# --------------------------------------------------------------------------
# layered:   True なら層ルール（G007）の対象
# same_type: True なら同じ type 同士しか結べない
# acyclic:   True なら循環検出（G006）の対象
# symmetric: True なら相互リンクを期待する（片側だけなら警告 G010）
EDGE_KINDS: dict[str, dict] = {
    "refines": {
        "layered": False,
        "same_type": True,
        "acyclic": True,
        "symmetric": False,
        "desc": "分割元のノード（1 つの文書を分けたときだけ使う。前提は depends_on）",
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
        "desc": "依存はしないが併読すべきノード",
    },
    "supersedes": {
        "layered": False,
        "same_type": True,
        "acyclic": True,
        "symmetric": False,
        "desc": "この決定が置き換える過去の決定（ADR 用）",
    },
    "decides": {
        "layered": False,
        "same_type": False,
        "acyclic": False,
        "symmetric": False,
        "desc": "この決定が影響を与えるノード（ADR 用）",
    },
}

# 本文中の [[ID]] から生まれる暗黙のエッジ種別。
# リンク切れは検出するが、層・循環のルールは適用しない。
BODY_EDGE_KIND = "mentions"

# --------------------------------------------------------------------------
# フロントマターの必須キーと語彙
# --------------------------------------------------------------------------
REQUIRED_KEYS = ("id", "type", "title", "status")

# status: 成熟度。stable なノードが未確定のノードに依存していたら警告する（G009）。
STATUSES = ("draft", "review", "stable", "deprecated")
UNSTABLE_STATUSES = ("draft", "deprecated")

# --------------------------------------------------------------------------
# 健全性のしきい値
# --------------------------------------------------------------------------
# G011: 確定していない status のまま、この日数だけ動きがなければ警告する。
#       「書きかけで放置された文書」を見つけるためのもの。
STALE_AFTER_DAYS = 90
STALE_STATUSES = ("draft", "review")

# G012: depends_on でこれより多く参照されているノードは、概念が混ざっている疑い。
#       変更時の影響範囲が広くなりすぎる前に分割を検討する。
MAX_INCOMING_DEPENDENCIES = 8

# G013: 用語の一貫性。ドメインノードの「用語」表に挙げた「使ってはいけない言い換え」が、
#       そのノードに依存している文書で使われていないかを見る。
#       見出しと列名は文書の言語に依存するので、ここで差し替えられるようにしてある。
TERM_SECTION_HEADING = "用語"
TERM_COLUMN = "用語"
TERM_FORBIDDEN_COLUMN = "使ってはいけない言い換え"

# 短すぎる語は本文のどこにでも現れるため対象から外す（誤検知が実害を超える）。
TERM_MIN_LENGTH = 2

# G014: テンプレートの必須節。type ごとに「これが無いと文書として成立しない」節を挙げる。
#
# **テンプレートの全節を並べないこと。** 雛形には「書くことがあれば書く」節も含まれる。
# 全節を必須にすると、意図的に省いた節まで警告になる（実データで 35% が該当した）。
# ここに挙げるのは、既存ノードのほぼ全てが実際に持っている節だけにする。
#
# 見出しは `## ` の直後の文字列と完全一致で照合する。文書の言語に依存するので、
# プロジェクトの語彙に合わせて書き換えてよい。**空のタプルにすればその type は検査しない。**
#
# テンプレートを取り込む（git merge template/main）ときにこの行が競合したら、
# **こちら側の値を残す。** 節の名前はプロジェクトごとに違う。
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "adr": ("背景", "決定", "理由", "却下した案", "影響", "見直しの条件"),
    # 「構成」は入れない。構成要素を持たず方針だけを書くノードがある
    # （認証と権限など）。そこに要素の表を作らせると中身の無い節が増える。
    "architecture": ("解決したい構造上の問題",),
    "domain": ("定義", "不変条件", "用語"),
    "usecase": ("概要", "事前条件"),
    # 契約は形が複数ある（HTTP / インタラクション / ファイル形式）。
    # 共通して現れる節が無いので検査しない。形が固まったら足す。
    "contract": (),
    "index": (),
    "meta": (),
}

# refines を持つノードは親から切り出したものなので、親が持つ節を繰り返さない。
# ここに type があれば、そのノードには REQUIRED_SECTIONS ではなくこちらを使う。
REQUIRED_SECTIONS_REFINED: dict[str, tuple[str, ...]] = {
    "domain": ("不変条件", "用語"),
    # architecture の必須節は「問題」と「構成」という枠組みそのもの。
    # 切り出した子がそれを繰り返すと親と重複する。子に共通の形はまだ無いので検査しない。
    "architecture": (),
}

# --------------------------------------------------------------------------
# グラフの走査対象
# --------------------------------------------------------------------------
DOCS_DIR = "docs"
ROOT_NODE_ID = "IDX-ROOT"

# グラフに含めないパス（docs からの相対、前方一致）
EXCLUDE_PREFIXES = ("00-meta/templates",)

# sync が本文末尾に書き込むブロックの目印
AUTO_BLOCK_START = "<!-- graph:auto:start -->"
AUTO_BLOCK_END = "<!-- graph:auto:end -->"

# render --into が図を書き込むブロックの目印
DIAGRAM_BLOCK_START = "<!-- graph:diagram:start -->"
DIAGRAM_BLOCK_END = "<!-- graph:diagram:end -->"

# 目次の一覧ブロックの目印。sync が中身を作り直す
CHILDREN_START = "<!-- graph:children:start -->"
CHILDREN_END = "<!-- graph:children:end -->"


def prefix_of(node_type: str) -> str:
    return NODE_TYPES[node_type]["prefix"]


def type_of_prefix(prefix: str) -> str | None:
    for name, spec in NODE_TYPES.items():
        if spec["prefix"] == prefix:
            return name
    return None


def frontmatter_edge_kinds() -> tuple[str, ...]:
    return tuple(EDGE_KINDS.keys())
