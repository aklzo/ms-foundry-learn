"""シナリオ定義 → 研修動画用モック画面 HTML の生成。

CU のフレーム制約(約 1 FPS サンプリング・512×512 縮小)を前提に、
文字はすべて大きめ(本文 26px〜、ダイアログ見出し 40px)にする。
画面操作は record.py が window.applyOp(op) を 1 op ずつ呼んで進める。
"""

from __future__ import annotations

import json
from pathlib import Path

from .scenarios import Scenario

_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Noto Sans CJK JP", "Yu Gothic UI", Meiryo, sans-serif;
         background: #eef1f5; width: 1280px; height: 720px; overflow: hidden; }
  header { background: #1f4e79; color: #fff; height: 72px; display: flex;
           align-items: center; justify-content: space-between; padding: 0 32px; }
  header .app { font-size: 30px; font-weight: bold; }
  header .lesson { font-size: 22px; opacity: .85; }
  main { padding: 36px 48px; }
  #screen-title { font-size: 40px; font-weight: bold; color: #1a1a1a; }
  #screen-subtitle { font-size: 24px; color: #555; margin-top: 8px; min-height: 30px; }
  #list { margin-top: 28px; display: flex; flex-direction: column; gap: 14px; max-width: 560px; }
  #list button, #actions button {
    font-size: 27px; padding: 14px 26px; text-align: left; background: #fff;
    border: 2px solid #b8c4d0; border-radius: 8px; cursor: default; }
  #fields { margin-top: 28px; display: flex; flex-direction: column; gap: 16px; max-width: 720px; }
  .field { display: flex; align-items: center; gap: 20px; }
  .field label { width: 280px; font-size: 26px; color: #333; }
  .field .val { flex: 1; font-size: 27px; background: #fff; border: 2px solid #b8c4d0;
                border-radius: 6px; padding: 12px 16px; min-height: 56px; }
  .field .val.placeholder { color: #999; }
  #note { position: absolute; right: 40px; top: 140px; width: 380px; background: #fff8dc;
          border: 3px solid #e0a800; border-radius: 10px; padding: 20px 24px;
          font-size: 25px; line-height: 1.5; color: #333; display: none; }
  #toast { position: absolute; left: 48px; bottom: 40px; background: #217346; color: #fff;
           font-size: 27px; padding: 16px 28px; border-radius: 10px; display: none; }
  #overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: none;
             align-items: center; justify-content: center; }
  #dialog { background: #fff; border-radius: 14px; padding: 40px 56px; min-width: 640px;
            box-shadow: 0 12px 40px rgba(0,0,0,.35); }
  #dialog.error { border-top: 12px solid #c62828; }
  #dialog h2 { font-size: 40px; margin-bottom: 24px; color: #1a1a1a; }
  #dialog.error h2 { color: #c62828; }
  #dialog p { font-size: 31px; line-height: 1.7; color: #222; }
  .clicking { background: #cfe3f7 !important; border-color: #1f4e79 !important; }
</style>
</head>
<body>
<header><span class="app">__APP__</span><span class="lesson">研修: __TITLE__</span></header>
<main>
  <div id="screen-title"></div>
  <div id="screen-subtitle"></div>
  <div id="list"></div>
  <div id="fields"></div>
</main>
<div id="note"></div>
<div id="toast"></div>
<div id="overlay"><div id="dialog"><h2 id="dialog-title"></h2><div id="dialog-body"></div></div></div>
<script>
const $ = (id) => document.getElementById(id);
function clearMain() {
  $("list").innerHTML = ""; $("fields").innerHTML = "";
  $("note").style.display = "none"; $("toast").style.display = "none";
}
window.applyOp = function (op) {
  if (op.op === "screen") {
    clearMain();
    $("screen-title").textContent = op.title; $("screen-subtitle").textContent = op.subtitle || "";
  } else if (op.op === "list") {
    $("list").innerHTML = "";
    for (const item of op.items) {
      const b = document.createElement("button"); b.textContent = item; $("list").appendChild(b);
    }
  } else if (op.op === "show_fields") {
    $("fields").innerHTML = "";
    for (const f of op.items) {
      const row = document.createElement("div"); row.className = "field";
      const lab = document.createElement("label"); lab.textContent = f.label;
      const val = document.createElement("div");
      val.className = "val" + (f.value ? "" : " placeholder");
      val.textContent = f.value || f.placeholder || "";
      row.appendChild(lab); row.appendChild(val); $("fields").appendChild(row);
    }
  } else if (op.op === "click") {
    let btn = [...document.querySelectorAll("button")].find((b) => b.textContent === op.label);
    if (!btn) {
      btn = document.createElement("button"); btn.textContent = op.label;
      let box = $("actions");
      if (!box) { box = document.createElement("div"); box.id = "actions";
        box.style.marginTop = "28px"; document.querySelector("main").appendChild(box); }
      box.appendChild(btn);
    }
    btn.classList.add("clicking");
    setTimeout(() => btn.classList.remove("clicking"), 900);
  } else if (op.op === "dialog") {
    $("dialog").className = ""; $("dialog-title").textContent = op.title;
    $("dialog-body").innerHTML = "";
    for (const line of op.lines) {
      const p = document.createElement("p"); p.textContent = line; $("dialog-body").appendChild(p);
    }
    $("overlay").style.display = "flex";
  } else if (op.op === "error") {
    $("dialog").className = "error"; $("dialog-title").textContent = op.code;
    $("dialog-body").innerHTML = "";
    const p = document.createElement("p"); p.textContent = op.text; $("dialog-body").appendChild(p);
    $("overlay").style.display = "flex";
  } else if (op.op === "close_dialog") {
    $("overlay").style.display = "none";
  } else if (op.op === "toast") {
    $("toast").textContent = op.text; $("toast").style.display = "block";
  } else if (op.op === "note") {
    $("note").textContent = op.text; $("note").style.display = "block";
  }
};
window.SCENARIO = __SCENARIO_JSON__;
</script>
</body>
</html>
"""


def generate_page(scenario: Scenario, out_dir: Path) -> Path:
    meta = {"id": scenario.id, "steps": [s.ops for s in scenario.steps]}
    html = (
        _TEMPLATE.replace("__TITLE__", scenario.title)
        .replace("__APP__", scenario.app_name)
        .replace("__SCENARIO_JSON__", json.dumps(meta, ensure_ascii=False))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{scenario.id}.html"
    path.write_text(html, encoding="utf-8")
    return path
