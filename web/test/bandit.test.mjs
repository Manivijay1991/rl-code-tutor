import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ACTIONS,
  bucket,
  chooseAction,
  counts,
  learnedContexts,
  posteriorMeans,
  sampleBeta,
  sampleGamma,
  updateBandit,
} from "../js/bandit.js";
import { makeRng } from "../js/random.js";

test("bucket", () => {
  assert.deepEqual([0, 1, 2, 3, 9].map(bucket), [1, 1, 2, 3, 3]);
});

test("samples stay in range and match the mean", () => {
  const rng = makeRng(1);
  const xs = Array.from({ length: 4000 }, () => sampleBeta(2, 6, rng));
  assert.ok(xs.every((x) => x > 0 && x < 1));
  const mean = xs.reduce((a, b) => a + b) / xs.length;
  assert.ok(Math.abs(mean - 0.25) < 0.02, `mean ${mean}`);
  assert.ok(sampleGamma(0.5, rng) > 0);
});

test("gamma rejects a non-positive shape", () => {
  assert.throws(() => sampleGamma(0), RangeError);
});

test("update is immutable and counts successes and failures", () => {
  const b0 = {};
  const b1 = updateBandit(b0, "t:c", 1, "walkthrough", 1);
  const b2 = updateBandit(b1, "t:c", 1, "walkthrough", 0);
  assert.deepEqual(b0, {});
  assert.deepEqual(counts(b2, "t:c", 1, "walkthrough"), [2, 2]);
  assert.deepEqual(counts(b2, "t:c", 2, "walkthrough"), [1, 1]);
});

test("update rejects unknown actions", () => {
  assert.throws(() => updateBandit({}, "t:c", 1, "nap", 1), RangeError);
});

test("choose prefers a clearly better action and is reproducible", () => {
  let b = {};
  for (let i = 0; i < 30; i++) {
    b = updateBandit(b, "t:c", 1, "contrast_pair", 1);
    for (const a of ACTIONS.filter((x) => x !== "contrast_pair")) b = updateBandit(b, "t:c", 1, a, 0);
  }
  const picks = Array.from({ length: 200 }, (_, i) => chooseAction(b, "t:c", 1, makeRng(i)));
  assert.ok(picks.filter((a) => a === "contrast_pair").length > 190);
  assert.equal(chooseAction(b, "t:c", 1, makeRng(7)), chooseAction(b, "t:c", 1, makeRng(7)));
});

test("posterior means and learned contexts", () => {
  let b = updateBandit({}, "t:c", 2, "find_meat", 1);
  b = updateBandit(b, "t:c", 2, "find_meat", 1);
  b = updateBandit(b, "t:c", 2, "rule_refresh", 0);
  assert.equal(posteriorMeans(b, "t:c", 2).find_meat, 0.75);
  assert.equal(posteriorMeans(b, "t:c", 2).walkthrough, 0.5);
  assert.deepEqual(learnedContexts(b, 2).map((c) => [c.confusion, c.bucket, c.best, c.trials]), [["t:c", 2, "find_meat", 3]]);
  assert.deepEqual(learnedContexts(b, 10), []);
});
