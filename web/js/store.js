// Browser storage, guarded: private windows, blocked storage and previews must not break the app.
// Progress lives only in this browser (no accounts, no server, no student identifiers).

export const PROGRESS_KEY = "coding-tutor.progress.v1";
export const PREFS_KEY = "coding-tutor.prefs.v1";

function storage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Read JSON, or return `fallback` when missing, unreadable or blocked. */
export function loadJSON(key, fallback, store = storage()) {
  try {
    const raw = store?.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

/** Write JSON; returns false when storage is unavailable. */
export function saveJSON(key, value, store = storage()) {
  try {
    if (!store) return false;
    store.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

/** Remove a key; ignores errors. */
export function removeKey(key, store = storage()) {
  try {
    store?.removeItem(key);
  } catch {
    /* storage blocked */
  }
}
