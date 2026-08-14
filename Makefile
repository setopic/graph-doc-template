PYTHON ?= python

.PHONY: help check strict sync sync-check graph json stats all

help:
	@echo "check       グラフを検証する（エラーがあれば失敗）"
	@echo "strict      警告も失敗として扱う"
	@echo "sync        各文書末尾の関連ドキュメントを再生成する"
	@echo "sync-check  再生成が必要なら失敗する（CI 用）"
	@echo "graph       docs/graph.mmd を書き出す（Mermaid）"
	@echo "json        docs/graph.json を書き出す"
	@echo "stats       ノード数・エッジ数を表示する"
	@echo "all         check + sync + graph"

check:
	$(PYTHON) -m tools.graph check

strict:
	$(PYTHON) -m tools.graph check --strict

sync:
	$(PYTHON) -m tools.graph sync

sync-check:
	$(PYTHON) -m tools.graph sync --dry-run --check

graph:
	$(PYTHON) -m tools.graph render --format mermaid --out docs/graph.mmd

json:
	$(PYTHON) -m tools.graph render --format json --out docs/graph.json

stats:
	$(PYTHON) -m tools.graph stats

all: check sync graph
