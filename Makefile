PYTHON ?= python

# リポジトリ固有の設定があれば読む（無くてもよい）。
# README の図が GitHub の描画上限（エッジ 500 本 / G018）に近づいたら、
# **そのリポジトリの graph.mk にだけ**次の 1 行を置く。
#
#     README_GRAPH_ARGS = --aggregate
#
# テンプレートは graph.mk を配らない。だから取り込み（git merge template/main）
# のたびに競合しないし、リポジトリごとに図の形を選べる。
-include graph.mk

# README の図に足す引数。既定は無し（全ノードをそのまま描く）。
README_GRAPH_ARGS ?=

.PHONY: help setup check strict sync sync-check linkify linkify-check graph json readme readme-check stats all

help:
	@echo "setup         クローンごとに要る設定を入れる（何度実行してもよい）"
	@echo "check         グラフを検証する（エラーがあれば失敗）"
	@echo "strict        警告も失敗として扱う"
	@echo "sync          各文書末尾の関連ドキュメントを再生成する"
	@echo "sync-check    再生成が必要なら失敗する（CI 用）"
	@echo "linkify       本文の [[ID]] を相対リンクに直す"
	@echo "linkify-check 直す必要があれば失敗する（CI 用）"
	@echo "graph         docs/graph.mmd を書き出す（Mermaid）"
	@echo "json          docs/graph.json を書き出す"
	@echo "readme        README の図を再生成する"
	@echo "readme-check  README の図が古ければ失敗する（CI 用）"
	@echo "stats         ノード数・エッジ数を表示する"
	@echo "all           check + sync + linkify + readme"

# **クローンごとに要る。** .gitattributes の merge=ours は、このドライバが
# 無効なクローンでは git が黙って無視し、通常の 3 方向マージに落ちる。
# 警告は出ないので、保護が外れていること自体が見えない。
# 冪等なので、取り込みの前に毎回実行してよい。
setup:
	@git config merge.ours.driver true
	@echo "merge=ours ドライバを有効にした。.gitattributes の保護が効く。"

check:
	$(PYTHON) -m tools.graph check

strict:
	$(PYTHON) -m tools.graph check --strict

sync:
	$(PYTHON) -m tools.graph sync

sync-check:
	$(PYTHON) -m tools.graph sync --check

linkify:
	$(PYTHON) -m tools.graph linkify

linkify-check:
	$(PYTHON) -m tools.graph linkify --check

readme:
	$(PYTHON) -m tools.graph render --format mermaid --into README.md $(README_GRAPH_ARGS)

readme-check:
	$(PYTHON) -m tools.graph render --format mermaid --into README.md --check $(README_GRAPH_ARGS)

graph:
	$(PYTHON) -m tools.graph render --format mermaid --out docs/graph.mmd

json:
	$(PYTHON) -m tools.graph render --format json --out docs/graph.json

stats:
	$(PYTHON) -m tools.graph stats

all: check sync linkify readme
