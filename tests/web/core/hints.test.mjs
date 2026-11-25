import assert from "node:assert/strict";
import { test } from "node:test";

import { ACTIONS } from "../../../web/js/core/bandit.js";
import { LADDERS, LEAN_MESSAGES, buildHint, hintTexts, narrowRemovals, scrub } from "../../../web/js/core/hints.js";
import { makeRng } from "../../../web/js/core/random.js";
import { exported, readView } from "../content.mjs";

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

test("every hint opens with a thinking prompt; details wait behind a reveal", () => {
  const scenario = { slots: { a: "x" }, evidence: [{ slot: "a", start: 0, end: 3 }], refs: ["Guideline I.A"] };
  const table = { slots: { a: { label: "Stage", values: { x: "X", y: "Y" } } }, confusions: { c: { description: "Picked Y.", lean: "over" } } };
  const option = { deciding: ["a"], confusion: "c", lean: "over", pivot: { slot: "a", value: "y" } };
  const hidden = new Set(["rule", "contrast", "spotlight", "absence"]);
  for (const kind of ["rule", "contrast", "question", "walk", "find", "spotlight", "narrow"]) {
    const h = buildHint({ kind, scenario, table, option, correctCodes: [], step: 1 });
    assert.ok(h.think?.length > 10, `${kind} has a thinking prompt`);
    assert.equal(Boolean(h.reveal), hidden.has(h.kind), `${kind} reveal`);
  }
  const noEvidence = buildHint({ kind: "find", scenario: { ...scenario, evidence: [] }, table, option, correctCodes: [], step: 1 });
  assert.ok(noEvidence.think.includes("Stage") && noEvidence.reveal);
});

test("lean messages are questions, not verdicts", () => {
  for (const text of Object.values(LEAN_MESSAGES)) assert.ok(text.endsWith("?"), text);
});

test("no hint for any real scenario names a correct code", { skip: !exported && "not exported" }, () => {
  const bundle = readView();
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
