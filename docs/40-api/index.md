---
id: IDX-API
type: index
title: API / 契約
status: stable
tags: [index]
---

# API / 契約（層 40）

境界をまたぐ通信の契約。**実装の入口であり、ここが最も具体的な層。**

`depends_on` には対応するユースケースを必ず挙げる。挙げられない API は、
仕様が決まっていないか、ユースケースとして書かれていないかのどちらか。

## ノード一覧

<!-- graph:children:start -->
- [API-01 予約確定エンドポイント](./api-01-confirm-booking.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type api --id API-02 --title "..." --slug some-slug
```
