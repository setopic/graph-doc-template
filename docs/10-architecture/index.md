---
id: IDX-ARCH
type: index
title: アーキテクチャ
status: stable
tags: [index]
---

# アーキテクチャ（層 10）

構成要素と責務、境界、技術選定の前提。**最も変わりにくい層**なので、
ここを変えるときは ADR を起票する。

書かないこと: 個別の画面、個別のエンドポイント、ドメインの詳細。

## ノード一覧

<!-- graph:children:start -->
- [ARCH-01 システム全体構成](./arch-01-system-overview.md)
- [ARCH-02 ワーカーの実行モデル](./arch-02-worker-execution-model.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type architecture --id ARCH-02 --title "..." --slug some-slug
```
