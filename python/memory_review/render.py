"""The desk page: a review packet as an interactive form. [da-04r]

A static page Steve has to answer in chat is a failed deliverable — the entire
point is that his decisions are captured without retyping. So this page:

  * carries the packet inline, so it opens with no server running;
  * autosaves every keystroke to `localStorage`, so closing the tab loses nothing;
  * posts to the local capture endpoint, and when that fails it says so **in red**
    and hands over a file the operator can import — it never reports success it
    did not get;
  * renders **COO INFERENCE** and **STEVE STATED** as visually different objects,
    because telling them apart is the reason the review exists.

Output path is a bookmark contract: `/var/moo/desk/desk-memory-review.html`
(`tmuxMOO/bin/desk-html.sh` header, moved there 2026-08-03 [co-gsbnb] because
`/tmp` is wiped on WSL restart). Written via a temp file and `os.replace`, so a
failed render never leaves a half-written page at an address Steve has parked a
tab on.
"""

from __future__ import annotations

import html
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

SECTION_TITLES = {
    "new_memory": "New memories since the last review",
    "collision": "Collisions with existing curated concepts",
    "contradiction": "Collisions with ALWAYS-LOADED instructions",
    "graduation_candidate": "Graduation candidates — said repeatedly, not yet curated",
}

SECTION_BLURBS = {
    "new_memory":
        "Written into a memory tier since your last sitting. The badge on each "
        "card says whether a verbatim quote of yours backs it up.",
    "collision":
        "A new memory landing on top of a concept that already exists. Same "
        "subject — could be agreement, could be the exact opposite. The score "
        "cannot tell the difference; you can.",
    "contradiction":
        "These collide with files loaded into EVERY session. A wrong line here "
        "outranks any correct memory, because an instruction is simply present "
        "while a memory has to be fetched. This is the butterfly failure: a wrong "
        "framing in an always-loaded file produced a month of wrong work.",
    "graduation_candidate":
        "Things you have said at least three times, across three sessions, on "
        "three different days, that no curated concept covers. Every line is "
        "verbatim — nothing here is a paraphrase.",
}

SECTION_ORDER = ["contradiction", "new_memory", "collision", "graduation_candidate"]

DECISIONS = [
    ("confirm", "Confirm", "Right as written"),
    ("correct", "Correct", "Nearly right — note the correction"),
    ("discard", "Discard", "Wrong — tombstone it"),
    ("graduate", "Graduate", "Promote to curated truth (proposes a bead)"),
    ("defer", "Defer", "Not now — bring it back"),
]


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def render(payload: dict, *, endpoint_url: str | None = None) -> str:
    """Return the complete HTML page for one packet payload."""
    endpoint = endpoint_url or f"http://{config.ENDPOINT_HOST}:{config.ENDPOINT_PORT}"
    # `<` is escaped so a payload containing `</script>` cannot break out of the
    # embedded JSON block. JSON decoders read < identically; browsers do not
    # read the literal identically, and that difference is an injection.
    packet_json = (json.dumps(payload, ensure_ascii=False)
                   .replace("<", "\\u003c")
                   .replace("\u2028", "\\u2028")
                   .replace("\u2029", "\\u2029"))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    stats = payload.get("stats") or {}
    corpus = stats.get("corpus") or {}
    sections = stats.get("sections") or {}
    degraded = payload.get("status") != "ok"

    banner = ""
    if degraded:
        banner = f"""
    <div class="banner banner-bad">
      <strong>THIS PACKET IS DEGRADED — {_esc(payload.get('status'))}.</strong>
      <div class="banner-detail">{_esc(payload.get('degraded_reason')
                                        or 'no reason recorded')}</div>
      <div class="banner-detail">Its contents may be incomplete. It is shown
      anyway, with this banner, because a pipeline that publishes nothing on a bad
      day goes quiet without anyone noticing.</div>
    </div>"""

    inference_count = sections.get("anchor:coo_inference", 0)
    stated_count = sections.get("anchor:steve_stated", 0)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Memory Review — packet {_esc(payload.get('packet_id'))}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>Memory Review</h1>
  <p class="sub">Packet {_esc(payload.get('packet_id'))} · built
     {_esc((payload.get('built_at') or '')[:16].replace('T', ' '))} UTC ·
     window {_esc((payload.get('window_from') or '')[:10])} →
     {_esc((payload.get('window_to') or '')[:10])}</p>
  <div id="conn" class="pill pill-unknown">checking capture endpoint…</div>
</header>

{banner}

<section class="statbar">
  <div class="stat"><span class="n" id="stat-total">0</span><span class="l">items</span></div>
  <div class="stat"><span class="n" id="stat-done">0</span><span class="l">decided</span></div>
  <div class="stat inference"><span class="n">{_esc(inference_count)}</span>
       <span class="l">COO inferences</span></div>
  <div class="stat stated"><span class="n">{_esc(stated_count)}</span>
       <span class="l">Steve stated</span></div>
  <div class="stat"><span class="n">{_esc(corpus.get('utterances_in_window', 0))}</span>
       <span class="l">your utterances in window</span></div>
  <div class="stat"><span class="n">{_esc(corpus.get('okf_concepts', 0))}</span>
       <span class="l">curated concepts</span></div>
  <div class="stat"><span class="n">{_esc(corpus.get('instruction_passages', 0))}</span>
       <span class="l">loaded passages</span></div>
</section>

<nav class="filters">
  <label><input type="checkbox" id="f-undecided"> Only undecided</label>
  <label><input type="checkbox" id="f-inference"> Only COO inferences</label>
  <span class="spacer"></span>
  <span class="hint">Every answer saves to this browser as you type. Nothing is
  lost if you close the tab.</span>
</nav>

<main id="items"></main>

<footer id="actionbar">
  <button id="save" class="primary">Record my decisions</button>
  <button id="download">Download as file</button>
  <span id="savestate" class="savestate"></span>
</footer>

<div id="fallback" class="fallback hidden">
  <h3>The capture endpoint did not accept these decisions.</h3>
  <p id="fallback-why" class="mono"></p>
  <p>Your answers are still held in this browser and will reappear when you
     reopen this page. To get them recorded, use the downloaded file:</p>
  <pre>cd /root/projects/DataArchive
python3 -m memory_review import ~/Downloads/memory-review-decisions.json</pre>
  <p>Or start the endpoint and press <em>Record my decisions</em> again:</p>
  <pre>bash scripts/cron/memory-review-endpoint.sh start</pre>
  <p class="mono">Endpoint: <input id="endpoint-url" value="{_esc(endpoint)}"
     spellcheck="false"> <button id="retest">re-test</button></p>
</div>

<script id="packet" type="application/json">{packet_json}</script>
<script>{_JS}</script>
<p class="generated">rendered {_esc(generated)} · backend
   {_esc(stats.get('backend', 'unknown'))} ·
   this page proposes, it never writes to a knowledge bundle</p>
</body></html>
"""


_CSS = """
:root { --bg:#fafafa; --fg:#222; --muted:#5a5a5a; --line:#ddd; --card:#fff;
        --inference:#b3261e; --inference-bg:#fdeceb; --stated:#1b5e20;
        --stated-bg:#eaf4ea; --warn:#8a5300; --warn-bg:#fdf3e2; --link:#0066cc; }
* { box-sizing: border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       font-size:20px; line-height:1.6; color:var(--fg); background:var(--bg);
       margin:0; padding:0 0 160px; }
header { padding:36px 48px 18px; border-bottom:1px solid var(--line); }
h1 { margin:0; font-size:1.7em; }
.sub { margin:6px 0 0; color:var(--muted); font-size:.8em; }
.pill { display:inline-block; margin-top:14px; padding:5px 14px; border-radius:20px;
        font-size:.72em; font-weight:600; }
.pill-ok { background:var(--stated-bg); color:var(--stated); }
.pill-bad { background:var(--inference-bg); color:var(--inference); }
.pill-unknown { background:#eee; color:var(--muted); }
.banner { margin:0; padding:20px 48px; font-size:.85em; }
.banner-bad { background:var(--inference-bg); color:var(--inference);
              border-bottom:3px solid var(--inference); }
.banner-detail { color:var(--fg); font-weight:400; margin-top:6px; }
.statbar { display:flex; flex-wrap:wrap; gap:10px; padding:20px 48px;
           border-bottom:1px solid var(--line); }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:10px 16px; min-width:110px; }
.stat .n { display:block; font-size:1.5em; font-weight:700; line-height:1.1; }
.stat .l { display:block; font-size:.6em; color:var(--muted); text-transform:uppercase;
           letter-spacing:.04em; }
.stat.inference { border-color:var(--inference); }
.stat.inference .n { color:var(--inference); }
.stat.stated { border-color:var(--stated); }
.stat.stated .n { color:var(--stated); }
.filters { display:flex; align-items:center; gap:24px; padding:14px 48px;
           border-bottom:1px solid var(--line); font-size:.75em; flex-wrap:wrap; }
.filters .spacer { flex:1; }
.filters .hint { color:var(--muted); }
main { padding:0 48px; }
section.group { margin:40px 0 0; }
section.group > h2 { font-size:1.15em; border-bottom:2px solid var(--line);
                     padding-bottom:.3em; margin-bottom:.2em; }
section.group.contradiction > h2 { border-bottom-color:var(--inference);
                                   color:var(--inference); }
.blurb { color:var(--muted); font-size:.78em; margin:0 0 18px; max-width:60em; }
.card { background:var(--card); border:1px solid var(--line); border-left-width:8px;
        border-radius:8px; padding:20px 24px; margin:16px 0; }
.card.coo_inference { border-left-color:var(--inference); }
.card.steve_stated  { border-left-color:var(--stated); }
.card.not_applicable{ border-left-color:#bbb; }
.card.decided { opacity:.62; }
.card.hidden { display:none; }
.badge { display:inline-block; padding:3px 10px; border-radius:4px; font-size:.6em;
         font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
.badge.coo_inference { background:var(--inference-bg); color:var(--inference); }
.badge.steve_stated  { background:var(--stated-bg); color:var(--stated); }
.badge.not_applicable{ background:#eee; color:var(--muted); }
.headline { font-weight:600; margin:10px 0 6px; font-size:1.02em; }
.bodytext { margin:0 0 10px; font-size:.85em; white-space:pre-wrap; }
.ref { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.66em;
       color:var(--muted); word-break:break-all; }
details { margin:10px 0; font-size:.78em; }
summary { cursor:pointer; color:var(--link); }
.quote { border-left:3px solid var(--line); margin:8px 0; padding:4px 0 4px 14px;
         color:#333; font-size:.95em; white-space:pre-wrap; }
.quote .when { display:block; color:var(--muted); font-size:.8em; margin-top:4px; }
.side-by-side { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:8px; }
.side-by-side > div { background:#f6f6f6; border-radius:6px; padding:10px 14px; }
.side-by-side h4 { margin:0 0 6px; font-size:.85em; }
.caveat { background:var(--warn-bg); color:var(--warn); border-radius:6px;
          padding:8px 14px; font-size:.78em; margin-top:10px; }
.choices { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 8px; }
.choices label { border:1px solid var(--line); border-radius:6px; padding:7px 14px;
                 cursor:pointer; font-size:.72em; background:#fff; }
.choices label:hover { border-color:#999; }
.choices input { margin-right:7px; }
.choices label.on { background:#eef4ff; border-color:var(--link); font-weight:600; }
.choices label .why { display:block; color:var(--muted); font-size:.85em;
                      font-weight:400; }
textarea { width:100%; min-height:60px; font-family:inherit; font-size:.78em;
           padding:10px 12px; border:1px solid var(--line); border-radius:6px;
           background:#fff; resize:vertical; }
footer#actionbar { position:fixed; bottom:0; left:0; right:0; background:#fff;
        border-top:1px solid var(--line); padding:14px 48px; display:flex;
        gap:14px; align-items:center; box-shadow:0 -2px 12px rgba(0,0,0,.06); }
button { font-size:.78em; padding:10px 20px; border-radius:6px; cursor:pointer;
         border:1px solid var(--line); background:#fff; font-family:inherit; }
button.primary { background:#1a4fa0; color:#fff; border-color:#1a4fa0; font-weight:600; }
button:disabled { opacity:.5; cursor:default; }
.savestate { font-size:.72em; color:var(--muted); }
.savestate.ok { color:var(--stated); font-weight:600; }
.savestate.bad { color:var(--inference); font-weight:600; }
.fallback { margin:24px 48px; padding:20px 24px; border:2px solid var(--inference);
            background:var(--inference-bg); border-radius:8px; font-size:.8em; }
.fallback h3 { margin-top:0; color:var(--inference); }
.fallback pre { background:#fff; padding:12px 14px; border-radius:6px;
                overflow-x:auto; font-size:.9em; }
.fallback input { font-size:1em; padding:5px 8px; width:22em; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.9em; }
.hidden { display:none; }
.empty { color:var(--muted); font-style:italic; padding:20px 0; }
.generated { color:var(--muted); font-size:.62em; padding:20px 48px 0; }
@media (max-width:900px) { .side-by-side { grid-template-columns:1fr; }
  header,.statbar,.filters,main,footer#actionbar,.generated { padding-left:20px;
  padding-right:20px; } .fallback { margin:20px; } }
"""


_JS = r"""
(function () {
  "use strict";

  var PACKET = JSON.parse(document.getElementById("packet").textContent);
  var STORE_KEY = "memory-review:packet:" + PACKET.packet_id;
  var ENDPOINT_KEY = "memory-review:endpoint";
  var SECTION_ORDER = ["contradiction", "new_memory", "collision",
                       "graduation_candidate"];
  var TITLES = __TITLES__;
  var BLURBS = __BLURBS__;
  var DECISIONS = __DECISIONS__;

  // ---- draft state, held in the browser so a closed tab loses nothing -------
  var drafts = {};
  try { drafts = JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }
  catch (e) { drafts = {}; }

  PACKET.items.forEach(function (item) {
    if (!drafts[item.dedupe_key] && item.prior_decision) {
      drafts[item.dedupe_key] = { decision: item.prior_decision,
                                  note: item.prior_note || "",
                                  decided_at: null, synced: true };
    }
  });

  function persist() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(drafts)); }
    catch (e) { setState("bad", "This browser refused to save locally: " + e.message); }
  }

  function endpointBase() {
    if (location.protocol === "http:" || location.protocol === "https:") {
      return location.origin;
    }
    var stored = null;
    try { stored = localStorage.getItem(ENDPOINT_KEY); } catch (e) { stored = null; }
    return stored || document.getElementById("endpoint-url").value;
  }

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---- rendering -----------------------------------------------------------
  function quoteBlock(anchors) {
    if (!anchors || !anchors.length) { return ""; }
    return anchors.map(function (a) {
      return '<div class="quote">' + esc(a.quote) +
        '<span class="when">' + esc(a.day || a.ts || "") +
        (a.project ? " · " + esc(a.project) : "") +
        (a.score !== undefined && a.score !== null ? " · match " + esc(a.score) : "") +
        "</span></div>";
    }).join("");
  }

  function evidenceBlock(item) {
    var ev = item.evidence || {};
    var out = "";

    if (item.anchor_class === "steve_stated" && (ev.anchors || []).length) {
      out += '<details open><summary>Your own words behind this (' +
             ev.anchors.length + ")</summary>" + quoteBlock(ev.anchors) + "</details>";
    } else if (item.anchor_class === "coo_inference") {
      out += '<div class="caveat"><strong>No verbatim quote of yours supports ' +
             "this.</strong> COO wrote it down as a distillation. That does not " +
             "make it wrong — it makes it unverified, and an unverified line that " +
             "hardens into curated truth starts outranking correct concepts.</div>";
    }

    if (ev.new_item && ev.existing_concept) {
      out += '<div class="side-by-side"><div><h4>The new memory</h4>' +
             '<div class="ref">' + esc(ev.new_item.path) + "</div><p>" +
             esc(ev.new_item.text) + "</p></div><div><h4>The existing concept</h4>" +
             '<div class="ref">' + esc(ev.existing_concept.path) + "</div><p>" +
             esc(ev.existing_concept.text) + "</p></div></div>";
    }

    if (ev.concept && ev.instruction) {
      var instrText = ev.instruction.text !== undefined
        ? ev.instruction.text : (ev.instruction.text || "");
      out += '<div class="side-by-side"><div><h4>The concept / memory</h4>' +
             '<div class="ref">' + esc(ev.concept.path) + "</div><p>" +
             esc(ev.concept.text) + "</p></div>" +
             "<div><h4>The ALWAYS-LOADED instruction</h4>" +
             '<div class="ref">' + esc(ev.instruction.path || "") +
             (ev.instruction.lines ? " lines " + esc(ev.instruction.lines) :
              (ev.instruction.line ? ":" + esc(ev.instruction.line) : "")) +
             "</div><p>" + esc(instrText) + "</p></div></div>";
    }

    if (ev.occurrences) {
      out += "<details open><summary>Said " + esc(ev.occurrences) + " times across " +
             esc(ev.sessions) + " sessions on " + esc(ev.day_spread) +
             " days</summary>" + quoteBlock(ev.anchors) + "</details>";
    }

    if (ev.full_body) {
      out += "<details><summary>Full text of the memory as written</summary>" +
             '<div class="quote">' + esc(ev.full_body) + "</div></details>";
    }

    if (ev.caveat) { out += '<div class="caveat">' + esc(ev.caveat) + "</div>"; }
    if (ev.why) { out += '<div class="caveat">' + esc(ev.why) + "</div>"; }
    return out;
  }

  function cardHTML(item) {
    var draft = drafts[item.dedupe_key] || {};
    var choices = DECISIONS.map(function (d) {
      var on = draft.decision === d[0] ? " on" : "";
      var checked = draft.decision === d[0] ? " checked" : "";
      return '<label class="choice' + on + '"><input type="radio" name="d-' +
        esc(item.dedupe_key) + '" value="' + d[0] + '"' + checked + ">" +
        esc(d[1]) + '<span class="why">' + esc(d[2]) + "</span></label>";
    }).join("");

    return '<article class="card ' + esc(item.anchor_class) +
      (draft.decision ? " decided" : "") + '" data-key="' + esc(item.dedupe_key) +
      '" data-anchor="' + esc(item.anchor_class) + '">' +
      '<span class="badge ' + esc(item.anchor_class) + '">' +
      (item.anchor_class === "coo_inference" ? "COO inference — nobody said this" :
       item.anchor_class === "steve_stated" ? "Steve stated this" :
       "comparison") + "</span>" +
      (item.score !== null && item.score !== undefined
        ? ' <span class="ref">score ' + esc(item.score) + "</span>" : "") +
      '<div class="headline">' + esc(item.headline) + "</div>" +
      (item.body ? '<div class="bodytext">' + esc(item.body) + "</div>" : "") +
      (item.source_ref ? '<div class="ref">' + esc(item.source_ref) + "</div>" : "") +
      evidenceBlock(item) +
      '<div class="choices">' + choices + "</div>" +
      '<textarea placeholder="Correction, reason, or anything you want recorded ' +
      'alongside this decision" data-note="' + esc(item.dedupe_key) + '">' +
      esc(draft.note || "") + "</textarea></article>";
  }

  function render() {
    var host = document.getElementById("items");
    var bySection = {};
    PACKET.items.forEach(function (item) {
      (bySection[item.section] = bySection[item.section] || []).push(item);
    });

    var html = "";
    var order = SECTION_ORDER.slice();
    Object.keys(bySection).forEach(function (s) {
      if (order.indexOf(s) === -1) { order.push(s); }
    });

    order.forEach(function (section) {
      var items = bySection[section] || [];
      html += '<section class="group ' + esc(section) + '"><h2>' +
        esc(TITLES[section] || section) + " (" + items.length + ")</h2>" +
        '<p class="blurb">' + esc(BLURBS[section] || "") + "</p>";
      html += items.length
        ? items.map(cardHTML).join("")
        : '<p class="empty">Nothing in this section for this window. That is a ' +
          "result, not a gap — the pass ran and found none.</p>";
      html += "</section>";
    });

    if (!PACKET.items.length) {
      html = '<section class="group"><h2>Nothing to review</h2><p class="blurb">' +
        "This packet ran against " +
        esc(((PACKET.stats || {}).corpus || {}).utterances_in_window || 0) +
        " of your utterances and " +
        esc(((PACKET.stats || {}).corpus || {}).okf_concepts || 0) +
        " curated concepts and found nothing that needs your ruling. A packet " +
        "that ran and found nothing looks like this; a packet that never ran " +
        "does not appear at all.</p></section>";
    }

    host.innerHTML = html;
    document.getElementById("stat-total").textContent = PACKET.items.length;
    updateProgress();
  }

  function updateProgress() {
    var done = PACKET.items.filter(function (i) {
      return drafts[i.dedupe_key] && drafts[i.dedupe_key].decision;
    }).length;
    document.getElementById("stat-done").textContent = done;
  }

  function applyFilters() {
    var undecidedOnly = document.getElementById("f-undecided").checked;
    var inferenceOnly = document.getElementById("f-inference").checked;
    Array.prototype.forEach.call(document.querySelectorAll(".card"), function (card) {
      var key = card.getAttribute("data-key");
      var decided = !!(drafts[key] && drafts[key].decision);
      var isInference = card.getAttribute("data-anchor") === "coo_inference";
      var hide = (undecidedOnly && decided) || (inferenceOnly && !isInference);
      card.classList.toggle("hidden", hide);
    });
  }

  // ---- interaction ---------------------------------------------------------
  document.addEventListener("change", function (event) {
    var target = event.target;
    if (target.type === "radio" && target.name.indexOf("d-") === 0) {
      var key = target.name.slice(2);
      drafts[key] = drafts[key] || {};
      drafts[key].decision = target.value;
      drafts[key].decided_at = new Date().toISOString().replace(/\.\d+Z$/, "Z");
      drafts[key].synced = false;
      persist();
      var card = target.closest(".card");
      if (card) {
        card.classList.add("decided");
        Array.prototype.forEach.call(card.querySelectorAll(".choice"), function (l) {
          l.classList.toggle("on", l.querySelector("input").checked);
        });
      }
      updateProgress();
      applyFilters();
      setState("", "Saved in this browser. Press Record my decisions to store them.");
    }
    if (target.id === "f-undecided" || target.id === "f-inference") { applyFilters(); }
  });

  document.addEventListener("input", function (event) {
    var key = event.target.getAttribute && event.target.getAttribute("data-note");
    if (!key) { return; }
    drafts[key] = drafts[key] || {};
    drafts[key].note = event.target.value;
    drafts[key].synced = false;
    persist();
  });

  // ---- capture -------------------------------------------------------------
  function pending() {
    return PACKET.items.filter(function (item) {
      var d = drafts[item.dedupe_key];
      return d && d.decision;
    }).map(function (item) {
      var d = drafts[item.dedupe_key];
      return {
        dedupe_key: item.dedupe_key,
        section: item.section,
        anchor_class: item.anchor_class,
        headline: item.headline,
        source_ref: item.source_ref,
        decision: d.decision,
        note: d.note || "",
        decided_at: d.decided_at || new Date().toISOString().replace(/\.\d+Z$/, "Z")
      };
    });
  }

  function setState(kind, message) {
    var el = document.getElementById("savestate");
    el.className = "savestate " + (kind || "");
    el.textContent = message;
  }

  function showFallback(why) {
    document.getElementById("fallback-why").textContent = why;
    document.getElementById("fallback").classList.remove("hidden");
  }

  function probe() {
    var pill = document.getElementById("conn");
    var url = endpointBase() + "/api/health";
    fetch(url, { method: "GET", mode: "cors", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (doc) {
        pill.className = "pill pill-ok";
        pill.textContent = "capture endpoint live · " + (doc.db || "store ready");
        document.getElementById("fallback").classList.add("hidden");
      })
      .catch(function (err) {
        pill.className = "pill pill-bad";
        pill.textContent = "capture endpoint UNREACHABLE — answers stay in this " +
                           "browser until it is up (" + err.message + ")";
      });
  }

  document.getElementById("save").addEventListener("click", function () {
    var batch = pending();
    if (!batch.length) {
      setState("bad", "Nothing decided yet — pick an option on at least one card.");
      return;
    }
    var button = this;
    button.disabled = true;
    setState("", "recording " + batch.length + "…");

    fetch(endpointBase() + "/api/adjudications", {
      method: "POST",
      mode: "cors",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packet_id: PACKET.packet_id,
                             client_id: clientId(), decisions: batch })
    })
      .then(function (response) {
        return response.json().catch(function () {
          throw new Error("HTTP " + response.status + " with an unreadable body");
        }).then(function (doc) {
          if (!response.ok || doc.ok !== true) {
            throw new Error(doc.error || ("HTTP " + response.status));
          }
          return doc;
        });
      })
      .then(function (doc) {
        batch.forEach(function (d) {
          if (drafts[d.dedupe_key]) { drafts[d.dedupe_key].synced = true; }
        });
        persist();
        setState("ok", "Recorded " + doc.recorded + " decision(s) — " +
                       doc.inserted + " new, " + doc.updated + " changed. " +
                       (doc.packet_complete
                         ? "Packet complete; the review window has moved on."
                         : doc.outstanding + " still undecided — they come back " +
                           "in the next packet.") +
                       " Ledger line count now " + doc.ledger_entries + ".");
        document.getElementById("fallback").classList.add("hidden");
      })
      .catch(function (err) {
        setState("bad", "NOT recorded: " + err.message);
        showFallback(err.message);
      })
      .then(function () { button.disabled = false; });
  });

  document.getElementById("download").addEventListener("click", function () {
    var payload = { packet_id: PACKET.packet_id, client_id: clientId(),
                    exported_at: new Date().toISOString(), decisions: pending() };
    var blob = new Blob([JSON.stringify(payload, null, 2)],
                        { type: "application/json" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "memory-review-decisions.json";
    link.click();
    setState("", "Downloaded " + payload.decisions.length +
                 " decision(s). Import with: python3 -m memory_review import <file>");
  });

  document.getElementById("retest").addEventListener("click", function () {
    var value = document.getElementById("endpoint-url").value.trim();
    try { localStorage.setItem(ENDPOINT_KEY, value); } catch (e) { /* non-fatal */ }
    probe();
  });

  function clientId() {
    var id = null;
    try { id = localStorage.getItem("memory-review:client"); } catch (e) { id = null; }
    if (!id) {
      id = "desk-" + Math.random().toString(36).slice(2, 10);
      try { localStorage.setItem("memory-review:client", id); } catch (e) { /* ignore */ }
    }
    return id;
  }

  render();
  applyFilters();
  probe();
})();
"""

_JS = (_JS
       .replace("__TITLES__", json.dumps(SECTION_TITLES))
       .replace("__BLURBS__", json.dumps(SECTION_BLURBS))
       .replace("__DECISIONS__", json.dumps(DECISIONS)))


def write_page(payload: dict, path: Path | None = None,
               endpoint_url: str | None = None) -> Path:
    """Render and atomically install the desk page. Returns the path written."""
    path = Path(path) if path else config.DESK_PAGE
    path.parent.mkdir(parents=True, exist_ok=True)
    markup = render(payload, endpoint_url=endpoint_url)

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".desk-", suffix=".partial")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(markup)
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp creates 0600; every other page in /var/moo/desk is 0644, and
        # Steve reads this one from Windows over the 9p share.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
