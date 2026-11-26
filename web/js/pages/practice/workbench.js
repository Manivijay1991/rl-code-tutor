// The answer card: choices (a keyboard radio group), checking, the hint ladder and finishing a case.

import { toEvents } from "../../data/api.js";
import { ACTION_LABELS, chooseAction } from "../../core/bandit.js";
import { h, icon, mount } from "../../ui/dom.js";
import { buildHint, LADDERS, narrowRemovals } from "../../core/hints.js";
import { today } from "../../core/format.js";
import { evidenceBySlot } from "../../core/note.js";
import { evidenceScore, nextMissLevel, recordOutcome } from "../../core/progress.js";
import { app, MAX_HINTS, $, correctCodes, savePrefs, saveProgress, ui } from "./state.js";

export function renderBench() {
  const q = app.q;
  const parts = [questionCard()];
  if (q.hintsUsed) parts.push(ui.hintCard());
  if (q.phase === "done") parts.push(ui.debriefCard());
  mount($("bench-inner"), parts);
}

export function questionCard() {
  const q = app.q;
  const opts = q.scenario.options;
  const done = q.phase === "done";
  const list = h("div", { class: "options", role: "radiogroup", "aria-label": "Answer choices", on: { keydown: onOptionKey } },
    q.order.map((idx, pos) => optionButton(opts[idx], idx, pos, done)));

  const actions = h("div", { class: "actions" });
  if (!done) {
    actions.append(h("span", { class: "spacer" }));
    if (q.phase === "stuck") {
      actions.append(h("button", { class: "btn ghost", type: "button", on: { click: keepTrying } }, "Keep trying"),
        h("button", { class: "btn", type: "button", on: { click: reveal } }, icon("book", 16), "Show answer"));
    } else {
      actions.append(h("button", { class: "btn big", type: "button", disabled: q.selected === null, on: { click: submit } },
        q.firstPick === null ? "Check" : "Check again", h("span", { class: "kbd" }, "Enter")));
    }
  }

  return h("div", { class: "card" },
    h("div", { class: "q-head" },
      h("h2", { class: "q-text", id: "question" }, q.table.question),
      h("div", { class: "q-sub" },
        h("span", {}, "Pick the code set the note supports."),
        h("label", { class: "switch" },
          h("input", { type: "checkbox", checked: app.prefs.showDesc, on: { change: toggleDesc } }), "Show code descriptions (codebook)"))),
    list,
    q.hintsUsed ? ladder() : null,
    actions);
}

export function optionButton(opt, idx, pos, done) {
  const q = app.q;
  const tried = q.tried.has(idx);
  const removed = q.removed.has(idx);
  const disabled = done || tried || removed || q.phase === "stuck";
  const classes = ["option", tried && !done ? "tried" : "", removed && !done ? "removed" : "", done && opt.correct ? "is-correct" : ""];
  const codes = opt.codes.length
    ? opt.codes.map((c) => h("span", { class: "code" }, c))
    : [h("span", { class: "code none" }, "No code: not supported for this visit")];
  const desc = app.prefs.showDesc && opt.codes.length
    ? h("ul", { class: "desc-list" }, opt.codes.map((c) => h("li", {}, h("b", {}, c), app.view.codes[c]?.desc ?? "")))
    : null;
  let badge = null;
  if (done && opt.correct) badge = h("span", { class: "opt-badge badge-ok" }, "Correct");
  else if (done && idx === q.firstPick) badge = h("span", { class: `opt-badge lean-${opt.lean}` }, "Your first pick");
  else if (tried) badge = h("span", { class: `opt-badge lean-${opt.lean}` }, opt.lean === "over" ? "Overcodes" : opt.lean === "under" ? "Undercodes" : "Wrong level");
  return h("button", {
    class: classes.filter(Boolean).join(" "),
    type: "button",
    role: "radio",
    "aria-checked": String(q.selected === idx),
    tabindex: idx === focusTarget() ? "0" : "-1",
    disabled,
    dataset: { idx: String(idx) },
    on: { click: () => select(idx) },
  }, h("span", { class: "opt-key" }, String(pos + 1)), h("span", {}, h("span", { class: "codes" }, codes), desc), badge ?? h("span"));
}

export function ladder() {
  const q = app.q;
  return h("div", { class: "ladder", style: "margin-top:14px" },
    h("span", { class: "pips", "aria-hidden": "true" }, Array.from({ length: MAX_HINTS }, (_, i) => h("span", { class: `pip${i < q.hintsUsed ? " on" : ""}` }))),
    `Hint ${q.hintsUsed} of ${MAX_HINTS}`,
    q.action ? h("span", { style: "margin-left:auto" }, `Coaching: ${ACTION_LABELS[q.action]}`) : null);
}

export function toggleDesc(e) {
  app.prefs.showDesc = e.target.checked;
  savePrefs();
  renderBench();
}

export function selectable(idx) {
  const q = app.q;
  return q.phase !== "done" && q.phase !== "stuck" && !q.tried.has(idx) && !q.removed.has(idx);
}

/** The option that takes Tab focus: the selected one, else the first selectable one. */
export function focusTarget() {
  const q = app.q;
  return q.selected ?? q.order.find(selectable);
}

export function select(idx, focus = false) {
  const q = app.q;
  if (!selectable(idx)) return;
  q.selected = idx;
  renderBench();
  if (focus) document.querySelector(`.option[data-idx="${idx}"]`)?.focus();
}

export function onOptionKey(e) {
  const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
  if (!(e.key in keys)) return;
  e.preventDefault();
  const q = app.q;
  const enabled = q.order.filter(selectable);
  if (!enabled.length) return;
  const current = enabled.indexOf(q.selected ?? Number(e.target.closest(".option")?.dataset.idx));
  const next = enabled[(current + keys[e.key] + enabled.length) % enabled.length];
  select(next, true);
}

export function submit() {
  const q = app.q;
  if (q.selected === null || q.phase === "done" || q.phase === "stuck") return;
  const idx = q.selected;
  const opt = q.scenario.options[idx];
  if (q.firstPick === null) q.firstPick = idx;
  if (opt.correct) return finish(q.hintsUsed ? "solved" : "first");

  q.tried.add(idx);
  q.selected = null;
  q.lastWrong = opt;
  if (q.action === null) {
    const conf = `${q.scenario.table}:${opt.confusion}`;
    q.missLevel = nextMissLevel(app.progress, conf);
    q.action = chooseAction(app.progress.bandit, conf, q.missLevel, Math.random, app.prefs.share ? app.shared?.arms : null);
  }
  if (q.hintsUsed < MAX_HINTS) showHint(opt);
  else q.phase = "stuck";
  ui.renderNote();
  renderBench();
  shake(idx);
  ui.announce(q.phase === "stuck" ? "Not quite. You can keep trying or show the answer." : `Not quite. Hint ${q.hintsUsed} is ready.`);
  document.querySelector(".hint")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

export function showHint(opt) {
  const q = app.q;
  q.hintsUsed += 1;
  const kind = LADDERS[q.action][q.hintsUsed - 1];
  q.hint = buildHint({ kind, scenario: q.scenario, table: q.table, option: opt, correctCodes: correctCodes(q.scenario), step: q.hintsUsed });
  q.hintState = {};
  q.phase = "hint";
  if (q.hint.kind === "narrow") narrowRemovals(q.scenario.options, q.tried).forEach((i) => q.removed.add(i));
}

export function keepTrying() {
  app.q.phase = "hint";
  renderBench();
}

export function reveal() {
  finish("revealed");
}

export function shake(idx) {
  const el = document.querySelector(`.option[data-idx="${idx}"]`);
  el?.classList.add("shake");
}

export function finish(result) {
  const q = app.q;
  q.phase = "done";
  q.result = result;
  const firstOption = q.scenario.options[q.firstPick ?? q.order[0]];
  q.evidence = q.marked.size ? evidenceScore([...q.marked], evidenceBySlot(q.blocks, q.scenario.evidence)) : null;
  const { progress, settled } = recordOutcome(app.progress, q.scenario, {
    firstOption,
    hintsUsed: q.hintsUsed,
    revealed: result === "revealed",
    action: q.action,
    missLevel: q.missLevel,
    evidence: q.evidence,
    date: today(),
  });
  app.progress = progress;
  saveProgress();
  ui.renderHeaderStats(result === "first");
  ui.renderNote();
  renderBench();
  if (settled.length) ui.sendOutbox(toEvents(settled));
  ui.refreshPolicy(); // background; the next choice uses whatever is in memory by then
  for (const s of settled) {
    ui.toast(s.reward
      ? `Your tutor learned: "${ACTION_LABELS[s.action]}" helped with this trap.`
      : `Noted: "${ACTION_LABELS[s.action]}" did not stick. Your tutor will adjust.`);
  }
  if (result === "first" && progress.streak && progress.streak % 5 === 0) ui.toast(`${progress.streak} in a row on the first try.`);
  ui.announce(result === "first" ? "Correct on the first try." : result === "solved" ? "Correct." : "Answer shown.");
  document.querySelector(".debrief")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
