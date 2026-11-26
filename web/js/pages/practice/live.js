// Optional live bandit API: shared coaching counts in, anonymous rewards out (data/api.js).
// The policy is loaded on page load and refreshed in the background after a finished question when it is
// POLICY_REFRESH_MS old; choosing a coaching style always uses the copy in memory (no network wait).

import { enqueue, flush, loadConfig, refreshPolicy as nextPolicy } from "../../data/api.js";
import { loadJSON, OUTBOX_KEY, removeKey, saveJSON } from "../../data/store.js";
import { app, savePrefs, ui } from "./state.js";

export async function connectApi() {
  app.api = (await loadConfig()).api;
  if (!app.api || !app.prefs.share) return;
  app.policyCheckedAt = null; // force a load now
  await refreshPolicy();
  await sendOutbox();
}

/** Reload the shared policy when it is stale; does nothing offline, when sharing is off, or while fresh. */
export async function refreshPolicy(now = Date.now()) {
  if (!app.prefs.share) return;
  const next = await nextPolicy({ api: app.api, shared: app.shared, checkedAt: app.policyCheckedAt }, now);
  if (next) [app.shared, app.policyCheckedAt] = [next.shared, next.checkedAt];
}

export async function sendOutbox(events = []) {
  if (!app.api || !app.prefs.share) return;
  const outbox = enqueue(loadJSON(OUTBOX_KEY, []), events);
  saveJSON(OUTBOX_KEY, outbox);
  saveJSON(OUTBOX_KEY, await flush(app.api, outbox));
}

export function setShare(on) {
  app.prefs.share = on;
  savePrefs();
  if (on) connectApi();
  else {
    app.shared = null;
    app.policyCheckedAt = null;
    removeKey(OUTBOX_KEY);
  }
  ui.renderDrawer();
}
