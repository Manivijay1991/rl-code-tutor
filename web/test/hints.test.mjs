import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { test } from "node:test";

import { ACTIONS } from "../js/bandit.js";
import { LADDERS, buildHint, hintTexts, narrowRemovals, scrub } from "../js/hints.js";
import { makeRng } from "../js/random.js";

const BUNDLE_URL = new URL("../data/bundle.json", import.meta.url);

test("every action has a ladder of 3 hints", () => {
  for (const a of ACTIONS) assert.equal(LADDERS[a].length, 3, a);
});

test("scrub removes correct codes in any form", () => {
  const out = scrub("Use E11.22 (e1122) not E11.9; E11.221 differs", ["E11.22"]);
  assert.equal(out, "Use the correct code (the correct code) not E11.9; E11.221 differs");
  assert.equal(scrub("nothing", []), "nothing");
  assert.equal(scrub(undefined, ["A"]), "");
});

test("narrow keeps the correct option and one untried wrong option", () => {
  const opts = [{ correct: true }, { correct: false }, { correct: false }, { correct: false }];
  const removed = narrowRemovals(opts, new Set([1]), makeRng(1));
  assert.equal(removed.length, 1);
  assert.ok(!removed.includes(0) && !removed.includes(1));
  assert.deepEqual(narrowRemovals(opts.slice(0, 2), new Set()), []);
});

test("unknown hint kind", () => {
  const scenario = { slots: { a: "x" }, evidence: [], refs: [] };
  const table = { slots: { a: { label: "A", values: { x: "X" } } }, confusions: {} };
  assert.throws(() => buildHint({ kind: "magic", scenario, table, option: { deciding: ["a"] }, correctCodes: [], step: 1 }), RangeError);
});

test("find and spotlight fall back to 'read what is not there' without evidence", () => {
  const scenario = { slots: { a: "x" }, evidence: [], refs: [] };
  const table = { slots: { a: { label: "A", values: { x: "X", y: "Y" } } }, confusions: {} };
  const h = buildHint({ kind: "spotlight", scenario, table, option: { deciding: ["a"], lean: "over" }, correctCodes: [], step: 2 });
  assert.equal(h.kind, "absence");
});

test("no hint for any real scenario names a correct code", { skip: !existsSync(BUNDLE_URL) && "bundle not exported" }, () => {
  const bundle = JSON.parse(readFileSync(BUNDLE_URL, "utf-8"));
  let checked = 0;
  for (const s of bundle.scenarios) {
    const table = bundle.tables[s.table];
    const correct = s.options.find((o) => o.correct).codes;
    const forms = correct.flatMap((c) => [c, c.replace(".", "")]);
    for (const option of s.options.filter((o) => !o.correct)) {
      for (const kind of new Set(Object.values(LADDERS).flat())) {
        const hint = buildHint({ kind, scenario: s, table, option, correctCodes: correct, step: 1 });
        for (const text of hintTexts(hint)) {
          for (const f of forms) {
            assert.ok(!new RegExp(`(?<![\\w.])${f.replace(".", "\\.")}(?!\\w)`, "i").test(text), `${s.id} ${kind}: "${text}" names ${f}`);
          }
        }
        checked++;
      }
    }
  }
  assert.ok(checked > 100);
});
