---
id: IDX-CON
type: index
title: 契約
status: stable
tags: [index]
---

# 契約（層 40）

**独立に変わりうる相手との取り決め。実装の入口であり、ここが最も具体的な層。**

HTTP の API に限らない。判定の基準は「片方だけが古いまま動きうるか」
（[META-02](../00-meta/node-types.md) の「契約か、アーキテクチャか」）。

| 契約の例 | ずれると何が壊れるか |
| --- | --- |
| HTTP エンドポイント | 呼び出し側のクライアント |
| CLI の引数・終了コード | それを叩くスクリプト |
| UI の操作（ボタン・フォーム） | 利用者の手順 |
| ファイル形式（CSV・JSON） | それを読む集計ツール、過去に保存したファイル |
| メッセージ・イベントの構造 | 受信側のワーカー |
| 設定ファイルのキー | 設定を書く運用者 |
| 配置パス・起動定義 | 起動の仕組み |

`depends_on` には対応するユースケースを必ず挙げる。挙げられない契約は、
仕様が決まっていないか、ユースケースとして書かれていないかのどちらか。

## ノード一覧

<!-- graph:children:start -->
- [CON-01 予約確定エンドポイント](./con-01-confirm-booking.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type contract --id CON-02 --title "..." --slug some-slug
```

HTTP の API を書くなら、専用の雛形を選ぶ。

```bash
python -m tools.graph new --type contract --template contract-http --id CON-02 --title "..."
```
