import assert from "node:assert/strict";
import { test } from "node:test";

import { today, trapName } from "../../../web/js/core/format.js";

test("today is the local date as YYYY-MM-DD", () => {
  assert.equal(today(new Date(2026, 0, 5)), "2026-01-05");
  assert.equal(today(new Date(2026, 10, 23, 23, 59)), "2026-11-23");
});

test("trap names are readable", () => {
  assert.equal(trapName("ckd_staging:missed_htn_ckd_link"), "Missed HTN CKD link");
  assert.equal(trapName("diabetes_complications:z794_for_type1"), "Z79.4 for type1");
  assert.equal(trapName("plain"), "Plain");
});
