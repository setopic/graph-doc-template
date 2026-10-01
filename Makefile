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

.PHONY: help setup update check strict sync sync-check linkify linkify-check graph json readme readme-check stats all

help:
	@echo "setup         以前のsetupが常設したmerge=oursドライバの設定を外す（何度実行してもよい）"
	@echo "update        テンプレートを取り込む（このときだけmerge=oursドライバを効かせる）"
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

# テンプレートを取り込む。.gitattributesのmerge=oursは、プロジェクト側の内容を残すための指定で、
# このドライバを効かせたマージでだけ働く。ドライバは、この取り込みのときだけ-cで効かせる。
#
# 以前はsetupでドライバをクローンに常設していた。常設すると、テンプレートの取り込み以外の
# マージ（作業ブランチどうしのマージ）でもmerge=oursが効き、相手の変更が何も言わずに落ちる
# （setopic/graph-doc-template#36）。
#
# 初回だけは、履歴を共有していないので、引数を足す。
#   make update UPDATE_ARGS=--allow-unrelated-histories
UPDATE_ARGS ?=
update:
	git fetch template
	git -c merge.ours.driver=true merge template/main $(UPDATE_ARGS)

# 以前のsetupが常設したドライバの設定を外す。設定が無ければ何もしない。何度実行してもよい。
# 外したあとのマージは、merge=oursのファイルも通常のマージになる。両側が変えていれば、
# 何も言わずに落ちる代わりに、競合として表に出る。
setup:
	@git config --unset merge.ours.driver || true
	@echo "merge=oursドライバの常設を外した。テンプレートの取り込みは make update で行う。"

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
