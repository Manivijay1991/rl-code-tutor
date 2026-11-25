// Choosing and starting the next case (core/selector.js decides which).

import { h, mount } from "../../ui/dom.js";
import { segment } from "../../core/note.js";
import { shuffled } from "../../core/random.js";
import { nextScenario } from "../../core/selector.js";
import { app, $, tableOf, ui } from "./state.js";

export function nextQuestion() {
  // app.view already holds only the chosen topic's cases (or the focused trap's topic), so no topic filter here.
  const choice = nextScenario(app.view, app.progress, {
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
    hintsUsed: 0,
    action: null,
    missLevel: null,
    hint: null,
    hintState: {},
    lit: new Set(),
    marked: new Set(),
    marking: app.q?.marking ?? false,
    phase: "answer",
    result: null,
    lastWrong: null,
  };
  ui.renderNote();
  ui.renderBench();
  $("note").scrollTop = 0;
  window.scrollTo({ top: 0, behavior: "smooth" });
}
