# 双掌 (sosho) ZMK ファームウェア設定

ELEKIT 製分割キーボード **双掌 (sosho)** の ZMK 設定リポジトリ。**自分専用のカスタマイズ用**で、
本家 upstream の追従・push・PR は行わない。
Seeed XIAO nRF52840 を左右に載せた 44 キー分割キーボードで、
各半分にロータリーエンコーダ 1 個と、ポインティングデバイス（トラックパッドまたはトラックボール）を持つ。

---

## この機体

| 側 | ポインタ | ビルドターゲット |
|---|---|---|
| 右（セントラル。PC と繋がる側、ZMK Studio もここ） | トラックパッド (Cirque) | `sosho_R_trackpad` |
| 左（ペリフェラル） | トラックボール (PMW3610) | `sosho_L_trackball` |

ビルド・書き込み・調査はこの 2 つを前提にする。`sosho_R_trackball` と `sosho_L_trackpad` は使っていないが、
本家由来のターゲットとして `build.yaml` に残している。

---

## 資料（事実の正本）

人間向けの資料は `docs/` の HTML で、**事実の正本はそちら**。このファイルは AI 向けの入口とルールだけを持つ。
HTML は長いので、目的の節を `id="…"` で Grep してから、その範囲だけを Read する。
資料の値は生成した時点のもの。設定を変える作業では元ファイル（keymap・dtsi・conf・overlay）を正とする。

| 知りたいこと | 場所 |
|---|---|
| 構成、ピン配置、エンコーダ、ポインタの配線、ファイル構成 | `docs/hardware.html` |
| レイヤー図（ファイル上の初期値）、**キー位置番号**（コンボの `key-positions` 用。テキスト版は `id="positions"`）、コンボ、エンコーダの割り当て | `docs/keymap.html` |
| どこを触ると何が変わるか。スクロール・ポインタ・エンコーダ・Kconfig の現在値と変え方 | `docs/settings.html` |
| 既知の課題（未解決のもの）。**関係するファイルを編集する前に確認する** | `docs/known-issues.html` |
| 使っている機能、ZMK の behavior 一覧、追加できる機能の候補 | `docs/features.html` |
| 使っている ZMK の版、手元の ZMK ソース（`.zmk-ref/`）の構成、確かめた仕様のメモ（出典つき） | `docs/zmk-reference.html` |
| main に取り込んだ変更の履歴と、書き込んだ版のタグ | `docs/changelog.html` |
| ビルドが要るかの判断、開発の流れ、git の運用 | `docs/workflow.html` の `#decide` `#loop` `#git` |
| ビルドのコマンド・ターゲット・仕組み、書き込み手順 | `docs/workflow.html` の `#build` `#flash` `#reset` |
| うまくいかないとき、ビルドスクリプトの制約 | `docs/workflow.html` の `#trouble` `#internals` |
| 資料の仕組みと決まりごと | `docs/workflow.html` の `#docs`（書き方は update-docs skill） |
| skills・サブエージェントの一覧、改善メモの仕組み、ZMK の調査用コピー | `docs/workflow.html` の `#ai` |

---

## まず: ビルドが必要か判断する

**キー割り当ての正本は ZMK Studio**（ユーザーの決定。2026-10-11）。割り当ての変更は Studio で行い、
ビルドも書き込みも要らない。`config/sosho.keymap` の各レイヤーの `bindings` は初期値で、Studio で保存したあとの
実機とは一致しない（資料のレイヤー図も初期値）。Studio で保存したあとは、ファイルの割り当てを書き換えて
書き込んでも「Restore Stock Settings」するまで反映されない。詳細は `docs/workflow.html#decide`。

- ファイルで管理するのは Studio で扱えないもの（コンボ、behavior の定義、エンコーダの割り当て、ポインタ、Kconfig）。これらはビルドが要る
- 機能の追加で特定のキーへの割り当てが要るとき（例: `&lt`）は、ファイルの初期値を変えたうえで、Studio で保存済みなら Studio でも同じ割り当てをするようユーザーに頼む
- キーマップ末尾の `scroll` / `extra2`（`status = "reserved"`）は、Studio でレイヤーを増やすための予約枠。`scroll`（L4）は左トラックボールのスクロールに使っている

---

## ファイル構成

```
build.yaml                       ビルド対象 5 種の定義。全ての入口
config/
  west.yml                       ZMK 本体 + 外部モジュール 4 つ（動作を確かめたコミットで固定）
  sosho.keymap                   キーマップ・コンボ・エンコーダ挙動（普段触るのはここ）
boards/shields/sosho/
  Kconfig.shield                 4 つのシールド名の定義
  Kconfig.defconfig              L/R 共通の必須 Kconfig（split の役割など）
  sosho.dtsi                     共通ハード定義: マトリクス変換/kscan/エンコーダ/SPI/センサ
  sosho-layouts.dtsi             物理レイアウト（ZMK Studio 用の 44 キー座標）
  sosho_L.dtsi / sosho_R.dtsi    左右の列 GPIO と col-offset、エンコーダ有効化
  sosho_{L,R}_{trackpad,trackball}.overlay   ポインタ有効化と input-processor
  sosho_{L,R}_{trackpad,trackball}.conf      Kconfig（BLE/LED/電池/Studio 等）
  sosho.zmk.yml                  シールドのメタ情報
  sosho.layout.json              旧形式のレイアウト情報（どのビルドからも参照されていない）
docs/                            人間向けの資料（HTML）。事実の正本
  assets/style.css               全ページ共通のスタイル
scripts/                         ビルド・lint・資料生成（一覧は docs/workflow.html#scripts）
  docgen/                        資料の生成器。テーマ別のモジュール（一覧は docgen/__init__.py）
.claude/
  agents/ skills/                サブエージェントと skills（一覧は docs/workflow.html#ai-tools）
  hooks/retro-nudge.py           作業の区切りで改善提案を促す Stop フック
  improvements.md                skills・エージェントの改善メモ（/retro が読む）
.zmk-ref/                        ZMK のソースと資料の調査用コピー（git 管理外。build-local.sh --ref で作る）
zephyr/module.yml                board_root: . を供給。boards/ を ZMK に認識させる要
memo.md                          本家の verB2 リリースノート（オリジナルのまま残す）
```

---

## 開発ループ

```bash
python3 scripts/lint-keymap.py              # キーマップの検査（1 秒未満）。編集の前後に
python3 scripts/gen-docs.py                 # 資料の生成ブロックを更新（--check で確認だけ）
./scripts/build-local.sh sosho_R_trackpad   # ビルド（キーマップ変更なら約 14 秒）
```

成果物は `firmware/<ターゲット>.uf2`。書き込みはユーザーが行う（`docs/workflow.html#flash`）。
ビルドは `/zmk-build` skill に任せると、ビルドログを読まずに結果の要約だけが返る。

`scripts/lint-keymap.py` はツールチェーン不要でホストの python3 だけで動く。
レイヤーごとのバインド数、括弧の対応、存在しないレイヤーへの参照、コンボの位置の範囲、
`sensor-bindings` の引数の数を検査する。期待キー数は 44 を決め打ちせず、
物理レイアウトとマトリクス変換から導出して 3 者の食い違いも検出する。
キーマップと overlay が参照するラベル（`&kp` や `&zip_*` など）が、ZMK・モジュール（`.zmk-ref/`）と
このリポジトリに定義されているかも照らし、見つからなければ警告する（`.zmk-ref/` が無ければ飛ばす）。

---

## リポジトリ運用

詳細は `docs/workflow.html#git`。AI が守ること:

- 作業はトピックブランチ（`feature/` `fix/` `build/` `docs/`）で行う。`main` は実機に書き込んで常用している状態
- `main` への取り込み（`git merge --no-ff`）とタグ付け（`fw-YYYY-MM-DD`）は、ユーザーが実機で確かめたと言ってから行う
- `git push` はしない（`.claude/settings.json` で deny 済み。push はユーザーが手動で行う）
- リモートは `origin`（ユーザーのフォーク。バックアップ用）だけ。upstream は登録しない。PR は作らない
- ビルドはローカル（Docker）だけで行う。GitHub Actions は使わない（GitHub 側で無効化済み）

---

## 資料の規約

- **資料を更新するときは、ほかの記述と矛盾していないかを必ず確かめる（大前提）。** 変えた事実・値・用語で `git grep -n --untracked` をかけ
  （資料・`CLAUDE.md`・`.claude/`・スクリプトや設定ファイルのコメントまで見る）、元ファイルとも突き合わせる。
  矛盾を見つけたら、どちらが正しいかを元ファイル・ZMK のソース（`.zmk-ref/`）・ユーザーの決定で確かめてから、
  誤っている方を直す（生成部分なら生成器を直す）。確かめられなければ推測で直さず、ユーザーに聞く。
  履歴の記録（`memo.md`、変更履歴、改善メモの「対応済み」）は当時の事実なので直さない
- 資料は HTML（`docs/*.html`、共通スタイルは `docs/assets/style.css`）。ユーザーの読みやすさを最優先する
- `<!-- gen:… -->` から `<!-- /gen:… -->` の中は `scripts/gen-docs.py` が上書きする。手で編集しない
- 繰り返し変わる事実は手書きせず、`scripts/docgen/` に生成器を足す。本文中の 1 つの値は `gen:value` で埋め込む
- 同じ事実を複数の場所に書かない。`CLAUDE.md` と skills は資料の節へのリンクで済ませる
- **仕様（挙動・設定値・キー割り当て・手順・AI ツールの使い方）を変えたら、資料を必ず同じコミットで更新する。** 生成部分は `python3 scripts/gen-docs.py`、手書き部分は docs-sync か update-docs skill で直す。資料が古いままの変更はコミットしない
- 新しいページは既存のページをひな形にし、`scripts/docgen/site.py` の `PAGES` に登録する
- 既知の課題を直したら、`docs/known-issues.html` の表示が「解消済み」に変わるので、その節を消す
- 本家由来の資料（`memo.md`）はオリジナルのまま残す

---

## エージェントとモデル

- サブエージェントの**同時起動は最大 5 本**、1 つの依頼で起動する延べ数は**最大 10 本**。超えそうなときは先にユーザーに確認する
- Workflow（多数のエージェントを束ねる仕組み）は、ユーザーが明示的に頼んだときだけ使う
- 場所の分かっている数ファイルを読むだけなら、エージェントを使わず直接読む
- 長い出力が出る作業（ビルドログなど）は、`context: fork` の skill かサブエージェントに任せ、メイン会話には要約だけを戻す
- skills とサブエージェントは frontmatter の `model` でモデルを指定する。低いモデルに任せるものほど、前提・手順・完了条件・やってはいけないことを本文に明記する

| モデル | 任せる作業 |
|---|---|
| `haiku` | 手順が決まっている作業。ビルドの実行と結果の要約、生成スクリプトの実行、定型の確認 |
| `sonnet` | 読んで判断する作業。ZMK のソースやドキュメントの調査、設定のレビュー、資料の執筆 |
| `opus`（メイン会話） | 設計判断、新しい機能の設計、複数ファイルにまたがる変更 |

---

## 改善メモと振り返り

- skills・サブエージェントが手順どおりに進まなかったとき（失敗、前提の不足、遠回り、ユーザーからの訂正、モデルの力不足や過剰）は、その場で `.claude/improvements.md` の「未対応」に 1 行書く。直すのは後でよい
- メモを書いたら `python3 scripts/gen-docs.py` も実行する（資料の改善メモ一覧がこのファイルから作られ、放っておくと `--check` が落ちるため）
- サブエージェントや fork の skill の報告に「改善メモ」があれば、メイン会話がそれを転記する
- 作業の区切り（直近 30 分以内にコミットがあり、未コミットの変更が無い）で未対応のメモがあると、Stop フック（`.claude/hooks/retro-nudge.py`）が `/retro` での改善提案を促す。1 セッション 1 回まで。止めたいときは環境変数 `SOSHO_RETRO_NUDGE=0`
- 改善案を適用するのは、ユーザーが承認したものだけ

---

## 規約

- **コミットメッセージは日本語**でよい。
  （`0ff1272` 以降の既存履歴は本家由来で英語だが、このリポジトリでは日本語に統一する）
- **コード内のコメントとドキュメントは日本語**
- **改行コードを変えない。** シールドの一部のファイル（conf、`sosho_L.dtsi` / `sosho_R.dtsi`、一部の overlay など）と `memo.md` は CRLF（一覧は `git ls-files --eol | grep i/crlf`）。
  スクリプトでまとめて書き換えるときは `open(…, newline='')` で読み書きする（Python の `read_text` は CRLF を LF に変え、全行が差分になる）
- `git push` は `.claude/settings.json` の deny リストで禁止されている（意図的な設定）
