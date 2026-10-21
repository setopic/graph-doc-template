---
id: META-08
type: meta
title: テンプレートの更新を取り込む
status: stable
tags: [meta, flow]
related:
  - META-01
  - META-07
---

# テンプレートの更新を取り込む

テンプレートから作ったプロジェクトに、あとからテンプレート側の改善を反映する手順を決める。**ファイルをコピーしない。** コピーすると、どれが共通のファイルかを毎回判断することになり、削除も伝わらず、いずれ気づかないうちにテンプレートとずれていく。

この文書は共通ファイルなので、取り込みで手順も一緒に更新される。`README.md`は`merge=ours`で取り込みが届かないため、手順を置かない。上に重ねた層のテンプレートも、この文書を指し、手順をREADMEに写さない。

## 1. 最初に一度だけ

"Use this template"で作ったリポジトリは、テンプレートと履歴を共有していない。そのままマージすると、共通の祖先が無いので、共有ファイルまで軒並み競合する。先に共有ファイルをテンプレートと一致させ、競合するところを無くしてから繋ぐ。

1. 共有ファイルをテンプレートの内容で上書きして、コミットする。対象は`tools/`、`tests/`、`docs/00-meta/`、`.claude/skills/`、`CLAUDE.md`、`TEMPLATE_CHANGELOG.md`、`Makefile`、`.github/`、`.gitattributes`、`.gitignore`、`LICENSE`である。上の層のテンプレートから作ったなら、その層が足した共通ファイルも対象にする。どれを足したかは、その層のREADMEにある。`README.md`・`docs/index.md`・各`index.md`・ノード本体は、プロジェクト固有なので対象外である

2. upstreamを追加する。URLは、作るときに使ったテンプレートのリポジトリにする。

   ```bash
   git remote add template https://github.com/setopic/graph-doc-template.git
   ```

3. 初回だけ、`--allow-unrelated-histories`を付けて取り込む。

   ```bash
   make update UPDATE_ARGS=--allow-unrelated-histories
   ```

   `make update`は、`.gitattributes`の`merge=ours`を効かせて取り込む。`merge=ours`のドライバは、この取り込みのときだけ効かせる。クローンに常設すると、作業ブランチどうしのマージでも`merge=ours`が効き、相手の変更が何も言わずに落ちる。

4. 以前の`make setup`でドライバを常設したクローンなら、設定を外す。設定が無ければ何もしないので、何度実行してもよい。

   ```bash
   make setup
   ```

5. issueの型が使うラベルを作る（[META-07](issue-pr-flow.md)）。

   ```bash
   gh label clone setopic/graph-doc-template
   ```

   ラベルの実体が無いと、`labels:`の指定は何も言わずに無視される。issueは立つが、ラベルが付かないまま残る。`gh`の組み込みのコマンドで、すでにあるラベルは飛ばすので、何度実行してもよい。

## 2. 取り込む

まず、テンプレートとの差を調べる。このコマンドは読み取りだけで、何も書き込まない。

```bash
python -m tools.graph upgrade
```

テンプレートより遅れていれば、その間の変更履歴と、変更されるファイルの一覧が出る。**majorが上がっていれば、移行作業が要る。** マージしただけでは動かなくなるので、表示された移行手順を先に読む。

取り込みの手順は次のとおりである。

```bash
make update
```

`make update`は、マージコミットのメッセージを「テンプレートの<版>を取り込む」にする。版は`python -m tools.graph upgrade --label`が作り、遅れている層の版を下の層から並べる（「3. テンプレートの層」）。競合したときも、解いたあとの`git commit`で同じメッセージが使われる。

```bash
python -m tools.graph reset-samples --yes
```

**取り込む側が、自分でもサンプルノードを配るテンプレート（graph-project-templateなど）なら、`reset-samples`は回さない。** 配るはずのサンプルノードが消え、目次からも外れる。

```bash
python -m tools.graph check && python -m tools.graph sync
```

取り込むときに知っておくことは、次のとおりである。

| 知っておくこと | 説明 |
| --- | --- |
| サンプルノードは毎回追加される | マージは、テンプレート側にしかないファイルをそのまま足す。そのため、`reset-samples`で消すところまでが1セットである。省くと、プロジェクト側の同じidと衝突して`G002`が残る。サンプルノードを配るテンプレートは例外で、`reset-samples`を回さない |
| `README.md`と`docs/index.md`は競合しない | `make update`で取り込めば、`.gitattributes`の`merge=ours`で、プロジェクト側が優先される。`git merge`を直接使うと`merge=ours`が効かず、競合する。テンプレート側の改善を取り込みたいときは、`git diff HEAD template/main -- README.md`で差分を見て、手で反映する |
| テンプレートがサンプルノードを変更したときだけ、modify/deleteの競合が出る | `git rm <path>`で解決してよい |
| 初回のマージだけ`--allow-unrelated-histories`が要る | GitHubの"Use this template"は、履歴を引き継がないため |

## 3. テンプレートの層

テンプレートは層を重ねられる。graph-project-templateは、graph-doc-templateの上に重ねた層である。版と変更履歴は層ごとにあり、`upgrade`は層ごとに比べる。

| 層 | 版 | 変更履歴 | 取り込みの版の書き方 |
| --- | --- | --- | --- |
| graph-doc-template | `tools/graph/version.py`の`TEMPLATE_VERSION` | `TEMPLATE_CHANGELOG.md` | `1.38.0` |
| 上の層 | `tools/graph/layers/<層の名前>.toml`の`version` | 同じファイルの`changelog`が指すもの | `<label>-<版>`（`project-0.14.0`など） |

両方の層が遅れていれば、取り込みの版は`1.38.0-project-0.14.0`になる。上の層を作るときは、`tools/graph/layers/<層の名前>.toml`を1つ置く。層ごとにファイルの名前が違うので、層を重ねても取り込みで競合しない。

```toml
name = "graph-project-template"
label = "project"
below = "graph-doc-template"
version = "0.14.0"
changelog = "PROJECT_TEMPLATE_CHANGELOG.md"
repository = "https://github.com/setopic/graph-project-template.git"
```

`label`は、取り込みの版で層を見分ける名前で、英小文字と数字で書く。`below`には1つ下の層の`name`を書く。リモート`template`が無いとき、`upgrade`はいちばん上の層の`repository`を案内する。

上の層のREADMEには、その層が足したもの（共通ファイル・サンプルノード・手順の例外）の説明と、この文書へのリンクだけを書く。取り込みの手順を写すと、写した側が古くなる。

## 4. 取り込みのPR

取り込みをPRにするときは、本文の「対応するノード」の節に、行の頭から`なし`と書く（`- なし`のように箇条書きにしてもよい）。取り込みには対応するノードが無いからである。`gh pr create --body`で本文を渡すと、PRの雛形を通らず、この節が入らない。節が無いと、CIの`refs`が落ちる。

```markdown
## 対応するノード

なし（テンプレートの取り込みのみ）
```

取り込みのブランチ名は`chore/template-<版>`にし（版は`make update`のメッセージと同じもの）、PRの題は`chore: テンプレートの<版>を取り込む`のように書く。CIの`names`が、ブランチ名とPRの題を確かめる（[META-07](issue-pr-flow.md)）。取り込みに入る上流のコミットは確かめない。

`merge=ours`のファイルに手で反映するものは、取り込みのPRとは別のPRにする（[META-07](issue-pr-flow.md)の「1つのPRには、1つの変更だけを入れる」）。

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

`related`: 依存はしないが、一緒に読むべきノード

- [META-01 グラフの規約](./graph-rules.md)
- [META-07 issueとPRの流れ](./issue-pr-flow.md)

このノードを参照しているノード

- (related) [META-01 グラフの規約](./graph-rules.md)
- (related) [META-07 issueとPRの流れ](./issue-pr-flow.md)

<!-- graph:auto:end -->
