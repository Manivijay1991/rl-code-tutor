// The coaching hint card: think-first question, reveal on request, mini-questions.

import { h, icon } from "../../ui/dom.js";
import { LEAN_MESSAGES } from "../../core/hints.js";
import { app, ui } from "./state.js";

export function hintCard() {
  const q = app.q;
  const hint = q.hint;
  const leanKey = q.lastWrong?.lean ?? "neutral";
  const body = [
    h("h3", {}, icon("bulb", 17), hint.title),
    h("div", { class: `lean-line lean-${leanKey}` }, LEAN_MESSAGES[leanKey]),
    h("p", { class: "hint-think" }, hint.think),
  ];
  // Think first: details stay hidden until the student asks for them.
  const more = [];
  if (hint.body) more.push(h("p", {}, hint.body));
  if (hint.kind === "rule" && hint.refs?.length) more.push(h("div", { class: "refs" }, hint.refs.map(ui.refChip)));
  if (hint.kind === "contrast") {
    more.push(h("div", { class: "contrast" },
      hint.pivotLabel ? h("div", { class: "would" }, h("div", { class: "k" }, "Your choice fits a note that says"), h("div", { class: "v" }, hint.pivotLabel)) : null,
      h("div", {}, h("div", { class: "k" }, "Other possibilities"), h("div", { class: "v" }, hint.alternatives.join(" · ")))));
  }
  if (!hint.reveal) body.push(...more);
  else if (q.hintState.revealed) body.push(h("div", { class: "hint-more", tabindex: "-1" }, more));
  else body.push(h("button", { class: "btn ghost small hint-reveal", type: "button", on: { click: revealHint } }, icon("bulb", 15), hint.reveal));
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

/** Show the hint's details (and, for the spotlight, light up the deciding words) after the student asks. */
export function revealHint() {
  const q = app.q;
  q.hintState.revealed = true;
  if (q.hint.kind === "spotlight") {
    q.hint.slots.forEach((s) => q.lit.add(s));
    ui.renderNote();
  }
  ui.renderBench();
  document.querySelector(".hint-more")?.focus();
}

export function miniQuestion(step, key, prefix = null) {
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

export function answerMini(key, step, value) {
  const q = app.q;
  if (value === step.value) {
    q.hintState[key] = "right";
    q.lit.add(step.slot);
    ui.renderNote();
  } else {
    q.hintState[`${key}:tried`] = [...(q.hintState[`${key}:tried`] ?? []), value];
    ui.toast("Check the note again.");
  }
  ui.renderBench();
}
