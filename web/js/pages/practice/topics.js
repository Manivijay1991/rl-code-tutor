// Header: topic chips, focused-trap chip, streak and daily goal.

import { h, icon, mount, svg } from "../../ui/dom.js";
import { DAILY_GOAL } from "../../data/prefs.js";
import { today, trapName } from "../../core/format.js";
import { buildView, loadTopics, topicIds } from "../../data/catalog.js";
import { app, $, savePrefs, ui } from "./state.js";

export function renderTopics() {
  const nav = $("topics");
  const topic = app.prefs.topic;
  const total = app.manifest.topics.reduce((n, tp) => n + tp.scenarios, 0);
  // A native select scales to any number of topics and is keyboard and screen-reader friendly as is.
  const select = h("select", { class: "topic-select", "aria-label": "Topic", title: "Practice topic", on: { change: (e) => setTopic(e.target.value || null) } },
    h("option", { value: "", selected: !topic }, `All topics (${total})`),
    app.manifest.topics.map((tp) => h("option", { value: tp.id, selected: topic === tp.id }, `${tp.title} (${tp.scenarios})`)));
  const focusChip = app.focus
    ? h("button", { class: "chip-btn focus-chip", type: "button", "aria-pressed": "true", title: "Stop focused practice", on: { click: clearFocus } },
      `Trap: ${trapName(app.focus)} ✕`)
    : null;
  mount(nav, select, focusChip);
  renderHeaderStats();
}

/**
 * Load a topic's scenario file (or every topic's for null) plus any `extra` topics, and make them the current
 * view. Files already loaded are reused; the browser caches them because their names change with their content.
 */
export async function useTopic(topic, extra = []) {
  const ids = [...new Set([...topicIds(app.manifest, topic), ...extra])];
  app.files = await loadTopics(app.manifest, ids, app.files);
  app.view = buildView(app.manifest, Object.fromEntries(ids.map((id) => [id, app.files[id]])));
}

/** Switch to a topic (or all topics) and start a case from it; keeps the current case if loading fails. */
export async function setTopic(id) {
  await switchTo(() => useTopic(id), () => {
    app.prefs.topic = id;
    app.focus = null;
    savePrefs();
  });
}

export async function clearFocus() {
  await switchTo(() => useTopic(app.prefs.topic), () => {
    app.focus = null;
  });
}

/** Practice one trap: load the topic that owns it, then pick only cases with that trap. */
export async function focusTrap(id) {
  const owner = app.manifest.tables[id.split(":")[0]]?.topic;
  await switchTo(() => useTopic(owner ?? app.prefs.topic), () => {
    app.focus = id;
  });
  if (app.focus === id) ui.toast(`Focused practice: ${trapName(id)}`);
}

async function switchTo(load, apply) {
  try {
    await load();
  } catch {
    ui.toast("Could not load that topic. Check your connection and try again.");
    return;
  }
  apply();
  renderTopics();
  ui.nextQuestion();
}

export function renderHeaderStats(bump = false) {
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
  const met = done >= DAILY_GOAL;
  const frac = Math.min(1, done / DAILY_GOAL);
  const r = 9;
  const c = 2 * Math.PI * r;
  const goal = $("goal");
  goal.classList.toggle("met", met);
  goal.title = met
    ? `Daily goal of ${DAILY_GOAL} cases met: ${done} done today`
    : `Daily goal: ${done} of ${DAILY_GOAL} cases done today`;
  mount(goal,
    met
      ? icon("check", 18)
      : svg("svg", { width: 22, height: 22, viewBox: "0 0 24 24", "aria-hidden": "true" },
          svg("circle", { cx: 12, cy: 12, r, fill: "none", stroke: "var(--line)", "stroke-width": 3 }),
          svg("circle", { cx: 12, cy: 12, r, fill: "none", stroke: "var(--accent)", "stroke-width": 3, "stroke-linecap": "round", "stroke-dasharray": `${c * frac} ${c}` })),
    h("span", {}, met ? `Goal met · ${done} today` : `${done} of ${DAILY_GOAL} today`));
}
