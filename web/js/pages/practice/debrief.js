// After a case: the answer, why, references, the risk-score change and the evidence score.

import { ACTION_LABELS } from "../../core/bandit.js";
import { h, icon } from "../../ui/dom.js";
import { term } from "../../ui/glossary.js";
import { app, ui } from "./state.js";

export function debriefCard() {
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
      ? correct.codes.map((c) => h("div", { class: "answer-row" }, h("span", { class: "code" }, c), h("span", {}, app.view.codes[c]?.desc ?? "")))
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
      h("p", { class: "note-small" }, h("span", { class: `opt-badge lean-${first.lean}` }, first.lean === "over" ? term("Overcoding", "overcoding") : first.lean === "under" ? term("Undercoding", "undercoding") : "Wrong level"), " ", first.why || trap?.description || ""),
      riskCard(first),
    );
  }
  parts.push(evidenceCard());
  if (q.action) {
    parts.push(h("div", { class: "coach-line", style: "margin-top:12px" }, icon("target", 16),
      `Coaching used: ${ACTION_LABELS[q.action]}. Your next new case with this trap tells your tutor whether it helped.`));
  }
  if (s.refs.length) parts.push(h("div", { class: "section-k" }, "References"), h("div", { class: "refs" }, s.refs.map(ui.refChip)));
  parts.push(h("div", { class: "actions" }, h("span", { class: "spacer" }),
    h("button", { class: "btn big", type: "button", on: { click: ui.nextQuestion } }, "Next case", icon("arrow", 16), h("span", { class: "kbd" }, "N"))));
  return h("div", { class: "card debrief", "aria-live": "polite" }, parts);
}

export function riskCard(first) {
  const g = first.gap;
  if (!g) return null;
  const hccName = (x) => app.view.hccs[x] ?? `HCC ${x}`;
  const head = h("div", { class: "section-k" }, "What the miss changes");
  const explain = h("p", { class: "note-small risk-key" },
    "Risk score (CMS-", term("HCC"), " V28): 1.0 = an average Medicare patient's expected cost. Higher score, higher payment.");
  // The HCC behind the difference, in words.
  const hccLine = [
    g.missing_hccs.length ? `Your pick misses ${g.missing_hccs.map(hccName).join(", ")}.` : "",
    g.extra_hccs.length ? `Your pick adds ${g.extra_hccs.map(hccName).join(", ")}.` : "",
  ].filter(Boolean).join(" ");

  if (g.direction === "none") {
    return h("div", { class: "risk" }, head,
      h("div", { class: "risk-chip none" }, icon("check", 15), `Same risk score (${g.correct.toFixed(3)})`),
      h("p", { class: "note-small" }, "The payment would not change here, but the code is still wrong, and audits check the code, not the score."),
      hccLine ? h("p", { class: "note-small" }, hccLine) : null,
      explain);
  }
  const diff = Math.abs(g.gap);
  const pctAvg = Math.round(diff * 100);
  const over = g.direction === "over";
  const max = Math.max(g.student, g.correct, 0.05);
  const bar = (label, v, cls) => h("div", { class: "gap-row" },
    h("span", {}, label), h("div", { class: "gap-track" }, h("div", { class: `gap-fill ${cls}`, style: `width:${Math.round((v / max) * 100)}%` })),
    h("span", { class: "gap-num" }, v.toFixed(3)));
  return h("div", { class: "risk" }, head,
    h("div", { class: `risk-chip ${g.direction}` }, icon(over ? "arrow" : "x", 15),
      over ? `+${diff.toFixed(3)}: overpaid by about ${pctAvg}% of an average patient's cost` : `−${diff.toFixed(3)}: underpaid by about ${pctAvg}% of an average patient's cost`),
    h("div", { class: "gap-viz" }, bar("Your pick", g.student, g.direction), bar("Correct", g.correct, "correct")),
    h("p", { class: "note-small" }, (over ? "An unsupported condition is an audit finding. " : "A supported condition goes unreported. ") + hccLine),
    explain);
}

export function evidenceCard() {
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
