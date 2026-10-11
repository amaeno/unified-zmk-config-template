"""CLAUDE.md の一部を資料に載せるための、小さな Markdown 変換器。

CLAUDE.md で使っている範囲（段落・箇条書き・表・コードブロック・### 見出し）だけを扱う。
"""
from __future__ import annotations

import re

from .common import code, esc


def inline(s: str) -> str:
    out = []
    for part in re.split(r"(`[^`]+`)", s):
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(code(part[1:-1]))
            continue
        t = esc(part)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
        out.append(t)
    return "".join(out)


def join_lines(lines: list[str]) -> str:
    """改行で折った文をつなぐ。日本語の途中に空白を入れないよう、英数字どうしのときだけ空白を挟む。"""
    out = ""
    for line in lines:
        if out and re.match(r"[\x21-\x7e]", out[-1]) and re.match(r"[\x21-\x7e]", line[0]):
            out += " "
        out += line
    return out


def table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ['<div class="table-wrap">', "<table>"]
    out.append("<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % inline(c) for c in head))
    out.append("<tbody>")
    out += ["<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in body]
    out += ["</tbody>", "</table>", "</div>"]
    return "\n".join(out)


def to_html(md: str) -> str:
    out: list[str] = []
    para: list[str] = []
    items: list[list[str]] = []
    rows: list[str] = []
    fence: list[str] | None = None

    def flush() -> None:
        if para:
            out.append("<p>%s</p>" % inline(join_lines(para)))
            para.clear()
        if items:
            lis = "\n".join("<li>%s</li>" % inline(join_lines(i)) for i in items)
            out.append("<ul>\n%s\n</ul>" % lis)
            items.clear()
        if rows:
            out.append(table(rows))
            rows.clear()

    for line in md.splitlines():
        if fence is not None:
            if line.startswith("```"):
                out.append("<pre><code>%s</code></pre>" % esc("\n".join(fence)))
                fence = None
            else:
                fence.append(line)
            continue
        s = line.strip()
        if line.startswith("```"):
            flush()
            fence = []
        elif not s or re.fullmatch(r"-{3,}|\*{3,}", s):
            flush()  # 空行と区切り線（節の境目にしか使っていない）
        elif s.startswith("|"):
            if not rows:
                flush()
            rows.append(s)
        elif re.match(r"#{3,6}\s", s):
            flush()
            level = len(s) - len(s.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (level, inline(s[level:].strip()), level))
        elif re.match(r"[-*]\s", line):
            if para or rows:
                flush()
            items.append([s[2:].strip()])
        elif items and line.startswith(" "):
            items[-1].append(s)
        else:
            if items or rows:
                flush()
            para.append(s)
    flush()
    return "\n".join(out)
