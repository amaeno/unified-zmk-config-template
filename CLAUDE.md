# 双掌 (sosho) ZMK ファームウェア設定

ELEKIT 製分割キーボード **双掌 (sosho)** の ZMK 設定リポジトリ。
Seeed Xiao nRF52840 を左右に載せた 44 キー分割キーボードで、
各半分にロータリーエンコーダ 1 個と、ポインティングデバイス（トラックパッドまたはトラックボール）を持つ。

このリポジトリは **自分専用のカスタマイズ用**。本家 upstream の追従は行わない。

---

## まず: ビルドが必要か判断する

R 側（セントラル）は **ZMK Studio が有効** (`CONFIG_ZMK_STUDIO=y`, `CONFIG_ZMK_STUDIO_LOCKING=n`)。
単純なキー割り当ての変更なら [zmk.studio](https://zmk.studio) に USB 接続するだけで済み、
**ビルドも書き込みも不要**。

| やりたいこと | 手段 |
|---|---|
| キー割り当てを変える / レイヤーを使い分ける | **ZMK Studio**（ビルド不要） |
| コンボ・エンコーダ挙動・新しい behavior・Kconfig・ポインタ感度 | ファイルを編集 → ビルド |

キーマップ末尾の `scroll` / `extra2` (`status = "reserved"`) は、Studio でレイヤーを増やせるようにするための
予約枠。Studio で使うぶんには再ビルドしなくてよい。

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
src/boot_delay_hack.c            起動時 1 秒 busy-wait（下記の注意を参照）
zephyr/module.yml                board_root: . を供給。boards/ を ZMK に認識させる要
scripts/                         ローカルビルドと lint（下記）
memo.md                          verB2 のリリースノート
```

### ビルドターゲット

board は全て `xiao_ble/nrf52840/zmk`。

| artifact | shield | 役割 |
|---|---|---|
| `sosho_R_trackpad` | `sosho_R_trackpad rgbled_adapter` | 右 = **セントラル**、Cirque トラックパッド、Studio 有効 |
| `sosho_R_trackball` | `sosho_R_trackball rgbled_adapter` | 右 = セントラル、PMW3610 トラックボール、Studio 有効 |
| `sosho_L_trackpad` | `sosho_L_trackpad rgbled_adapter` | 左 = ペリフェラル、Cirque |
| `sosho_L_trackball` | `sosho_L_trackball rgbled_adapter` | 左 = ペリフェラル、PMW3610 |
| `settings_reset` | `settings_reset` | ペアリング情報のリセット（ZMK 標準） |

**右がセントラル**（PC と繋がる側。Studio もここ）、**左がペリフェラル**。
左右で異なる uf2 を書き込む。トラックパッド版とトラックボール版は排他。

### 外部モジュール (`config/west.yml`)

| モジュール | 用途 |
|---|---|
| `zmkfirmware/zmk` | ZMK 本体 |
| `caksoylar/zmk-rgbled-widget` | RGB LED による状態表示（電池残量・接続状態） |
| `badjeff/zmk-pmw3610-driver` | トラックボール (PMW3610) ドライバ |
| `elekit-official/zmk_encoder` | `zmk,behavior-encoder-mouse-scroll`。エンコーダのスクロール |

`zmk_encoder` は verB2 で導入されたもの。従来の `zmk,behavior-sensor-rotate-var` + `&msc` は
1 スクロールにつき press と release の 2 イベントを発行し、負荷時に release が落ちて
スクロールが固まることがあった。この モジュールは 1 イベントで完結する。詳細は `memo.md`。

---

## 開発ループ

```bash
# 1. 編集前に確認したければ
python3 scripts/lint-keymap.py

# 2. 編集後、まず lint（数十 ms）
python3 scripts/lint-keymap.py

# 3. ビルド（普段は 1 ターゲットだけ。キーマップ変更なら約 14 秒）
./scripts/build-local.sh sosho_R_trackpad

# 4. firmware/sosho_R_trackpad.uf2 を書き込む
```

初回のみ Docker イメージと west ワークスペースの取得で約 6 分かかる。以降は再利用される。

`scripts/lint-keymap.py` はツールチェーン不要でホストの python3 だけで動く。
レイヤーごとのバインド数、括弧の対応、存在しないレイヤーへの参照、コンボの位置の範囲、
`sensor-bindings` の引数の数を検査する。期待キー数は 44 を決め打ちせず、
物理レイアウトとマトリクス変換から導出して 3 者の食い違いも検出する。

ビルドの詳細と書き込み手順は `.claude/skills/zmk-build/SKILL.md` を参照。

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
