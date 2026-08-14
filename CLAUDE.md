# CLAUDE.md

このリポジトリの設計文書は**グラフ**として管理されている。文書を書き換える前に
[docs/00-meta/graph-rules.md](docs/00-meta/graph-rules.md) を読むこと。

## 絶対に守ること

1. **文書を新規作成するときは手でファイルを置かない。** 必ず次を使う。

   ```bash
   python -m tools.graph new --type <type> --id <ID> --title "..." --slug <ascii-slug>
   ```

   手で置くと採番・配置・目次登録のどれかを必ず落とす。
   数が多いときは `--from <file>`（`type | id | title | slug` 形式）でまとめて作る。
   `contract` を HTTP で書くなら `--template contract-http` を付ける。

2. **文書を編集したら検証する。** 通らない状態で「完了」と報告しない。

   ```bash
   python -m tools.graph check
   ```

3. **リンクを増やしたら sync する。** ノードやエッジを増減したら README の図も再生成する。

   ```bash
   python -m tools.graph sync
   ```

   ```bash
   python -m tools.graph render --format mermaid --into README.md
   ```

   どちらも CI で最新かを検証している。忘れると落ちる。

4. **`<!-- graph:auto:start -->` 〜 `<!-- graph:auto:end -->` を手で編集しない。**
   `sync` が上書きする。ここを直したいときは、元になっているフロントマターの側を直す。

5. **依存の向きを逆にしない。** `40-contracts → 30-usecases → 20-domain → 10-architecture`。
   ドメイン文書がユースケースを参照したくなったら、それは概念の切り出しが足りない合図。
   参照を足すのではなく、概念をドメイン側に定義する。

## 文書を書くときの前提

- **前提は本文ではなくフロントマターに書く。** 本文の `[[ID]]` はリンク切れしか検査されず、
  層の逆流（`G007`）も循環（`G006`）もすり抜ける。「これがないと成立しない」ものは
  必ず `depends_on` に入れる。本文リンクは道案内に留める
- **`refines` は分割したときだけ使う。** 同じ type 同士では `depends_on` と両方書けてしまうが、
  `refines` は「もともと 1 つの文書だったものを分けた」場合に限る。
  別の概念への前提なら `depends_on`。迷ったら `depends_on` を選ぶ
- `depends_on` に挙げたノードの**用語だけ**を使って書く。挙げていない概念を持ち出さない
- ユースケースの事後条件は、ドメインノードで定義された言葉で書く
- 契約ノードは必ず対応するユースケースを `depends_on` に持つ。持てないなら
  ユースケースが未定義なので、先にそちらを書く
- 決定を変えるときは既存文書を書き換えず、新しい ADR を起こして `supersedes` で繋ぐ

## 文脈の取り方

全文書を読み込まない。対象ノードとその近傍だけを読む。

```bash
python -m tools.graph render --format json --focus UC-01 --depth 1
```

これが「前提（`depends_on` 先）」と「影響範囲（そのノードを指している側）」の
両方を含んだ最小の集合になる。返ってきた `nodes` のファイルだけを読む。

範囲が足りなければ `--depth 2` に広げる。全体を見たいときだけ `--focus` を外す。

```bash
python -m tools.graph render --format json --out docs/graph.json
```

## 変更の影響範囲を確かめる

ノードを変更したら、そのノードを `depends_on` している側が追従不要かを確認する。
各文書末尾の「このノードを参照しているノード」がその一覧になっている
（`sync` が生成しているので手で数えない）。

図で見るなら次を使う。

```bash
python -m tools.graph render --format mermaid --focus DOM-01 --depth 1
```

## よくある落とし方

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `G005` が出る | `index.md` の一覧ブロックに登録していない | `<!-- graph:children:start -->` の中に追記 |
| `G004` が出る | `id` の綴り間違い、または参照先が未作成 | `stats` で存在する id を確認 |
| `G007` が出る | 依存の向きが逆 | 概念を下位層に移す。向きだけ変えて意味が壊れないか確認する |
| `G001` が出る | フロントマターにネストしたマップを書いた | サブセット記法のみ。`graph-rules.md` の例に合わせる |
| `G011` が出る | `draft` のまま放置されている | 確定させるか削除する。意図的に寝かせているなら理由を本文に書く |
| `G012` が出る | 1 ノードに参照が集まりすぎ | 概念が混ざっていないか点検する。中心的な語彙なら放置してよい |

## ツールを直すとき

- 語彙（ノード種別・エッジ種別・層）は `tools/graph/schema.py` に集約されている。
  ここを変えたら `docs/00-meta/node-types.md` の表も必ず合わせる
- 検証ルールは `tools/graph/rules.py` に 1 ルール 1 関数で並んでいる。
  ルールを足したら `RULE_INDEX` と `graph-rules.md` の一覧の両方に追記する
- 外部依存を足さない。標準ライブラリだけで動くことがこのツールの前提
