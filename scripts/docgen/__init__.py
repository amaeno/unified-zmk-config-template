"""docs/*.html の自動生成ブロックを作る生成器の集まり。

scripts/gen-docs.py から import される。モジュールを import すると、その中の
`@generator("名前")` が登録される。テーマごとにファイルを分けてある:

    common.py     登録の仕組み・HTML の部品・ファイルの読み取り
    md.py         CLAUDE.md の一部を HTML にする小さな Markdown 変換器
    site.py       ナビ・目次・ページ一覧・スクリプト一覧・AI ツール一覧・CLAUDE.md の節・改善メモ
    build.py      ビルドターゲット・ビルドコマンド・west のモジュール
    keymap.py     レイヤー図・キー位置番号・コンボ・エンコーダの割り当て
    shield.py     ピン配置・エンコーダ・ポインタ・input-processors・Kconfig・現在値
    issues.py     既知の課題が残っているかの判定
    reference.py  ZMK の調査用コピー（.zmk-ref/）から: 使っている版・behavior の一覧
    history.py    変更履歴（git の履歴から）
    search.py     資料の検索索引（docs/assets/search-index.js）。生成ブロックではなく別ファイル
"""
from . import build, history, issues, keymap, reference, shield, site  # noqa: F401  （import で生成器が登録される）
from .common import DOCS, GENERATORS, REPO, VOLATILE, Page, SourceMissing, rel
from .search import build_index

__all__ = ["DOCS", "GENERATORS", "REPO", "VOLATILE", "Page", "SourceMissing", "build_index", "rel"]
