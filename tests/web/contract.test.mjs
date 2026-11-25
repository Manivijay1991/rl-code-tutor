// The JS side of the contracts in schemas/: what the app reads (bundle) and what it sends (events).
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { CLIENT, toEvents } from "../../web/js/api.js";
import { ACTIONS } from "../../web/js/bandit.js";
import { validate } from "./schema.mjs";

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), "utf-8"));
const BUNDLE = new URL("../../web/data/bundle.json", import.meta.url);
const bundleSchema = read("../../schemas/bundle.schema.json");
const eventSchema = read("../../schemas/event.schema.json");

test("the committed bundle matches the contract the app relies on", { skip: !existsSync(BUNDLE) && "bundle not exported" }, () => {
  assert.deepEqual(validate(JSON.parse(readFileSync(BUNDLE, "utf-8")), bundleSchema), []);
});

test("a renamed field breaks the contract", () => {
  const bundle = JSON.parse(readFileSync(BUNDLE, "utf-8"));
  const s = bundle.scenarios[0];
  s.choices = s.options;
  delete s.options;
  const problems = validate(bundle, bundleSchema);
  assert.ok(problems.some((p) => p.includes("missing required 'options'")));
});

test("events the app sends match the event schema", () => {
  const settled = [{ confusion: "diabetes_complications:missed_with_link", missLevel: 2, action: "contrast_pair", reward: 1, scenarioId: "x" }];
  assert.deepEqual(validate({ events: toEvents(settled), client: CLIENT }, eventSchema), []);
});

test("the app's actions are the schema's actions", () => {
  assert.deepEqual(ACTIONS, eventSchema.properties.events.items.properties.action.enum);
});

test("validator basics", () => {
  assert.deepEqual(validate(1, { type: "string" }), ["$: expected string"]);
  assert.deepEqual(validate(true, { enum: [1] }), ["$: must be one of [1]"]);
  assert.deepEqual(validate({ a: 1 }, { type: "object", additionalProperties: false }), ["$: unexpected property 'a'"]);
  assert.throws(() => validate(1, { $ref: "https://x" }));
});
