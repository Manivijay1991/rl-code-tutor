// Dialogs, toasts and screen-reader announcements.

import { h, mount } from "../../ui/dom.js";
import { app, $, savePrefs } from "./state.js";

export function showOverlay(content, onClose) {
  const ov = $("overlay");
  const opener = document.activeElement;
  const close = () => {
    ov.hidden = true;
    onClose?.();
    opener?.focus?.();
  };
  mount(ov, h("div", { class: "modal", role: "dialog", "aria-modal": "true" }, content(close)));
  ov.hidden = false;
  ov.onclick = (e) => e.target === ov && close();
  ov.querySelector("button")?.focus();
}

export function showKeys() {
  const rows = [["1–6", "Pick a choice"], ["↑ ↓", "Move between choices"], ["Enter", "Check / next case"],
    ["M", "Highlighter"], ["D", "Code descriptions"], ["N", "Next case (after answering)"],
    ["P", "Progress"], ["?", "This help"], ["Esc", "Close"]];
  showOverlay((close) => [
    h("h2", {}, "Keyboard shortcuts"),
    h("div", { class: "keys" }, rows.flatMap(([k, d]) => [h("span", { class: "kbd" }, k), h("span", {}, d)])),
    h("label", { class: "switch" },
      h("input", { type: "checkbox", checked: app.prefs.shortcuts, on: { change: (e) => { app.prefs.shortcuts = e.target.checked; savePrefs(); } } }),
      "Single-key shortcuts (turn off if you use speech input)"),
    h("div", { class: "actions" }, h("span", { class: "spacer" }), h("button", { class: "btn", type: "button", on: { click: close } }, "Got it")),
  ]);
}

export function toast(text) {
  const el = $("toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2800);
}

export function announce(text) {
  $("announce").textContent = text;
}
