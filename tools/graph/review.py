"""本文の質を、AIに見てもらう（`graph review`）。

**`check`とは性質が違う。** `check`のG0xxは、同じ入力なら同じ結果が出て、
CIがそれを強制する。ここで出る指摘は再現しない。だからコードの名前空間を
`A001`〜に分け、CIでは回さず、終了コードも常に0にしてある。

外部パッケージは使わない。標準ライブラリの`urllib`でAPIを呼ぶ。
ただし、ネットワークとは通信する。これはこのリポジトリで唯一の例外で、
`check`は今までどおりオフラインで完結する。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import schema
from .model import Graph, Node
from .rules import forbidden_terms, sections, term_rows

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_LIMIT = 10
# 思考に使った分も、この上限に数える。thinkingを省くと、claude-sonnet-5は適応型の思考を使う。
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 120

API_KEY_ENV = "ANTHROPIC_API_KEY"

# 指摘コード。G系とは別の名前空間にする（再現しないため）。
FINDING_CODES: dict[str, str] = {
    "A001": "曖昧表現",
    "A002": "冗長表現",
    "A003": "用語の不統一（同じ意味のことを、用語表とは別の語で書いている）",
    "A004": "必須説明の欠落・粒度の不揃い",
    "A005": "「前提 → 本文 → まとめ」の構造が成立していない",
    "A006": "このノードが何を説明するものか不明瞭",
    "A007": "「Nつある」と書いた数が、直後の列挙の数と合わない",
    "A008": "まだ必要になっていない一般化を規定している",
    "A009": "1つしか実装が無いのに抽象を置いている",
}

_CODE_LIST = "\n".join(f"- {code}: {desc}" for code, desc in FINDING_CODES.items())

# 応答の形。structured outputs（output_config.format）で、この形のJSONだけを返させる。
FINDINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": list(FINDING_CODES)},
                    "quote": {"type": "string", "description": "本文からの短い引用"},
                    "message": {"type": "string", "description": "何が問題か"},
                    "suggestion": {"type": "string", "description": "どう直すか"},
                },
                "required": ["code", "quote", "message", "suggestion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""あなたは、設計文書のレビュアーである。日本語のMarkdownの文書を読み、
文章の質と、文書に現れた過剰な設計だけを指摘すること。

指摘に使えるのは、次のコードだけである。

{_CODE_LIST}

次のことを守る。

- **構造の誤り（リンク切れ、依存の向き、必須の節の欠落）は指摘しない。**
  それらは別の検査が機械的に見ていて、あなたの担当ではない
- 内容の正しさを疑わない。書かれている事実は、正しいものとして扱う
- 好みの問題は指摘しない。直さなくても通じるなら、指摘しない
- 指摘が無ければ、空の配列を返す。無理に見つけない
- A003の対象は、渡した「ドメインの用語」と同じ意味のことを、別の語で書いている箇所だけである。
  用語表の語をそのまま使っていれば、指摘しない。「使わない語」を使っていれば、指摘する。
  どの用語にも当たらない語は、新しい概念かもしれないので、指摘しない
- **A007は、数えてから指摘する。** 対象は、「理由は3つある」のように個数を宣言し、
  直後にその列挙が続く場合だけである。数えて合っていれば、指摘しない。
  「1つだけ試す」「1つある」のように、列挙の個数を指していない用法は対象外である
  （機械的に当てはめると、この取り違えのために、誤検出が本物を上回った）
- A008・A009の対象は、文書が「こう作る」と規定している箇所だけである。
  「将来に備えて」「汎用的に」のような語が出てくるだけでは、指摘しない。
  次の3つは対象外とする。
  - ADRの「検討した案」「却下した案」。案を並べるのはADRの仕事である
  - 「やらない」「必要になったら足す」と先送りを明記した箇所。
    過剰な設計を避けた記録であって、兆候ではない
  - 一般化や抽象が要る理由（2つ目の実体がある、受け入れ条件が求めている）が、
    本文か、本文のリンクの題名から読み取れるもの
- A009は、具体例を数えてから指摘する。差し替えられる仕組み（インターフェース、
  基底、戦略、プラグイン）に対して、本文が挙げている具体例が1つだけのときに限る。
  契約（type: contract）が境界の約束を定めることは、使う側が1つでも対象外である
- A008・A009は断定しない。依存先の本文は渡していないので、根拠が依存先にだけ
  あることがある。「根拠が本文から辿れない」と書き、根拠のノードを本文から指すか、
  先送りとして書き直すことを提案する
"""


@dataclass
class Finding:
    """1件の指摘。"""

    node_id: str
    rel: str
    code: str
    quote: str
    message: str
    suggestion: str

    def format(self) -> str:
        head = f"{self.code} {self.rel}: {self.message}"
        body = f"\n      引用: {self.quote}" if self.quote else ""
        fix = f"\n      提案: {self.suggestion}" if self.suggestion else ""
        return head + body + fix

    def to_dict(self) -> dict:
        return {
            "node": self.node_id,
            "location": self.rel,
            "code": self.code,
            "quote": self.quote,
            "message": self.message,
            "suggestion": self.suggestion,
        }


class ReviewError(Exception):
    """APIの呼び出しに失敗した。"""


def call_api(payload: dict, api_key: str) -> dict:
    """Claude APIを1回呼ぶ。テストでは、この関数を差し替える。"""
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise ReviewError(f"APIが{error.code}を返した: {detail}") from error
    except urllib.error.URLError as error:
        raise ReviewError(f"APIに接続できない: {error.reason}") from error
    except TimeoutError as error:
        # 応答の読み込み中のタイムアウトは、URLErrorに包まれずにここへ来る
        raise ReviewError(f"APIの応答が{TIMEOUT_SECONDS}秒で返らない") from error
    ensure_complete(data)
    return data


def ensure_complete(data: dict) -> None:
    """応答が最後まで返っていなければ、ReviewErrorにする。

    途中で切れた応答や断った応答からは、指摘を読めない。そのまま渡すと、
    `parse_findings`が空の一覧を返し、「指摘なし」と区別が付かなくなる。
    """
    reason = data.get("stop_reason")
    if reason == "max_tokens":
        raise ReviewError(f"応答がmax_tokens（{MAX_TOKENS}）で切れた")
    if reason == "refusal":
        raise ReviewError("モデルが応答を断った（stop_reason: refusal）")


def vocabulary_for(graph: Graph, node: Node) -> list[tuple[str, str, str, list[str]]]:
    """全ドメインノードの用語を、`(ノードid, 用語, 意味, 使わない語)`で集める。

    **依存先には絞らない。** G013は依存の向きにしか届かず、上位層と兄弟ノードの
    揺れが見えない。そこを見てもらうのがA003なので、依存先の語だけを渡しても
    その揺れは見つからない（上流の大会のノードが、兄弟の「棄権」を「辞退」と書いていた例がある）。
    渡す量は、いちばん多い派生で約4,000字である（1.20.0）。
    """
    vocabulary: list[tuple[str, str, str, list[str]]] = []
    for owner in graph.sorted_nodes():
        if owner.type not in schema.TERM_TYPES:
            continue
        avoided: dict[str, list[str]] = {}
        for word, (term, _note) in forbidden_terms(owner.body).items():
            avoided.setdefault(term, []).append(word)
        for row in term_rows(owner.body):
            term = row.get(schema.TERM_COLUMN, "")
            meaning = row.get(schema.TERM_MEANING_COLUMN, "")
            vocabulary.append((owner.id, term, meaning, avoided.get(term, [])))
    return vocabulary


def build_prompt(graph: Graph, node: Node) -> list[dict]:
    """1ノード分の入力を、テキストのブロックの並びで組み立てる。

    用語の一覧は、同じ実行のどのノードでも同じなので、先頭のブロックに置いて
    キャッシュの区切りを付ける。2つ目以降のノードでは、システムプロンプトと
    用語の一覧をキャッシュから読む。ノードごとに変わる部分は、その後ろに置く。
    """
    blocks: list[dict] = []

    vocabulary = vocabulary_for(graph, node)
    if vocabulary:
        rows = "\n".join(
            f"- {term}（{owner_id}）: {meaning}"
            + (f"。使わない語: {'、'.join(avoided)}" if avoided else "")
            for owner_id, term, meaning, avoided in vocabulary
        )
        blocks.append(
            {
                "type": "text",
                "text": f"# ドメインの用語（全ドメインノード）\n\n{rows}",
                "cache_control": {"type": "ephemeral"},
            }
        )

    parts = [
        f"# 対象ノード\n\nid: {node.id}\ntype: {node.type}\ntitle: {node.title}",
    ]

    wanted = schema.REQUIRED_SECTIONS.get(node.type, ())
    if wanted:
        parts.append(
            "この種別の文書に期待される節: " + " / ".join(wanted) + "\n"
            "節の有無は別の検査が見ているので、指摘しないこと。"
        )

    parts.append(f"# 本文\n\n{node.body.strip()}")
    blocks.append({"type": "text", "text": "\n\n".join(parts)})
    return blocks


def parse_findings(node: Node, data: dict) -> list[Finding]:
    """APIの応答から、指摘を取り出す。読めない応答は、何も言わずに捨てる。"""
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []

    findings = []
    for raw in parsed.get("findings", []):
        code = str(raw.get("code", "")).strip()
        if code not in FINDING_CODES:
            continue
        findings.append(
            Finding(
                node_id=node.id,
                rel=node.rel,
                code=code,
                quote=str(raw.get("quote", "")).strip(),
                message=str(raw.get("message", "")).strip(),
                suggestion=str(raw.get("suggestion", "")).strip(),
            )
        )
    return findings


def review_node(
    graph: Graph,
    node: Node,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    transport=call_api,
) -> list[Finding]:
    """1ノードをレビューする。`transport`を差し替えれば、通信しない。"""
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_prompt(graph, node)}],
        "output_config": {"format": {"type": "json_schema", "schema": FINDINGS_SCHEMA}},
    }
    return parse_findings(node, transport(payload, api_key))


def select_nodes(graph: Graph, *, limit: int) -> list[Node]:
    """レビューの対象を選ぶ。費用がかかるので、既定では全件は送らない。"""
    targets = [n for n in graph.sorted_nodes() if n.type != "index" and n.body.strip()]
    return targets[:limit] if limit > 0 else targets


def api_key_from_env() -> str | None:
    key = (os.environ.get(API_KEY_ENV) or "").strip()
    return key or None


USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def add_usage(totals: dict[str, int], data: dict) -> None:
    """応答の`usage`を`totals`に足す。費用とキャッシュの効き方を見るために使う。"""
    usage = data.get("usage") or {}
    for field in USAGE_FIELDS:
        totals[field] = totals.get(field, 0) + int(usage.get(field) or 0)


def format_usage(totals: dict[str, int]) -> str:
    return "、".join(f"{field} {totals.get(field, 0)}" for field in USAGE_FIELDS)
