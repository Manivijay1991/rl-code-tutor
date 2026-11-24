// Shared by both pages (index.html = home, practice.html = assessment): preferences, theme, dates, names.

import { icon, mount } from "./dom.js";
import { PREFS_KEY, loadJSON, saveJSON } from "./store.js";

export const DAILY_GOAL = 10;
export const DEFAULT_PREFS = { theme: null, showDesc: true, topic: null, share: true };

/** Stored preferences merged over the defaults. */
export function loadPrefs() {
  return { ...DEFAULT_PREFS, ...loadJSON(PREFS_KEY, {}) };
}

/** Persist preferences (ignored when storage is blocked). */
export function savePrefs(prefs) {
  saveJSON(PREFS_KEY, prefs);
}

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

/** Today's date in local time, "YYYY-MM-DD" (the key used for daily counts). */
export function today(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const TRAP_WORDS = { ckd: "CKD", htn: "HTN", esrd: "ESRD", meat: "MEAT", z794: "Z79.4", dm: "DM", mdd: "MDD" };

/** Readable trap name from its id: "table:missed_htn_ckd_link" -> "Missed HTN CKD link". */
export function trapName(confusion) {
  const words = confusion.split(":").pop().split("_").map((w) => TRAP_WORDS[w] ?? w);
  const text = words.join(" ");
  return text[0].toUpperCase() + text.slice(1);
}

/** Load the exported bundle (scenarios, tables, codes). Throws on failure. */
export async function loadBundle(url = "data/bundle.json") {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** URL of the assessment page, optionally for one topic. */
export function practiceUrl(topic = null) {
  return topic ? `practice.html?topic=${encodeURIComponent(topic)}` : "practice.html";
}
