---
id: META-01
type: meta
title: グラフの規約
status: stable
tags: [meta, rules]
related:
  - META-02
---

# グラフの規約

設計文書をグラフとして扱うための規約。**すべて `python -m tools.graph check` で機械検証できる**
形にしてある。ルール ID（G0xx）は検証結果に必ず出るので、エラーが出たらここを引く。

## 1. ノード

- 1 つの Markdown ファイル = 1 ノード。
- 先頭に必ずフロントマターを置く。

```yaml
---
id: UC-01              # 必須。型ごとの接頭辞つき
type: usecase          # 必須。node-types.md の語彙
title: 予約を確定する    # 必須。一覧に出る名前
status: draft          # 必須。draft / review / stable / deprecated
tags: [booking]
depends_on:
  - DOM-01
related: []
---
```

フロントマターは YAML のサブセット（スカラー・インラインリスト・ブロックリスト）のみ。
ネストしたマップや複数行文字列は使わない。

## 2. エッジ

エッジは 2 種類の書き方がある。**意味を持つのはフロントマターの側だけ。**

| 書き方 | 例 | 検証対象 |
| --- | --- | --- |
| フロントマター（型つき） | `depends_on: [DOM-01]` | リンク切れ・層・循環・成熟度 |
| 本文の `[[ID]]` / 相対リンク | `[[DOM-01]]` | リンク切れのみ |

型つきエッジの種類:

| 種類 | 意味 | 制約 |
| --- | --- | --- |
| `refines` | 同種のより大きいノードを具体化する | 同じ `type` 同士のみ / 循環禁止 |
| `depends_on` | これが成立する前提となるノード | 層の逆流禁止 / 循環禁止 |
| `related` | 依存しないが併読すべきノード | 相互に書くこと（片側だけなら警告） |
| `supersedes` | この決定が置き換える過去の決定 | ADR 同士のみ |
| `decides` | この決定が影響を与えるノード | ADR 起点 |

## 3. 層の向き

依存は **抽象度の高い側へ向ける**。逆向きは `G007` で落ちる。

```
40-api  ──depends_on──▶ 30-usecases ──depends_on──▶ 20-domain ──depends_on──▶ 10-architecture
```

ドメインがユースケースを知っている状態は設計の破綻なので、規約ではなく検証で止める。
ADR（`50-adr/`）とメタ文書は横断的なので層ルールの対象外。

## 4. 到達可能性

すべてのノードは [IDX-ROOT](../index.md) から辿れること。新しい文書を作ったら、
その層の `index.md` の一覧ブロックに必ず載せる（`python -m tools.graph new` は自動で載せる）。

## 5. ルール一覧

| コード | 内容 | 直し方 |
| --- | --- | --- |
| `G001` | フロントマターが読めない / 必須キー不足 | `id` `type` `title` `status` を埋める |
| `G002` | `id` の重複 | 片方を採番し直す |
| `G003` | `id` 接頭辞・`type` 語彙・置き場所の不一致 | [META-02](./node-types.md) の表に合わせる |
| `G004` | リンク切れ | 参照先の `id` を直すか、ノードを作る |
| `G005` | ルート目次から到達できない | その層の `index.md` に載せる |
| `G006` | 依存の循環 | どちらかを共通の下位ノードに切り出す |
| `G007` | 層の逆流 | 依存の向きを反転させるか、下位層に概念を移す |
| `G008` | `refines` の種別不一致 | 同じ `type` 同士にする、または `depends_on` にする |
| `G009` | `status` 語彙違反 / stable が draft に依存（警告） | 依存先を固めるか、こちらを `review` に落とす |
| `G010` | `related` が片側だけ（警告） | 相手側にも `related` を書く |

## 6. 運用サイクル

1. `python -m tools.graph new --type usecase --id UC-02 --title "..."` でノードを起こす
2. 本文とフロントマターの `depends_on` を書く
3. `python -m tools.graph check` が通るまで直す
4. `python -m tools.graph sync` で各文書末尾の関連リンクを再生成する
5. コミット（CI でも 3 と 4 を検証する）

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

**related** — 依存はしないが併読すべきノード

- [META-02 ノード種別と層](./node-types.md)

**このノードを参照しているノード**

- (decides) [ADR-0001 設計文書をグラフとして管理する](../50-adr/adr-0001-graph-driven-docs.md)
- (related) [META-02 ノード種別と層](./node-types.md)

<!-- graph:auto:end -->
