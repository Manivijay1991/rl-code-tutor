// The progress drawer: stats, lean, evidence eye, trap map, insights, sharing, reset.

import { ACTION_LABELS, learnedContexts } from "../../core/bandit.js";
import { h, icon, mount } from "../../ui/dom.js";
import { term } from "../../ui/glossary.js";
import { trapName } from "../../core/format.js";
import { accuracy, confStats, emptyProgress, leanSummary } from "../../core/progress.js";
import { PROGRESS_KEY, removeKey } from "../../data/store.js";
import { app, $, ui } from "./state.js";

export function openDrawer() {
  app.returnFocus = document.activeElement;
  renderDrawer();
  $("drawer").hidden = false;
  $("btn-drawer-close").focus();
}

export function closeDrawer() {
  if ($("drawer").hidden) return;
  $("drawer").hidden = true;
  app.returnFocus?.focus?.();
}

export function renderDrawer() {
  const p = app.progress;
  const t = p.totals;
  const pctFirst = t.answered ? Math.round((t.firstTry / t.answered) * 100) : 0;
  const lean = leanSummary(p);
  const total = lean.over + lean.under;
  const needle = total ? 50 + ((lean.over - lean.under) / total) * 45 : 50;
  const leanText = {
    balanced: total < 3 ? "Answer a few more cases to see your lean." : "No strong lean: your misses go both ways.",
    over: "You lean toward overcoding: reporting more than the note supports. Look for MEAT before you code.",
    under: "You lean toward undercoding: leaving out supported conditions. Watch for 'with' links and code-also notes.",
  }[lean.label];

  const sections = [
    h("div", { class: "stats" },
      stat(t.answered, "cases"), stat(`${pctFirst}%`, "first try"), stat(p.bestStreak, "best streak"), stat(t.answered ? (t.hintsUsed / t.answered).toFixed(1) : "0", "hints per case")),
    h("div", { class: "card" },
      h("h3", { style: "margin:0;font-size:15px" }, "Your ", term("lean")),
      h("div", { class: "lean-meter", role: "img", "aria-label": `Lean: ${lean.label}` }, h("div", { class: "lean-needle", style: `left:${needle}%` })),
      h("div", { class: "lean-ends" }, h("span", {}, `Undercoding · ${lean.under}`), h("span", {}, `${lean.over} · Overcoding`)),
      h("p", { class: "note-small" }, leanText)),
    h("div", { class: "card" },
      h("h3", { style: "margin:0;font-size:15px" }, "Evidence eye"),
      p.evidence.questions
        ? h("p", { class: "note-small" }, `You found ${p.evidence.hit} of ${p.evidence.hit + p.evidence.missed} deciding details across ${p.evidence.questions} marked case${p.evidence.questions === 1 ? "" : "s"}.`)
        : h("p", { class: "note-small" }, "Use the highlighter (M) to mark evidence and see your evidence eye here.")),
    trapMap(),
    insights(),
    sharingCard(),
    h("div", { class: "card" },
      h("h3", { style: "margin:0 0 6px;font-size:15px" }, "Your data"),
      h("p", { class: "note-small" }, app.api && app.prefs.share
        ? "Progress is stored only in this browser, with no account. Only the anonymous coaching results described above are shared."
        : "Progress is stored only in this browser. No account, and nothing is sent anywhere."),
      h("button", { class: "btn ghost danger", type: "button", style: "margin-top:8px", on: { click: resetProgress } }, icon("reset", 16), "Reset progress")),
  ];
  mount($("drawer-body"), sections);
}

export function stat(n, label) {
  return h("div", { class: "stat" }, h("div", { class: "n" }, String(n)), h("div", { class: "l" }, label));
}

/** Every trap of every topic (from the manifest, so no topic file is needed), grouped by topic. */
export function trapMap() {
  const traps = (tp) => tp.tables.flatMap((tid) =>
    Object.entries(app.manifest.tables[tid].confusions).map(([cid, c]) => [`${tid}:${cid}`, c]));
  const groups = app.manifest.topics.map((tp) =>
    h("div", { class: "trap-group" },
      h("h4", {}, tp.title),
      h("div", { class: "traps" }, traps(tp).map(([id, c]) => {
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
  return h("div", { class: "card" }, h("h3", { style: "margin:0;font-size:15px" }, term("Trap", "trap"), " map"),
    h("p", { class: "note-small" }, "Each tile is a common coding trap. Click one to practice it."), groups);
}

export function insights() {
  const learned = learnedContexts(app.progress.bandit, 2).slice(0, 6);
  return h("div", { class: "card" },
    h("h3", { style: "margin:0;font-size:15px" }, "What helps you"),
    learned.length
      ? learned.map((c) => h("div", { class: "insight" }, icon("bulb", 16),
          h("span", {}, h("b", {}, ACTION_LABELS[c.best]), ` works best for "${trapName(c.confusion)}"`,
            c.missLevel > 1 ? ` after ${c.missLevel === 3 ? "3+" : c.missLevel} misses` : "", ` (${Math.round(c.mean * 100)}%, ${c.trials} cases).`)))
      : h("p", { class: "note-small" }, "Your tutor tries different coaching styles after a miss and learns which ones help you on the next new case. Insights appear here as you practice."));
}

export function sharingCard() {
  const status = !app.api
    ? "This copy runs offline: your tutor learns from your answers only."
    : !app.prefs.share
      ? "Off. Your tutor learns from your answers only."
      : app.shared
        ? `On. Your tutor also learns from ${app.shared.events.toLocaleString()} anonymous results from other students.`
        : "On. Waiting for the shared tutor (offline right now).";
  return h("div", { class: "card" },
    h("h3", { style: "margin:0 0 6px;font-size:15px" }, "Learning together"),
    h("p", { class: "note-small" },
      "When a coaching style is tested on your next case, this app can share one anonymous result: the trap, how many times you missed it (1, 2 or 3+), the coaching style, and whether it helped. No name, no account, no answers, no notes."),
    app.api ? h("label", { class: "switch", style: "margin-top:8px" },
      h("input", { type: "checkbox", checked: app.prefs.share, on: { change: (e) => ui.setShare(e.target.checked) } }),
      "Share anonymous results to improve coaching for everyone") : null,
    h("p", { class: "note-small" }, status));
}

export function practiceTrap(id) {
  closeDrawer();
  ui.focusTrap(id);
}

export function resetProgress() {
  if (!confirm("Reset all progress in this browser? This cannot be undone.")) return;
  app.progress = emptyProgress();
  removeKey(PROGRESS_KEY);
  ui.renderHeaderStats();
  renderDrawer();
  ui.toast("Progress reset.");
}
