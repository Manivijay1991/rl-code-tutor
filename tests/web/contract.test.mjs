// The JS side of the contracts in schemas/: what the app reads (manifest + topic files) and what it sends (events).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { ACTIONS } from "../../web/js/core/bandit.js";
import { CLIENT, FEEDBACK_KINDS, FEEDBACK_LIMITS, feedbackPayload, toEvents } from "../../web/js/data/api.js";
import { exported, readManifest, readTopicFiles } from "./content.mjs";
import { validate } from "./schema.mjs";

const read = (rel) => JSON.parse(readFileSync(new URL(rel, import.meta.url), "utf-8"));
const bundleSchema = read("../../schemas/bundle.schema.json");
const eventSchema = read("../../schemas/event.schema.json");
const feedbackSchema = read("../../schemas/feedback.schema.json");
const asManifest = (v) => validate(v, { $ref: "#/$defs/manifest" }, bundleSchema);
const asTopicFile = (v) => validate(v, { $ref: "#/$defs/topic_file" }, bundleSchema);

test("the exported manifest and topic files match the contract the app relies on", { skip: !exported && "not exported" }, () => {
  const manifest = readManifest();
  assert.deepEqual(asManifest(manifest), []);
  for (const [id, file] of Object.entries(readTopicFiles(manifest))) assert.deepEqual(asTopicFile(file), [], id);
});

test("every manifest table belongs to a listed topic and every topic file matches its entry", { skip: !exported && "not exported" }, () => {
  const manifest = readManifest();
  const topics = new Set(manifest.topics.map((t) => t.id));
  for (const [tid, t] of Object.entries(manifest.tables)) assert.ok(topics.has(t.topic), tid);
  const files = readTopicFiles(manifest);
  for (const entry of manifest.topics) {
    assert.equal(files[entry.id].topic, entry.id);
    assert.equal(files[entry.id].scenarios.length, entry.scenarios);
  }
});

test("a renamed field breaks the contract", { skip: !exported && "not exported" }, () => {
  const file = Object.values(readTopicFiles())[0];
  const s = file.scenarios[0];
  s.choices = s.options;
  delete s.options;
  assert.ok(asTopicFile(file).some((p) => p.includes("missing required 'options'")));
});

test("events the app sends match the event schema", () => {
  const settled = [{ confusion: "diabetes_complications:missed_with_link", missLevel: 2, action: "contrast_pair", reward: 1, scenarioId: "x" }];
  assert.deepEqual(validate({ events: toEvents(settled), client: CLIENT }, eventSchema), []);
});

test("the app's actions are the schema's actions", () => {
  assert.deepEqual(ACTIONS, eventSchema.properties.events.items.properties.action.enum);
});

test("feedback the app sends matches the feedback schema, and the form's limits are the schema's", () => {
  const full = feedbackPayload("ckd_staging-0123456789", { kind: "wrong_answer", comment: "Stage 3b, not 3a.", expected: "N18.32", name: "J. Doe, CRC" });
  assert.deepEqual(validate(full, feedbackSchema), []);
  assert.deepEqual(validate(feedbackPayload("ckd_staging-0123456789", { kind: "other", comment: "Typo here." }), feedbackSchema), []);
  assert.deepEqual(FEEDBACK_KINDS, feedbackSchema.properties.kind.enum);
  for (const [field, max] of Object.entries(FEEDBACK_LIMITS)) assert.equal(max, feedbackSchema.properties[field].maxLength, field);
});

test("validator basics", () => {
  assert.deepEqual(validate(1, { type: "string" }), ["$: expected string"]);
  assert.deepEqual(validate(true, { enum: [1] }), ["$: must be one of [1]"]);
  assert.deepEqual(validate({ a: 1 }, { type: "object", additionalProperties: false }), ["$: unexpected property 'a'"]);
  assert.throws(() => validate(1, { $ref: "https://x" }));
});
