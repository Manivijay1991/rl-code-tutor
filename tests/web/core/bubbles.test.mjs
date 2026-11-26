import assert from "node:assert/strict";
import { test } from "node:test";

import {
  bounds, fitRadii, initials, labelSize, scatter, settle, shortLabel, step, uniqueInitials,
} from "../../../web/js/core/bubbles.js";
import { makeRng } from "../../../web/js/core/random.js";

const COUNTS = Array.from({ length: 36 }, (_, i) => 12 + ((i * 37) % 110));
const area = (rs) => rs.reduce((s, r) => s + Math.PI * r * r, 0);
const maxOverlap = (bs, gap = 4) => {
  let worst = 0;
  bs.forEach((a, i) => bs.forEach((b, j) => {
    if (j > i) worst = Math.max(worst, a.r + b.r + gap - Math.hypot(a.x - b.x, a.y - b.y));
  }));
  return worst;
};
const inside = (b, w, h) => {
  const { x0, x1, y0, y1 } = bounds(b.r, w, h);
  return b.x >= x0 - 1e-6 && b.x <= x1 + 1e-6 && b.y >= y0 - 1e-6 && b.y <= y1 + 1e-6;
};

test("radii fill the requested share of the box and grow with the count", () => {
  const rs = fitRadii(COUNTS, 1000, 440, { density: 0.4, minR: 1 });
  assert.ok(Math.abs(area(rs) / (1000 * 440) - 0.4) < 0.01);
  const big = COUNTS.indexOf(Math.max(...COUNTS)), small = COUNTS.indexOf(Math.min(...COUNTS));
  assert.ok(rs[big] > rs[small]);
  assert.ok(rs[small] / rs[big] >= 0.45 - 1e-9);
});

test("radii: minimum and cap, zero counts, invalid boxes", () => {
  assert.ok(fitRadii(COUNTS, 288, 460).every((r) => r >= 18));
  assert.ok(fitRadii([500], 300, 200).every((r) => r <= 50)); // cap: a quarter of the short side
  assert.deepEqual(fitRadii([], 300, 300), []);
  const zeros = fitRadii([0, 0], 300, 300);
  assert.equal(zeros[0], zeros[1]);
  assert.throws(() => fitRadii([1], 0, 100), RangeError);
  assert.throws(() => fitRadii([1], 100, 100, { density: 1 }), RangeError);
});

test("label size: smaller for small bubbles and long words, clamped 9-14px", () => {
  assert.equal(labelSize(80, "Diabetes"), 14);
  assert.ok(labelSize(50, "MEAT documentation") < labelSize(50, "HIV")); // the long word shrinks the font
  const fs = labelSize(60, "documentation"); // big enough to stay above the 9px floor
  assert.ok(fs > 9 && "documentation".length * 0.58 * fs <= 2 * 60 * 0.8 + 1e-9);
  assert.equal(labelSize(5, "Supercalifragilistic"), 9);
  assert.equal(labelSize(40, ""), 9.523809523809524); // r / 4.2
});

test("short label: first part of the name, at most two words", () => {
  assert.equal(shortLabel("Sepsis and opportunistic infections"), "Sepsis");
  assert.equal(shortLabel("Epilepsy, Parkinson's and MS"), "Epilepsy");
  assert.equal(shortLabel("Eye: AMD and retinopathy"), "Eye");
  assert.equal(shortLabel("Chronic kidney disease"), "Chronic kidney");
  assert.equal(shortLabel("HIV"), "HIV");
  assert.equal(shortLabel("Andersen syndrome"), "Andersen syndrome"); // "and" only as a whole word
  assert.equal(shortLabel(""), "");
  assert.equal(shortLabel(", and"), ", and"); // nothing left after splitting: keep the original
});

test("initials: acronyms kept, significant words, single words, empty", () => {
  assert.equal(initials("Chronic kidney disease"), "CKD");
  assert.equal(initials("Heart failure"), "HF");
  assert.equal(initials("Sepsis and opportunistic infections"), "SOI");
  assert.equal(initials("Epilepsy, Parkinson's and MS"), "EPM");
  assert.equal(initials("Head injury, vertebral fracture and amputation"), "HIV"); // only the first three words
  assert.equal(initials("COPD and respiratory failure"), "COPD");
  assert.equal(initials("DVT and pulmonary embolism"), "DVT");
  assert.equal(initials("HIV"), "HIV");
  assert.equal(initials("Diabetes"), "Di");
  assert.equal(initials("Dementia"), "De");
  assert.equal(initials("Eye: AMD and retinopathy"), "EAR");
  assert.equal(initials(""), "");
});

test("unique initials: acronyms win, clashing single words grow, multi-word clashes shorten, the rest get numbers", () => {
  assert.deepEqual(uniqueInitials(["HIV", "Head injury, vertebral fracture and amputation"]), ["HIV", "HI"]);
  assert.deepEqual(uniqueInitials(["Dementia", "Depression", "Diabetes"]), ["Dem", "Dep", "Di"]);
  assert.deepEqual(uniqueInitials(["Heart failure", "Hip fracture"]), ["HF", "HF2"]);
  assert.deepEqual(uniqueInitials([]), []);
  const real = ["Chronic kidney disease", "Diabetes", "Dementia", "Depression", "HIV", "Head injury, vertebral fracture and amputation",
    "Heart failure", "Hip fracture encounters", "COPD and respiratory failure"];
  const codes = uniqueInitials(real);
  assert.equal(new Set(codes.map((c) => c.toLowerCase())).size, real.length);
});

for (const [w, h] of [[288, 460], [700, 440], [1100, 440]]) {
  test(`scatter at ${w}x${h}: inside the box, no overlaps, reproducible`, () => {
    const rs = fitRadii(COUNTS, w, h);
    const bs = scatter(rs, w, h, makeRng(7));
    assert.equal(bs.length, 36);
    assert.ok(bs.every((b) => inside(b, w, h)));
    assert.ok(maxOverlap(bs) <= 1e-6, `overlap ${maxOverlap(bs)}`);
    assert.deepEqual(scatter(rs, w, h, makeRng(7)), bs);
  });

  test(`step at ${w}x${h}: bubbles keep moving, stay inside and do not pile up`, () => {
    const rs = fitRadii(COUNTS, w, h);
    let bs = scatter(rs, w, h, makeRng(3));
    const start = bs.map((b) => [b.x, b.y]);
    const rng = makeRng(11);
    for (let k = 0; k < 1800; k += 1) bs = step(bs, 1 / 60, w, h, rng); // 30 seconds
    assert.ok(bs.every((b) => inside(b, w, h)));
    assert.ok(maxOverlap(bs) < 3, `overlap ${maxOverlap(bs).toFixed(2)}`);
    const moved = bs.filter((b, i) => Math.hypot(b.x - start[i][0], b.y - start[i][1]) > 10).length;
    assert.ok(moved >= 30, `only ${moved} moved`);
  });
}

test("cohesion gathers the bubbles into a cloud that keeps moving and does not overlap", () => {
  const [w, h] = [1000, 440];
  const rs = fitRadii(COUNTS, w, h);
  const start = scatter(rs, w, h, makeRng(4));
  const spread = (bs) => bs.reduce((s, b) => s + Math.hypot((b.x - w / 2) / (w / 2), (b.y - h / 2) / (h / 2)), 0) / bs.length;
  const cloud = settle(start, 20, w, h, makeRng(9), { cohesion: 0.5 });
  const loose = settle(start, 20, w, h, makeRng(9), { cohesion: 0 });
  assert.ok(spread(cloud) < spread(loose) * 0.8, `cloud ${spread(cloud).toFixed(2)} vs loose ${spread(loose).toFixed(2)}`);
  assert.ok(maxOverlap(cloud) < 3 && cloud.every((b) => inside(b, w, h)));
  const later = settle(cloud, 3, w, h, makeRng(10), { cohesion: 0.5 });
  assert.ok(later.filter((b, i) => Math.hypot(b.x - cloud[i].x, b.y - cloud[i].y) > 5).length >= 20); // still drifting
});

test("settle: zero seconds returns the input; it matches stepping by hand", () => {
  const rs = fitRadii(COUNTS.slice(0, 5), 500, 300);
  const bs = scatter(rs, 500, 300, makeRng(6));
  assert.equal(settle(bs, 0, 500, 300, makeRng(1)), bs);
  let manual = bs;
  const rng = makeRng(2);
  for (let k = 0; k < 30; k += 1) manual = step(manual, 1 / 60, 500, 300, rng);
  assert.deepEqual(settle(bs, 0.5, 500, 300, makeRng(2)), manual);
});

test("step: frozen bubbles stay put, dt 0 changes nothing, inputs are not mutated, long frames are cut", () => {
  const rs = fitRadii(COUNTS.slice(0, 8), 600, 400);
  const bs = scatter(rs, 600, 400, makeRng(5));
  const copy = structuredClone(bs);
  const next = step(bs, 1 / 30, 600, 400, makeRng(1), { frozen: new Set([2]) });
  assert.deepEqual(bs, copy);
  assert.equal(next[2].x, bs[2].x);
  assert.equal(next[2].y, bs[2].y);
  assert.deepEqual(step(bs, 0, 600, 400, makeRng(1)), bs);
  const jump = step(bs, 5, 600, 400, makeRng(1));
  assert.ok(jump.every((b, i) => Math.hypot(b.x - bs[i].x, b.y - bs[i].y) < 20)); // 5 s counted as 0.05 s
});

test("step: a frozen bubble is immovable when another one runs into it", () => {
  const still = { x: 200, y: 200, r: 30, vx: 0, vy: 0, heading: 0 };
  const mover = { x: 240, y: 200, r: 30, vx: -50, vy: 0, heading: Math.PI }; // overlapping, heading into it
  const [a, b] = step([still, mover], 1 / 60, 600, 400, makeRng(3), { frozen: new Set([0]) });
  assert.equal(a.x, 200);
  assert.equal(a.y, 200);
  assert.ok(Math.hypot(b.x - a.x, b.y - a.y) >= 64 - 1e-6); // the mover was pushed clear instead
  const [c, d] = step([still, { ...still, x: 230 }], 1 / 60, 600, 400, makeRng(3), { frozen: new Set([0, 1]) });
  assert.deepEqual([c.x, d.x], [200, 230]); // both frozen: neither moves
});

test("step: two bubbles on the same spot are separated", () => {
  const b = { x: 100, y: 100, r: 20, vx: 0, vy: 0, heading: 0 };
  const [p, q] = step([b, { ...b }], 1 / 60, 400, 400, makeRng(2));
  assert.ok(Math.hypot(p.x - q.x, p.y - q.y) >= 40 + 4 - 1e-6);
});
