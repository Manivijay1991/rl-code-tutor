import assert from "node:assert/strict";
import { test } from "node:test";

import { BATCH, OUTBOX_LIMIT, enqueue, fetchPolicy, flush, loadConfig, toEvents } from "../js/api.js";
import { SHARED_CAP, combinedCounts } from "../js/bandit.js";

const json = (body, status = 200) => ({ ok: status < 300, status, json: async () => body });
const E = { confusion: "t:c", bucket: 1, action: "walkthrough", reward: 1 };

test("config: valid URL, trailing slash trimmed; anything else is offline", async () => {
  assert.deepEqual(await loadConfig(async () => json({ api: "https://api.example.org/" })), { api: "https://api.example.org" });
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

test("events carry only the four allowed fields", () => {
  const out = toEvents([{ ...E, scenarioId: "s1", extra: "secret" }]);
  assert.deepEqual(out, [E]);
});

test("outbox keeps the newest events", () => {
  const many = Array.from({ length: OUTBOX_LIMIT + 5 }, (_, i) => ({ ...E, bucket: (i % 3) + 1 }));
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
