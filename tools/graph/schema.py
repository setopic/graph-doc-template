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
    "api": {
        "prefix": "API",
        "dir": "40-api",
        "layer": 40,
        "exempt_layer": False,
        "label": "API / 契約",
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
        "desc": "より大きい同種ノードを具体化する（親 → 子の子側に書く）",
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
# グラフの走査対象
# --------------------------------------------------------------------------
DOCS_DIR = "docs"
ROOT_NODE_ID = "IDX-ROOT"

# グラフに含めないパス（docs からの相対、前方一致）
EXCLUDE_PREFIXES = ("00-meta/templates",)

# sync が本文末尾に書き込むブロックの目印
AUTO_BLOCK_START = "<!-- graph:auto:start -->"
AUTO_BLOCK_END = "<!-- graph:auto:end -->"


def prefix_of(node_type: str) -> str:
    return NODE_TYPES[node_type]["prefix"]


def type_of_prefix(prefix: str) -> str | None:
    for name, spec in NODE_TYPES.items():
        if spec["prefix"] == prefix:
            return name
    return None


def frontmatter_edge_kinds() -> tuple[str, ...]:
    return tuple(EDGE_KINDS.keys())
