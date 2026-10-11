#!/usr/bin/env bash
# zmkfirmware/zmk-build-arm コンテナの中で動く。ホストから直接実行しないこと。
# 呼び出し元は scripts/build-local.sh。
set -euo pipefail

WS=/ws
REPO=/zmk-config
OUT="$REPO/firmware"
MATRIX="$REPO/build.yaml"
DEFAULT_TARGET="${ZMK_DEFAULT_TARGET:-sosho_R_trackpad}"

blue()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
green() { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m==> %s\033[0m\n' "$*" >&2; }

PRISTINE=0
DO_UPDATE=0
BUILD_ALL=0
LIST_ONLY=0
REF_ONLY=0
TARGETS=()

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--pristine) PRISTINE=1 ;;
    --update)      DO_UPDATE=1 ;;
    --all)         BUILD_ALL=1 ;;
    --list)        LIST_ONLY=1 ;;
    --ref)         REF_ONLY=1 ;;
    --shell)       exec bash ;;
    -h|--help)     sed -n '2,16p' "$REPO/scripts/build-local.sh"; exit 0 ;;
    -*)            red "不明なオプション: $1"; exit 2 ;;
    *)             TARGETS+=("$1") ;;
  esac
  shift
done

# ------------------------------------------------------------- build.yaml
# TSV で出力: name \t board \t shield \t snippet \t cmake-args
read_matrix() {
  python3 -c '
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1])) or {}
for e in doc.get("include", []):
    board  = e["board"]
    shield = e.get("shield", "") or ""
    name   = e.get("artifact-name") or (
        (shield.replace(" ", "+") + "-" if shield else "") + board.replace("/", "_") + "-zmk")
    ca = e.get("cmake-args", "")
    if isinstance(ca, list):
        ca = " ".join(ca)
    print("\t".join([name, board, shield, e.get("snippet", "") or "", ca]))
' "$MATRIX"
}

if [ "$LIST_ONLY" = 1 ]; then
  blue "build.yaml のターゲット:"
  read_matrix | while IFS=$'\t' read -r n b s sn ca; do
    printf '  %-22s board=%s shield=%s\n' "$n" "$b" "${s:-<なし>}"
  done
  exit 0
fi

# ------------------------------------------------------------- ブートストラップ
if [ ! -d "$WS/.west" ]; then
  blue "初回実行: west ワークスペースを初期化します（約 1GB の取得。1 回だけ）"
  west init -l "$WS/config"
  DO_UPDATE=1
fi
if [ "$DO_UPDATE" = 1 ] || [ ! -d "$WS/zephyr" ] || [ ! -d "$WS/zmk" ]; then
  blue "west update（blobless clone）"
  west update --fetch-opt=--filter=tree:0
fi
# --rm で /root が毎回消えるので、Zephyr の CMake パッケージ登録をやり直す。1 秒未満。
west zephyr-export >/dev/null

# ------------------------------------------------------------- 調査用のコピー
# ワークスペースは名前付きボリュームの中にあり、ホストからは読めない。
# AI の調査役（.claude/agents/zmk-researcher.md）が Read/Grep で読めるよう、
# 調べることの多い部分だけを .zmk-ref/（git 管理外）に写す。.git は写さない。
sync_ref() {
  local dst="$REPO/.zmk-ref"
  blue "ZMK のソースと資料を .zmk-ref/ に写す（調査用）"
  rm -rf "$dst"
  mkdir -p "$dst"
  tar -C "$WS" --exclude=.git -cf - \
      zmk/app zmk/docs/docs zmk-rgbled-widget zmk-pmw3610-driver modules/zmk_encoder \
      zephyr/boards/seeed/xiao_ble \
    | tar -C "$dst" -xf -
  # 階層を浅くして、パスを短くする
  mv "$dst/zmk/app" "$dst/zmk-app"
  mv "$dst/zmk/docs/docs" "$dst/zmk-docs"
  mv "$dst/modules/zmk_encoder" "$dst/zmk_encoder"
  mv "$dst/zephyr/boards/seeed/xiao_ble" "$dst/zephyr-xiao_ble"
  rm -rf "$dst/zmk" "$dst/modules" "$dst/zephyr"
  # マニフェスト（config/）はコンテナ内では git リポジトリではなく sha を取れないので外す
  local -a projects
  read -r -a projects <<<"$(west list -f '{name}' | grep -v '^manifest$' | tr '\n' ' ')"
  {
    echo "# .zmk-ref/ の元になった各プロジェクトの版（scripts/build-local.sh --ref が作る）"
    echo "# 名前 revision コミット"
    west list -f "{name} {revision} {sha}" "${projects[@]}"
  } > "$dst/VERSIONS.txt"
  green ".zmk-ref/ を更新しました"
}

if [ "$REF_ONLY" = 1 ]; then
  sync_ref
  exit 0
fi
# 版を動かしたら、調査用のコピーも同じ版にそろえる
if [ "$DO_UPDATE" = 1 ]; then
  sync_ref
fi

# ------------------------------------------------------------- ビルド
build_one() {
  local name="$1" board="$2" shield="$3" snippet="$4" cmake_args="$5"
  local bdir="$WS/build/$name"

  # west の引数は `--` より前、CMake の -D は `--` より後。
  local -a wargs=(build -s "$WS/zmk/app" -d "$bdir" -b "$board")
  [ -n "$snippet" ] && wargs+=(-S "$snippet")
  [ "$PRISTINE" = 1 ] && wargs+=(-p)

  # ZMK_EXTRA_MODULES がリポジトリを Zephyr モジュールとして読み込ませる。
  # これが zephyr/module.yml の board_root: . を有効にし、boards/shields/sosho/ を見つけさせる。
  local -a cargs=(-DZMK_CONFIG="$WS/config" -DZMK_EXTRA_MODULES="$REPO")
  # shield が複数語のときは、フラグを分けず 1 つの空白区切り文字列として渡す
  # （Kconfig.shield の shields_list_contains がこのリストを解釈する）。
  [ -n "$shield" ] && cargs+=(-DSHIELD="$shield")
  if [ -n "$cmake_args" ]; then
    local -a extra
    read -r -a extra <<<"$cmake_args"
    cargs+=("${extra[@]}")
  fi

  blue "build $name  (board=$board shield='${shield:-なし}' snippet='${snippet:-なし}')"
  west "${wargs[@]}" -- "${cargs[@]}"

  mkdir -p "$OUT"
  if [ -f "$bdir/zephyr/zmk.uf2" ]; then
    cp "$bdir/zephyr/zmk.uf2" "$OUT/$name.uf2"
    green "firmware/$name.uf2"
  elif [ -f "$bdir/zephyr/zmk.bin" ]; then
    cp "$bdir/zephyr/zmk.bin" "$OUT/$name.bin"
    green "firmware/$name.bin (uf2 は生成されませんでした)"
  else
    red "$name の成果物が生成されませんでした"; return 1
  fi
}

if [ "$BUILD_ALL" = 1 ]; then
  WANT=""
elif [ ${#TARGETS[@]} -gt 0 ]; then
  WANT=" ${TARGETS[*]} "
else
  WANT=" $DEFAULT_TARGET "
fi

FOUND=0
while IFS=$'\t' read -r name board shield snippet cmake_args; do
  if [ -n "$WANT" ] && [[ "$WANT" != *" $name "* ]]; then continue; fi
  FOUND=1
  build_one "$name" "$board" "$shield" "$snippet" "$cmake_args"
done < <(read_matrix)

if [ "$FOUND" = 0 ]; then
  red "該当するターゲットがありません。指定できるのは:"
  read_matrix | cut -f1 | sed 's/^/  /' >&2
  exit 1
fi

green "完了 -> $OUT"
