// Motion helpers shared by the pages: respect prefers-reduced-motion, pause/play toggles, reveal on scroll.

import { icon, mount } from "./dom.js";

/** True when the student asked the system for less motion. */
export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** A pause/play toggle; `onToggle` flips the state, setPlayButton shows it. Hidden under reduced motion. */
export function playButton(id, onToggle) {
  const b = document.createElement("button");
  Object.assign(b, { className: "btn ghost small play", type: "button", id });
  b.setAttribute("aria-pressed", "false");
  b.addEventListener("click", onToggle);
  if (reducedMotion()) b.hidden = true;
  mount(b, icon("pause", 14), "Pause");
  return b;
}

/** Show a pause/play toggle's state. */
export function setPlayButton(id, paused) {
  const b = document.getElementById(id);
  if (!b) return;
  b.setAttribute("aria-pressed", String(paused));
  mount(b, icon(paused ? "play" : "pause", 14), paused ? "Play" : "Pause");
}

/** Fade sections in as they scroll into view (immediately under reduced motion or without IntersectionObserver). */
export function revealOnScroll() {
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
