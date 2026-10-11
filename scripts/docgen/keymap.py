"""キーマップ: レイヤー図、キー位置番号、コンボ、エンコーダの割り当て、キーマップ内の behavior 定義。

キーの並びは物理レイアウト（sosho-layouts.dtsi）の座標から描くので、配列が変わっても追従する。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import zmk_dts as dts

from .common import KEYMAP, SHIELD_DIR, Page, code, esc, generator, read, sources, table, source_note

LAYOUTS = SHIELD_DIR / "sosho-layouts.dtsi"
SHIELD = SHIELD_DIR / "sosho.dtsi"

SENSOR_NAMES = {"left_encoder": "左エンコーダ", "right_encoder": "右エンコーダ"}

# キーコードの表示名。ここに無いものはキーコード名をそのまま出す。
KEY_LABELS = {
    "TAB": "Tab", "BSPC": "BS", "BACKSPACE": "BS", "ENTER": "Enter", "RET": "Enter", "RETURN": "Enter",
    "ESC": "Esc", "ESCAPE": "Esc", "SPACE": "Space", "SPC": "Space", "DEL": "Del", "DELETE": "Del",
    "INS": "Ins", "INSERT": "Ins", "CAPS": "Caps", "CAPSLOCK": "Caps", "PSCRN": "PrtSc",
    "LCTRL": "Ctrl", "LCTL": "Ctrl", "RCTRL": "Ctrl", "RCTL": "Ctrl",
    "LSHFT": "Shift", "LSHIFT": "Shift", "RSHFT": "Shift", "RSHIFT": "Shift",
    "LALT": "Alt", "RALT": "Alt", "LGUI": "GUI", "RGUI": "GUI", "LCMD": "GUI", "RCMD": "GUI",
    "PG_UP": "PgUp", "PG_DN": "PgDn", "HOME": "Home", "END": "End",
    "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→",
    "GRAVE": "`", "TILDE": "~", "MINUS": "-", "UNDER": "_", "EQUAL": "=", "PLUS": "+",
    "LBKT": "[", "RBKT": "]", "LBRC": "{", "RBRC": "}", "BSLH": "\\", "PIPE": "|", "NUBS": "ISO \\",
    "SEMI": ";", "SEMICOLON": ";", "COLON": ":", "SQT": "'", "APOS": "'", "DQT": '"',
    "COMMA": ",", "DOT": ".", "PERIOD": ".", "SLASH": "/", "FSLH": "/", "QMARK": "?", "LT": "<", "GT": ">",
    "EXCL": "!", "AT": "@", "HASH": "#", "DLLR": "$", "PRCNT": "%", "CARET": "^", "AMPS": "&",
    "STAR": "*", "ASTRK": "*", "LPAR": "(", "RPAR": ")",
    "LANG1": "かな", "LANG2": "英数", "INT_YEN": "¥", "INT_RO": "ろ", "K_APP": "Menu",
    "C_VOL_UP": "音量+", "C_VOL_DN": "音量−", "C_MUTE": "消音", "C_PP": "再生/停止",
    "C_NEXT": "次の曲", "C_PREV": "前の曲", "C_BRI_UP": "明るさ+", "C_BRI_DN": "明るさ−",
}
MOD_FUNCS = {"LA": "Alt", "RA": "Alt", "LC": "Ctrl", "RC": "Ctrl", "LS": "Shift", "RS": "Shift", "LG": "GUI", "RG": "GUI"}
MOUSE_LABELS = {
    "LCLK": "左クリック", "RCLK": "右クリック", "MCLK": "中クリック", "MB4": "戻る", "MB5": "進む",
    "SCRL_UP": "スクロール↑", "SCRL_DOWN": "スクロール↓", "SCRL_LEFT": "スクロール←", "SCRL_RIGHT": "スクロール→",
    "MOVE_UP": "カーソル↑", "MOVE_DOWN": "カーソル↓", "MOVE_LEFT": "カーソル←", "MOVE_RIGHT": "カーソル→",
}
LAYER_BEHAVIORS = {"&mo": "押している間", "&lt": "長押し", "&to": "切り替え", "&tog": "オン/オフ", "&sl": "次の 1 キーだけ"}


# ------------------------------------------------------------------ 読み取り


@dataclass
class Layer:
    index: int
    name: str
    reserved: bool
    keys: list[list[str]]
    sensors: list[list[str]] | None


@dataclass
class Combo:
    name: str
    positions: list[int]
    binding: list[str]
    timeout: int | None


def keymap_src() -> str:
    return dts.strip_comments(read(KEYMAP))


def layers() -> list[Layer]:
    km = dts.find_node(keymap_src(), "keymap") or ""
    out = []
    for i, (name, body) in enumerate(dts.child_nodes(km)):
        cells = dts.prop_cells(body, "bindings")
        sens = dts.prop_cells(body, "sensor-bindings")
        out.append(
            Layer(
                i,
                name,
                re.search(r'status\s*=\s*"reserved"', body) is not None,
                dts.groups(cells[0]) if cells else [],
                dts.groups(sens[0]) if sens else None,
            )
        )
    return out


def combos() -> list[Combo]:
    node = dts.find_node(keymap_src(), "combos") or ""
    out = []
    for name, body in dts.child_nodes(node):
        pos = dts.prop_cells(body, "key-positions")
        b = dts.prop_cells(body, "bindings")
        out.append(
            Combo(
                name,
                [int(p) for p in pos[0].split()] if pos else [],
                dts.groups(b[0])[0] if b and dts.groups(b[0]) else [],
                dts.prop_int(body, "timeout-ms"),
            )
        )
    return out


def physical_keys() -> list[tuple[int, int, int, int, int, int, int]]:
    """物理レイアウトのキー (w, h, x, y, rot, rx, ry)。キーマップの並び順と同じ。"""
    text = dts.strip_comments(read(LAYOUTS))
    pat = r"&key_physical_attrs" + r"\s+(-?\d+)" * 7
    return [tuple(int(v) for v in m.groups()) for m in re.finditer(pat, text)]  # type: ignore[misc]


def sensor_names() -> list[str]:
    text = dts.strip_comments(read(SHIELD))
    raw = dts.prop_raw(dts.find_node(text, "sensors") or "", "sensors")
    return [SENSOR_NAMES.get(l, l) for l in re.findall(r"&(\w+)", raw or "")]


# ------------------------------------------------------------------ 表示名


def key_label(kc: str) -> str:
    m = re.fullmatch(r"([LR][ACSG])\((.+)\)", kc)
    if m and m.group(1) in MOD_FUNCS:
        return MOD_FUNCS[m.group(1)] + "+" + key_label(m.group(2))
    m = re.fullmatch(r"N(?:UMBER_)?(\d)", kc)
    if m:
        return m.group(1)
    return KEY_LABELS.get(kc, kc)


def binding_label(b: list[str]) -> tuple[str, str, str]:
    """バインディング 1 つを (主表示, 補足, 種類) にする。種類は CSS のクラス名に使う。"""
    if not b:
        return "", "", "none"
    name, p = b[0], b[1:]
    if name == "&kp" and p:
        return key_label(p[0]), "", ""
    if name == "&trans":
        return "", "", "trans"
    if name == "&none":
        return "—", "", "none"
    if name in ("&mo", "&to", "&tog", "&sl") and p:
        return "L" + p[0], LAYER_BEHAVIORS[name], "layer"
    if name == "&lt" and len(p) >= 2:
        return key_label(p[1]), "長押し L" + p[0], "layer"
    if name == "&mt" and len(p) >= 2:
        return key_label(p[1]), "長押し " + key_label(p[0]), ""
    if name == "&sk" and p:
        return key_label(p[0]), "次の 1 キーだけ", ""
    if name == "&bt" and p:
        if p[0] == "BT_SEL" and len(p) > 1:
            return "BT " + p[1], "接続先", "system"
        return {"BT_CLR": "消去", "BT_CLR_ALL": "全消去", "BT_NXT": "BT 次", "BT_PRV": "BT 前"}.get(
            p[0], " ".join(p)
        ), {"BT_CLR": "BT いまの接続先", "BT_CLR_ALL": "BT 全接続先"}.get(p[0], ""), "system"
    if name == "&out" and p:
        return {"OUT_BLE": "BLE", "OUT_USB": "USB", "OUT_TOG": "USB/BLE"}.get(p[0], p[0]), "出力先", "system"
    if name in ("&mkp", "&msc", "&mmv") and p:
        return MOUSE_LABELS.get(p[0], p[0]), "", "mouse"
    simple = {
        "&caps_word": ("Caps Word", "", ""),
        "&key_repeat": ("リピート", "", ""),
        "&studio_unlock": ("Studio", "ロック解除", "system"),
        "&bootloader": ("Boot", "書き込みモード", "system"),
        "&sys_reset": ("Reset", "再起動", "system"),
    }
    if name in simple:
        return simple[name]
    return name[1:], " ".join(p), ""


def sensor_param_label(param: str) -> str:
    return MOUSE_LABELS.get(param) or key_label(param)


# ------------------------------------------------------------------ 描画


def _pct(v: float, total: float) -> str:
    return ("%.3f" % (v / total * 100)).rstrip("0").rstrip(".")


def keyboard(cells: list[tuple[str, str, str, str]], label: str) -> str:
    """cells[i] = (主表示 HTML, 補足 HTML, 種類, ツールチップ) をキー位置 i に置いたキーボード図。"""
    keys = physical_keys()
    width = max(x + w for w, h, x, y, *_ in keys)
    height = max(y + h for w, h, x, y, *_ in keys)
    out = [
        '<div class="kb-scroll">',
        '<div class="kb" role="img" aria-label="%s" style="aspect-ratio: %d / %d">' % (esc(label), width, height),
    ]
    for i, (w, h, x, y, rot, rx, ry) in enumerate(keys):
        main, sub, kind, tip = cells[i] if i < len(cells) else ("", "", "none", "")
        style = "left:%s%%;top:%s%%;width:%s%%;height:%s%%" % (
            _pct(x, width), _pct(y, height), _pct(w, width), _pct(h, height)
        )
        if rot:  # 回転は 1/100 度、回転の中心 rx, ry はレイアウト座標
            style += ";transform-origin:%s%% %s%%;transform:rotate(%sdeg)" % (
                _pct(rx - x, w), _pct(ry - y, h), rot / 100
            )
        out.append(
            '<div class="key%s" style="%s"%s><span class="pos">%d</span><span class="main">%s</span>%s</div>'
            % (
                " " + kind if kind else "",
                style,
                ' title="%s"' % esc(tip) if tip else "",
                i,
                main,
                '<span class="sub">%s</span>' % sub if sub else "",
            )
        )
    out += ["</div>", "</div>"]
    return "\n".join(out)


def ascii_map(labels: list[str], width: int) -> str:
    """1 キー = 1 マスの文字の図。キーの無い列（左右の間）は │ にする。"""
    keys = physical_keys()
    cols = max(round(x / 100) for w, h, x, y, *_ in keys) + 1
    rows = max(round(y / 100) for w, h, x, y, *_ in keys) + 1
    grid: list[list[str | None]] = [[None] * cols for _ in range(rows)]
    for i, (w, h, x, y, *_) in enumerate(keys):
        grid[round(y / 100)][round(x / 100)] = labels[i] if i < len(labels) else ""
    gaps = {c for c in range(cols) if all(grid[r][c] is None for r in range(rows))}
    lines = []
    for r in range(rows):
        parts = []
        for c in range(cols):
            if c in gaps:
                parts.append("  │")
            else:
                parts.append((grid[r][c] or "")[:width].rjust(width))
        lines.append("".join(parts).rstrip())
    return "\n".join(lines)


def reach_sources(ls: list[Layer], target: int) -> list[tuple[int, int, str]]:
    """レイヤー target に切り替えるキーを (元のレイヤー, キー位置, behavior) で列挙する。"""
    out = []
    for layer in ls:
        for pos, b in enumerate(layer.keys):
            if b[0] in LAYER_BEHAVIORS and len(b) > 1 and b[1] == str(target):
                out.append((layer.index, pos, b[0]))
    return out


def reach(ls: list[Layer], target: int) -> list[str]:
    """レイヤー target に切り替えるキーを「L0 の 38 番（押している間）」の形で列挙する。"""
    return ["L%d の %d 番（%s）" % (src, pos, LAYER_BEHAVIORS[b]) for src, pos, b in reach_sources(ls, target)]


def base_layer(ls: list[Layer], layer: Layer) -> Layer | None:
    """このレイヤーが有効なときに、すぐ下で有効になっているレイヤー。

    番号が 1 つ下のレイヤーとは限らない。L0 の &mo 3 で L3 を出したなら、
    有効なのは L0 と L3 だけなので、透過キーやエンコーダは L0 に落ちる。
    切り替え元が 1 つに決まればそれを、決まらなければ L0 を返す。
    """
    if layer.index == 0:
        return None
    srcs = {src for src, _, _ in reach_sources(ls, layer.index) if src < layer.index}
    return ls[srcs.pop()] if len(srcs) == 1 else ls[0]


def effective_key(ls: list[Layer], layer: Layer, pos: int) -> list[str]:
    """透過キーをたどって、実際に効くバインディングを返す。"""
    cur: Layer | None = layer
    while cur is not None:
        if pos < len(cur.keys) and cur.keys[pos][0] != "&trans":
            return cur.keys[pos]
        cur = base_layer(ls, cur)
    return []


def layer_cells(ls: list[Layer], layer: Layer) -> list[tuple[str, str, str, str]]:
    cells = []
    for pos, b in enumerate(layer.keys):
        main, sub, kind = binding_label(b)
        tip = " ".join(b)
        if kind == "trans":
            # 透過キーは、下のレイヤーで実際に効くキーを薄く出す
            below = effective_key(ls, layer, pos)
            main = binding_label(below)[0] if below else ""
            tip = "&trans（下のレイヤーと同じ: %s）" % " ".join(below)
        cells.append((esc(main), esc(sub), kind, tip))
    return cells


def sensor_lines(ls: list[Layer], layer: Layer) -> str:
    names = sensor_names()
    if layer.sensors is None:
        below = base_layer(ls, layer)
        while below is not None and below.sensors is None:
            below = base_layer(ls, below)
        where = "L%d" % below.index if below else "下のレイヤー"
        return '<p class="sensors">エンコーダ: このレイヤーには割り当てなし（%s の割り当てが効く）</p>' % where
    items = []
    for i, g in enumerate(layer.sensors):
        name = names[i] if i < len(names) else "センサ %d" % i
        if len(g) >= 3:
            items.append(
                "<li>%s: 時計回り → <strong>%s</strong> ／ 反時計回り → <strong>%s</strong> <small>%s</small></li>"
                % (esc(name), esc(sensor_param_label(g[1])), esc(sensor_param_label(g[2])), esc(g[0]))
            )
        else:
            items.append("<li>%s: %s</li>" % (esc(name), code(" ".join(g))))
    return '<ul class="sensors">\n%s\n</ul>' % "\n".join(items)


# ------------------------------------------------------------------ 生成器


@generator("keymap-layers")
def gen_keymap_layers(page: Page, args: dict[str, str]) -> str:
    ls = layers()
    out = ['<div class="gen">']
    for layer in ls:
        if layer.reserved:
            continue
        how = reach(ls, layer.index)
        if layer.index == 0:
            how_text = "いちばん下のレイヤー（常に有効）"
        else:
            how_text = "、".join(how) if how else "切り替えるキーが無い"
        out += [
            '<section class="layer" id="layer-%d">' % layer.index,
            "<h3>L%d %s</h3>" % (layer.index, code(layer.name)),
            '<p class="layer-how">%s</p>' % esc(how_text),
            keyboard(layer_cells(ls, layer), "レイヤー L%d %s" % (layer.index, layer.name)),
            sensor_lines(ls, layer),
            "</section>",
        ]
    reserved = [l for l in ls if l.reserved]
    if reserved:
        out.append(
            '<p class="reserved">%s は <code>status = "reserved"</code> の空き枠（ZMK Studio でレイヤーを増やすときに使われる）。</p>'
            % "、".join("L%d %s" % (l.index, code(l.name)) for l in reserved)
        )
    out += [source_note(sources(KEYMAP, LAYOUTS)), "</div>"]
    return "\n".join(out)


@generator("key-positions")
def gen_key_positions(page: Page, args: dict[str, str]) -> str:
    ls = layers()
    base = ls[0].keys if ls else []
    labels = [binding_label(b)[0] or "▽" for b in base]
    cells = [(str(i), esc(labels[i]) if i < len(labels) else "", "positions", "") for i in range(len(physical_keys()))]
    numbers = [str(i) for i in range(len(physical_keys()))]
    text = ascii_map(numbers, 4) + "\n\n" + ascii_map(labels, 6)
    return "\n".join(
        [
            '<div class="gen">',
            keyboard(cells, "キー位置番号"),
            "<details>",
            "<summary>テキスト版（コピー用・AI 用）</summary>",
            "<pre><code>%s</code></pre>" % esc(text),
            "</details>",
            source_note(sources(LAYOUTS, KEYMAP) + "（下段は L0 の割り当て）"),
            "</div>",
        ]
    )


@generator("combos")
def gen_combos(page: Page, args: dict[str, str]) -> str:
    ls = layers()
    base = ls[0].keys if ls else []
    rows = []
    for c in combos():
        keys = " + ".join(binding_label(base[p])[0] if p < len(base) else "?" for p in c.positions)
        main, sub, _ = binding_label(c.binding)
        rows.append(
            [
                code(c.name),
                esc(" ".join(str(p) for p in c.positions)),
                esc(keys),
                esc(main) + (" <small>%s</small>" % esc(sub) if sub else "") + " " + code(" ".join(c.binding)),
                "%d ms" % c.timeout if c.timeout is not None else "既定",
            ]
        )
    return table(["コンボ", "キー位置", "同時に押すキー（L0）", "動作", "判定時間"], rows, sources(KEYMAP))


@generator("keymap-behaviors")
def gen_keymap_behaviors(page: Page, args: dict[str, str]) -> str:
    src = keymap_src()
    rows = []
    for name, value in dts.defines(src).items():
        rows.append(["マクロ", code(name), code(value)])
    for label, node, body in dts.labeled_nodes(dts.find_node(src, "behaviors") or ""):
        compat = dts.prop_str(body, "compatible") or ""
        used = len(re.findall(r"&%s\b" % re.escape(label or node), src))
        rows.append(["behavior の定義", code("&%s" % (label or node)), "%s（キーマップ内で %d 回使用）" % (code(compat), used)])
    for m in re.finditer(r"(?m)^\s*&(\w+)\s*\{", src):
        body, _ = dts.match_brace(src, src.index("{", m.start()))
        props = [p.strip() for p in (body or "").split(";") if p.strip()]
        rows.append(["既存 behavior の上書き", code("&" + m.group(1)), "<br>".join(code(p) for p in props)])
    return table(["種類", "名前", "内容"], rows, sources(KEYMAP))
