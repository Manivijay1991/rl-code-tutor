import assert from "node:assert/strict";
import { test } from "node:test";

import {
  BATCH, FEEDBACK_LIMITS, OUTBOX_LIMIT, POLICY_REFRESH_MS, enqueue, feedbackPayload, fetchPolicy, flush, loadConfig, policyIsStale,
  refreshPolicy, sendFeedback, toEvents,
  upgradeEvent,
} from "../../../web/js/data/api.js";
import { SHARED_CAP, combinedCounts } from "../../../web/js/core/bandit.js";

const json = (body, status = 200) => ({ ok: status < 300, status, json: async () => body });
const E = { confusion: "t:c", miss_level: 1, action: "walkthrough", reward: 1 };

test("config: valid URL, trailing slash trimmed; anything else is offline", async () => {
  assert.deepEqual(await loadConfig(async () => json({ api: "https://api.example.org/" })), { api: "https://api.example.org" });
  assert.deepEqual(await loadConfig(async () => json({ api: "/api/" })), { api: "/api" }); // same origin
  assert.deepEqual(await loadConfig(async () => json({ api: "/" })), { api: null });
  assert.deepEqual(await loadConfig(async () => json({ api: "//evil.example" })), { api: null });
  assert.deepEqual(await loadConfig(async () => json({ api: null })), { api: null });
  assert.deepEqual(await loadConfig(async () => json({ api: "javascript:alert(1)" })), { api: null });
  assert.deepEqual(await loadConfig(async () => json({}, 404)), { api: null });
  assert.deepEqual(await loadConfig(async () => { throw new Error("offline"); }), { api: null });
});

test("policy fetch returns arms or null", async () => {
  const arms = { "t:c|1|walkthrough": [3, 1] };
  assert.deepEqual(await fetchPolicy("https://a", async () => json({ arms, events: 4 })), { arms, events: 4 });
  assert.equal(await fetchPolicy("https://a", async () => json({}, 500)), null);
  assert.equal(await fetchPolicy("https://a", async () => { throw new Error("x"); }), null);
  assert.equal(await fetchPolicy(null), null);
});

test("policy is stale when never checked or at least 10 minutes old", () => {
  const t = 1_000_000;
  assert.equal(POLICY_REFRESH_MS, 600_000);
  assert.equal(policyIsStale(null, t), true);
  assert.equal(policyIsStale(undefined, t), true);
  assert.equal(policyIsStale(t, t), false);
  assert.equal(policyIsStale(t, t + POLICY_REFRESH_MS - 1), false);
  assert.equal(policyIsStale(t, t + POLICY_REFRESH_MS), true);
  assert.equal(policyIsStale(t, t + 5, 5), true); // custom max age
});

test("refreshPolicy fetches only when stale and keeps the last good counts on failure", async () => {
  const old = { arms: { "t:c|1|walkthrough": [1, 0] }, events: 1 };
  const fresh = { arms: { "t:c|1|walkthrough": [2, 0] }, events: 2 };
  let calls = 0;
  const ok = async () => { calls += 1; return json(fresh); };
  const down = async () => { calls += 1; throw new Error("offline"); };
  const t = 5_000_000;

  // fresh: no request at all
  assert.equal(await refreshPolicy({ api: "/api", shared: old, checkedAt: t }, t + 1000, ok), null);
  assert.equal(calls, 0);
  // stale: fetch and replace
  assert.deepEqual(await refreshPolicy({ api: "/api", shared: old, checkedAt: t }, t + POLICY_REFRESH_MS, ok),
    { shared: fresh, checkedAt: t + POLICY_REFRESH_MS });
  // never loaded: fetch
  assert.deepEqual(await refreshPolicy({ api: "/api", shared: null, checkedAt: null }, t, ok), { shared: fresh, checkedAt: t });
  // API down: keep the old counts, but record the attempt so it is not retried after every question
  assert.deepEqual(await refreshPolicy({ api: "/api", shared: old, checkedAt: null }, t, down), { shared: old, checkedAt: t });
  assert.deepEqual(await refreshPolicy({ api: "/api", shared: null, checkedAt: null }, t, down), { shared: null, checkedAt: t });
  assert.equal(calls, 4);
  // offline (no API configured): nothing to do
  assert.equal(await refreshPolicy({ api: null, shared: null, checkedAt: null }, t, ok), null);
  assert.equal(calls, 4);
});

test("feedback payload: trimmed to the limits, optional fields left out when empty, unknown kind -> other", () => {
  const p = feedbackPayload("ckd_staging-0123456789", { kind: "note", comment: "  Too short a note.  ", expected: " ", name: "" });
  assert.deepEqual(p, { scenario: "ckd_staging-0123456789", kind: "note", comment: "Too short a note.", client: "web/0.1" });
  const long = feedbackPayload("x-0123456789", { kind: "rude", comment: "c".repeat(2000), expected: "E".repeat(80), name: "n".repeat(90) });
  assert.equal(long.kind, "other");
  assert.equal(long.comment.length, FEEDBACK_LIMITS.comment);
  assert.equal(long.expected.length, FEEDBACK_LIMITS.expected);
  assert.equal(long.name.length, FEEDBACK_LIMITS.name);
});

test("sendFeedback reports sent, full, rejected or failed", async () => {
  const seen = [];
  const ok = async (url, init) => { seen.push([url, JSON.parse(init.body)]); return json({ received: true }, 202); };
  assert.equal(await sendFeedback("/api", { scenario: "s" }, ok), "sent");
  assert.deepEqual(seen, [["/api/v1/feedback", { scenario: "s" }]]);
  assert.equal(await sendFeedback("/api", {}, async () => json({ received: false }, 202)), "full");
  assert.equal(await sendFeedback("/api", {}, async () => json({ error: "x" }, 400)), "rejected");
  assert.equal(await sendFeedback("/api", {}, async () => json({ error: "x" }, 403)), "rejected");
  assert.equal(await sendFeedback("/api", {}, async () => json({}, 503)), "failed");
  assert.equal(await sendFeedback("/api", {}, async () => { throw new Error("offline"); }), "failed");
  assert.equal(await sendFeedback(null, {}, ok), "failed");
});

test("events carry only the four allowed fields", () => {
  const settled = { confusion: E.confusion, missLevel: 1, action: E.action, reward: E.reward, scenarioId: "s1", extra: "secret" };
  assert.deepEqual(toEvents([settled]), [E]);
});

test("events queued before the rename are upgraded from bucket to miss_level", async () => {
  const old = { confusion: "t:c", bucket: 2, action: "walkthrough", reward: 0 };
  const upgraded = { confusion: "t:c", miss_level: 2, action: "walkthrough", reward: 0 };
  assert.deepEqual(upgradeEvent(old), upgraded);
  assert.equal(upgradeEvent(E), E); // current events pass through untouched
  assert.deepEqual(enqueue([old], [E]), [upgraded, E]);
  const sent = [];
  await flush("https://a", [old], async (url, init) => { sent.push(JSON.parse(init.body)); return json({}, 202); });
  assert.deepEqual(sent[0].events, [upgraded]);
});

test("outbox keeps the newest events", () => {
  const many = Array.from({ length: OUTBOX_LIMIT + 5 }, (_, i) => ({ ...E, miss_level: (i % 3) + 1 }));
  assert.equal(enqueue([], many).length, OUTBOX_LIMIT);
  assert.deepEqual(enqueue([E], []), [E]);
});

test("flush sends in batches and keeps what failed", async () => {
  const sent = [];
  const ok = async (url, init) => {
    sent.push(JSON.parse(init.body));
    return json({ accepted: 1 }, 202);
  };
  const outbox = Array.from({ length: BATCH + 3 }, () => E);
  assert.deepEqual(await flush("https://a", outbox, ok), []);
  assert.deepEqual(sent.map((b) => b.events.length), [BATCH, 3]);
  assert.equal(sent[0].client, "web/0.1");

  assert.deepEqual(await flush("https://a", [E, E], async () => { throw new Error("offline"); }), [E, E]);
  assert.deepEqual(await flush("https://a", [E], async () => json({}, 429)), [E]);
  assert.deepEqual(await flush("https://a", [E], async () => json({ error: "bad" }, 400)), []); // dropped, not stuck
  assert.deepEqual(await flush(null, [E]), [E]);
});

test("shared counts are combined and capped", () => {
  const shared = { "t:c|1|walkthrough": [300, 100] };
  const [a, b] = combinedCounts({}, shared, "t:c", 1, "walkthrough");
  assert.equal(a + b, 2 + SHARED_CAP); // prior + capped shared evidence
  assert.equal(a - 1, SHARED_CAP * 0.75); // success rate kept
  assert.deepEqual(combinedCounts({}, null, "t:c", 1, "walkthrough"), [1, 1]);
  assert.deepEqual(combinedCounts({ "t:c|1|walkthrough": [4, 2] }, { "t:c|1|walkthrough": [1, 1] }, "t:c", 1, "walkthrough"), [5, 3]);
});
