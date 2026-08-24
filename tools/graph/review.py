"""本文の質を AI に見てもらう（`graph review`）。

**`check` とは性質が違う。** `check` の G001〜G014 は同じ入力なら同じ結果が出て、
CI がそれを強制する。ここで出る指摘は**再現しない**。だからコードの名前空間を
`A001`〜 に分け、CI では回さず、終了コードも常に 0 にしてある。

外部パッケージは使わない。標準ライブラリの `urllib` で API を叩く。
**ただしネットワークには出る。** これはこのリポジトリで唯一の例外で、
`check` は今までどおりオフラインで完結する。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import schema
from .model import Graph, Node
from .rules import forbidden_terms, sections

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_LIMIT = 10
MAX_TOKENS = 2000
TIMEOUT_SECONDS = 120

API_KEY_ENV = "ANTHROPIC_API_KEY"

# 指摘コード。G 系とは別の名前空間にする（再現しないため）。
FINDING_CODES: dict[str, str] = {
    "A001": "曖昧表現",
    "A002": "冗長表現",
    "A003": "用語の不統一（G013 が届かない範囲）",
    "A004": "必須説明の欠落・粒度の不揃い",
    "A005": "「前提 → 本文 → まとめ」の構造が成立していない",
    "A006": "このノードが何を説明するものか不明瞭",
}

_CODE_LIST = "\n".join(f"- {code}: {desc}" for code, desc in FINDING_CODES.items())

SYSTEM_PROMPT = f"""あなたは設計文書のレビュアーです。日本語の Markdown 文書を読み、
文章の質だけを指摘してください。

指摘できるのは次のコードだけです。

{_CODE_LIST}

守ること:

- **構造の誤り（リンク切れ、依存の向き、必須の節の欠落）は指摘しない。**
  それらは別の検査が機械的に見ており、あなたの担当ではない
- 内容の正しさを疑わない。**書かれている事実は正しいものとして扱う**
- 好みの問題を指摘しない。**直さなくても通じる**なら指摘しない
- 指摘が無ければ空の配列を返す。**無理に見つけない**

次の JSON だけを返してください。前後に説明を書かないこと。

{{"findings": [{{"code": "A001", "quote": "本文からの短い引用", "message": "何が問題か", "suggestion": "どう直すか"}}]}}
"""


@dataclass
class Finding:
    """1 件の指摘。"""

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
    """API 呼び出しに失敗した。"""


def call_api(payload: dict, api_key: str) -> dict:
    """Claude API を 1 回叩く。**テストではこの関数を差し替える。**"""
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
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise ReviewError(f"API が {error.code} を返しました: {detail}") from error
    except urllib.error.URLError as error:
        raise ReviewError(f"API に接続できません: {error.reason}") from error


def vocabulary_for(graph: Graph, node: Node) -> dict[str, tuple[str, str]]:
    """依存先が禁じている言い換えを集める。

    G013 は `depends_on` を辿って完全一致で見るが、届かない揺れがある
    （上位層、兄弟ノード）。**そこを人の目の代わりに見てもらう。**
    """
    terms: dict[str, tuple[str, str]] = {}
    for edge in node.out_edges("depends_on") + node.out_edges("refines"):
        target = graph.nodes.get(edge.dst)
        if target is not None:
            terms.update(forbidden_terms(target.body))
    return terms


def build_prompt(graph: Graph, node: Node) -> str:
    """1 ノード分の入力を組み立てる。"""
    parts = [
        f"# 対象ノード\n\nid: {node.id}\ntype: {node.type}\ntitle: {node.title}",
    ]

    wanted = schema.REQUIRED_SECTIONS.get(node.type, ())
    if wanted:
        parts.append(
            "この種別の文書に期待される節: " + " / ".join(wanted) + "\n"
            "**節の有無は別の検査が見ているので指摘しないこと。**"
        )

    terms = vocabulary_for(graph, node)
    if terms:
        rows = "\n".join(
            f"- {word}: 正しくは「{term}」{f'（{note}）' if note else ''}"
            for word, (term, note) in sorted(terms.items())
        )
        parts.append(f"# 依存先が禁じている言い換え\n\n{rows}")

    parts.append(f"# 本文\n\n{node.body.strip()}")
    return "\n\n".join(parts)


def parse_findings(node: Node, data: dict) -> list[Finding]:
    """API の応答から指摘を取り出す。**壊れた応答は黙って捨てる。**"""
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    text = text.strip()
    # モデルが ```json で包むことがある
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
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
    """1 ノードをレビューする。`transport` を差し替えれば通信しない。"""
    payload = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": build_prompt(graph, node)}],
    }
    return parse_findings(node, transport(payload, api_key))


def select_nodes(graph: Graph, *, limit: int) -> list[Node]:
    """レビュー対象を選ぶ。**既定では全件流さない**（費用がかかるため）。"""
    targets = [n for n in graph.sorted_nodes() if n.type != "index" and n.body.strip()]
    return targets[:limit] if limit > 0 else targets


def api_key_from_env() -> str | None:
    key = (os.environ.get(API_KEY_ENV) or "").strip()
    return key or None
