import assert from "node:assert/strict";
import { test } from "node:test";

import { DAILY_GOAL, DEFAULT_PREFS, isDark, loadPrefs, practiceUrl, today, trapName } from "../../web/js/common.js";

test("today is the local date as YYYY-MM-DD", () => {
  assert.equal(today(new Date(2026, 0, 5)), "2026-01-05");
  assert.equal(today(new Date(2026, 10, 23, 23, 59)), "2026-11-23");
});

test("trap names are readable", () => {
  assert.equal(trapName("ckd_staging:missed_htn_ckd_link"), "Missed HTN CKD link");
  assert.equal(trapName("diabetes_complications:z794_for_type1"), "Z79.4 for type1");
  assert.equal(trapName("plain"), "Plain");
});

test("practice links carry the topic", () => {
  assert.equal(practiceUrl(), "practice.html");
  assert.equal(practiceUrl(null), "practice.html");
  assert.equal(practiceUrl("ckd_staging"), "practice.html?topic=ckd_staging");
  assert.equal(practiceUrl("a b&c"), "practice.html?topic=a%20b%26c");
});

test("preferences fall back to defaults without storage", () => {
  assert.deepEqual(loadPrefs(), DEFAULT_PREFS);
  assert.notEqual(loadPrefs(), DEFAULT_PREFS); // a fresh copy, safe to mutate
});

test("an explicit theme decides dark mode", () => {
  assert.equal(isDark("dark"), true);
  assert.equal(isDark("light"), false);
  assert.equal(DAILY_GOAL, 10);
});
