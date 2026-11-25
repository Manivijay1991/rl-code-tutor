// Home page (index.html): what the app is, an animated walkthrough of a case, how the next case is chosen,
// and the way into the assessment (practice.html). Reads only the manifest (topics and counts), never the
// scenarios.

import { ACTIONS } from "../../core/bandit.js";
import { migrate } from "../../core/progress.js";
import { catalogStats, loadManifest, resolveTopic } from "../../data/catalog.js";
import { loadPrefs, savePrefs } from "../../data/prefs.js";
import { PROGRESS_KEY, loadJSON } from "../../data/store.js";
import { h, icon, mount } from "../../ui/dom.js";
import { reducedMotion, revealOnScroll } from "../../ui/motion.js";
import { practiceUrl } from "../../ui/nav.js";
import { applyTheme, toggleTheme } from "../../ui/theme.js";
import { learningLoop } from "./loop.js";
import { startWalk, walkthrough } from "./walkthrough.js";

const $ = (id) => document.getElementById(id);
const EMPTY_MANIFEST = { topics: [], tables: {} };
const state = { prefs: loadPrefs(), manifest: EMPTY_MANIFEST };

async function boot() {
  applyTheme(state.prefs, $("btn-theme"));
  $("btn-theme").addEventListener("click", () => toggleTheme(state.prefs, $("btn-theme")));
  try {
    state.manifest = await loadManifest();
  } catch {
    state.manifest = EMPTY_MANIFEST; // the page still explains the app; counts show 0
  }
  state.prefs.topic = resolveTopic(state.manifest, state.prefs.topic);
  render();
  revealOnScroll();
}

// ---------------------------------------------------------------- page
function render() {
  mount($("home"), hero(), walkthrough(), learningLoop(), trust());
  countUp();
  startWalk();
  updateStartLinks();
}

function updateStartLinks() {
  for (const a of document.querySelectorAll("[data-start]")) a.href = practiceUrl(state.prefs.topic);
}

function hero() {
  const progress = migrate(loadJSON(PROGRESS_KEY, null));
  const t = progress.totals;
  const returning = t.answered > 0;
  const pct = returning ? Math.round((t.firstTry / t.answered) * 100) : 0;
  const { topics } = state.manifest;
  const stats = catalogStats(state.manifest);

  const chip = (id, label) =>
    h("button", {
      class: "chip-btn", type: "button", "aria-pressed": String(state.prefs.topic === id),
      on: { click: () => { state.prefs.topic = id; savePrefs(state.prefs); markTopic(); updateStartLinks(); } },
      dataset: { topic: id ?? "" },
    }, label);

  return h("section", { class: "hero reveal in" },
    h("div", { class: "hero-copy" },
      h("span", { class: "eyebrow" }, icon("target", 14), "Free practice for CRC risk adjustment coding"),
      h("h1", {}, "Read the note like an ", h("em", {}, "auditor"), ". Code what it supports."),
      h("p", { class: "lead" },
        "Clinical cases built from the official ICD-10-CM code set and CMS-HCC V28. When you miss, you get coached, not told, and your next case is chosen from how you answered."),
      h("div", { class: "cta" },
        h("a", { class: "btn big", href: practiceUrl(state.prefs.topic), dataset: { start: "" } },
          returning ? "Continue assessment" : "Start assessment", icon("arrow", 16)),
        returning ? h("a", { class: "btn ghost", href: "practice.html#progress" }, icon("chart", 16), "Your progress") : null),
      h("div", { class: "topic-pick", role: "group", "aria-label": "Topic" },
        h("span", { class: "label" }, "Practice"),
        chip(null, "All topics"),
        topics.map((tp) => chip(tp.id, tp.title))),
      returning
        ? h("p", { class: "welcome-back" }, `Welcome back: ${t.answered} cases done, ${pct}% right on the first try, best streak ${progress.bestStreak}.`)
        : null),
    h("div", { class: "stat-grid", "aria-label": "What is inside" },
      statTile("book", stats.scenarios, "clinical cases", "Practice notes to read and code"),
      statTile("target", stats.traps, "coding traps", "Common mistakes the tutor spots and coaches"),
      statTile("chart", stats.topics, "topics", topics.map((tp) => tp.title).join(", ")),
      statTile("bulb", ACTIONS.length, "coaching styles", "Ways the tutor can teach you after a miss")));
}

function markTopic() {
  for (const b of document.querySelectorAll(".topic-pick .chip-btn")) {
    b.setAttribute("aria-pressed", String((b.dataset.topic || null) === state.prefs.topic));
  }
}

function statTile(iconName, n, label, explain) {
  return h("div", { class: "stat-tile" },
    h("span", { class: "stat-icon" }, icon(iconName, 18)),
    h("span", { class: "stat-num" },
      h("span", { class: "n", dataset: { count: String(n) } }, "0"),
      h("span", { class: "l" }, label)),
    h("span", { class: "stat-explain" }, explain));
}

function countUp() {
  const els = [...document.querySelectorAll("[data-count]")];
  if (reducedMotion()) {
    els.forEach((el) => { el.textContent = el.dataset.count; });
    return;
  }
  const t0 = performance.now();
  const tick = (now) => {
    const k = Math.min(1, (now - t0) / 900);
    const ease = 1 - (1 - k) ** 3;
    els.forEach((el) => { el.textContent = String(Math.round(Number(el.dataset.count) * ease)); });
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function trust() {
  const card = (name, title, text) => h("div", { class: "card" }, h("h3", {}, icon(name, 16), title), h("p", {}, text));
  return h("section", { class: "trust reveal" },
    card("book", "Answers from rules, not AI", "Every answer comes from the official code set and a rules engine. AI only writes the practice notes."),
    card("check", "Private by design", "No account. Your progress stays in this browser. Sharing anonymous coaching results is optional."),
    card("target", "Draft content", "Cases are drafts until a certified coder reviews them. CRC is an AAPC credential; this tool is not affiliated with AAPC, AHIMA, AMA or CMS."));
}

boot();
