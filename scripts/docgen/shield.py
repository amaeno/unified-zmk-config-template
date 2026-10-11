"""シールド定義から作るもの: ピン配置、エンコーダ、ポインティングデバイス、input-processors、Kconfig、現在値。"""
from __future__ import annotations

import re
from pathlib import Path

import zmk_dts as dts

from .common import (
    SHIELD_DIR,
    Page,
    badge,
    code,
    conf_files,
    esc,
    generator,
    my_targets,
    pin,
    read,
    sources,
    table,
)
from .keymap import keymap_src

SHIELD = SHIELD_DIR / "sosho.dtsi"
SIDE_DTSI = {"左": SHIELD_DIR / "sosho_L.dtsi", "右": SHIELD_DIR / "sosho_R.dtsi"}
DEFCONFIG = SHIELD_DIR / "Kconfig.defconfig"

# 右の overlay にある input-listener が、どの入力を受けるか
LISTENERS = {
    "glidepoint_listener": ("右のトラックパッド", "R", "trackpad"),
    "trackball_listener": ("右のトラックボール", "R", "trackball"),
    "glidepoint_split_listener": ("左のトラックパッド（左から届く）", "L", "trackpad"),
    "trackball_split_listener": ("左のトラックボール（左から届く）", "L", "trackball"),
}
DEVICE_NAMES = {"glidepoint": "トラックパッド", "trackball": "トラックボール"}

# Kconfig の説明。(分類, 説明)。分類はこの順で並べる。ここに無いものは「その他」に入る。
KCONFIG_GROUPS = ["基本", "Bluetooth", "ZMK Studio", "エンコーダ", "ポインタ", "ハードウェア", "LED", "電池・電源", "その他"]
KCONFIG_NOTES = {
    "ZMK_KEYBOARD_NAME": ("基本", "キーボードの名前（Bluetooth の一覧に出る）"),
    "ZMK_SPLIT": ("基本", "分割キーボードとして動く"),
    "ZMK_SPLIT_ROLE_CENTRAL": ("基本", "セントラル（PC と繋がる側）として動く"),
    "ZMK_BLE": ("Bluetooth", "Bluetooth を使う"),
    "BT_PERIPHERAL_PREF_MIN_INT": ("Bluetooth", "接続間隔の希望の下限。右では PC との接続、左では右との接続に効く"),
    "BT_PERIPHERAL_PREF_MAX_INT": ("Bluetooth", "接続間隔の希望の上限"),
    "BT_PERIPHERAL_PREF_LATENCY": ("Bluetooth", "応答を省いてよい接続イベントの数。大きいほど省電力だが反応が遅れうる"),
    "BT_PERIPHERAL_PREF_TIMEOUT": ("Bluetooth", "切断とみなすまでの時間"),
    "ZMK_STUDIO": ("ZMK Studio", "ZMK Studio を有効にする"),
    "ZMK_STUDIO_LOCKING": ("ZMK Studio", "Studio の編集ロック（n = ロックしない。いつでも編集できる）"),
    "EC11": ("エンコーダ", "EC11 ロータリーエンコーダのドライバ"),
    "EC11_TRIGGER_GLOBAL_THREAD": ("エンコーダ", "エンコーダの割り込みを共有のスレッドで処理する"),
    "ZMK_BEHAVIORS_QUEUE_SIZE": ("エンコーダ", "behavior の待ち行列の長さ（既定 64）。エンコーダを速く回したときの取りこぼし対策"),
    "USB_HID_POLL_INTERVAL_MS": ("エンコーダ", "USB HID の問い合わせ間隔 (ms)"),
    "ZMK_MOUSE": ("ポインタ", "マウス機能の旧名（非推奨。ZMK_POINTING と同じ意味）"),
    "ZMK_POINTING": ("ポインタ", "マウス・ポインタ機能"),
    "SPI": ("ポインタ", "SPI バス（トラックパッド・トラックボールの接続に使う）"),
    "INPUT": ("ポインタ", "Zephyr の入力サブシステム"),
    "INPUT_INIT_PRIORITY": ("ポインタ", "入力デバイスを初期化する順番（小さいほど先）"),
    "INPUT_PINNACLE": ("ポインタ", "Cirque Pinnacle（トラックパッド）のドライバ"),
    "PMW3610_ALT": ("ポインタ", "PMW3610（トラックボール）のドライバ"),
    "PMW3610_ALT_REPORT_INTERVAL_MIN": ("ポインタ", "トラックボールの報告間隔の下限（既定 0）。無線で送りきれるよう間引く"),
    "NFCT_PINS_AS_GPIOS": ("ハードウェア", "NFC 用のピン（P0.09・P0.10）を普通のピンとして使う。列のピンに使っているので必須"),
    "RGBLED_WIDGET": ("LED", "RGB LED で電池残量と接続状態を表示する"),
    "RGBLED_WIDGET_BATTERY_LEVEL_HIGH": ("LED", "電池残量の色分けで「多い」とする下限 %（既定 80）"),
    "RGBLED_WIDGET_BATTERY_LEVEL_CRITICAL": ("LED", "電池残量の色分けで「危険」とする上限 %（既定 5）"),
    "ZMK_BATTERY_REPORTING": ("電池・電源", "電池残量を測って報告する"),
    "ZMK_SLEEP": ("電池・電源", "操作が無いと deep sleep に入る（既定 15 分）"),
    "BT_BAS": ("電池・電源", "Bluetooth の電池残量サービス（PC に残量を見せる）"),
    "ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY": ("電池・電源", "左の電池残量も PC に見せる"),
    "ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING": ("電池・電源", "左の電池残量を右が取得する"),
    "ZMK_USB_LOGGING": ("その他", "USB 経由のログ出力"),
}


def shield_src() -> str:
    return dts.strip_comments(read(SHIELD))


def side_of(path: Path) -> str:
    return "右" if "_R" in path.stem else "左"


def is_mine(path: Path) -> bool:
    return path.stem in my_targets()


def file_label(path: Path) -> str:
    return code(path.name) + (" " + badge("この機体", "ok") if is_mine(path) else "")


# ------------------------------------------------------------------ ハードウェア


@generator("matrix-pins")
def gen_matrix_pins(page: Page, args: dict[str, str]) -> str:
    kscan = dts.find_labeled(shield_src(), "kscan0") or ""
    rows_ = dts.gpios(dts.prop_raw(kscan, "row-gpios"))
    cols = {s: dts.gpios(dts.prop_raw(dts.find_node(dts.strip_comments(read(p)), "&kscan0") or "", "col-gpios")) for s, p in SIDE_DTSI.items()}
    out_rows = []
    for i, g in enumerate(rows_):
        out_rows.append(["行 %d" % i, pin(*g), pin(*g)])
    for i in range(max(len(c) for c in cols.values())):
        left = pin(*cols["左"][i]) if i < len(cols["左"]) else "—"
        right = pin(*cols["右"][i]) if i < len(cols["右"]) else "—"
        out_rows.append(["列 %d" % i, left, right])
    return table(["", "左", "右"], out_rows, sources(SHIELD, SIDE_DTSI["左"], SIDE_DTSI["右"]))


@generator("matrix-facts")
def gen_matrix_facts(page: Page, args: dict[str, str]) -> str:
    src = shield_src()
    kscan = dts.find_labeled(src, "kscan0") or ""
    tr = dts.find_labeled(src, "default_transform") or ""
    r_side = dts.find_node(dts.strip_comments(read(SIDE_DTSI["右"])), "&default_transform") or ""
    items = [
        ("ダイオードの向き", code(dts.prop_str(kscan, "diode-direction") or "?")),
        ("マトリクスの大きさ", "%s 行 × %s 列（左右合わせて）" % (dts.prop_int(tr, "rows"), dts.prop_int(tr, "columns"))),
        ("キーの数", "%d" % len(re.findall(r"RC\(", dts.prop_raw(tr, "map") or ""))),
        ("右の列のずらし", "col-offset %s（右の列 0〜5 がマトリクスの列 %s〜 になる）" % (dts.prop_int(r_side, "col-offset"), dts.prop_int(r_side, "col-offset"))),
    ]
    lis = "\n".join("<dt>%s</dt><dd>%s</dd>" % (k, v) for k, v in items)
    return '<div class="gen">\n<dl class="facts">\n%s\n</dl>\n<p class="gen-note">自動生成 · 元: %s</p>\n</div>' % (
        lis,
        sources(SHIELD, SIDE_DTSI["右"]),
    )


@generator("encoders")
def gen_encoders(page: Page, args: dict[str, str]) -> str:
    src = shield_src()
    enabled = {}
    for side, p in SIDE_DTSI.items():
        for m in re.finditer(r"&(\w+_encoder)\s*\{", dts.strip_comments(read(p))):
            enabled[m.group(1)] = side
    rows = []
    for label in ("left_encoder", "right_encoder"):
        body = dts.find_labeled(src, label) or ""
        a = dts.gpios(dts.prop_raw(body, "a-gpios"))
        b = dts.gpios(dts.prop_raw(body, "b-gpios"))
        rows.append(
            [
                code(label),
                enabled.get(label, "—"),
                pin(*a[0]) if a else "—",
                pin(*b[0]) if b else "—",
                esc(dts.prop_int(body, "steps")),
                esc(dts.prop_int(body, "resolution")),
            ]
        )
    sensors = dts.find_node(src, "sensors") or ""
    out = table(["ノード", "有効にする側", "A ピン", "B ピン", "steps", "resolution"], rows, sources(SHIELD, *SIDE_DTSI.values()))
    return out.replace(
        '<p class="gen-note">',
        "<p>1 回転あたりの発火数（triggers-per-rotation）: <strong>%s</strong></p>\n<p class=\"gen-note\">"
        % esc(dts.prop_int(sensors, "triggers-per-rotation")),
        1,
    )


@generator("pointing-devices")
def gen_pointing_devices(page: Page, args: dict[str, str]) -> str:
    src = shield_src()
    rows = []
    for bus, label in (("spi0", "glidepoint"), ("spi1", "trackball")):
        spi = dts.find_node(src, "&" + bus) or ""
        dev = dts.find_labeled(spi, label) or ""
        pinctrl = dts.find_labeled(src, bus + "_default") or ""
        pins = ["%s %s" % (f.replace("SPIM_", ""), pin(p, n)) for f, p, n in dts.psels(dts.prop_raw(pinctrl, "psels"))]
        cs = dts.gpios(dts.prop_raw(spi, "cs-gpios"))
        if cs:
            pins.append("CS %s" % pin(*cs[0]))
        for prop, name in (("data-ready-gpios", "DR"), ("irq-gpios", "IRQ")):
            g = dts.gpios(dts.prop_raw(dev, prop))
            if g:
                pins.append("%s %s" % (name, pin(*g[0])))
        settings = []
        if dts.prop_str(dev, "sensitivity"):
            settings.append("sensitivity %s" % code(dts.prop_str(dev, "sensitivity")))
        if dts.prop_int(dev, "cpi"):
            settings.append("cpi %s" % code(dts.prop_int(dev, "cpi")))
        for axis in ("x-input-code", "y-input-code"):
            v = dts.prop_raw(dev, axis)
            if v:
                settings.append("%s %s" % (axis, code(v.strip("<> "))))
        settings.append("最大 %s Hz" % format(dts.prop_int(dev, "spi-max-frequency") or 0, ","))
        rows.append(
            [
                "%s %s" % (DEVICE_NAMES[label], code(label)),
                code(dts.prop_str(dev, "compatible") or ""),
                code(bus),
                "<br>".join(pins),
                "<br>".join(settings),
            ]
        )
    return table(["デバイス", "ドライバ", "バス", "ピン", "設定"], rows, sources(SHIELD))


def overlay_nodes(path: Path) -> list[tuple[str, str, str]]:
    """overlay の `&name { ... }` を (名前, コメントを除いた中身, コメント込みの中身) で返す。"""
    raw = read(path)
    src = dts.strip_comments(raw)  # 位置を保ったまま潰すので、同じ範囲を raw から切り出せる
    out = []
    for m in re.finditer(r"&(\w+)\s*\{", src):
        open_idx = src.index("{", m.start())
        body, end = dts.match_brace(src, open_idx)
        if body is not None and end is not None:
            out.append((m.group(1), body, raw[open_idx + 1 : end - 1]))
    return out


@generator("pointer-overlays")
def gen_pointer_overlays(page: Page, args: dict[str, str]) -> str:
    rows, classes = [], []
    for path in sorted(SHIELD_DIR.glob("sosho_*.overlay"), key=lambda p: (not is_mine(p), p.stem)):
        enabled, notes = [], []
        for name, body, _ in overlay_nodes(path):
            if name in DEVICE_NAMES and '"okay"' in body:
                enabled.append("%s %s" % (DEVICE_NAMES[name], code(name)))
                for flag in ("invert-x", "invert-y", "swap-xy"):
                    if dts.prop_bool(body, flag):
                        notes.append(code(flag))
            m = re.search(r"&(\w+)", dts.prop_raw(body, "device") or "")
            if name.endswith("_split") and m:
                notes.append("%s の入力を右へ送る" % code(m.group(1)))
        rows.append([file_label(path), side_of(path), "、".join(enabled) or "—", "<br>".join(notes) or "—"])
        classes.append("" if is_mine(path) else "dim")
    return table(["overlay", "側", "有効にするデバイス", "向き・その他"], rows, "<code>boards/shields/sosho/*.overlay</code>", classes)


@generator("input-listeners")
def gen_input_listeners(page: Page, args: dict[str, str]) -> str:
    left_pointer = next(("trackball" if "trackball" in t else "trackpad" for t in my_targets() if "_L_" in t), "")
    rows, classes = [], []
    for path in sorted(SHIELD_DIR.glob("sosho_R_*.overlay"), key=lambda p: (not is_mine(p), p.stem)):
        right_pointer = "trackball" if "trackball" in path.stem else "trackpad"
        for name, body, raw in overlay_nodes(path):
            if name not in LISTENERS:
                continue
            what, side, kind = LISTENERS[name]
            used = is_mine(path) and kind == (right_pointer if side == "R" else left_pointer)
            procs = dts.prop_raw(body, "input-processors")
            examples = re.findall(r"//\s*input-processors\s*=\s*(.+?);", raw)
            rows.append(
                [
                    code(path.name),
                    code(name) + (" " + badge("この機体", "ok") if used else ""),
                    esc(what),
                    code(procs) if procs else "なし（そのまま）",
                    "<br>".join(code(e) for e in examples) or "—",
                ]
            )
            classes.append("" if used else "dim")
    return table(
        ["overlay", "リスナー", "受ける入力", "input-processors（有効）", "コメントアウト中の例"],
        rows,
        "<code>boards/shields/sosho/sosho_R_*.overlay</code>",
        classes,
    )


# ------------------------------------------------------------------ Kconfig


def conf_values(path: Path) -> dict[str, list[str]]:
    """有効な `CONFIG_X=値` を、宣言順の値のリストで返す（2 回宣言されていれば 2 個）。"""
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"^CONFIG_(\w+)=(.*?)\s*$", read(path), re.M):
        out.setdefault(m.group(1), []).append(m.group(2))
    return out


def fmt_kconfig(sym: str, v: str) -> str:
    """単位のある値は人が読める形を添える。"""
    extra = ""
    if v.isdigit():
        n = int(v)
        if sym in ("BT_PERIPHERAL_PREF_MIN_INT", "BT_PERIPHERAL_PREF_MAX_INT"):
            extra = "%g ms" % (n * 1.25)
        elif sym == "BT_PERIPHERAL_PREF_TIMEOUT":
            extra = "%g 秒" % (n / 100)
        elif sym in ("PMW3610_ALT_REPORT_INTERVAL_MIN", "USB_HID_POLL_INTERVAL_MS"):
            extra = "ms"
        elif sym.startswith("RGBLED_WIDGET_BATTERY_LEVEL"):
            extra = "%"
    return code(v) + (" <small>%s</small>" % extra if extra else "")


@generator("kconfig-matrix")
def gen_kconfig_matrix(page: Page, args: dict[str, str]) -> str:
    files = conf_files()
    values = {p: conf_values(p) for p in files}
    syms: list[str] = []
    for p in files:
        for s in values[p]:
            if s not in syms:
                syms.append(s)
    order = {g: i for i, g in enumerate(KCONFIG_GROUPS)}
    first_seen = {s: i for i, s in enumerate(syms)}
    syms.sort(key=lambda s: (order[KCONFIG_NOTES.get(s, ("その他", ""))[0]], first_seen[s]))
    head = ["設定"] + [file_label(p).replace(".conf", "") for p in files]
    rows, classes, group = [], [], None
    for s in syms:
        g, note = KCONFIG_NOTES.get(s, ("その他", ""))
        if g != group:
            rows.append(["<strong>%s</strong>" % esc(g)])
            classes.append("group")
            group = g
        cells, seen = [], set()
        for p in files:
            vs = values[p].get(s)
            if not vs:
                cells.append("—")
                continue
            seen.add(vs[-1])
            cell = fmt_kconfig(s, vs[-1])
            if len(vs) > 1:
                cell += " " + badge("%d 回宣言・後勝ち" % len(vs), "warn")
            cells.append(cell)
        rows.append([code(s) + ('<span class="note">%s</span>' % esc(note) if note else "")] + cells)
        classes.append("diff" if len(seen) > 1 or "—" in cells else "")
    return table(head, rows, "<code>boards/shields/sosho/*.conf</code>（CONFIG_ は省略）", classes)


@generator("kconfig-defaults")
def gen_kconfig_defaults(page: Page, args: dict[str, str]) -> str:
    text = read(DEFCONFIG)
    rows = []
    for m in re.finditer(r"^if (.+?)\n(.*?)^endif", text, re.S | re.M):
        side = "右" if "_R_" in m.group(1) else "左"
        for sym, val in re.findall(r"config (\w+)\s+default (.+)", m.group(2)):
            rows.append([side, code(sym), code(val.strip()), esc(KCONFIG_NOTES.get(sym, ("", "—"))[1])])
    return table(["側", "設定", "既定値", "説明"], rows, sources(DEFCONFIG))


# ------------------------------------------------------------------ 現在値（本文に埋め込む 1 つの値）


def _value(key: str) -> str:
    km = keymap_src()
    src = shield_src()

    def s(v: object) -> str:
        return "" if v is None else str(v)  # 0 も正しい値なので `or` で潰さない

    if key == "scrl-val":
        return dts.defines(km).get("ZMK_POINTING_DEFAULT_SCRL_VAL", "")
    if key in ("msc-time-to-max", "msc-accel"):
        prop = {"msc-time-to-max": "time-to-max-speed-ms", "msc-accel": "acceleration-exponent"}[key]
        return s(dts.prop_int(dts.find_node(km, "&msc") or "", prop))
    if key == "trackball-cpi":
        return s(dts.prop_int(dts.find_labeled(src, "trackball") or "", "cpi"))
    if key == "trackpad-sensitivity":
        return s(dts.prop_str(dts.find_labeled(src, "glidepoint") or "", "sensitivity"))
    if key in ("encoder-steps", "encoder-resolution"):
        return s(dts.prop_int(dts.find_labeled(src, "left_encoder") or "", key.split("-")[1]))
    if key == "encoder-triggers":
        return s(dts.prop_int(dts.find_node(src, "sensors") or "", "triggers-per-rotation"))
    raise ValueError("未知の値 %s" % key)


@generator("value")
def gen_value(page: Page, args: dict[str, str]) -> str:
    key = args.get("of", "")
    if key == "my-targets":
        t = my_targets()
        return "右 %s ／ 左 %s" % (
            " ".join(code(x) for x in t if "_R_" in x),
            " ".join(code(x) for x in t if "_L_" in x),
        )
    v = _value(key)
    if v == "":
        raise ValueError("%s の値が見つかりません" % key)
    return code(v)
