import assert from "node:assert/strict";
import { test } from "node:test";

import { evidenceBySlot, isHeading, pieces, segment, sentences, sentencesWithEvidence } from "../../web/js/note.js";

const NOTE = [
  "Chief Complaint",
  "Follow-up for diabetes.",
  "",
  "HPI",
  "Mr. Smith has type 2 diabetes with CKD stage 4. He takes insulin daily. Temp 98.6 F today.",
  "Assessment: 1. Type 2 diabetes. 2. CKD stage 4.",
].join("\n");

test("headings", () => {
  assert.ok(isHeading("Chief Complaint"));
  assert.ok(isHeading("Medication List"));
  assert.ok(isHeading("Plan:"));
  assert.ok(isHeading("Social History:"));
  assert.ok(!isHeading("Metformin"));
  assert.ok(!isHeading("Lisinopril 10 mg daily"));
  assert.ok(!isHeading("He takes insulin daily."));
  assert.ok(!isHeading(""));
});

test("evidence by slot", () => {
  const blocks = segment("Type 2 diabetes. On insulin. Insulin again.");
  const spans = [
    { start: 0, end: 15, slot: "dm" },
    { start: 20, end: 27, slot: "meds" },
    { start: 29, end: 36, slot: "meds" },
  ];
  assert.deepEqual(evidenceBySlot(blocks, spans), { dm: [0], meds: [1, 2] });
});

test("segment keeps offsets that point back into the note", () => {
  const blocks = segment(NOTE);
  assert.deepEqual(blocks.filter((b) => b.type === "heading").map((b) => b.text), ["Chief Complaint", "HPI", "Assessment"]);
  for (const s of sentences(blocks)) assert.equal(NOTE.slice(s.start, s.end), s.text);
  const texts = sentences(blocks).map((s) => s.text);
  assert.ok(texts.includes("Mr. Smith has type 2 diabetes with CKD stage 4."), texts.join(" | "));
  assert.ok(texts.includes("Temp 98.6 F today."));
  assert.ok(texts.includes("1. Type 2 diabetes."));
  assert.deepEqual(sentences(blocks).map((s) => s.i), [...Array(texts.length).keys()]);
});

test("segment of an empty note", () => {
  assert.deepEqual(segment(""), []);
});

test("evidence maps to sentences and pieces", () => {
  const blocks = segment(NOTE);
  const start = NOTE.indexOf("CKD stage 4");
  const spans = [{ start, end: start + 11, slot: "complication" }, { start: NOTE.indexOf("insulin"), end: NOTE.indexOf("insulin") + 7, slot: "meds" }];
  const all = sentencesWithEvidence(blocks, spans);
  assert.equal(all.length, 2);
  assert.deepEqual(sentencesWithEvidence(blocks, spans, ["meds"]).length, 1);
  const s = sentences(blocks).find((x) => x.i === all[0]);
  const ps = pieces(s, spans);
  assert.equal(ps.map((p) => p.text).join(""), s.text);
  assert.deepEqual(ps.filter((p) => p.slot).map((p) => p.text), ["CKD stage 4"]);
  assert.deepEqual(pieces(s, []), [{ text: s.text, slot: null }]);
});
