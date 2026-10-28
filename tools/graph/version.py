"""テンプレートのバージョン。

このファイルは共通ファイルなので、`make update`でテンプレートを
取り込むと自動的に更新される。マージの前は自分のバージョン、マージの後はテンプレートのバージョンになる。

**`schema.py`には置かない。** プロジェクトは語彙もしきい値も`graph.toml`で変えるので、
`schema.py`は書き換えない。それでも`schema.py`を手で直した派生では、バージョンを混ぜておくと、
マージのたびに競合する。

変更の内容と移行手順は、TEMPLATE_CHANGELOG.mdにある。
"""

from __future__ import annotations

TEMPLATE_VERSION = "1.57.1"

# 動作を保証するPythonの下限。**動かしている場所は、すべて3.12に揃っている。**
# 開発機・CI・本番のホスト（deadsnakesのpython3.12で作ったvenv）のいずれも3.12で、
# 幅を持たせる理由が無くなったので、実際に回しているバージョンを、そのまま下限にする。
#
# **これより古いバージョンは、誰も試していない。** 3.11で動くかは分からない、と言うのが正しい。
# 上げるときは、次の3つを揃える。ずれたら、test_python_floorが落ちる。
#   1. この定数
#   2. .github/workflows/graph-check.ymlのpython-version
#   3. READMEの冒頭にある「Python 3.12+」の記載
MIN_PYTHON = "3.12"
