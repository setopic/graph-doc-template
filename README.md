# graph-doc-template

**設計文書をグラフとして管理し、その整合性を CI で検証する**プロジェクトテンプレート。

1 文書 = 1 ノード、フロントマターの型つきリンク = エッジ。リンク切れ・孤立ノード・
循環依存・**層の逆流**を機械検証する。外部依存なし（Python 3.10+ の標準ライブラリのみ）。

## なぜ

設計文書は増えると必ず次の 3 つが起きる。

1. どこに何が書いてあるか分からなくなる
2. 上流（ドメイン）を変えたとき、下流（ユースケース・API）の追従漏れに気づけない
3. 人も AI も、文書間の前提関係を毎回読み直して推測する

目次を手で整備しても 2 と 3 は解決しない。**前提関係そのものを機械可読にして検証する**のが
このテンプレートの主張。詳しくは [ADR-0001](docs/50-adr/adr-0001-graph-driven-docs.md)。

## すぐ試す

```bash
python -m tools.graph check
```

```bash
python -m tools.graph stats
```

グラフを図にする（Mermaid）:

```bash
python -m tools.graph render --format mermaid --out docs/graph.mmd
```

## 構成

```
docs/
  index.md              グラフのルート。全ノードはここから辿れること
  00-meta/              規約とテンプレート（グラフの語彙そのもの）
    graph-rules.md      ルール ID G001〜G010 と直し方
    node-types.md       ノード種別・接頭辞・置き場所・層
    templates/          new コマンドが使う雛形（グラフには含めない）
  10-architecture/      層 10: 構成要素と責務、境界
  20-domain/            層 20: 概念・不変条件・用語
  30-usecases/          層 30: 誰が何をして何が起きるか
  40-api/               層 40: 境界の契約
  50-adr/               横断: 決定・理由・却下案
tools/graph/            検証・可視化・生成ツール（依存なし）
```

依存は必ず**上の層（数字の小さい側）へ**向ける。逆向きは `G007` で落ちる。

```
40-api ──▶ 30-usecases ──▶ 20-domain ──▶ 10-architecture
```

## コマンド

| コマンド | 用途 |
| --- | --- |
| `python -m tools.graph check` | 検証。エラーがあれば終了コード 1 |
| `python -m tools.graph check --strict` | 警告も失敗として扱う |
| `python -m tools.graph check --format json` | CI やエディタ連携向け |
| `python -m tools.graph sync` | 各文書末尾の「関連ドキュメント」を再生成 |
| `python -m tools.graph sync --dry-run --check` | 再生成が必要なら終了コード 1（CI 用） |
| `python -m tools.graph render --format mermaid\|json\|dot` | 図・データの書き出し |
| `python -m tools.graph new --type usecase --id UC-02 --title "..."` | 雛形からノードを起こす |
| `python -m tools.graph new --from <file>` | 1 行 1 ノードのファイルからまとめて起こす |
| `python -m tools.graph reset-samples` | 同梱のサンプルノードを一括で取り除く |
| `python -m tools.graph stats` | ノード数・エッジ数の集計 |

`make check` `make sync` `make graph` も同じことをする（Makefile 参照）。

## 新しいノードを作る

```bash
python -m tools.graph new --type usecase --id UC-02 --title "予約をキャンセルする" --slug cancel-booking
```

これは 3 つのことを同時にやる。

1. `docs/30-usecases/uc-02-cancel-booking.md` を雛形から作る
2. フロントマターの `id` / `type` / `title` / `status` / 日付を埋める
3. `docs/30-usecases/index.md` の一覧に登録する（＝孤立ノードにしない）

あとは本文と `depends_on` を書いて `check` を通す。

同じ type に複数の書式が要るときは `--template` で雛形を選ぶ。
`api` には汎用（既定）と HTTP 用の 2 つがある。

```bash
python -m tools.graph new --type api --template api-http --id API-02 --title "..."
```

立ち上げ時などで数が多いときは、1 行 1 ノードのファイルからまとめて作る。

```bash
python -m tools.graph new --from docs/00-meta/new-nodes.txt
```

```
# type | id | title | slug | status | template
usecase | UC-02  | 予約をキャンセルする | cancel-booking
api     | API-02 | キャンセル API      | cancel-api | draft | api-http
```

## 検証されること

| コード | 内容 |
| --- | --- |
| `G001` | フロントマターが読めない / 必須キー不足 |
| `G002` | `id` の重複 |
| `G003` | `id` 接頭辞・`type` 語彙・置き場所の不一致 |
| `G004` | リンク切れ（フロントマター・本文の `[[ID]]`・相対リンク） |
| `G005` | ルート目次から到達できない孤立ノード |
| `G006` | 依存の循環 |
| `G007` | 層の逆流 |
| `G008` | `refines` の種別不一致 |
| `G009` | `status` 語彙違反 / stable が draft に依存（警告） |
| `G010` | `related` が片側だけ（警告） |

コードブロック・コードスパン・HTML コメントの中は検査しない。規約文書や雛形に
記法の例を書いても落ちない。逆に、コメントアウトした参照はグラフに現れない。

**本文の `[[ID]]` はリンク切れしか見ない。** 層（`G007`）と循環（`G006`）の検査を受けるのは
フロントマターの型つきエッジだけ。前提は本文ではなく `depends_on` に書く
（詳細は [graph-rules.md](docs/00-meta/graph-rules.md) の「本文リンクは層と循環の検査を受けない」）。

## 自分のプロジェクトに合わせる

1. **サンプルを消す** — 同梱のサンプルノードを取り除く。

   ```bash
   python -m tools.graph reset-samples --yes
   ```

   `tags` に `sample` を持つノード（ARCH-01 / ARCH-02 / DOM-01 / UC-01 / API-01）を削除し、
   各 `index.md` の一覧からも外す。**他のノードからの参照は自動で消さない**ので、
   残った参照は `check` が `G004`（リンク切れ）として指す。それを見て直す

2. **ADR-0001 を残すか決める** — この進め方自体を採用するなら残す。
   残す場合、サンプル削除で切れた `decides` の参照を実プロジェクトのノードに張り替える

3. **表紙を書き換える** — この 3 つはテンプレートの説明のままなので、
   プロジェクトの説明に差し替える

   | ファイル | 何を書くか |
   | --- | --- |
   | `README.md` | プロジェクトの目的、読む順番、未確定なものの一覧 |
   | `CLAUDE.md` | エージェント向けの前提。グラフ規約の部分はそのまま使える |
   | `docs/index.md` | グラフのルート。層の表は流用でき、冒頭にプロジェクトの説明を足す |

4. **語彙を決める** — `tools/graph/schema.py` の `NODE_TYPES` と `EDGE_KINDS` を編集。
   層を増やす／減らす、ノード種別を足すのはここだけで済む。
   **まず 1〜3 で書き始めてみて、層が合わないと分かってから触るのでよい**

5. **表を合わせる** — 4 を変えたら `docs/00-meta/node-types.md` の表を一致させる

6. **雛形を直す** — `docs/00-meta/templates/*.md` を自分たちの書式にする

## AI エージェントと使う

[CLAUDE.md](CLAUDE.md) にエージェント向けの作業手順を書いてある。要点は 2 つ。

- 文脈は**全文書ではなく、対象ノードとその近傍**を渡す。`render --format json` が近傍の取得に使える
- 生成した文書は必ず `check` に通す。通らないものはマージしない

## CI

`.github/workflows/graph-check.yml` が push / PR で `check` と `sync --dry-run --check` を回す。
GitHub 以外を使うなら、この 2 コマンドを同等のジョブに移すだけでよい。

## ライセンス

[MIT](LICENSE)。複製して自分のプロジェクトの土台にすることを想定している。
