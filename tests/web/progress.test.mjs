import assert from "node:assert/strict";
import { test } from "node:test";

import { counts } from "../../web/js/bandit.js";
import {
  accuracy,
  emptyProgress,
  evidenceScore,
  leanSummary,
  migrate,
  nextMissLevel,
  recordOutcome,
  reviewGap,
  scenarioConfusions,
} from "../../web/js/progress.js";

const scenario = (id, confusions = ["a", "b"]) => ({
  id,
  table: "t",
  options: [{ codes: ["X1"], correct: true }, ...confusions.map((c) => ({ codes: ["Y"], correct: false, confusion: c, lean: "under", gap: { gap: -0.2, direction: "under" } }))],
});
const right = (s) => s.options[0];
const wrong = (s, k = 1) => s.options[k];
const base = { hintsUsed: 0, revealed: false, action: null, missLevel: null, evidence: null, date: "2026-11-23" };

test("scenario confusions are unique and prefixed", () => {
  assert.deepEqual(scenarioConfusions(scenario("s", ["a", "a", "b"])), ["t:a", "t:b"]);
});

test("a first-try success updates totals, streak and review interval", () => {
  const s = scenario("s1");
  const { progress } = recordOutcome(emptyProgress(), s, { ...base, firstOption: right(s) });
  assert.equal(progress.totals.firstTry, 1);
  assert.equal(progress.streak, 1);
  assert.equal(accuracy(progress, "t:a"), 1);
  assert.equal(progress.conf["t:a"].due, 1 + 2);
  assert.equal(progress.daily["2026-11-23"], 1);
});

test("review gap: misses come back soon, first-pick successes wait longer", () => {
  assert.equal(reviewGap(8, { fellFor: true, firstCorrect: false }), 1); // fell for this trap
  assert.equal(reviewGap(8, { fellFor: false, firstCorrect: false }), 2); // missed another trap
  assert.equal(reviewGap(0, { fellFor: false, firstCorrect: true }), 2);
  assert.equal(reviewGap(8, { fellFor: false, firstCorrect: true }), 16);
  assert.equal(reviewGap(32, { fellFor: false, firstCorrect: true }), 32); // capped
});

test("a trap you fell for is due right after the next case", () => {
  const s = scenario("s1");
  const p = recordOutcome(emptyProgress(), s, { ...base, firstOption: wrong(s) }).progress;
  assert.equal(p.conf["t:a"].due, p.qIndex + 1);
});

test("a miss records the trap, lean, gap and a pending reward", () => {
  const s = scenario("s1");
  const { progress } = recordOutcome(emptyProgress(), s, {
    ...base, firstOption: wrong(s), hintsUsed: 2, action: "contrast_pair", missLevel: 1,
  });
  assert.equal(progress.conf["t:a"].misses, 1);
  assert.equal(progress.conf["t:b"].misses, 0);
  assert.equal(progress.streak, 0);
  assert.equal(progress.lean.under, 1);
  assert.equal(progress.gap.under, 0.2);
  assert.deepEqual(progress.pending["t:a"], { action: "contrast_pair", missLevel: 1, scenarioId: "s1" });
  assert.equal(nextMissLevel(progress, "t:a"), 2);
  assert.equal(progress.totals.solvedWithHints, 1);
});

test("reward is settled only by a NEW question with the same trap", () => {
  const s1 = scenario("s1");
  let { progress } = recordOutcome(emptyProgress(), s1, { ...base, firstOption: wrong(s1), action: "walkthrough", missLevel: 1 });
  // same scenario again: no reward
  ({ progress } = recordOutcome(progress, s1, { ...base, firstOption: right(s1) }));
  assert.ok(progress.pending["t:a"]);
  // a different scenario without the trap: no reward
  const other = scenario("s3", ["z"]);
  ({ progress } = recordOutcome(progress, other, { ...base, firstOption: right(other) }));
  assert.ok(progress.pending["t:a"]);
  // a new scenario with the trap, answered right first try: reward 1
  const s2 = scenario("s2");
  const r = recordOutcome(progress, s2, { ...base, firstOption: right(s2) });
  assert.deepEqual(r.settled, [{ confusion: "t:a", missLevel: 1, action: "walkthrough", reward: 1 }]);
  assert.equal(r.progress.pending["t:a"], undefined);
  assert.deepEqual(counts(r.progress.bandit, "t:a", 1, "walkthrough"), [2, 1]);
});

test("a failed reward question records 0", () => {
  const s1 = scenario("s1");
  let { progress } = recordOutcome(emptyProgress(), s1, { ...base, firstOption: wrong(s1), action: "rule_refresh", missLevel: 1 });
  const s2 = scenario("s2");
  const r = recordOutcome(progress, s2, { ...base, firstOption: wrong(s2, 2), action: "find_meat", missLevel: 1 });
  assert.deepEqual(r.settled, [{ confusion: "t:a", missLevel: 1, action: "rule_refresh", reward: 0 }]);
  assert.deepEqual(counts(r.progress.bandit, "t:a", 1, "rule_refresh"), [1, 2]);
  assert.equal(r.progress.pending["t:b"].action, "find_meat");
});

test("evidence and revealed counts", () => {
  const s = scenario("s1");
  const { progress } = recordOutcome(emptyProgress(), s, {
    ...base, firstOption: wrong(s), revealed: true, evidence: { hit: 1, missed: 1, extra: 2 },
  });
  assert.deepEqual(progress.evidence, { questions: 1, hit: 1, missed: 1, extra: 2 });
  assert.equal(progress.totals.revealed, 1);
  assert.equal(progress.totals.solvedWithHints, 0);
});

test("evidence score counts deciding details, not sentences", () => {
  const bySlot = { dm: [0, 4, 7], meds: [2], link: [] };
  assert.deepEqual(evidenceScore([4, 9], bySlot), { hit: 1, missed: 1, extra: 1 });
  assert.deepEqual(evidenceScore([0, 2, 4], bySlot), { hit: 2, missed: 0, extra: 0 });
  assert.deepEqual(evidenceScore([], {}), { hit: 0, missed: 0, extra: 0 });
});

test("lean summary needs a few misses", () => {
  const p = emptyProgress();
  assert.equal(leanSummary({ ...p, lean: { over: 1, under: 0, neutral: 0 } }).label, "balanced");
  assert.equal(leanSummary({ ...p, lean: { over: 5, under: 1, neutral: 0 } }).label, "over");
  assert.equal(leanSummary({ ...p, lean: { over: 0, under: 4, neutral: 0 } }).label, "under");
});

test("migrate rejects missing or outdated data", () => {
  assert.deepEqual(migrate(null), emptyProgress());
  assert.deepEqual(migrate({ version: 0, streak: 9 }), emptyProgress());
  assert.equal(migrate({ ...emptyProgress(), streak: 4 }).streak, 4);
});

test("history is capped", () => {
  const s = scenario("s1");
  let p = emptyProgress();
  for (let i = 0; i < 305; i++) p = recordOutcome(p, s, { ...base, firstOption: right(s) }).progress;
  assert.equal(p.history.length, 300);
  assert.equal(p.bestStreak, 305);
});

test("pending rewards saved with `bucket` are migrated to missLevel", () => {
  const old = { ...emptyProgress(), pending: { "t:c": { action: "walkthrough", bucket: 2, scenarioId: "s1" } } };
  assert.deepEqual(migrate(old).pending, { "t:c": { action: "walkthrough", missLevel: 2, scenarioId: "s1" } });
  const current = { ...emptyProgress(), pending: { "t:c": { action: "walkthrough", missLevel: 3, scenarioId: "s1" } } };
  assert.deepEqual(migrate(current).pending, current.pending);
  assert.deepEqual(migrate({ ...emptyProgress(), pending: undefined }).pending, {});
});

test("older saved progress loses the removed confidence stats", () => {
  const old = { ...emptyProgress(), streak: 2, calibration: { sure: { n: 3, right: 1 }, unsure: { n: 0, right: 0 } } };
  const p = migrate(old);
  assert.equal(p.streak, 2);
  assert.equal("calibration" in p, false);
});
