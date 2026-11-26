// Topic picker as transparent bubbles drifting in a box: one button per topic, sized by its number of questions.
// core/bubbles.js does the sizing and the physics; this module only draws. Bubbles wander at random, bounce off
// the walls and each other, and stop under a hovered or focused bubble (which grows so its name is readable).
// Motion stops with the Pause button, under prefers-reduced-motion, off screen and in a hidden tab.

import {
  INITIALS_BELOW, SHORT_BELOW, fitRadii, labelSize, scatter, settle, shortLabel, step, uniqueInitials,
} from "../../core/bubbles.js";
import { h, icon } from "../../ui/dom.js";
import { playButton, reducedMotion, setPlayButton } from "../../ui/motion.js";

const COHESION = 0.5; // pull toward the centre that gathers the bubbles into a cloud
const plural = (n) => `${n} question${n === 1 ? "" : "s"}`;

/**
 * The "Practice by topic" section.
 * @param {{topics: object[], selected: string|null, startHref: string, onPick: (id: string|null) => void}} opts
 */
export function topicCloud({ topics, selected, startHref, onPick }) {
  const total = topics.reduce((s, t) => s + (t.scenarios ?? 0), 0);
  const sim = { bodies: [], frozen: new Set(), paused: false, visible: true, frame: 0, last: 0, size: [0, 0] };
  const codes = uniqueInitials(topics.map((t) => t.title));
  // Screen readers get each bubble's full name from its aria-label, so the caption is for sighted users only.
  sim.caption = h("div", { class: "cloud-caption", "aria-hidden": "true" });
  const box = h("div", { class: "cloud", role: "group", "aria-label": "Topics, sized by number of questions" },
    topics.map((tp, i) => bubble(tp, i, codes[i], selected === tp.id, onPick, sim)), sim.caption);
  const section = h("section", { class: "reveal topics-section", id: "topics", "aria-labelledby": "topics-title" },
    h("div", { class: "section-head" },
      h("h2", { class: "section-title", id: "topics-title" }, "Practice by topic"),
      playButton("cloud-play", () => {
        sim.paused = !sim.paused;
        setPlayButton("cloud-play", sim.paused);
        run(box, sim);
      })),
    h("p", { class: "cloud-help" }, "Bigger bubbles hold more questions. Hover, tap or tab to a bubble to see its name; pick one, or practice them all."),
    h("div", { class: "cloud-bar" },
      h("button", {
        class: "chip-btn", type: "button", "aria-pressed": String(selected === null), dataset: { topic: "" },
        on: { click: () => onPick(null) },
      }, `All topics (${total})`),
      h("a", { class: "btn", href: startHref, dataset: { start: "" } }, "Start practice", icon("arrow", 16))),
    box);
  watch(box, topics, sim);
  return section;
}

function bubble(tp, i, code, pressed, onPick, sim) {
  const n = tp.scenarios ?? 0;
  const hold = (on) => () => {
    if (on) sim.frozen.add(i);
    else sim.frozen.delete(i);
    sim.caption.textContent = on ? `${tp.title} · ${plural(n)}` : "";
    const b = sim.bodies[i];
    sim.caption.classList.toggle("top", Boolean(on && b && b.y > sim.size[1] / 2)); // keep the caption off the bubble
  };
  return h("div", { class: "bubble-float" },
    h("button", {
      class: "bubble", type: "button", "aria-pressed": String(pressed), "aria-label": `${tp.title}, ${plural(n)}`,
      title: `${tp.title}: ${plural(n)}`, dataset: { topic: tp.id, kind: tp.kind ?? "hcc", tint: String((i % 5) + 1) },
      on: { click: () => onPick(tp.id), mouseenter: hold(true), mouseleave: hold(false), focus: hold(true), blur: hold(false) },
    },
    h("span", { class: "bubble-name full", "aria-hidden": "true" }, tp.title),
    h("span", { class: "bubble-name short", "aria-hidden": "true" }, shortLabel(tp.title)),
    h("span", { class: "bubble-initials", "aria-hidden": "true" }, code),
    h("span", { class: "bubble-count", "aria-hidden": "true" }, String(n))));
}

/** Size the bubbles for the box and (re)start them: first layout scatters, a resize rescales positions. */
function layout(box, topics, sim) {
  const w = box.clientWidth, ht = box.clientHeight;
  if (!w || !ht) return;
  const radii = fitRadii(topics.map((t) => t.scenarios ?? 0), w, ht);
  if (!sim.bodies.length) {
    // Start with the cloud already formed (and a still cloud under reduced motion).
    sim.bodies = settle(scatter(radii, w, ht, Math.random), 6, w, ht, Math.random, { cohesion: COHESION });
  }
  else {
    const [ow, oh] = sim.size;
    sim.bodies = sim.bodies.map((b, i) => ({ ...b, r: radii[i], x: (b.x * w) / ow, y: (b.y * ht) / oh }));
    sim.bodies = settle(sim.bodies, 1, w, ht, Math.random, { cohesion: COHESION }); // re-forms the cloud at the new size
  }
  sim.size = [w, ht];
  box.classList.toggle("narrow", w < INITIALS_BELOW); // phones: initials only, the name on hover, tap or focus
  [...box.querySelectorAll(".bubble-float")].forEach((el, i) => {
    const r = radii[i];
    Object.assign(el.style, { width: `${2 * r}px`, height: `${2 * r}px` });
    const small = r < SHORT_BELOW; // small bubbles show the short name until hovered or focused
    el.classList.toggle("small", small);
    el.style.setProperty("--fs", `${labelSize(r, small ? shortLabel(topics[i].title) : topics[i].title).toFixed(1)}px`);
    el.style.setProperty("--grow", Math.min(2.4, Math.max(1.3, 56 / r)).toFixed(2)); // small bubbles grow more
    el.style.setProperty("--fs-i", `${Math.max(11, Math.min(18, r / 2.3)).toFixed(1)}px`);
  });
  draw(box, sim);
}

function draw(box, sim) {
  const [w, ht] = sim.size;
  [...box.querySelectorAll(".bubble-float")].forEach((el, i) => {
    const b = sim.bodies[i];
    el.style.transform = `translate(${(b.x - b.r).toFixed(1)}px, ${(b.y - b.r).toFixed(1)}px)`;
    // Grow toward the middle of the box: a bubble near the left wall grows to the right, and so on.
    el.firstChild.style.transformOrigin = `${((b.x / w) * 100).toFixed(0)}% ${((b.y / ht) * 100).toFixed(0)}%`;
  });
}

/** Run the animation loop while it should move; stop it otherwise. */
function run(box, sim) {
  const moving = !sim.paused && sim.visible && !document.hidden && !reducedMotion() && sim.bodies.length;
  if (!moving) {
    cancelAnimationFrame(sim.frame);
    sim.frame = 0;
    return;
  }
  if (sim.frame) return;
  sim.last = performance.now();
  const tick = (now) => {
    const [w, ht] = sim.size;
    sim.bodies = step(sim.bodies, (now - sim.last) / 1000, w, ht, Math.random, { frozen: sim.frozen, cohesion: COHESION });
    sim.last = now;
    draw(box, sim);
    sim.frame = requestAnimationFrame(tick);
  };
  sim.frame = requestAnimationFrame(tick);
}

function watch(box, topics, sim) {
  let width = 0, height = 0;
  const resize = () => {
    if (box.clientWidth === width && box.clientHeight === height) return;
    [width, height] = [box.clientWidth, box.clientHeight];
    layout(box, topics, sim);
    run(box, sim);
  };
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(box);
  else addEventListener("resize", resize);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => {
      sim.visible = e.isIntersecting;
      run(box, sim);
    }).observe(box);
  }
  document.addEventListener("visibilitychange", () => run(box, sim));
  requestAnimationFrame(resize);
}
