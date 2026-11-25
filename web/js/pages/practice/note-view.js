// The clinical note: sentences, highlighter marking, and the find-the-evidence hint.

import { h, icon, mount } from "../../ui/dom.js";
import { pieces, sentencesWithEvidence } from "../../core/note.js";
import { REASONS } from "../../core/selector.js";
import { app, $, savePrefs, ui } from "./state.js";

export function renderNote() {
  const q = app.q;
  const note = $("note");
  const finding = q.hint?.kind === "find" && !q.hintState.found;
  note.classList.toggle("marking", q.marking && q.phase !== "done");
  note.classList.toggle("finding", finding);
  const showAll = q.phase === "done";
  const spans = q.scenario.evidence;
  const interactive = (q.marking || finding) && q.phase !== "done";
  mount(note, q.blocks.map((b) =>
    b.type === "heading"
      ? h("h3", { text: b.text })
      : h("p", {}, b.sentences.flatMap((sent, k) => [
          k ? " " : null,
          h("span", {
            class: `sent${q.marked.has(sent.i) ? " marked" : ""}${q.hintState.found === sent.i ? " found" : ""}`,
            dataset: { i: String(sent.i) },
            tabindex: interactive ? "0" : null,
            role: interactive ? "button" : null,
            "aria-pressed": q.marking && !finding ? String(q.marked.has(sent.i)) : null,
          }, pieces(sent, spans).map((p) =>
            p.slot ? h("mark", { class: `ev${showAll || q.lit.has(p.slot) ? " lit" : ""}`, dataset: { slot: p.slot } }, p.text) : p.text)),
        ])),
  ));
  const meta = [
    h("span", { class: "tag reason" }, REASONS[q.reason] ?? "Practice"),
    h("span", { class: "tag", title: q.table.title }, app.manifest.topics.find((tp) => tp.id === q.table.topic)?.title ?? q.table.title),
    q.table.status === "draft" ? h("span", { class: "tag draft", title: "Not yet reviewed by a certified coder" }, "Draft") : null,
  ];
  mount($("chart-meta"), meta);
  const marker = $("btn-marker");
  marker.setAttribute("aria-pressed", String(q.marking));
  mount(marker, icon("marker", 16), q.marking ? "Highlighter on" : "Highlighter");
  const banner = $("find-banner");
  const tip = !finding && !q.marking && !app.prefs.tipSeen && q.phase !== "done";
  banner.hidden = !finding && !tip;
  if (finding) mount(banner, "Tap (or Tab to and press Enter on) the sentence that decides the codes.");
  else if (tip) {
    mount(banner, h("span", {}, "Tip: turn on the ", h("b", {}, "Highlighter"),
      " and mark the words that decide the codes. The debrief shows how many you found."),
    h("button", { class: "btn ghost small", type: "button", on: { click: dismissTip } }, "Got it"));
  }
}

export function dismissTip() {
  app.prefs.tipSeen = true;
  savePrefs();
  renderNote();
}

export function toggleMarker() {
  if (!app.q || app.q.phase === "done") return;
  app.q.marking = !app.q.marking;
  if (app.q.marking && !app.prefs.tipSeen) {
    app.prefs.tipSeen = true;
    savePrefs();
  }
  renderNote();
  ui.toast(app.q.marking ? "Highlighter on: tap the sentences that decide the codes" : "Highlighter off");
}

export function onNoteClick(e) {
  const q = app.q;
  const el = e.target.closest(".sent");
  if (!q || !el || q.phase === "done") return;
  const i = Number(el.dataset.i);
  if (q.hint?.kind === "find" && !q.hintState.found) return checkFind(i, el);
  if (!q.marking) return;
  if (q.marked.has(i)) q.marked.delete(i);
  else q.marked.add(i);
  renderNote();
}

export function checkFind(i, el) {
  const q = app.q;
  const right = sentencesWithEvidence(q.blocks, q.scenario.evidence, q.hint.slots);
  if (right.includes(i)) {
    q.hintState.found = i;
    q.hint.slots.forEach((s) => q.lit.add(s));
    ui.announce("Found it. That sentence decides the codes.");
    ui.toast("Found it. Now pick again.");
    renderNote();
    ui.renderBench();
    return;
  }
  q.hintState.misses = (q.hintState.misses ?? 0) + 1;
  el.classList.remove("miss-tap");
  void el.offsetWidth;
  el.classList.add("miss-tap");
  if (q.hintState.misses >= 2) {
    q.hintState.found = right[0] ?? -1;
    q.hint.slots.forEach((s) => q.lit.add(s));
    ui.toast("Here it is, highlighted. Read it, then pick again.");
    renderNote();
    ui.renderBench();
  } else {
    ui.toast("Not that one. Look for the detail that changes the code.");
  }
}
