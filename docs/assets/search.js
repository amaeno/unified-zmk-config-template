/* 双掌 (sosho) 資料のフリーワード検索。
   索引は assets/search-index.js（scripts/gen-docs.py が作る window.SOSHO_SEARCH_INDEX）。
   ナビの「資料を検索」か、入力欄の外で / を押すと開く。
   スペースで区切った語をすべて含む節を、見出しに含むものから順に並べる。 */
(function () {
  "use strict";

  var MAX_RESULTS = 30;
  var index = (window.SOSHO_SEARCH_INDEX || []).map(function (e) {
    return { e: e, h: norm(e.h), t: norm(e.t), x: norm(e.x) };
  });

  function norm(s) {
    // 全角英数を半角に、大文字を小文字にそろえる
    return (s || "").normalize("NFKC").toLowerCase();
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function search(query) {
    var terms = norm(query).split(/\s+/).filter(Boolean);
    if (!terms.length) return { terms: terms, hits: [] };
    var hits = [];
    index.forEach(function (p) {
      var score = 0;
      for (var i = 0; i < terms.length; i++) {
        var t = terms[i];
        var inH = p.h.indexOf(t) >= 0;
        var inT = p.t.indexOf(t) >= 0;
        var inX = p.x.indexOf(t) >= 0;
        if (!inH && !inT && !inX) return; // すべての語を含むものだけ
        score += (inH ? 10 : 0) + (inT ? 2 : 0) + (inX ? 1 : 0);
      }
      hits.push({ p: p, score: score });
    });
    hits.sort(function (a, b) {
      return b.score - a.score;
    });
    return { terms: terms, hits: hits.slice(0, MAX_RESULTS) };
  }

  function snippet(p, terms) {
    var text = p.e.x;
    var at = -1;
    for (var i = 0; i < terms.length && at < 0; i++) at = p.x.indexOf(terms[i]);
    var start = Math.max(0, at - 30);
    var part = (start > 0 ? "…" : "") + text.slice(start, start + 110) + (start + 110 < text.length ? "…" : "");
    var html = escapeHtml(part);
    terms.forEach(function (t) {
      if (t) html = html.replace(new RegExp("(" + escapeRe(escapeHtml(t)) + ")", "gi"), "<mark>$1</mark>");
    });
    return html;
  }

  var dialog, input, list, selected = 0;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "search-dialog";
    dialog.setAttribute("aria-label", "資料を検索");
    dialog.innerHTML =
      '<input type="search" placeholder="キーワード（スペースで区切ると絞り込み）" aria-label="キーワード">' +
      '<ol class="search-results" role="listbox"></ol>';
    document.body.appendChild(dialog);
    input = dialog.querySelector("input");
    list = dialog.querySelector(".search-results");
    input.addEventListener("input", update);
    input.addEventListener("keydown", onKey);
    dialog.addEventListener("click", function (ev) {
      if (ev.target === dialog) dialog.close(); // 外側（背景）を押したら閉じる
    });
    list.addEventListener("click", function (ev) {
      if (ev.target.closest("a")) dialog.close();
    });
  }

  function update() {
    var r = search(input.value);
    selected = 0;
    if (!input.value.trim()) {
      list.innerHTML = '<li class="search-empty">ページ名・見出し・本文（表の中身を含む）から探します</li>';
      return;
    }
    if (!r.hits.length) {
      list.innerHTML = '<li class="search-empty">見つかりませんでした</li>';
      return;
    }
    list.innerHTML = r.hits
      .map(function (h, i) {
        var e = h.p.e;
        var where = e.a ? escapeHtml(e.t) + " › " + escapeHtml(e.h) : escapeHtml(e.t);
        return (
          '<li><a href="' + e.p + (e.a ? "#" + e.a : "") + '" role="option" aria-selected="' + (i === 0) + '">' +
          '<span class="sr-where">' + where + "</span>" +
          '<span class="sr-snippet">' + snippet(h.p, r.terms) + "</span></a></li>"
        );
      })
      .join("");
  }

  function onKey(ev) {
    var links = list.querySelectorAll("a");
    if (!links.length) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      links[selected].setAttribute("aria-selected", "false");
      selected = (selected + (ev.key === "ArrowDown" ? 1 : links.length - 1)) % links.length;
      links[selected].setAttribute("aria-selected", "true");
      links[selected].scrollIntoView({ block: "nearest" });
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      dialog.close();
      links[selected].click();
    }
  }

  function open() {
    if (!dialog) build();
    dialog.showModal();
    input.select();
    update();
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest("[data-search-open]")) open();
  });
  document.addEventListener("keydown", function (ev) {
    var typing = /^(input|textarea|select)$/i.test(ev.target.tagName) || ev.target.isContentEditable;
    if (ev.key === "/" && !typing && !(dialog && dialog.open)) {
      ev.preventDefault();
      open();
    }
  });
})();
