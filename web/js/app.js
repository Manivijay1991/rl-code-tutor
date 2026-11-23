// Coach-mode controller: renders the note and workbench, runs the hint ladder, records progress.
// Answers come from the exported bundle (built by the rules engine); nothing here decides codes.

import { ACTION_LABELS, chooseAction, learnedContexts } from "./bandit.js";
import { h, icon, mount, svg } from "./dom.js";
import { LADDERS, LEAN_MESSAGES, buildHint, narrowRemovals } from "./hints.js";
import { evidenceBySlot, pieces, segment, sentencesWithEvidence } from "./note.js";
import {
  accuracy,
  confStats,
  emptyProgress,
  evidenceScore,
  leanSummary,
  migrate,
  nextMissBucket,
  recordOutcome,
} from "./progress.js";
import { shuffled } from "./random.js";
import { REASONS, nextScenario } from "./selector.js";
import { PREFS_KEY, PROGRESS_KEY, loadJSON, removeKey, saveJSON } from "./store.js";

const DAILY_GOAL = 10;
const MAX_HINTS = 3;
const $ = (id) => document.getElementById(id);

const app = {
  bundle: null,
  progress: emptyProgress(),
  prefs: { theme: null, showDesc: true, topic: null, onboarded: false },
  focus: null,
  q: null,
};

// ---------------------------------------------------------------- boot
async function boot() {
  app.prefs = { ...app.prefs, ...loadJSON(PREFS_KEY, {}) };
  app.progress = migrate(loadJSON(PROGRESS_KEY, null));
  applyTheme();
  staticButtons();
  try {
    const res = await fetch("data/bundle.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    app.bundle = await res.json();
  } catch (e) {
    mount($("bench-inner"), h("div", { class: "card empty" }, h("h2", { text: "No scenarios found" }),
      h("p", {}, "Run ", h("code", { text: "python -m coding_tutor.ui.export" }), " and serve this folder with ",
        h("code", { text: "python -m coding_tutor.ui.serve" }), "."), h("p", { class: "note-small", text: String(e) })));
    return;
  }
  if (app.prefs.topic && !app.bundle.tables[app.prefs.topic]) app.prefs.topic = null;
  const cs = app.bundle.code_set;
  if (cs?.icd10cm) $("code-set").textContent = `Code set: ${cs.icd10cm}; ${cs.hcc_map}.`;
  renderTopics();
  document.addEventListener("keydown", onKey);
  nextQuestion();
  if (!app.prefs.onboarded) showWelcome();
}

function savePrefs() {
  saveJSON(PREFS_KEY, app.prefs);
}

function saveProgress() {
  saveJSON(PROGRESS_KEY, app.progress);
}

// ---------------------------------------------------------------- header
function staticButtons() {
  mount($("btn-progress"), icon("chart"));
  mount($("btn-keys"), icon("key"));
  mount($("btn-drawer-close"), icon("x"));
  $("btn-progress").addEventListener("click", openDrawer);
  $("btn-keys").addEventListener("click", showKeys);
  $("btn-theme").addEventListener("click", toggleTheme);
  $("btn-drawer-close").addEventListener("click", closeDrawer);
  $("drawer").addEventListener("click", (e) => e.target === $("drawer") && closeDrawer());
  $("btn-marker").addEventListener("click", toggleMarker);
  $("note").addEventListener("click", onNoteClick);
}

function applyTheme() {
  const t = app.prefs.theme;
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  mount($("btn-theme"), icon(dark ? "sun" : "moon"));
}

function toggleTheme() {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  app.prefs.theme = dark ? "light" : "dark";
  savePrefs();
  applyTheme();
}

function renderTopics() {
  const nav = $("topics");
  const topic = app.prefs.topic;
  const chips = [
    h("button", { class: "chip-btn", type: "button", "aria-pressed": String(!topic && !app.focus), on: { click: () => setTopic(null) } }, "All topics"),
    ...Object.entries(app.bundle.tables).map(([id, t]) =>
      h("button", { class: "chip-btn", type: "button", "aria-pressed": String(topic === id && !app.focus), title: t.title, on: { click: () => setTopic(id) } },
        t.topic || t.title),
    ),
  ];
  if (app.focus) {
    chips.push(h("button", { class: "chip-btn focus-chip", type: "button", "aria-pressed": "true", title: "Stop focused practice", on: { click: clearFocus } },
      `Trap: ${trapName(app.focus)} ✕`));
  }
  mount(nav, chips);
  renderHeaderStats();
}

function setTopic(id) {
  app.prefs.topic = id;
  app.focus = null;
  savePrefs();
  renderTopics();
  nextQuestion();
}

function clearFocus() {
  app.focus = null;
  renderTopics();
  nextQuestion();
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function renderHeaderStats(bump = false) {
  const p = app.progress;
  const streak = $("streak");
  mount(streak, icon("flame", 15), String(p.streak));
  streak.classList.toggle("hot", p.streak >= 3);
  streak.title = `First-try streak (best ${p.bestStreak})`;
  if (bump) {
    streak.classList.remove("bump");
    void streak.offsetWidth;
    streak.classList.add("bump");
  }
  const done = p.daily[today()] ?? 0;
  const frac = Math.min(1, done / DAILY_GOAL);
  const r = 9;
  const c = 2 * Math.PI * r;
  mount($("goal"),
    svg("svg", { width: 24, height: 24, viewBox: "0 0 24 24", "aria-hidden": "true" },
      svg("circle", { cx: 12, cy: 12, r, fill: "none", stroke: "var(--line)", "stroke-width": 3 }),
      svg("circle", { cx: 12, cy: 12, r, fill: "none", stroke: "var(--accent)", "stroke-width": 3, "stroke-linecap": "round", "stroke-dasharray": `${c * frac} ${c}` })),
    h("span", {}, `${done}/${DAILY_GOAL} today`));
}

// ---------------------------------------------------------------- question state
function tableOf(scenario) {
  return app.bundle.tables[scenario.table];
}

function correctCodes(scenario) {
  return scenario.options.find((o) => o.correct).codes;
}

const TRAP_WORDS = { ckd: "CKD", htn: "HTN", esrd: "ESRD", meat: "MEAT", z794: "Z79.4", dm: "DM", mdd: "MDD" };

/** Readable trap name from its id: "missed_htn_ckd_link" -> "Missed HTN CKD link". */
function trapName(confusion) {
  const words = confusion.split(":")[1].split("_").map((w) => TRAP_WORDS[w] ?? w);
  const text = words.join(" ");
  return text[0].toUpperCase() + text.slice(1);
}

function nextQuestion() {
  const choice = nextScenario(app.bundle, app.progress, {
    topic: app.focus ? null : app.prefs.topic,
    focus: app.focus,
    excludeId: app.q?.scenario.id,
  });
  if (!choice) {
    app.q = null;
    mount($("note"));
    mount($("bench-inner"), h("div", { class: "card empty", text: "No scenarios for this topic yet." }));
    return;
  }
  const s = choice.scenario;
  app.q = {
    scenario: s,
    table: tableOf(s),
    reason: choice.reason,
    order: shuffled(s.options.map((_, i) => i)),
    blocks: segment(s.note),
    selected: null,
    tried: new Set(),
    removed: new Set(),
    firstPick: null,
    sure: true,
    hintsUsed: 0,
    action: null,
    missBucket: null,
    hint: null,
    hintState: {},
    lit: new Set(),
    marked: new Set(),
    marking: app.q?.marking ?? false,
    phase: "answer",
    result: null,
    lastWrong: null,
  };
  renderNote();
  renderBench();
  $("note").scrollTop = 0;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------- note
function renderNote() {
  const q = app.q;
  const note = $("note");
  const finding = q.hint?.kind === "find" && !q.hintState.found;
  note.classList.toggle("marking", q.marking && q.phase !== "done");
  note.classList.toggle("finding", finding);
  const showAll = q.phase === "done";
  const spans = q.scenario.evidence;
  mount(note, q.blocks.map((b) =>
    b.type === "heading"
      ? h("h3", { text: b.text })
      : h("p", {}, b.sentences.flatMap((sent, k) => [
          k ? " " : null,
          h("span", {
            class: `sent${q.marked.has(sent.i) ? " marked" : ""}${q.hintState.found === sent.i ? " found" : ""}`,
            dataset: { i: String(sent.i) },
          }, pieces(sent, spans).map((p) =>
            p.slot ? h("mark", { class: `ev${showAll || q.lit.has(p.slot) ? " lit" : ""}`, dataset: { slot: p.slot } }, p.text) : p.text)),
        ])),
  ));
  const meta = [
    h("span", { class: "tag reason" }, REASONS[q.reason] ?? "Practice"),
    h("span", { class: "tag", title: q.table.title }, q.table.topic || q.table.title),
    q.table.status === "draft" ? h("span", { class: "tag draft", title: "Not yet reviewed by a certified coder" }, "Draft") : null,
  ];
  mount($("chart-meta"), meta);
  const marker = $("btn-marker");
  marker.setAttribute("aria-pressed", String(q.marking));
  mount(marker, icon("marker", 16), q.marking ? "Highlighter on" : "Highlighter");
  const banner = $("find-banner");
  banner.hidden = !finding;
  if (finding) mount(banner, "Tap the sentence that decides the codes.");
}

function toggleMarker() {
  if (!app.q || app.q.phase === "done") return;
  app.q.marking = !app.q.marking;
  renderNote();
  toast(app.q.marking ? "Highlighter on: tap the sentences that decide the codes" : "Highlighter off");
}

function onNoteClick(e) {
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

function checkFind(i, el) {
  const q = app.q;
  const right = sentencesWithEvidence(q.blocks, q.scenario.evidence, q.hint.slots);
  if (right.includes(i)) {
    q.hintState.found = i;
    q.hint.slots.forEach((s) => q.lit.add(s));
    announce("Found it. That sentence decides the codes.");
    toast("Found it. Now pick again.");
    renderNote();
    renderBench();
    return;
  }
  q.hintState.misses = (q.hintState.misses ?? 0) + 1;
  el.classList.remove("miss-tap");
  void el.offsetWidth;
  el.classList.add("miss-tap");
  if (q.hintState.misses >= 2) {
    q.hintState.found = right[0] ?? -1;
    q.hint.slots.forEach((s) => q.lit.add(s));
    toast("Here it is, highlighted. Read it, then pick again.");
    renderNote();
    renderBench();
  } else {
    toast("Not that one. Look for the detail that changes the code.");
  }
}

// ---------------------------------------------------------------- workbench
function renderBench() {
  const q = app.q;
  const parts = [questionCard()];
  if (q.hintsUsed) parts.push(hintCard());
  if (q.phase === "done") parts.push(debriefCard());
  mount($("bench-inner"), parts);
}

function questionCard() {
  const q = app.q;
  const opts = q.scenario.options;
  const done = q.phase === "done";
  const list = h("div", { class: "options", role: "radiogroup", "aria-label": "Answer choices" },
    q.order.map((idx, pos) => optionButton(opts[idx], idx, pos, done)));

  const actions = h("div", { class: "actions" });
  if (!done) {
    if (q.firstPick === null) {
      actions.append(h("div", { class: "seg", role: "group", "aria-label": "Confidence" },
        h("button", { type: "button", "aria-pressed": String(q.sure), on: { click: () => setSure(true) } }, "Sure"),
        h("button", { type: "button", "aria-pressed": String(!q.sure), on: { click: () => setSure(false) } }, "Not sure")));
    }
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
          h("input", { type: "checkbox", checked: app.prefs.showDesc, on: { change: toggleDesc } }), "Show code descriptions"))),
    list,
    q.hintsUsed ? ladder() : null,
    actions);
}

function optionButton(opt, idx, pos, done) {
  const q = app.q;
  const tried = q.tried.has(idx);
  const removed = q.removed.has(idx);
  const disabled = done || tried || removed || q.phase === "stuck";
  const classes = ["option", tried && !done ? "tried" : "", removed && !done ? "removed" : "", done && opt.correct ? "is-correct" : ""];
  const codes = opt.codes.length
    ? opt.codes.map((c) => h("span", { class: "code" }, c))
    : [h("span", { class: "code none" }, "No code: not supported for this visit")];
  const desc = app.prefs.showDesc && opt.codes.length
    ? h("ul", { class: "desc-list" }, opt.codes.map((c) => h("li", {}, h("b", {}, c), app.bundle.codes[c]?.desc ?? "")))
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
    disabled,
    dataset: { idx: String(idx) },
    on: { click: () => select(idx) },
  }, h("span", { class: "opt-key" }, String(pos + 1)), h("span", {}, h("span", { class: "codes" }, codes), desc), badge ?? h("span"));
}

function ladder() {
  const q = app.q;
  return h("div", { class: "ladder", style: "margin-top:14px" },
    h("span", { class: "pips", "aria-hidden": "true" }, Array.from({ length: MAX_HINTS }, (_, i) => h("span", { class: `pip${i < q.hintsUsed ? " on" : ""}` }))),
    `Hint ${q.hintsUsed} of ${MAX_HINTS}`,
    q.action ? h("span", { style: "margin-left:auto" }, `Coaching: ${ACTION_LABELS[q.action]}`) : null);
}

function setSure(v) {
  app.q.sure = v;
  renderBench();
}

function toggleDesc(e) {
  app.prefs.showDesc = e.target.checked;
  savePrefs();
  renderBench();
}

function select(idx) {
  const q = app.q;
  if (q.phase === "done" || q.tried.has(idx) || q.removed.has(idx)) return;
  q.selected = idx;
  renderBench();
}

// ---------------------------------------------------------------- checking
function submit() {
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
    q.missBucket = nextMissBucket(app.progress, conf);
    q.action = chooseAction(app.progress.bandit, conf, q.missBucket);
  }
  if (q.hintsUsed < MAX_HINTS) showHint(opt);
  else q.phase = "stuck";
  renderNote();
  renderBench();
  shake(idx);
  announce(q.phase === "stuck" ? "Not quite. You can keep trying or show the answer." : `Not quite. Hint ${q.hintsUsed} is ready.`);
  document.querySelector(".hint")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function showHint(opt) {
  const q = app.q;
  q.hintsUsed += 1;
  const kind = LADDERS[q.action][q.hintsUsed - 1];
  q.hint = buildHint({ kind, scenario: q.scenario, table: q.table, option: opt, correctCodes: correctCodes(q.scenario), step: q.hintsUsed });
  q.hintState = {};
  q.phase = "hint";
  if (q.hint.kind === "spotlight") q.hint.slots.forEach((s) => q.lit.add(s));
  if (q.hint.kind === "narrow") narrowRemovals(q.scenario.options, q.tried).forEach((i) => q.removed.add(i));
}

function keepTrying() {
  app.q.phase = "hint";
  renderBench();
}

function reveal() {
  finish("revealed");
}

function shake(idx) {
  const el = document.querySelector(`.option[data-idx="${idx}"]`);
  el?.classList.add("shake");
}

function finish(result) {
  const q = app.q;
  q.phase = "done";
  q.result = result;
  const firstOption = q.scenario.options[q.firstPick ?? q.order[0]];
  q.evidence = q.marked.size ? evidenceScore([...q.marked], evidenceBySlot(q.blocks, q.scenario.evidence)) : null;
  const { progress, settled } = recordOutcome(app.progress, q.scenario, {
    firstOption,
    sure: q.sure,
    hintsUsed: q.hintsUsed,
    revealed: result === "revealed",
    action: q.action,
    missBucket: q.missBucket,
    evidence: q.evidence,
    date: today(),
  });
  app.progress = progress;
  saveProgress();
  renderHeaderStats(result === "first");
  renderNote();
  renderBench();
  for (const s of settled) {
    toast(s.reward
      ? `Your tutor learned: "${ACTION_LABELS[s.action]}" helped with this trap.`
      : `Noted: "${ACTION_LABELS[s.action]}" did not stick. Your tutor will adjust.`);
  }
  if (result === "first" && progress.streak && progress.streak % 5 === 0) toast(`${progress.streak} in a row on the first try.`);
  announce(result === "first" ? "Correct on the first try." : result === "solved" ? "Correct." : "Answer shown.");
  document.querySelector(".debrief")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------- hint card
function hintCard() {
  const q = app.q;
  const hint = q.hint;
  const leanKey = q.lastWrong?.lean ?? "neutral";
  const body = [
    h("h3", {}, icon("bulb", 17), hint.title),
    h("div", { class: `lean-line lean-${leanKey}` }, LEAN_MESSAGES[leanKey]),
    h("p", {}, hint.body),
  ];
  if (hint.kind === "rule" && hint.refs?.length) body.push(h("div", { class: "refs" }, hint.refs.map((r) => h("span", { class: "ref" }, r))));
  if (hint.kind === "contrast") {
    body.push(h("div", { class: "contrast" },
      h("div", { class: "would" }, h("div", { class: "k" }, "Your choice fits a note that says"), h("div", { class: "v" }, hint.pivotLabel ?? "something else")),
      h("div", {}, h("div", { class: "k" }, "Other possibilities"), h("div", { class: "v" }, hint.alternatives.join(" · ")))));
  }
  if (hint.kind === "question") body.push(miniQuestion(hint.question, "q0"));
  if (hint.kind === "walk") {
    const answered = hint.steps.filter((_, i) => q.hintState[`w${i}`] === "right").length;
    const current = hint.steps.findIndex((_, i) => q.hintState[`w${i}`] !== "right");
    hint.steps.forEach((step, i) => {
      if (i < current || current === -1) body.push(h("div", { class: "step-done" }, `✓ ${step.label}: ${step.valueLabel}`));
    });
    if (current !== -1) body.push(miniQuestion(hint.steps[current], `w${current}`, `Step ${current + 1} of ${hint.steps.length}`));
    else body.push(h("p", { class: "step-done" }, `All ${answered} steps done. Now pick again.`));
  }
  if (hint.kind === "find" && q.hintState.found !== undefined) {
    body.push(h("p", { class: "step-done" }, "✓ Highlighted in the note. Pick again."));
  }
  return h("div", { class: "card hint", role: "region", "aria-label": "Hint" }, body);
}

function miniQuestion(step, key, prefix = null) {
  const q = app.q;
  const state = q.hintState[key];
  const tried = q.hintState[`${key}:tried`] ?? [];
  return h("div", { class: "mini-q" },
    h("div", { class: "label" }, prefix ? `${prefix}: ` : "", `What does the note say about "${step.label}"?`),
    h("div", { class: "choices" }, step.choices.map((c) => {
      const isRight = c.value === step.value;
      const cls = state === "right" && isRight ? "choice right" : tried.includes(c.value) ? "choice wrong" : "choice";
      return h("button", {
        class: cls, type: "button", disabled: state === "right",
        on: { click: () => answerMini(key, step, c.value) },
      }, c.label);
    })),
    state === "right" ? h("p", { class: "step-done" }, "✓ Right. Keep that detail in mind when you pick.") : null);
}

function answerMini(key, step, value) {
  const q = app.q;
  if (value === step.value) {
    q.hintState[key] = "right";
    q.lit.add(step.slot);
    renderNote();
  } else {
    q.hintState[`${key}:tried`] = [...(q.hintState[`${key}:tried`] ?? []), value];
    toast("Check the note again.");
  }
  renderBench();
}

// ---------------------------------------------------------------- debrief
function debriefCard() {
  const q = app.q;
  const s = q.scenario;
  const first = s.options[q.firstPick];
  const correct = s.options.find((o) => o.correct);
  const titles = {
    first: ["Correct on the first try", "Clean read of the documentation."],
    solved: [`Solved with ${q.hintsUsed} hint${q.hintsUsed === 1 ? "" : "s"}`, "You found it yourself. The next case with this trap is the real test."],
    revealed: ["Here is the answer", "Worth another look: this trap will come back in a new case."],
  };
  const [title, sub] = titles[q.result];
  const parts = [
    h("div", { class: `result ${q.result}` },
      h("div", { class: "big-icon" }, icon(q.result === "revealed" ? "book" : "check", 24)),
      h("div", {}, h("h3", {}, title), h("p", {}, sub))),
    h("div", { class: "section-k" }, "Correct answer"),
    h("div", { class: "answer-rows" }, correct.codes.length
      ? correct.codes.map((c) => h("div", { class: "answer-row" }, h("span", { class: "code" }, c), h("span", {}, app.bundle.codes[c]?.desc ?? "")))
      : h("div", {}, "No code: the condition is not supported for this date of service.")),
  ];
  if (s.explanations.length) {
    parts.push(h("div", { class: "section-k" }, "Why"), h("ul", { class: "explain" }, s.explanations.map((e) => h("li", {}, e))));
  }
  if (!first.correct) {
    const trap = q.table.confusions[first.confusion];
    parts.push(
      h("div", { class: "section-k" }, "Your first pick"),
      h("div", { class: "codes" }, first.codes.length ? first.codes.map((c) => h("span", { class: "code" }, c)) : h("span", { class: "code none" }, "No code")),
      h("p", { class: "note-small" }, h("span", { class: `opt-badge lean-${first.lean}` }, first.lean === "over" ? "Overcoding" : first.lean === "under" ? "Undercoding" : "Wrong level"), " ", first.why || trap?.description || ""),
      riskCard(first),
    );
  }
  parts.push(evidenceCard());
  if (q.action) {
    parts.push(h("div", { class: "coach-line", style: "margin-top:12px" }, icon("target", 16),
      `Coaching used: ${ACTION_LABELS[q.action]}. Your next new case with this trap tells your tutor whether it helped.`));
  }
  if (s.refs.length) parts.push(h("div", { class: "section-k" }, "References"), h("div", { class: "refs" }, s.refs.map((r) => h("span", { class: "ref" }, r))));
  parts.push(h("div", { class: "actions" }, h("span", { class: "spacer" }),
    h("button", { class: "btn big", type: "button", on: { click: nextQuestion } }, "Next case", icon("arrow", 16), h("span", { class: "kbd" }, "N"))));
  return h("div", { class: "card debrief", "aria-live": "polite" }, parts);
}

function riskCard(first) {
  const g = first.gap;
  if (!g) return null;
  const max = Math.max(g.student, g.correct, 0.05);
  const pct = (v) => `${Math.round((v / max) * 100)}%`;
  const hccList = (hs) => hs.map((x) => `HCC ${x} ${app.bundle.hccs[x] ? `(${app.bundle.hccs[x]})` : ""}`).join("; ");
  const text = g.direction === "none"
    ? "Same risk score here, but the code is still wrong: audits check the code, not just the score."
    : g.direction === "over"
      ? `Your pick raises the risk score by ${Math.abs(g.gap).toFixed(3)}: an unsupported HCC is an audit finding.`
      : `Your pick lowers the risk score by ${Math.abs(g.gap).toFixed(3)}: a supported condition goes unreported.`;
  return h("div", {},
    h("div", { class: "section-k" }, `What the miss changes (CMS-HCC V28, ${g.segment} segment)`),
    h("div", { class: "gap-viz" },
      h("div", { class: "gap-row" }, h("span", {}, "Your pick"), h("div", { class: "gap-track" }, h("div", { class: `gap-fill ${g.direction}`, style: `width:${pct(g.student)}` })), h("span", { class: "gap-num" }, g.student.toFixed(3))),
      h("div", { class: "gap-row" }, h("span", {}, "Correct"), h("div", { class: "gap-track" }, h("div", { class: "gap-fill correct", style: `width:${pct(g.correct)}` })), h("span", { class: "gap-num" }, g.correct.toFixed(3)))),
    h("p", { class: "note-small" }, text),
    g.missing_hccs.length ? h("p", { class: "note-small" }, `Missing: ${hccList(g.missing_hccs)}`) : null,
    g.extra_hccs.length ? h("p", { class: "note-small" }, `Extra: ${hccList(g.extra_hccs)}`) : null,
    h("p", { class: "note-small" }, "Shown for feedback only. Your score is right or wrong on the codes."));
}

function evidenceCard() {
  const q = app.q;
  if (!q.evidence) {
    return h("p", { class: "note-small", style: "margin-top:12px" }, "The deciding words are now highlighted in the note. Tip: turn on the highlighter (", h("span", { class: "kbd" }, "M"), ") and mark them yourself before you answer.");
  }
  const { hit, missed, extra } = q.evidence;
  const total = hit + missed;
  const verdict = !total ? "This note has no single deciding phrase; what is missing matters." :
    hit === total ? "You found every deciding detail. That is how auditors read." :
      "The green words in the note are the details you did not mark.";
  return h("div", {},
    h("div", { class: "section-k" }, "Your evidence marks"),
    h("div", { class: "ev-score" }, h("span", {}, `✓ ${hit} of ${total} deciding details found`),
      extra ? h("span", {}, `${extra} sentence${extra === 1 ? "" : "s"} marked without a deciding detail`) : null),
    h("p", { class: "note-small" }, verdict));
}

// ---------------------------------------------------------------- progress drawer
function openDrawer() {
  renderDrawer();
  $("drawer").hidden = false;
  $("btn-drawer-close").focus();
}

function closeDrawer() {
  $("drawer").hidden = true;
}

function renderDrawer() {
  const p = app.progress;
  const t = p.totals;
  const pctFirst = t.answered ? Math.round((t.firstTry / t.answered) * 100) : 0;
  const lean = leanSummary(p);
  const total = lean.over + lean.under;
  const needle = total ? 50 + ((lean.over - lean.under) / total) * 45 : 50;
  const cal = (k) => (p.calibration[k].n ? `${Math.round((p.calibration[k].right / p.calibration[k].n) * 100)}%` : "–");
  const leanText = {
    balanced: total < 3 ? "Answer a few more cases to see your lean." : "No strong lean: your misses go both ways.",
    over: "You lean toward overcoding: reporting more than the note supports. Look for MEAT before you code.",
    under: "You lean toward undercoding: leaving out supported conditions. Watch for 'with' links and code-also notes.",
  }[lean.label];

  const sections = [
    h("div", { class: "stats" },
      stat(t.answered, "cases"), stat(`${pctFirst}%`, "first try"), stat(p.bestStreak, "best streak"), stat(t.answered ? (t.hintsUsed / t.answered).toFixed(1) : "0", "hints per case")),
    h("div", { class: "card" },
      h("h3", { style: "margin:0;font-size:15px" }, "Your lean"),
      h("div", { class: "lean-meter", role: "img", "aria-label": `Lean: ${lean.label}` }, h("div", { class: "lean-needle", style: `left:${needle}%` })),
      h("div", { class: "lean-ends" }, h("span", {}, `Undercoding · ${lean.under}`), h("span", {}, `${lean.over} · Overcoding`)),
      h("p", { class: "note-small" }, leanText)),
    h("div", { class: "card" },
      h("h3", { style: "margin:0;font-size:15px" }, "Confidence check"),
      h("p", { class: "note-small" }, `When you said Sure: ${cal("sure")} right · Not sure: ${cal("unsure")} right.`),
      p.evidence.questions
        ? h("p", { class: "note-small" }, `Evidence eye: you found ${p.evidence.hit} of ${p.evidence.hit + p.evidence.missed} deciding details across ${p.evidence.questions} marked case${p.evidence.questions === 1 ? "" : "s"}.`)
        : h("p", { class: "note-small" }, "Use the highlighter (M) to mark evidence and see your evidence eye here.")),
    trapMap(),
    insights(),
    h("div", { class: "card" },
      h("h3", { style: "margin:0 0 6px;font-size:15px" }, "Your data"),
      h("p", { class: "note-small" }, "Progress is stored only in this browser. No account, no server, nothing sent anywhere."),
      h("button", { class: "btn ghost danger", type: "button", style: "margin-top:8px", on: { click: resetProgress } }, icon("reset", 16), "Reset progress")),
  ];
  mount($("drawer-body"), sections);
}

function stat(n, label) {
  return h("div", { class: "stat" }, h("div", { class: "n" }, String(n)), h("div", { class: "l" }, label));
}

function trapMap() {
  const groups = Object.entries(app.bundle.tables).map(([tid, t]) =>
    h("div", { class: "trap-group" },
      h("h4", {}, t.topic || t.title),
      h("div", { class: "traps" }, Object.entries(t.confusions).map(([cid, c]) => {
        const id = `${tid}:${cid}`;
        const st = confStats(app.progress, id);
        const acc = accuracy(app.progress, id);
        return h("button", {
          class: `trap${st.seen ? "" : " unseen"}`, type: "button", title: `${c.description}\nClick to practice this trap.`,
          on: { click: () => practiceTrap(id) },
        },
          h("span", {}, trapName(id)),
          h("span", { class: "bar" }, h("i", { style: `width:${acc === null ? 0 : Math.round(acc * 100)}%` })),
          h("span", { class: "meta" }, st.seen ? `${Math.round(acc * 100)}% · seen ${st.seen}` : "not met yet"));
      }))));
  return h("div", { class: "card" }, h("h3", { style: "margin:0;font-size:15px" }, "Trap map"),
    h("p", { class: "note-small" }, "Each tile is a common coding trap. Click one to practice it."), groups);
}

function insights() {
  const learned = learnedContexts(app.progress.bandit, 2).slice(0, 6);
  return h("div", { class: "card" },
    h("h3", { style: "margin:0;font-size:15px" }, "What helps you"),
    learned.length
      ? learned.map((c) => h("div", { class: "insight" }, icon("bulb", 16),
          h("span", {}, h("b", {}, ACTION_LABELS[c.best]), ` works best for "${trapName(c.confusion)}"`,
            c.bucket > 1 ? ` after ${c.bucket === 3 ? "3+" : c.bucket} misses` : "", ` (${Math.round(c.mean * 100)}%, ${c.trials} cases).`)))
      : h("p", { class: "note-small" }, "Your tutor tries different coaching styles after a miss and learns which ones help you on the next new case. Insights appear here as you practice."));
}

function practiceTrap(id) {
  app.focus = id;
  closeDrawer();
  renderTopics();
  nextQuestion();
  toast(`Focused practice: ${trapName(id)}`);
}

function resetProgress() {
  if (!confirm("Reset all progress in this browser? This cannot be undone.")) return;
  app.progress = emptyProgress();
  removeKey(PROGRESS_KEY);
  renderHeaderStats();
  renderDrawer();
  toast("Progress reset.");
}

// ---------------------------------------------------------------- overlays
function showOverlay(content, onClose) {
  const ov = $("overlay");
  const close = () => {
    ov.hidden = true;
    onClose?.();
  };
  mount(ov, h("div", { class: "modal", role: "dialog", "aria-modal": "true" }, content(close)));
  ov.hidden = false;
  ov.onclick = (e) => e.target === ov && close();
  ov.querySelector("button")?.focus();
}

function showWelcome() {
  showOverlay((close) => [
    h("h2", {}, "Code like an auditor reads"),
    h("p", { class: "note-small" }, "Practice for CRC risk adjustment coding. Every answer comes from the official code set and draft rules; nothing here is guessed by AI."),
    h("ol", { class: "steps" },
      h("li", {}, h("span", {}, h("b", {}, "Read the note. "), "Turn on the highlighter (M) and tap the sentences that decide the codes.")),
      h("li", {}, h("span", {}, h("b", {}, "Pick the code set. "), "Say whether you are sure, then check.")),
      h("li", {}, h("span", {}, h("b", {}, "Miss? Get coached, not told. "), "Up to three hints, each one closer; the answer only if you ask.")),
      h("li", {}, h("span", {}, h("b", {}, "Your tutor adapts. "), "It learns which coaching style helps you, and brings each trap back in a new case."))),
    h("div", { class: "actions" }, h("span", { class: "spacer" }),
      h("button", { class: "btn big", type: "button", on: { click: close } }, "Start practicing", icon("arrow", 16))),
  ], () => {
    app.prefs.onboarded = true;
    savePrefs();
  });
}

function showKeys() {
  const rows = [["1–6", "Pick a choice"], ["Enter", "Check / next case"], ["S", "Toggle Sure / Not sure"], ["M", "Highlighter"],
    ["D", "Code descriptions"], ["N", "Next case (after answering)"], ["P", "Progress"], ["?", "This help"], ["Esc", "Close"]];
  showOverlay((close) => [
    h("h2", {}, "Keyboard shortcuts"),
    h("div", { class: "keys" }, rows.flatMap(([k, d]) => [h("span", { class: "kbd" }, k), h("span", {}, d)])),
    h("div", { class: "actions" }, h("span", { class: "spacer" }), h("button", { class: "btn", type: "button", on: { click: close } }, "Got it")),
  ]);
}

function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2800);
}

function announce(text) {
  $("announce").textContent = text;
}

// ---------------------------------------------------------------- keyboard
function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.matches("input, textarea, select")) return;
  const overlayOpen = !$("overlay").hidden;
  const drawerOpen = !$("drawer").hidden;
  if (e.key === "Escape") {
    if (overlayOpen) $("overlay").hidden = true;
    if (drawerOpen) closeDrawer();
    return;
  }
  if (overlayOpen) return;
  const k = e.key.toLowerCase();
  if (k === "p") return drawerOpen ? closeDrawer() : openDrawer();
  if (drawerOpen) return;
  if (k === "?") return showKeys();
  const q = app.q;
  if (!q) return;
  if (/^[1-9]$/.test(k)) {
    const idx = q.order[Number(k) - 1];
    if (idx !== undefined) select(idx);
    return;
  }
  if (k === "enter") {
    if (e.target.closest?.("button")) return; // let the focused button handle it
    e.preventDefault();
    return q.phase === "done" ? nextQuestion() : submit();
  }
  if (k === "n" && q.phase === "done") return nextQuestion();
  if (k === "m") return toggleMarker();
  if (k === "s" && q.firstPick === null) return setSure(!q.sure);
  if (k === "d") {
    app.prefs.showDesc = !app.prefs.showDesc;
    savePrefs();
    renderBench();
  }
}

boot();
