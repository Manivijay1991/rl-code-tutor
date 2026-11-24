// Home page (index.html): what the app is, an animated walkthrough of a case, how the next case is
// chosen, and the way into the assessment (practice.html). Reads the bundle only for counts.

import { ACTIONS, ACTION_LABELS, chooseAction, posteriorMeans, updateBandit } from "./bandit.js";
import { applyTheme, loadBundle, loadPrefs, practiceUrl, savePrefs, toggleTheme, trapName } from "./common.js";
import { h, icon, mount } from "./dom.js";
import { makeRng, shuffled } from "./random.js";
import { migrate } from "./progress.js";
import { PROGRESS_KEY, loadJSON } from "./store.js";

const STEP_MS = 5200;
const $ = (id) => document.getElementById(id);
const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = { prefs: loadPrefs(), bundle: null, step: 0, timer: null, paused: false, userPaused: false };

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
  startJourney();
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
      statTile("book", state.bundle.scenarios.length, "clinical cases", "Practice notes to read and code"),
      statTile("target", traps, "coding traps", "Common mistakes the tutor spots and coaches"),
      statTile("chart", tables.length, "topics", tables.map(([, tb]) => (tb.topic || tb.title).split("/").pop().trim()).join(", ")),
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

// ---------------------------------------------------------------- animated walkthrough
const STEPS = [
  { title: "Read and mark the evidence", text: "Turn on the highlighter and tap the words that decide the codes, the way an auditor reads.", scene: sceneRead },
  { title: "Pick the code set", text: "Choose the code set the note supports, then check your answer.", scene: scenePick },
  { title: "Miss? Get coached", text: "Up to 3 hints, each one closer, with a re-pick after each. No hint names the answer.", scene: sceneCoach },
  { title: "Learn why it matters", text: "The rule, the deciding words, and how the miss moves the CMS-HCC risk score.", scene: sceneDebrief },
];

function walkthrough() {
  return h("section", { class: "reveal", "aria-labelledby": "walk-title" },
    h("div", { class: "section-head" },
      h("h2", { class: "section-title", id: "walk-title" }, "How a case works"),
      playButton("walk-play", () => setUserPause(!state.userPaused))),
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
  bar.style.animationPlayState = state.paused || state.userPaused ? "paused" : "running";
}

function schedule() {
  clearTimeout(state.timer);
  if (reducedMotion() || state.paused || state.userPaused) return;
  state.timer = setTimeout(() => goTo((state.step + 1) % STEPS.length), STEP_MS);
}

function pause(on) {
  state.paused = on;
  const bar = document.querySelector(`#walk-tab-${state.step} .walk-bar i`);
  if (bar) bar.style.animationPlayState = on || state.userPaused ? "paused" : "running";
  if (on) clearTimeout(state.timer);
  else schedule();
}

function setUserPause(on) {
  state.userPaused = on;
  setPlayButton("walk-play", on);
  pause(state.paused);
}

/** A pause/play toggle; `onToggle` flips the state, setPlayButton shows it. */
function playButton(id, onToggle) {
  const b = h("button", { class: "btn ghost small play", type: "button", id, "aria-pressed": "false", on: { click: onToggle } });
  if (reducedMotion()) b.hidden = true;
  mount(b, icon("pause", 14), "Pause");
  return b;
}

function setPlayButton(id, paused) {
  const b = $(id);
  if (!b) return;
  b.setAttribute("aria-pressed", String(paused));
  mount(b, icon(paused ? "play" : "pause", 14), paused ? "Play" : "Pause");
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
    h("div", { class: "mini-row end" }, h("span", { class: "mini-btn pulse" }, "Check")),
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
// "Try the loop": an interactive journey the visitor drives. Choices decide the path; the coaching
// pick and the learning use the real bandit (bandit.js). Traps rotate through real ones from the content.

const RAIL = [
  { id: "choose", label: "Case", icon: "target" },
  { id: "read", label: "Read", icon: "marker" },
  { id: "trap", label: "Trap", icon: "x" },
  { id: "coach", label: "Coach", icon: "bulb" },
  { id: "hints", label: "Hints", icon: "book" },
  { id: "retest", label: "Re-test", icon: "reset" },
  { id: "learn", label: "Learn", icon: "chart" },
];
const RIGHT_PATH = new Set(["choose", "read", "right"]);
const jr = { traps: [], t: 0, step: "choose", odds: {}, pick: null, helped: null, rolling: false, visited: new Set(["choose"]) };

const jTrap = () => jr.traps[jr.t % jr.traps.length];

function journeyTraps() {
  const all = Object.entries(state.bundle.tables).flatMap(([tid, t]) => Object.keys(t.confusions).map((c) => `${tid}:${c}`));
  return all.length ? shuffled(all, makeRng(11)) : ["demo:missed_with_link"];
}

function learningLoop() {
  return h("section", { class: "reveal", "aria-labelledby": "loop-title" },
    h("div", { class: "section-head" },
      h("h2", { class: "section-title", id: "loop-title" }, "How your next case is chosen"),
      h("button", { class: "btn ghost small", type: "button", on: { click: restartJourney } }, icon("reset", 14), "Start over")),
    h("div", { class: "journey" },
      h("ol", { class: "rail", id: "rail", "aria-label": "Steps of the loop" }),
      h("div", { class: "jcard", id: "jcard", "aria-live": "polite" })),
    h("p", { class: "loop-foot" }, icon("bulb", 16), "Try it: your choices decide the path. Every student has their own coaching odds for every trap."));
}

function go(step) {
  jr.step = step;
  jr.visited.add(step === "right" ? "read" : step);
  renderJourney();
  $("jcard")?.querySelector("button")?.focus({ preventScroll: true });
}

function restartJourney() {
  jr.visited = new Set(["choose"]);
  jr.pick = null;
  jr.helped = null;
  go("choose");
}

function nextCase() {
  jr.t += 1;
  restartJourney();
}

function renderRail() {
  const order = RAIL.map((r) => r.id);
  const current = jr.step === "right" ? "read" : jr.step;
  const at = order.indexOf(current);
  const skipped = (id) => jr.step === "right" && !RIGHT_PATH.has(id);
  mount($("rail"), RAIL.map((r, i) =>
    h("li", {
      class: `rnode${r.id === current ? " on" : ""}${i < at || (jr.step === "right" && i <= at) ? " done" : ""}${skipped(r.id) ? " skip" : ""}`,
      "aria-current": r.id === current ? "step" : null,
    }, h("span", { class: "rdot" }, icon(r.icon, 16)), h("span", { class: "rlabel" }, r.label))));
  $("rail").style.setProperty("--fill", String(Math.max(0, at) / (RAIL.length - 1)));
}

function choice(label, kind, onClick) {
  return h("button", { class: `btn ${kind === "ghost" ? "ghost" : ""}`, type: "button", on: { click: onClick } }, label);
}

function oddsBars(highlight, delta = 0) {
  const trap = jTrap();
  const means = posteriorMeans(jr.odds[trap] ?? {}, trap, 1);
  return h("ul", { class: "jodds" }, ACTIONS.map((a) => {
    const pct = Math.round(means[a] * 100);
    return h("li", { class: a === highlight ? `hl${delta > 0 ? " up" : delta < 0 ? " down" : ""}` : "" },
      h("span", { class: "jo-label" }, ACTION_LABELS[a]),
      h("span", { class: "jo-bar" }, h("i", { style: `width:${pct}%` })),
      h("span", { class: "jo-num" }, `${pct}%`));
  }));
}

function stageCard() {
  const trap = trapName(jTrap());
  const style = jr.pick ? ACTION_LABELS[jr.pick] : "";
  const card = (iconName, kicker, title, text, visual, actions) =>
    [h("div", { class: "jhead" }, h("span", { class: "jicon" }, icon(iconName, 22)), h("span", {}, h("span", { class: "jkicker" }, kicker), h("h3", {}, title))),
      h("p", { class: "jtext" }, text), visual, h("div", { class: "jactions" }, actions)];

  switch (jr.step) {
    case "choose":
      return card("target", "Step 1", "A case is chosen for you",
        "Traps waiting for a re-test come first, then reviews that are due, then new traps, then your weakest trap.",
        h("div", { class: "jqueue" }, ["Re-test", "Due review", "New trap", "Weakest"].map((q, i) => h("span", { style: `--i:${i}` }, q))),
        [choice("Open the case", "", () => go("read"))]);
    case "read":
      return card("marker", "Step 2", "Read the note, pick the codes",
        "Mark the words that decide the codes and choose a code set. How did it go?",
        h("div", { class: "jnote" }, "Assessment: ", h("mark", {}, "Type 2 diabetes"), " with ", h("mark", {}, "CKD stage 4"), ". Continue ", h("mark", {}, "insulin"), "."),
        [choice("I got it right", "", () => go("right")), choice("I fell for a trap", "ghost", () => go("trap"))]);
    case "right":
      return card("check", "Right on the first pick", "Your review gap grows",
        "Each time you get this trap right on the first pick, it waits longer before it comes back for review.",
        h("div", { class: "jgap" }, [2, 4, 8, 16].map((n, i) => h("span", { style: `--i:${i}` }, `${n}`)), h("em", {}, "cases until review")),
        [choice("Next case", "", nextCase)]);
    case "trap":
      return card("x", "Not quite", `Trap found: ${trap}`,
        "Your wrong choice is tagged with the trap behind it, so the tutor knows exactly what to coach.",
        trapDetail(),
        [choice("Coach me", "", () => { jr.pick = null; go("coach"); })]);
    case "coach":
      return card("bulb", "Step 3", "The tutor picks a coaching style",
        jr.pick ? `It picked "${style}": the best odds for this trap so far, while still trying others now and then.`
          : "It weighs what has worked for this trap before, and leaves room to try others.",
        h("div", { class: "jchips", id: "jchips" }, ACTIONS.map((a) => h("span", { class: `chip${a === jr.pick ? " won" : ""}`, dataset: { a } }, ACTION_LABELS[a]))),
        [jr.pick ? choice("See the hints", "", () => go("hints")) : choice("Pick a style", "", rollStyle)]);
    case "hints":
      return card("book", "Step 4", "Up to 3 hints, then re-pick",
        `Coaching with "${style}": each hint gets closer, you re-pick after each, and no hint names the answer.`,
        h("div", { class: "jpips" }, [1, 2, 3].map((n) => h("span", { style: `--i:${n}` }, `Hint ${n}`))),
        [choice("Later: a new case", "", () => go("retest"))]);
    case "retest":
      return card("reset", "Step 5", "Same trap, new case",
        `A different note tests "${trap}" again. This is the real test of whether "${style}" worked. How did it go?`,
        null,
        [choice("Right this time", "", () => learn(1)), choice("Missed again", "ghost", () => learn(0))]);
    case "learn":
      return card("chart", "Step 6", jr.helped ? "The coaching worked" : "The coaching did not stick",
        jr.helped ? `"${style}" becomes more likely for "${trap}".` : `"${style}" becomes less likely for "${trap}"; the tutor will try other styles more.`,
        oddsBars(jr.pick, jr.helped ? 1 : -1),
        [choice("Next case", "", nextCase), choice("Try this trap again", "ghost", () => { jr.visited = new Set(["choose", "read"]); go("trap"); })]);
    default:
      return [];
  }
}

/** The current trap's own description and lean, straight from the decision tables. */
function trapDetail() {
  const [tid, cid] = jTrap().split(":");
  const info = state.bundle.tables[tid]?.confusions?.[cid];
  if (!info) return null;
  const lean = { over: "Overcoding", under: "Undercoding", neutral: "Wrong level of detail" }[info.lean] ?? "";
  return h("div", { class: "jtrap" },
    h("span", { class: `opt-badge lean-${info.lean}` }, lean),
    h("span", { class: "jtrap-desc" }, info.description));
}

/** Spin through the styles, then land on the real Thompson-sampling pick. */
function rollStyle() {
  if (jr.rolling) return;
  const trap = jTrap();
  const pick = chooseAction(jr.odds[trap] ?? {}, trap, 1);
  const done = () => {
    jr.rolling = false;
    jr.pick = pick;
    renderJourney();
    $("jcard")?.querySelector(".jactions button")?.focus({ preventScroll: true });
  };
  if (reducedMotion()) return done();
  jr.rolling = true;
  const chips = [...document.querySelectorAll("#jchips .chip")];
  const target = ACTIONS.indexOf(pick);
  const steps = ACTIONS.length * 2 + target; // two full rounds, then stop on the pick
  const SPIN_MS = 1400;
  const t0 = performance.now();
  // Time-based, so throttled timers (busy device, background tab) cannot leave it stuck mid-spin.
  const tick = () => {
    const k = Math.min(1, (performance.now() - t0) / SPIN_MS);
    const at = Math.round(steps * (1 - (1 - k) ** 2)); // ease out: slows down near the end
    chips.forEach((c, i) => c.classList.toggle("spin", i === at % ACTIONS.length));
    if (k < 1) setTimeout(tick, 50);
    else setTimeout(done, 200);
  };
  tick();
}

function learn(helped) {
  const trap = jTrap();
  jr.helped = helped;
  jr.odds[trap] = updateBandit(jr.odds[trap] ?? {}, trap, 1, jr.pick, helped);
  go("learn");
}

function renderJourney() {
  renderRail();
  mount($("jcard"), stageCard());
}

function startJourney() {
  jr.traps = journeyTraps();
  renderJourney();
}

function trust() {
  const card = (name, title, text) => h("div", { class: "card" }, h("h3", {}, icon(name, 16), title), h("p", {}, text));
  return h("section", { class: "trust reveal" },
    card("book", "Answers from rules, not AI", "Every answer comes from the official code set and a rules engine. AI only writes the practice notes."),
    card("check", "Private by design", "No account. Your progress stays in this browser. Sharing anonymous coaching results is optional."),
    card("target", "Draft content", "Cases are drafts until a certified coder reviews them. CRC is an AAPC credential; this tool is not affiliated with AAPC, AHIMA, AMA or CMS."));
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
