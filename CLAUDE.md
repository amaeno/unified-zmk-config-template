# 双掌 (sosho) ZMK ファームウェア設定

ELEKIT 製分割キーボード **双掌 (sosho)** の ZMK 設定リポジトリ。**自分専用のカスタマイズ用**で、
本家 upstream の追従・push・PR は行わない。
Seeed XIAO nRF52840 を左右に載せた 44 キー分割キーボードで、
各半分にロータリーエンコーダ 1 個と、ポインティングデバイス（トラックパッドまたはトラックボール）を持つ。

---

## 資料（事実の正本）

人間向けの資料は `docs/` の HTML で、**事実の正本はそちら**。このファイルは AI 向けの入口とルールだけを持つ。
HTML は長いので、目的の節を `id="…"` で Grep してから、その範囲だけを Read する。

| 知りたいこと | 場所 |
|---|---|
| ビルドが要るかの判断、開発の流れ、git の運用 | `docs/workflow.html` の `#decide` `#loop` `#git` |
| ビルドのコマンド・ターゲット・仕組み、書き込み手順 | `docs/workflow.html` の `#build` `#flash` `#reset` |
| うまくいかないとき、ビルドスクリプトの制約 | `docs/workflow.html` の `#trouble` `#internals` |
| 資料の仕組みと決まりごと | `docs/workflow.html` の `#docs` |

---

## まず: ビルドが必要か判断する

R 側（セントラル）は **ZMK Studio が有効**。単純なキー割り当ての変更なら [zmk.studio](https://zmk.studio) に
USB 接続するだけで済み、**ビルドも書き込みも不要**。コンボ・エンコーダ挙動・behavior・Kconfig・
ポインタ感度はファイルを編集してビルドする。詳細は `docs/workflow.html#decide`。

キーマップ末尾の `scroll` / `extra2` (`status = "reserved"`) は、Studio でレイヤーを増やせるようにするための
予約枠。一度 Studio でキーマップを変えると、`.keymap` を書き換えても「Restore Stock Settings」するまで反映されない。

---

## どこを触ると何が変わるか

| 変更したいこと | ファイル |
|---|---|
| キー割り当て・レイヤー・コンボ | `config/sosho.keymap` |
| スクロール量 | `config/sosho.keymap` の `#define ZMK_POINTING_DEFAULT_SCRL_VAL`（既定 150） |
| スクロールの加速 | `config/sosho.keymap` の `&msc`（現在は加速なしに設定） |
| トラックボールの解像度 (CPI) | `boards/shields/sosho/sosho.dtsi` の `trackball` ノード `cpi`（現在 600） |
| トラックパッドの感度 | 同 `glidepoint` ノード `sensitivity`（現在 `"1x"`。上げると BLE で問題が出るとのコメントあり） |
| ポインタの速度・反転・スクロール化 | 各 `*.overlay` の `input-processors` |
| LED の電池残量しきい値・BLE 接続パラメータ・電池報告 | 各 `*.conf` |
| 列/行 GPIO・エンコーダ・SPI 配線 | `sosho.dtsi`, `sosho_L.dtsi`, `sosho_R.dtsi` |
| ビルド対象の増減 | `build.yaml` |
| ZMK 本体・外部モジュールのバージョン | `config/west.yml` |

`input-processors` は `*.overlay` の冒頭に日本語の解説コメントがある。代表的なもの:

- `<&zip_xy_scaler 2 1>` — 分子 分母。2 倍速くする
- `<&zip_xy_to_scroll_mapper>` — ポインタの移動をスクロールに変換
- `<&zip_xy_transform (INPUT_TRANSFORM_X_INVERT | INPUT_TRANSFORM_Y_INVERT)>` — 反転
- 併記も可: `<&zip_xy_scaler 1 3>, <&zip_xy_to_scroll_mapper>;`

詳細は https://zmk.dev/docs/keymaps/input-processors

---

## キー位置番号 (0–43)

コンボの `key-positions` はこの番号で指定する。マトリクス変換 (`sosho.dtsi` の `default_transform`) から導出。

```
 0   1   2   3   4   5  │  6   7   8   9  10  11
12  13  14  15  16  17  │ 18  19  20  21  22  23
24  25  26  27  28  29  │ 30  31  32  33  34  35
36  37          38  39  │ 40  41          42  43

TAB  Q   W   E   R   T  │  Y   U   I   O   P  BSPC
CTL  A   S   D   F   G  │  H   J   K   L   '  ENT
SFT  Z   X   C   V   B  │  N   M   ,   .   /  SFT
ESC ALT         MO2 SPC │ MO1 A(`)        MO3 GUI
```

左半分が 0〜5 / 12〜17 / 24〜29 / 36〜39、右半分が 6〜11 / 18〜23 / 30〜35 / 40〜43。
最下段は左右とも 2 列ぶん欠けている（マトリクス上は col 2,3 と col 8,9 が無い）。

既存のコンボ:

| コンボ | 位置 | キー | 動作 |
|---|---|---|---|
| `combo_LCLK` | 19 20 | J + K | 左クリック |
| `combo_RCLK` | 20 21 | K + L | 右クリック |
| `combo_MCLK` | 19 21 | J + L | ホイールクリック |

---

## ファイル構成

```
build.yaml                       ビルド対象 5 種の定義。全ての入口
config/
  west.yml                       ZMK 本体 + 外部モジュール 3 つ
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
src/boot_delay_hack.c            起動時 1 秒 busy-wait（下記の注意を参照）
zephyr/module.yml                board_root: . を供給。boards/ を ZMK に認識させる要
scripts/                         ローカルビルド・lint・資料生成（docs/workflow.html#scripts）
memo.md                          本家の verB2 リリースノート（オリジナルのまま残す）
```

右がセントラル（PC と繋がる側。Studio もここ）、左がペリフェラル。左右で異なる uf2 を書き込む。
トラックパッド版とトラックボール版は排他。ターゲットの一覧は `docs/workflow.html#targets`。

### 外部モジュール (`config/west.yml`)

一覧は `docs/workflow.html#modules`。`zmk_encoder` は verB2 で導入されたもの。従来の
`zmk,behavior-sensor-rotate-var` + `&msc` は 1 スクロールにつき press と release の 2 イベントを発行し、
負荷時に release が落ちてスクロールが固まることがあった。このモジュールは 1 イベントで完結する。詳細は `memo.md`。

---

## 開発ループ

```bash
python3 scripts/lint-keymap.py              # キーマップの検査（数十 ms）。編集の前後に
python3 scripts/gen-docs.py                 # 資料の生成ブロックを更新（--check で確認だけ）
./scripts/build-local.sh sosho_R_trackpad   # ビルド（キーマップ変更なら約 14 秒）
```

成果物は `firmware/<ターゲット>.uf2`。書き込みはユーザーが行う（`docs/workflow.html#flash`）。
ビルドは `/zmk-build` skill に任せると、ビルドログを読まずに結果の要約だけが返る。

`scripts/lint-keymap.py` はツールチェーン不要でホストの python3 だけで動く。
レイヤーごとのバインド数、括弧の対応、存在しないレイヤーへの参照、コンボの位置の範囲、
`sensor-bindings` の引数の数を検査する。期待キー数は 44 を決め打ちせず、
物理レイアウトとマトリクス変換から導出して 3 者の食い違いも検出する。

---

## リポジトリ運用

詳細は `docs/workflow.html#git`。AI が守ること:

- 作業はトピックブランチ（`feature/` `fix/` `build/` `docs/`）で行う。`main` は実機に書き込んで常用している状態
- `main` への取り込み（`git merge --no-ff`）とタグ付け（`fw-YYYY-MM-DD`）は、ユーザーが実機で確かめたと言ってから行う
- `git push` はしない（`.claude/settings.json` で deny 済み。push はユーザーが手動で行う）
- リモートは `origin`（ユーザーのフォーク。バックアップ用）だけ。upstream は登録しない。PR は作らない
- ビルドはローカル（Docker）だけで行う。GitHub Actions は使わない

---

## 資料の規約

- 資料は HTML（`docs/*.html`、共通スタイルは `docs/assets/style.css`）。ユーザーの読みやすさを最優先する
- `<!-- gen:… -->` から `<!-- /gen:… -->` の中は `scripts/gen-docs.py` が上書きする。手で編集しない
- 繰り返し変わる事実は手書きせず、`scripts/gen-docs.py` に生成器を足す
- 同じ事実を複数の場所に書かない。このファイルと skills は資料の節へのリンクで済ませる
- コードや設定を変えたら `python3 scripts/gen-docs.py` を実行し、生成結果も同じコミットに含める。手書き部分が古くなったら合わせて直す
- 新しいページは既存のページをひな形にし、`scripts/gen-docs.py` の `PAGES` に登録する
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

## 注意点（既知の不整合。現時点では動作に影響しないため未修正）

- **`sosho-layouts.dtsi:9`** が存在しないラベル `&default_transform0` を参照している。
  直後に `sosho.dtsi:6-8` が `&default_transform` で上書きするため動いているが、
  その上書きを消すとビルドが壊れる。
- **`sosho_L_trackpad.conf`** が `CONFIG_BT_PERIPHERAL_PREF_*` を 2 回宣言している
  （前半 6/12/0/400 は死にコード、後半「フリーズ対策」の 10/20/10/400 が有効）。
- **`CONFIG_ZMK_MOUSE=y`** が全ての `.conf` に残っている。現行の `CONFIG_ZMK_POINTING=y` と併記された
  非推奨シンボル。
- **`CONFIG_ZMK_STUDIO=y`** が `build.yaml` の `cmake-args` と R 側 `.conf` の両方にあり重複。
- **`config/west.yml` は ZMK 本体を含め全て `revision: main`**。ビルドが再現可能でなく、
  upstream の破壊的変更である日突然壊れうる。安定させたいならタグに固定する。
  ただし ZMK のバージョンが動くのは `./scripts/build-local.sh --update` を実行したときだけで、
  通常のビルドは再現可能。
- **`src/boot_delay_hack.c` はビルドに含まれていない（確認済み）。** `zephyr/module.yml` の `cmake: .` が
  コメントアウトされているため、ルートの `CMakeLists.txt`（`zephyr_sources(src/boot_delay_hack.c)`）が
  読まれない。Zephyr の既定は module の `zephyr/` 配下を見るが、そこに `CMakeLists.txt` は無いため。
  生成された `build.ninja` にも `zmk.elf` のシンボルにも `force_boot_delay` は出てこない。
  つまり **1 秒の起動遅延はすでに効いていない**。復活させたいなら `cmake: .` を有効にする。
  なおファイル内のコメントは「PRE_KERNEL_2 で実行」と書いてあるが、実際のコードは `POST_KERNEL` 優先度 10。
- **`sosho.zmk.yml`** の `requires` が旧ボード名 `seeeduino_xiao_ble`、`url` が無関係な個人リポジトリを
  指したままになっている。

---

## 規約

- **コミットメッセージは日本語**でよい。
  （`0ff1272` 以降の既存履歴は本家由来で英語だが、このリポジトリでは日本語に統一する）
- **コード内のコメントとドキュメントは日本語**
- `git push` は `.claude/settings.json` の deny リストで禁止されている（意図的な設定）
