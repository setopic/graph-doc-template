---
id: IDX-ARCH
type: index
title: アーキテクチャ
status: stable
tags: [index]
---

# アーキテクチャ（層 10）

構成要素と責務、境界、技術選定の前提を書く。最も変わりにくい層なので、
ここを変えるときはADRを起こす。

個別の画面、個別のエンドポイント、ドメインの詳細は、この層には書かない。

## ノード一覧

<!-- graph:children:start -->
- [ARCH-01 システム全体構成](./arch-01-sample-system-overview.md)
- [ARCH-02 ワーカーの実行モデル](./arch-02-sample-worker-execution-model.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type architecture --id ARCH-02 --title "..." --slug some-slug
```
