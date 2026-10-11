"""docs/*.html の自動生成ブロックを作る生成器の集まり。

scripts/gen-docs.py から import される。モジュールを import すると、その中の
`@generator("名前")` が登録される。テーマごとにファイルを分けてある:

    common.py   登録の仕組み・HTML の部品・ファイルの読み取り
    md.py       CLAUDE.md の一部を HTML にする小さな Markdown 変換器
    site.py     ナビ・目次・ページ一覧・スクリプト一覧・AI ツール一覧・CLAUDE.md の節
    build.py    ビルドターゲット・ビルドコマンド・west のモジュール
    keymap.py   レイヤー図・キー位置番号・コンボ・エンコーダの割り当て
    shield.py   ピン配置・エンコーダ・ポインタ・input-processors・Kconfig・現在値
    issues.py   既知の課題が残っているかの判定
"""
from . import build, issues, keymap, shield, site  # noqa: F401  （import で生成器が登録される）
from .common import DOCS, GENERATORS, REPO, Page, rel

__all__ = ["DOCS", "GENERATORS", "REPO", "Page", "rel"]
