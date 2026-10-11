"""既知の課題が、いまもリポジトリに残っているかを調べる。

known-issues.html の各課題（`<h2 id="issue-ID">`）に対応するチェックをここに置く。
直した課題は資料の表示が自動で「解消済み」に変わるので、それを見て節ごと消し、チェックも消す。
ファイルから判定できない課題（実機の操作感など）は、常に「未修正」を返すチェックにする。
"""
from __future__ import annotations

import re
from typing import Callable

from .common import Page, badge, code, esc, generator, read

# チェックは (残っているか, 補足) を返す
Check = Callable[[], "tuple[bool, str]"]
CHECKS: dict[str, Check] = {}


def check(issue_id: str) -> Callable[[Check], Check]:
    def deco(fn: Check) -> Check:
        CHECKS[issue_id] = fn
        return fn

    return deco


def active_lines(path, pattern: str) -> list[str]:
    """コメント行（# 始まり）を除いて、pattern に当たる行を返す。"""
    return [l for l in read(path).splitlines() if not l.lstrip().startswith("#") and re.search(pattern, l)]


def status_html(issue_id: str) -> str:
    fn = CHECKS.get(issue_id)
    if fn is None:
        raise ValueError("課題 %s のチェックが scripts/docgen/issues.py にありません" % issue_id)
    remains, detail = fn()
    if not remains:
        return badge("解消済み", "ok")
    return badge("未修正", "warn") + (" <small>%s</small>" % esc(detail) if detail else "")


@generator("issue-status")
def gen_issue_status(page: Page, args: dict[str, str]) -> str:
    return status_html(args.get("id", ""))


@generator("issue-summary")
def gen_issue_summary(page: Page, args: dict[str, str]) -> str:
    rows = []
    for issue_id, title in re.findall(r'<h2 id="issue-([\w-]+)">(.*?)</h2>', page.text, re.S):
        rows.append('<tr><td><a href="#issue-%s">%s</a></td><td>%s</td></tr>' % (issue_id, title, status_html(issue_id)))
    note = '<p class="gen-note">自動生成 · 状態は %s がファイルを調べて判定</p>' % code("scripts/docgen/issues.py")
    if not rows:
        return "\n".join(['<div class="gen">', "<p>いま、未解決の課題はありません。</p>", note, "</div>"])
    return "\n".join(
        [
            '<div class="gen">',
            '<div class="table-wrap">',
            "<table>",
            "<thead><tr><th>課題</th><th>状態</th></tr></thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
            "</div>",
            note,
            "</div>",
        ]
    )
