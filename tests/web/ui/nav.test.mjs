import assert from "node:assert/strict";
import { test } from "node:test";

import { practiceUrl } from "../../../web/js/ui/nav.js";

test("practice links carry the topic", () => {
  assert.equal(practiceUrl(), "practice.html");
  assert.equal(practiceUrl(null), "practice.html");
  assert.equal(practiceUrl("ckd"), "practice.html?topic=ckd");
  assert.equal(practiceUrl("a b&c"), "practice.html?topic=a%20b%26c");
});
