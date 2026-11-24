import assert from "node:assert/strict";
import { test } from "node:test";

import { emptyProgress, recordOutcome } from "../../web/js/progress.js";
import { makeRng } from "../../web/js/random.js";
import { nextScenario, weakest } from "../../web/js/selector.js";

const sc = (id, table, traps, nCodes = 1) => ({
  id,
  table,
  options: [
    { codes: Array.from({ length: nCodes }, (_, i) => `C${i}`), correct: true },
    ...traps.map((c) => ({ codes: ["W"], correct: false, confusion: c, lean: "over" })),
  ],
});
const bundle = {
  scenarios: [sc("a1", "t", ["x"], 3), sc("a2", "t", ["x"], 1), sc("a3", "t", ["x", "y"], 2), sc("b1", "u", ["z"])],
};
const base = { hintsUsed: 0, revealed: false, evidence: null, date: "d" };

test("empty pool returns null", () => {
  assert.equal(nextScenario({ scenarios: [] }, emptyProgress()), null);
  assert.equal(nextScenario(bundle, emptyProgress(), { topic: "nope" }), null);
});

test("unseen traps come first and topic filters", () => {
  const r = nextScenario(bundle, emptyProgress(), { topic: "u", rng: makeRng(1) });
  assert.equal(r.scenario.id, "b1");
  assert.equal(r.reason, "new");
});

test("a pending reward picks a NEW case with the same trap", () => {
  const miss = recordOutcome(emptyProgress(), bundle.scenarios[0], {
    ...base, firstOption: bundle.scenarios[0].options[1], action: "contrast_pair", missBucket: 1,
  }).progress;
  for (let seed = 0; seed < 10; seed++) {
    const r = nextScenario(bundle, miss, { rng: makeRng(seed) });
    assert.equal(r.reason, "reward");
    assert.equal(r.confusion, "t:x");
    assert.notEqual(r.scenario.id, "a1");
  }
});

test("easier_case picks the case with the fewest codes", () => {
  const miss = recordOutcome(emptyProgress(), bundle.scenarios[2], {
    ...base, firstOption: bundle.scenarios[2].options[1], action: "easier_case", missBucket: 1,
  }).progress;
  const r = nextScenario(bundle, miss, { rng: makeRng(3) });
  assert.equal(r.reason, "easier");
  assert.equal(r.scenario.id, "a2");
});

test("focus narrows to one trap", () => {
  const r = nextScenario(bundle, emptyProgress(), { focus: "t:y", rng: makeRng(2) });
  assert.equal(r.scenario.id, "a3");
  assert.equal(r.reason, "focus");
});

test("the current case is not repeated when there is a choice", () => {
  for (let seed = 0; seed < 10; seed++) {
    assert.notEqual(nextScenario(bundle, emptyProgress(), { topic: "t", excludeId: "a2", rng: makeRng(seed) }).scenario.id, "a2");
  }
  assert.equal(nextScenario(bundle, emptyProgress(), { topic: "u", excludeId: "b1" }).scenario.id, "b1");
});

test("due reviews come before the weakest trap", () => {
  let p = emptyProgress();
  for (const s of bundle.scenarios) p = recordOutcome(p, s, { ...base, firstOption: s.options[0] }).progress;
  p = { ...p, qIndex: p.qIndex + 10 };
  const r = nextScenario(bundle, p, { rng: makeRng(4) });
  assert.equal(r.reason, "review");
});

test("weakest picks the lowest accuracy", () => {
  const p = { ...emptyProgress(), conf: { a: { seen: 4, right: 4 }, b: { seen: 4, right: 1 } } };
  assert.equal(weakest(["a", "b"], p), "b");
});
