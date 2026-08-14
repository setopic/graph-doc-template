"""ドキュメント知識グラフの検証・可視化ツール。

外部依存なし。リポジトリルートで `python -m tools.graph check` を実行する。
"""

from .loader import load
from .model import Edge, Graph, Issue, Node
from .rules import check_all

__all__ = ["load", "check_all", "Graph", "Node", "Edge", "Issue"]
