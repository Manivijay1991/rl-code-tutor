import assert from "node:assert/strict";
import { test } from "node:test";

import { DAILY_GOAL, DEFAULT_PREFS, loadPrefs, savePrefs } from "../../../web/js/data/prefs.js";

test("preferences fall back to defaults without storage", () => {
  assert.deepEqual(loadPrefs(), DEFAULT_PREFS);
  assert.notEqual(loadPrefs(), DEFAULT_PREFS); // a fresh copy, safe to mutate
  assert.equal(DAILY_GOAL, 10);
});

test("saving without storage is a harmless no-op", () => {
  assert.doesNotThrow(() => savePrefs({ ...DEFAULT_PREFS, theme: "dark" }));
});
