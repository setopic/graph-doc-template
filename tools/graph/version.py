"""テンプレートの版。

派生プロジェクトはこのファイルを共有しているので、`git merge template/main`を
すると自動的に更新される。マージの前は自分の版、マージの後はテンプレートの版になる。

**`schema.py`には置かない。** `schema.py`は、プロジェクトが語彙を調整するために
書き換える前提のファイルなので、版を混ぜると、マージのたびに競合する。

変更の内容と移行手順は、TEMPLATE_CHANGELOG.mdにある。
"""

from __future__ import annotations

TEMPLATE_VERSION = "1.24.4"

# 動作を保証するPythonの下限。**動かしている場所は、すべて3.12に揃っている。**
# 開発機・CI・本番のホスト（deadsnakesのpython3.12で作ったvenv）のいずれも3.12で、
# 幅を持たせる理由が無くなったので、実際に回している版を、そのまま下限にする。
#
# **これより古い版は、誰も試していない。** 3.11で動くかは分からない、と言うのが正しい。
# 上げるときは、次の3つを揃える。ずれたら、test_python_floorが落ちる。
#   1. この定数
#   2. .github/workflows/graph-check.ymlのpython-version
#   3. READMEの冒頭にある「Python 3.12+」の記載
MIN_PYTHON = "3.12"
