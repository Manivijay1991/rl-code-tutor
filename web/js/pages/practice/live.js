// Optional live bandit API: shared coaching counts in, anonymous rewards out (data/api.js).

import { enqueue, fetchPolicy, flush, loadConfig } from "../../data/api.js";
import { loadJSON, OUTBOX_KEY, removeKey, saveJSON } from "../../data/store.js";
import { app, savePrefs, ui } from "./state.js";

export async function connectApi() {
  app.api = (await loadConfig()).api;
  if (!app.api || !app.prefs.share) return;
  app.shared = await fetchPolicy(app.api);
  await sendOutbox();
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
    removeKey(OUTBOX_KEY);
  }
  ui.renderDrawer();
}
