// Student preferences (theme, topic, sharing, shortcuts...), kept in localStorage.

import { PREFS_KEY, loadJSON, saveJSON } from "./store.js";

export const DAILY_GOAL = 10;
export const DEFAULT_PREFS = { theme: null, showDesc: false, topic: null, share: true, shortcuts: true, tipSeen: false };

/** Stored preferences merged over the defaults (a fresh object each call, safe to mutate). */
export function loadPrefs() {
  return { ...DEFAULT_PREFS, ...loadJSON(PREFS_KEY, {}) };
}

/** Persist preferences (ignored when storage is blocked). */
export function savePrefs(prefs) {
  saveJSON(PREFS_KEY, prefs);
}
