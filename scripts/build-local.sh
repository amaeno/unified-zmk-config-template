#!/usr/bin/env bash
# 双掌 (sosho) のファームウェアを Docker でローカルビルドする。
#
#   scripts/build-local.sh                     既定ターゲットをビルド
#   scripts/build-local.sh sosho_L_trackball   build.yaml のターゲットを 1 つビルド
#   scripts/build-local.sh --all               全ターゲットをビルド（リリース時）
#   scripts/build-local.sh --list              ターゲット一覧
#   scripts/build-local.sh -p sosho_R_trackpad クリーンビルド
#   scripts/build-local.sh --update            west update をやり直す（west.yml を変えた後）
#   scripts/build-local.sh --shell             ツールチェーンのコンテナ内シェル
#
# 初回は west ワークスペースの取得に 10〜15 分かかる。2 回目以降は
# 名前付きボリューム上のワークスペースと ccache が再利用される。
#
# macOS の bash 3.2 で動く範囲に留めること（配列処理はコンテナ側に置いてある）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

IMAGE="${ZMK_IMAGE:-zmkfirmware/zmk-build-arm:stable}"
VOLUME="${ZMK_VOLUME:-sosho-zmk-ws}"

if ! docker info >/dev/null 2>&1; then
  echo "error: Docker デーモンが動いていません。Docker Desktop を起動してください。" >&2
  exit 1
fi

docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null
mkdir -p "$REPO_ROOT/firmware"

# パイプや CI でも動くよう、端末のときだけ -t を付ける。
TTY_FLAGS="-i"
[ -t 1 ] && TTY_FLAGS="-it"

# -u $(id -u) は付けないこと。Zephyr SDK は root の CMake パッケージレジストリ
# (/root/.cmake/packages/Zephyr-sdk) に登録されており、別 UID だと見つからない。
# /root にも何もマウントしないこと（SDK 登録を隠してしまう）。
# macOS の bind mount はコンテナ内 root の書き込みをホストユーザーに割り当てるので、
# リポジトリが root 所有になる心配はない。
#
# west ワークスペースは名前付きボリューム上に置く。リポジトリ直下に置くと
# west が作る zephyr/ が既存の zephyr/module.yml と衝突する（module.yml は
# board_root: . を供給しているので失うと boards/ が見つからなくなる）。
# ZMK 公式 CI も zephyr/module.yml があるリポジトリでは同じ回避をしている。
exec docker run --rm $TTY_FLAGS \
  -v "$VOLUME:/ws" \
  -v "$REPO_ROOT:/zmk-config" \
  -v "$REPO_ROOT/config:/ws/config" \
  -e CCACHE_DIR=/ws/.ccache \
  -w /ws \
  "$IMAGE" \
  bash /zmk-config/scripts/build-in-container.sh "$@"
