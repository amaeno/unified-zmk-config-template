---
name: zmk-build
description: 双掌 (sosho) のファームウェアをビルドして書き込む。キーマップ・コンボ・エンコーダ挙動・ポインタ設定・Kconfig を変更した後の検証と、uf2 の書き込み手順。ビルドが失敗したときの対処も含む。
---

# 双掌 (sosho) のビルドと書き込み

## 0. そもそもビルドが要るか確認する

R 側は ZMK Studio が有効。**キー割り当てを変えるだけなら [zmk.studio](https://zmk.studio) に
USB 接続するだけで済み、ビルドも書き込みも不要**。予約レイヤー `scroll` / `extra2` があるので
レイヤーを増やすのも Studio でできる。

ビルドが必要なのは以下を変えたとき:

- コンボ、新しい behavior の定義、`sensor-bindings`（エンコーダの割り当て）
- `#define ZMK_POINTING_DEFAULT_SCRL_VAL` などキーマップ内のマクロ
- `*.overlay` の `input-processors`（ポインタの速度・反転・スクロール化）
- `*.conf` の Kconfig、`*.dtsi` のハードウェア定義
- `config/west.yml` のモジュール構成

## 1. lint（数十 ms）

```bash
python3 scripts/lint-keymap.py
```

`ok: config/sosho.keymap  (レイヤー 6 / 1 レイヤー 44 キー / センサ 2)` が出れば OK。
バインド数の過不足、括弧の対応、存在しないレイヤーへの参照、コンボ位置の範囲外、
`sensor-bindings` の引数の数を検出する。ビルドを回す前に必ず通しておく。

## 2. ビルド

```bash
./scripts/build-local.sh --list              # ターゲット一覧
./scripts/build-local.sh sosho_R_trackpad    # 1 つビルド（普段はこれ）
./scripts/build-local.sh --all               # 5 つ全部（リリース時）
./scripts/build-local.sh -p <target>         # クリーンビルド
./scripts/build-local.sh --update            # west.yml を変えた後
./scripts/build-local.sh --shell             # コンテナ内シェル
```

成果物は `firmware/<target>.uf2`（gitignore 済み）。

実測（Apple Silicon / Docker 8 CPU・メモリ 4.1GB）:

| ケース | 所要時間 |
|---|---|
| 初回（イメージ取得 + west update + フルビルド） | 約 6 分 |
| キーマップを変更して 1 ターゲット | **約 14 秒** |
| 無変更で 1 ターゲット | 約 6 秒 |
| `--all`（5 ターゲット、キャッシュあり） | 約 60 秒 |

初回に取得したものは名前付きボリューム `sosho-zmk-ws` に残り、以降ずっと再利用される。
反復中は 1 ターゲットだけビルドし、`--all` はリリース時に使う。

ディスクはイメージ 2.2GB + ワークスペース 3.2GB（5 ターゲットのビルドディレクトリ込み）。
ワークスペースを捨てたいときは `docker volume rm sosho-zmk-ws`。

## 3. 書き込み

XIAO nRF52840 のブートローダに入れて、USB ドライブとして uf2 をコピーする。

1. リセットボタンを **素早く 2 回** 押す
2. USB ドライブとしてマウントされる
3. `firmware/<target>.uf2` をそのドライブにコピーする
4. 書き込みが終わると自動で再起動する

**分割キーボードなので左右それぞれに書き込む。** 左右で異なる uf2 を使う
（`sosho_L_*` と `sosho_R_*`）。トラックパッド版とトラックボール版を取り違えないこと。

ペアリングや左右接続がおかしくなったときは、**両側に `settings_reset.uf2` を書き込んでから**
通常のファームウェアを書き直す。ホスト側の Bluetooth 設定からも古いペアリングを削除しておく。

## 4. うまくいかないとき

| 症状 | 対処 |
|---|---|
| `Docker デーモンが動いていません` | Docker Desktop を起動する |
| `ninja: build stopped` / 唐突に終わる | Docker VM のメモリ不足。Docker Desktop → Settings → Resources → Memory を 8GB に上げる（現状 4.1GB）。上げたくなければ `west build` に `-j4` を足して並列度を下げる |
| `west init` が「already initialized」 | ワークスペースが壊れている。`docker volume rm sosho-zmk-ws` して作り直す |
| `west.yml` を変えたのに反映されない | `./scripts/build-local.sh --update` |
| 何も変えていないのにビルドが壊れた | `config/west.yml` が全て `revision: main` 追従。`--update` を実行したときだけ ZMK のバージョンが動く。直前に `--update` したなら upstream の破壊的変更を疑う |
| `Missing ZMK Compat` | board 名から `/zmk` サフィックスが落ちている。`xiao_ble/nrf52840/zmk` が正しい |
| シールドが見つからない | `-DZMK_EXTRA_MODULES` が渡っていない。これが `zephyr/module.yml` の `board_root: .` を有効にしている |

Docker がどうしても使えない場合は、ブランチを push して GitHub Actions にビルドさせ、
Actions のページから artifact をダウンロードする従来の方法が使える。

## 実装上の制約（スクリプトを直すときに壊さないこと）

- **west ワークスペースをリポジトリ直下に置かない。** `west init -l config` は topdir を
  リポジトリルートにするため、`west update` が作る `zephyr/` が既存の `zephyr/module.yml` と
  衝突する。この `module.yml` が `board_root: .` を供給しており、失うと `boards/` が見つからなくなる。
  ZMK 公式 CI も `zephyr/module.yml` があるリポジトリでは同じ回避をしている。
  シンボリックリンクも不可（`west init -l` は `Path.resolve()` するのでリポジトリ内に戻る）。
- **`-u $(id -u)` を付けない。** Zephyr SDK は root の CMake パッケージレジストリ
  (`/root/.cmake/packages/Zephyr-sdk`) に登録されている。`/root` に何かをマウントするのも同じ理由で不可。
- **ビルドディレクトリは名前付きボリューム上に置く。** macOS の bind mount は小さいファイルが
  大量にあると極端に遅い。
- **`west zephyr-export` を毎回実行する。** `--rm` で `/root` が消えるため。
- **複数語の shield は 1 つの空白区切り文字列として `-DSHIELD` に渡す。** フラグを分けてはいけない
  （`Kconfig.shield` の `shields_list_contains` がこのリストを解釈する）。
- `snippet` は west の引数なので `--` より前、`cmake-args` は `--` より後。
