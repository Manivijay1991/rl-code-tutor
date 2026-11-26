// Shared state of the assessment page and the `ui` registry. Feature modules import only this module (plus
// core/, data/ and ui/); they call each other through `ui.<name>`, which main.js fills in once.

import { loadPrefs, savePrefs as storePrefs } from "../../data/prefs.js";
import { saveJSON, PROGRESS_KEY } from "../../data/store.js";
import { emptyProgress } from "../../core/progress.js";

export const MAX_HINTS = 3;
export const $ = (id) => document.getElementById(id);

/** Feature functions by name, registered by main.js (avoids import cycles between feature modules). */
export const ui = {};

export const app = {
  manifest: null, // data/manifest.json: topics, tables, references, HCC labels
  files: {}, // loaded topic files by topic id
  view: null, // what the core logic reads: the manifest plus the topic files in play (data/catalog.js buildView)
  progress: emptyProgress(),
  prefs: loadPrefs(),
  api: null, // live bandit API base URL from config.json, or null (offline)
  shared: null, // {arms, events} from GET /v1/policy
  policyCheckedAt: null, // ms timestamp of the last policy fetch attempt (refreshed every POLICY_REFRESH_MS)
  focus: null,
  q: null,
};

export function tableOf(scenario) {
  return app.view.tables[scenario.table];
}

export function correctCodes(scenario) {
  return scenario.options.find((o) => o.correct).codes;
}

export function savePrefs() {
  storePrefs(app.prefs);
}

export function saveProgress() {
  saveJSON(PROGRESS_KEY, app.progress);
}
