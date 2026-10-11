---
name: zmk-build
description: 双掌 (sosho) のファームウェアを lint してビルドし、結果を要約して返す。キーマップ・コンボ・エンコーダ挙動・ポインタ設定・Kconfig を変更した後の検証に使う。引数はターゲット名（複数可。省略時は sosho_R_trackpad、--all で全部）。書き込みはユーザーが行う。
argument-hint: "[ターゲット名... | --all]"
model: haiku
context: fork
background: false
allowed-tools: Bash(python3 scripts/lint-keymap.py:*) Bash(python3 scripts/gen-docs.py --check) Bash(./scripts/build-local.sh:*) Bash(grep:*) Read Grep
disallowed-tools: Write Edit NotebookEdit
---

# 双掌 (sosho) のビルド

あなたの仕事は lint とビルドを実行し、結果を短く報告すること。
**ファイルは直さない。原因を推測で断定しない。**

対象ターゲット: $ARGUMENTS
（空なら `sosho_R_trackpad`）

## 前提

- 作業ディレクトリはリポジトリのルート（`CLAUDE.md` があるところ）
- ビルドは Docker の中で動く `./scripts/build-local.sh`。成果物は `firmware/<ターゲット>.uf2`
- ターゲットは `sosho_R_trackpad` `sosho_R_trackball` `sosho_L_trackpad` `sosho_L_trackball` `settings_reset`
  の 5 つ（正本は `build.yaml`）。`_R_` は右、`_L_` は左に書き込むもの
- この機体で使うのは CLAUDE.md の「この機体」の表にある 2 つ（右 `sosho_R_trackpad`、左 `sosho_L_trackball`）。
  それ以外のターゲットを指定されたら、そのままビルドしてよいが報告で「この機体では使っていない」と添える
- 差分ビルドでは設定（Kconfig）の段階が走らず、その警告が出ないことがある。警告を前と比べるように頼まれたら、
  クリーンビルド（`./scripts/build-local.sh -p <ターゲット>`）にする

## 手順

1. `python3 scripts/lint-keymap.py` を実行する。
   終了コードが 0 でなければ、`ERROR:` の行をそのまま報告して終わる（ビルドしない）
2. `python3 scripts/gen-docs.py --check` を実行する。資料が古くてもビルドは続けるが、報告の「資料（生成部分）」に書く
   （仕様を変えたら資料も必ず更新する決まりなので、更新漏れをここで知らせる）
3. `./scripts/build-local.sh <ターゲット...>` を実行する。Bash のタイムアウトは 600000 ms にする
   （初回は west ワークスペースの取得で約 6 分かかる。2 回目以降は 1 ターゲット 10〜20 秒）
4. 失敗したら、`docs/workflow.html` を `id="trouble"` で検索し（Grep が無ければ Bash の `grep -n`）、その表を Read する。
   症状に合う行があれば、その対処を報告に含める。合う行が無ければ、最初のエラー行とその前後数行をそのまま報告する
5. 下の形で報告する

## 報告の形（これ以外は書かない）

- **結果**: 成功 / lint で失敗 / ビルドで失敗
- **成果物**: 成功したターゲットごとに `firmware/<ターゲット>.uf2` と書き込む側（右 / 左 / 左右とも）
- **失敗の内容**: エラー行の抜粋と、trouble 表に合う対処（あれば）
- **資料（生成部分）**: 最新 / 要更新（`gen-docs.py --check` が挙げたファイル）。手書きの説明が古いかどうかは、この確認では分からない
- **所要時間**: 分かれば
- **改善メモ**: この手順どおりに進まなかった点（足りない前提、表に無かった失敗など）があれば 1〜2 行。無ければ書かない
