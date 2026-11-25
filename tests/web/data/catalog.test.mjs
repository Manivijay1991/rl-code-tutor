import assert from "node:assert/strict";
import { test } from "node:test";

import { buildView, catalogStats, loadManifest, loadTopics, resolveTopic, topicIds } from "../../../web/js/data/catalog.js";

const MANIFEST = {
  code_set: { icd10cm: "FY2027" },
  topics: [
    { id: "ckd", title: "CKD", file: "topics/ckd.aaaaaaaaaa.json", scenarios: 2, tables: ["ckd_staging"] },
    { id: "meat", title: "MEAT", file: "topics/meat.bbbbbbbbbb.json", scenarios: 1, tables: ["meat_support"] },
  ],
  tables: {
    ckd_staging: { topic: "ckd", confusions: { a: {}, b: {} } },
    meat_support: { topic: "meat", confusions: { c: {} } },
    retired_table: { topic: "gone", confusions: {} },
  },
  hccs: { 327: "CKD 4" },
  references: { R: { title: "t", url: "https://x" } },
};
const FILES = {
  "data/topics/ckd.aaaaaaaaaa.json": { topic: "ckd", codes: { "N18.4": { desc: "CKD 4" } }, scenarios: [{ id: "c1" }, { id: "c2" }] },
  "data/topics/meat.bbbbbbbbbb.json": { topic: "meat", codes: { "J44.9": { desc: "COPD" } }, scenarios: [{ id: "m1" }] },
};
const json = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

function fakeFetch(calls = []) {
  return async (url, init) => {
    calls.push([url, init]);
    if (url === "data/manifest.json") return json(MANIFEST);
    return url in FILES ? json(FILES[url]) : json({}, 404);
  };
}

test("the manifest is fetched fresh; failures throw with the status", async () => {
  const calls = [];
  assert.deepEqual(await loadManifest(fakeFetch(calls)), MANIFEST);
  assert.deepEqual(calls[0][1], { cache: "no-cache" });
  await assert.rejects(loadManifest(async () => json({}, 503)), /manifest: HTTP 503/);
});

test("topic ids for one topic, all topics, or an unknown one", () => {
  assert.deepEqual(topicIds(MANIFEST, null), ["ckd", "meat"]);
  assert.deepEqual(topicIds(MANIFEST, "meat"), ["meat"]);
  assert.deepEqual(topicIds(MANIFEST, "nope"), []);
});

test("saved topics resolve, including older table ids", () => {
  assert.equal(resolveTopic(MANIFEST, "ckd"), "ckd");
  assert.equal(resolveTopic(MANIFEST, "ckd_staging"), "ckd"); // saved before topics existed
  assert.equal(resolveTopic(MANIFEST, "retired_table"), null); // its topic is no longer served
  assert.equal(resolveTopic(MANIFEST, "nope"), null);
  assert.equal(resolveTopic(MANIFEST, null), null);
  assert.equal(resolveTopic(MANIFEST, ""), null);
});

test("topic files load once, in parallel, and are reused from the cache", async () => {
  const calls = [];
  const fetchFn = fakeFetch(calls);
  const one = await loadTopics(MANIFEST, ["ckd"], {}, fetchFn);
  assert.deepEqual(Object.keys(one), ["ckd"]);
  const both = await loadTopics(MANIFEST, ["ckd", "meat"], one, fetchFn);
  assert.deepEqual(Object.keys(both).sort(), ["ckd", "meat"]);
  assert.deepEqual(calls.map(([u]) => u), ["data/topics/ckd.aaaaaaaaaa.json", "data/topics/meat.bbbbbbbbbb.json"]);
  assert.equal(both.ckd, one.ckd);
});

test("loading an unknown topic or a missing file fails clearly", async () => {
  await assert.rejects(loadTopics(MANIFEST, ["nope"], {}, fakeFetch()), /unknown topic nope/);
  const broken = { ...MANIFEST, topics: [{ ...MANIFEST.topics[0], file: "topics/ckd.cccccccccc.json" }] };
  await assert.rejects(loadTopics(broken, ["ckd"], {}, fakeFetch()), /ckd: HTTP 404/);
});

test("a view merges the manifest with the loaded topic files", () => {
  const files = { ckd: FILES["data/topics/ckd.aaaaaaaaaa.json"], meat: FILES["data/topics/meat.bbbbbbbbbb.json"] };
  const view = buildView(MANIFEST, files);
  assert.deepEqual(view.scenarios.map((s) => s.id), ["c1", "c2", "m1"]);
  assert.deepEqual(Object.keys(view.codes), ["N18.4", "J44.9"]);
  assert.equal(view.tables, MANIFEST.tables);
  assert.equal(view.hccs, MANIFEST.hccs);
  assert.deepEqual(buildView(MANIFEST, {}).scenarios, []);
});

test("menu totals come from the manifest alone", () => {
  assert.deepEqual(catalogStats(MANIFEST), { topics: 2, scenarios: 3, traps: 3 });
  assert.deepEqual(catalogStats({ topics: [], tables: {} }), { topics: 0, scenarios: 0, traps: 0 });
});
