// Home page (index.html): what the app is, an animated walkthrough of a case, how the next case is
// chosen, and the way into the assessment (practice.html). Reads the bundle only for counts.

import { ACTIONS } from "./bandit.js";
import { applyTheme, loadBundle, loadPrefs, practiceUrl, savePrefs, toggleTheme } from "./common.js";
import { h, icon, mount } from "./dom.js";
import { migrate } from "./progress.js";
import { PROGRESS_KEY, loadJSON } from "./store.js";

const STEP_MS = 5200;
const $ = (id) => document.getElementById(id);
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = { prefs: loadPrefs(), bundle: null, step: 0, timer: null, paused: false };

async function boot() {
  applyTheme(state.prefs, $("btn-theme"));
  $("btn-theme").addEventListener("click", () => toggleTheme(state.prefs, $("btn-theme")));
  try {
    state.bundle = await loadBundle();
  } catch {
    state.bundle = { scenarios: [], tables: {} };
  }
  if (state.prefs.topic && !state.bundle.tables[state.prefs.topic]) state.prefs.topic = null;
  render();
  revealOnScroll();
}

// ---------------------------------------------------------------- page
function render() {
  mount($("home"), hero(), walkthrough(), nextCaseLoop(), trust());
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
  const tables = Object.entries(state.bundle.tables);
  const traps = tables.reduce((n, [, tb]) => n + Object.keys(tb.confusions).length, 0);

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
        tables.map(([id, tb]) => chip(id, tb.topic || tb.title))),
      returning
        ? h("p", { class: "welcome-back" }, `Welcome back: ${t.answered} cases done, ${pct}% right on the first try, best streak ${progress.bestStreak}.`)
        : null),
    h("div", { class: "stat-grid", "aria-label": "What is inside" },
      statTile(state.bundle.scenarios.length, "clinical cases"),
      statTile(traps, "coding traps"),
      statTile(tables.length, "topics"),
      statTile(ACTIONS.length, "coaching styles")));
}

function markTopic() {
  for (const b of document.querySelectorAll(".topic-pick .chip-btn")) {
    b.setAttribute("aria-pressed", String((b.dataset.topic || null) === state.prefs.topic));
  }
}

function statTile(n, label) {
  return h("div", { class: "stat-tile" }, h("span", { class: "n", dataset: { count: String(n) } }, "0"), h("span", { class: "l" }, label));
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

// ---------------------------------------------------------------- animated walkthrough
const STEPS = [
  { title: "Read and mark the evidence", text: "Turn on the highlighter and tap the words that decide the codes, the way an auditor reads.", scene: sceneRead },
  { title: "Pick the code set", text: "Choose the codes the note supports and say how confident you are.", scene: scenePick },
  { title: "Miss? Get coached", text: "Up to 3 hints, each one closer, with a re-pick after each. No hint names the answer.", scene: sceneCoach },
  { title: "Learn why it matters", text: "The rule, the deciding words, and how the miss moves the CMS-HCC risk score.", scene: sceneDebrief },
];

function walkthrough() {
  return h("section", { class: "reveal", "aria-labelledby": "walk-title" },
    h("h2", { class: "section-title", id: "walk-title" }, "How a case works"),
    h("div", { class: "walk", on: { mouseenter: () => pause(true), mouseleave: () => pause(false), focusin: () => pause(true), focusout: () => pause(false) } },
      h("div", { class: "walk-steps", role: "tablist", "aria-label": "Steps" },
        STEPS.map((s, i) => h("button", {
          class: "walk-step", type: "button", role: "tab", id: `walk-tab-${i}`, "aria-controls": "walk-stage",
          "aria-selected": String(i === 0), on: { click: () => goTo(i, true) },
        },
          h("span", { class: "walk-num" }, String(i + 1)),
          h("span", { class: "walk-copy" }, h("span", { class: "walk-title" }, s.title), h("span", { class: "walk-text" }, s.text)),
          h("span", { class: "walk-bar", "aria-hidden": "true" }, h("i"))))),
      h("div", { class: "stage", id: "walk-stage", role: "tabpanel", "aria-labelledby": "walk-tab-0" })));
}

function goTo(i, user = false) {
  state.step = i;
  document.querySelectorAll(".walk-step").forEach((b, k) => {
    b.setAttribute("aria-selected", String(k === i));
    b.classList.toggle("done", k < i);
  });
  const stage = $("walk-stage");
  stage.setAttribute("aria-labelledby", `walk-tab-${i}`);
  stage.dataset.title = `${i + 1}. ${STEPS[i].title}`;
  mount(stage, h("div", { class: `scene scene-${i + 1}`, "aria-hidden": "true" }, STEPS[i].scene()));
  restartBar();
  if (user) schedule();
}

function restartBar() {
  const bar = document.querySelector(`#walk-tab-${state.step} .walk-bar i`);
  if (!bar) return;
  bar.style.animation = "none";
  void bar.offsetWidth;
  bar.style.animation = reducedMotion() ? "none" : "";
  bar.style.animationPlayState = state.paused ? "paused" : "running";
}

function schedule() {
  clearTimeout(state.timer);
  if (reducedMotion() || state.paused) return;
  state.timer = setTimeout(() => goTo((state.step + 1) % STEPS.length), STEP_MS);
}

function pause(on) {
  state.paused = on;
  const bar = document.querySelector(`#walk-tab-${state.step} .walk-bar i`);
  if (bar) bar.style.animationPlayState = on ? "paused" : "running";
  if (on) clearTimeout(state.timer);
  else schedule();
}

function startWalk() {
  document.documentElement.style.setProperty("--step-ms", `${STEP_MS}ms`);
  goTo(0);
  schedule();
}

// Scenes: small static mock-ups whose parts animate with CSS (see .scene-* in app.css).
function noteLine() {
  return h("div", { class: "mini-note" },
    h("span", { class: "mini-h" }, "Assessment"),
    h("p", {}, h("mark", { class: "sweep s1" }, "Type 2 diabetes"), " with ", h("mark", { class: "sweep s2" }, "CKD stage 4"),
      ". Continue ", h("mark", { class: "sweep s3" }, "insulin"), "."));
}

function option(codes, cls = "") {
  return h("div", { class: `mini-opt ${cls}` }, codes.map((c) => h("span", { class: "code" }, c)));
}

function sceneRead() {
  return [noteLine(), h("div", { class: "mini-tip pop d4" }, icon("marker", 15), "3 deciding details found")];
}

function scenePick() {
  return [
    option(["E11.22", "N18.4", "Z79.4"]),
    option(["E11.9", "N18.4", "Z79.4"], "pick"),
    option(["E11.22", "Z79.4"]),
    h("div", { class: "mini-row" }, h("span", { class: "mini-seg" }, h("b", {}, "Sure"), "Guessing"), h("span", { class: "mini-btn pulse" }, "Check")),
  ];
}

function sceneCoach() {
  return [
    option(["E11.9", "N18.4", "Z79.4"], "wrong"),
    h("div", { class: "mini-pips" }, h("i", { class: "on" }), h("i"), h("i"), h("span", {}, "Hint 1 of 3")),
    h("div", { class: "mini-hint slide" }, h("b", {}, "Contrast pair. "),
      "Your choice would be right if the provider said the CKD is NOT caused by the diabetes. Check what this note says."),
    option(["E11.22", "N18.4", "Z79.4"], "right d5"),
  ];
}

function sceneDebrief() {
  return [
    h("div", { class: "mini-result pop" }, icon("check", 18), "Solved with 1 hint"),
    h("div", { class: "mini-bars" },
      h("div", {}, h("span", {}, "Your first pick"), h("span", { class: "bar" }, h("i", { class: "grow b1" })), h("span", { class: "num" }, "0.166")),
      h("div", {}, h("span", {}, "Correct"), h("span", { class: "bar" }, h("i", { class: "grow b2" })), h("span", { class: "num" }, "0.680"))),
    h("div", { class: "mini-tip pop d5" }, icon("target", 15), "This trap returns in a new case to test the coaching"),
  ];
}

// ---------------------------------------------------------------- how the next case is chosen
function nextCaseLoop() {
  const steps = [
    ["Every wrong answer has a cause", "Each wrong choice is tagged with the trap behind it, like missing a diabetes 'with' link or coding from a medication list."],
    ["A coaching style is picked", "Rule refresher, contrast pair, find the evidence, guiding question, walkthrough or an easier case: whichever has helped most, while still trying others."],
    ["The same trap returns in a new case", "Your next case tests the same trap with a different note. That result is the real test of whether the coaching worked."],
    ["Your tutor learns", "The coaching style that helped is used more for that trap. Confident mistakes come back sooner; mastered traps come back less often."],
  ];
  return h("section", { class: "reveal" },
    h("h2", { class: "section-title" }, "How your next case is chosen"),
    h("ol", { class: "loop" }, steps.map(([title, text], i) =>
      h("li", { style: `--i:${i}` }, h("span", { class: "loop-num" }, String(i + 1)), h("h3", {}, title), h("p", {}, text)))),
    h("p", { class: "loop-foot" }, icon("bulb", 16), "New and weak traps come first, and spaced review brings each one back."));
}

function trust() {
  const card = (name, title, text) => h("div", { class: "card" }, h("h3", {}, icon(name, 16), title), h("p", {}, text));
  return h("section", { class: "trust reveal" },
    card("book", "Answers from rules, not AI", "Every answer comes from the official code set and a rules engine. AI only writes the practice notes."),
    card("check", "Private by design", "No account. Your progress stays in this browser. Sharing anonymous coaching results is optional."),
    card("target", "Draft content", "Cases are drafts until a certified coder reviews them. Not affiliated with AAPC, AHIMA, AMA or CMS."));
}

function revealOnScroll() {
  const els = document.querySelectorAll(".reveal:not(.in)");
  if (reducedMotion() || !("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) {
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    }
  }, { threshold: 0.12 });
  els.forEach((el) => io.observe(el));
}

boot();
