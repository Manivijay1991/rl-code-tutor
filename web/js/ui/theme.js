// Light/dark theme: follows the system unless the student picked one.

import { savePrefs } from "../data/prefs.js";
import { icon, mount } from "./dom.js";

/** True when the page is (or would be) dark. */
export function isDark(theme) {
  return theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Apply the theme preference to the page and show the matching toggle icon. */
export function applyTheme(prefs, button) {
  if (prefs.theme) document.documentElement.dataset.theme = prefs.theme;
  else delete document.documentElement.dataset.theme;
  if (button) mount(button, icon(isDark(prefs.theme) ? "sun" : "moon"));
}

/** Flip light/dark, save it, and apply it. */
export function toggleTheme(prefs, button) {
  prefs.theme = isDark(document.documentElement.dataset.theme) ? "light" : "dark";
  savePrefs(prefs);
  applyTheme(prefs, button);
}
