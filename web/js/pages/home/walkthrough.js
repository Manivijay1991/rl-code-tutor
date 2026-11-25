// Home page: the animated "How a case works" walkthrough. Steps auto-advance with a progress bar; hover,
// focus or the Pause button stop them, and reduced motion turns auto-advance off.

import { h, icon, mount } from "../../ui/dom.js";
import { playButton, reducedMotion, setPlayButton } from "../../ui/motion.js";

const STEP_MS = 5200;
const state = { step: 0, timer: null, paused: false, userPaused: false };
const $ = (id) => document.getElementById(id);

const STEPS = [
  { title: "Read and mark the evidence", text: "Turn on the highlighter and tap the words that decide the codes, the way an auditor reads.", scene: sceneRead },
  { title: "Pick the code set", text: "Choose the code set the note supports, then check your answer.", scene: scenePick },
  { title: "Miss? Get coached", text: "Up to 3 hints, each one closer, with a re-pick after each. No hint names the answer.", scene: sceneCoach },
  { title: "Learn why it matters", text: "The rule, the deciding words, and how the miss moves the CMS-HCC risk score.", scene: sceneDebrief },
];

/** The walkthrough section (call startWalk() once it is in the page). */
export function walkthrough() {
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

/** Show the first step and start auto-advancing. */
export function startWalk() {
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
    option(["E11.22", "Z79.4"], "pick"),
    option(["E11.9", "N18.4", "Z79.4"]),
    h("div", { class: "mini-row end" }, h("span", { class: "mini-btn pulse" }, "Check")),
  ];
}

function sceneCoach() {
  return [
    option(["E11.22", "Z79.4"], "wrong"),
    h("div", { class: "mini-pips" }, h("i", { class: "on" }), h("i"), h("i"), h("span", {}, "Hint 1 of 3")),
    h("div", { class: "mini-hint slide" }, h("b", {}, "Rule refresher. "),
      "The note documents a CKD stage. Does the diabetes-with-CKD code tell you to add another code for it?"),
    option(["E11.22", "N18.4", "Z79.4"], "right d5"),
  ];
}

// Real CMS-HCC V28 scores for this case: leaving out the CKD stage code drops HCC 327 (CKD stage 4, 0.514).
// (The diabetes HCCs share one weight in V28, so a diabetes-only miss would not change the score.)
function sceneDebrief() {
  return [
    h("div", { class: "mini-result pop" }, icon("check", 18), "Solved with 1 hint"),
    h("div", { class: "mini-bars" },
      h("p", { class: "mini-bars-k" }, "Risk score ", h("span", {}, "(1.0 = an average Medicare patient)")),
      h("div", {}, h("span", {}, "Your first pick"), h("span", { class: "bar" }, h("i", { class: "grow b1" })), h("span", { class: "num" }, "0.166")),
      h("div", {}, h("span", {}, "Correct"), h("span", { class: "bar" }, h("i", { class: "grow b2" })), h("span", { class: "num" }, "0.680")),
      h("p", { class: "mini-bars-cap" }, "Leaving out CKD stage 4 under-reports this patient by 0.514, about half an average patient's cost.")),
    h("div", { class: "mini-tip pop d5" }, icon("target", 15), "This trap returns in a new case to test the coaching"),
  ];
}
