---
name: update-docs
description: 双掌 (sosho) の資料（docs/*.html）を書く・直すときの決まりごと。ページのひな形、使える CSS の部品、自動生成ブロックの扱い、生成器（scripts/docgen/）の足し方、文章の書き方、見た目の確かめ方。資料のページを足すとき、手書きの説明を直すとき、資料に新しい事実を載せるとき、生成器を足すときは、HTML を書き始める前に必ずこれを読むこと。
model: sonnet
---

# 双掌 (sosho) の資料の書き方

資料はユーザー本人が読むためのものです。**読みやすさを最優先**にし、AI もこれを事実の正本として読みます。

## 原則

- **仕様が変わったら、必ず同じコミットで資料を直す。** 挙動・設定値・キー割り当て・手順・AI ツールの使い方が変わったら、生成部分は `python3 scripts/gen-docs.py`、手書き部分はこの決まりに従って直す。資料が古いままの変更は残さない（資料は事実の正本なので、ずれると次の作業を誤らせるため）
- **同じ事実を 2 か所に書かない。** 書いた瞬間から食い違いが始まるため。CLAUDE.md や skills からは資料の節へリンクする
- **繰り返し変わる事実は手で書かない。** 設定値・ピン・ターゲット・キーの割り当てなどは生成器で作る。手書きは「なぜそうなっているか」「どう変えるか」の説明に使う
- **確かめた事実と推測を書き分ける。** ソースやドキュメントで確かめたら「ZMK のソースで確認」のように書き、確かめていないことは「未確認」と書く

## ページのひな形

新しいページは既存のページ（例: `docs/settings.html`）を複製して作り、`scripts/docgen/site.py` の `PAGES` に（ファイル名, ナビの表示名, 説明）を足します。生成し直すと、全ページのナビとトップのページ一覧に自動で出ます。

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ページ名 — 双掌 (sosho) カスタマイズ資料</title>
<meta name="description" content="1 行の説明">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="layout">
<!-- gen:nav -->
<!-- /gen:nav -->
<main>
<header class="page-head">
<h1>ページ名</h1>
<p class="lead">このページで分かること（1〜2 文）。</p>
</header>

<!-- gen:toc -->
<!-- /gen:toc -->

<section>
<h2 id="英小文字の-id">節の見出し</h2>
…
</section>
</main>
</div>
</body>
</html>
```

- `h2` には必ず `id` を付ける（目次・リンク・AI の Grep の目印になる）。`id` は一度決めたら変えない（CLAUDE.md や skills がリンクしているため）
- 目次は `h2` だけから作られる。細かい区切りは `h3`

## 使える部品（`docs/assets/style.css`）

| 部品 | 書き方 | 使いどころ |
|---|---|---|
| 注記 | `<aside class="callout note">`（`tip` / `warn` も） | 補足、うまいやり方、壊しやすい所の注意。最初に `<strong>見出し:</strong>` |
| 札 | `<span class="badge ok">ビルド不要</span>`（`build` / `warn` も） | 状態や区分を短く示す |
| 手順 | `<ol class="steps">` の `li` に `<p><strong>動詞。</strong> 説明</p>` | 順番に行う操作 |
| 表 | `<div class="table-wrap"><table>…</table></div>` | 必ず `table-wrap` で包む（狭い画面で横スクロールさせるため） |
| 事実の一覧 | `<dl class="facts">` | 項目と値の短い組 |
| 長い説明の一覧 | `<ul class="item-list">` | 表にすると列が潰れるもの |
| 小さな札 | `<span class="tag">D0</span>` | ピンの別名など |
| 折りたたみ | `<details><summary>…</summary>…</details>` | 普段は要らない詳細 |
| キー | `<kbd>Enter</kbd>` | キーボードのキーそのもの |

色や余白を `style=""` で直接書かない（ダークモードで崩れるため。足りない部品は `style.css` にトークンを使って足す）。

## 自動生成ブロック

```html
<!-- gen:名前 引数=値 -->
<!-- /gen:名前 -->
```

- 中身は `python3 scripts/gen-docs.py` が上書きする。手で直さない
- 本文中に 1 つの値を埋め込むときは `<!-- gen:value of=キー -->` と `<!-- /gen:value -->` を使う（例: `of=scrl-val`）
- 使える生成器の一覧: `grep -rn '@generator(' scripts/docgen/`。`value` のキーは `scripts/docgen/shield.py` の `_value()`
- 生成器の中身が変・古いと思ったら、HTML ではなく生成器を直す
- `gen-docs.py` は検索の索引 `docs/assets/search-index.js` も作り直す（手で直さない）。`h2`・`h3` に付けた `id` が検索結果の飛び先になる
- 元が git 管理外のもの（`.zmk-ref/` から作る版や behavior の一覧）は、元が無い環境では前の内容のまま残る。git の履歴から作るもの（変更履歴）は `--check` で比べない。生成器を足すときは、前者なら `SourceMissing` を投げ、後者なら `@generator(..., volatile=True)` にする

## 生成器の足し方

1. テーマに合う `scripts/docgen/*.py` を選ぶ（一覧は `scripts/docgen/__init__.py` の docstring）。合うものが無ければ新しいモジュールを作り、`__init__.py` の import に足す
2. `@generator("名前")` を付けた関数 `(page, args) -> str` を書く。部品は `common.py` の `table` / `code` / `esc` / `badge` / `source_note` を使い、**最後に `source_note` で元ファイルを示す**（読み手が「どこを直せば変わるか」を辿れるように）
3. ファイルを読むときはコメントを除いてから読む（`zmk_dts.strip_comments`）。DTS は `zmk_dts.py` の部品で読む
4. HTML に囲みを置いて `python3 scripts/gen-docs.py` を実行し、`--check` が通ることを確かめる

## 文章

- です・ます調。1 文に 1 つのこと。結論を先に書く
- 見出しは名詞句（「ビルド」「接続がおかしいとき」）
- 英数字と日本語の間は半角スペースを空ける（例: 「ZMK Studio が有効」）
- ファイル名・設定名・コマンドは `<code>`。別ページの節へのリンクは「ページ名 › 節名」の形にする
- 専門用語は初出で一言説明する（例: 「セントラル（PC と繋がる側）」）

## 見た目を確かめる

`.claude/launch.json` の `docs` でローカルサーバーを立て（`http://localhost:8765`）、ブラウザで表示を確かめる。デスクトップ幅に加え、スマホ幅（375px）でもページが横にはみ出さないこと。キャッシュで古い CSS が出るときは強制再読み込みする。
