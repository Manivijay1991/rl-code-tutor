// WCAG 2.2 AA contrast for the colour tokens in web/css/app.css (light and dark themes).
// Normal text needs 4.5:1; large text and UI parts (icons, borders of controls) need 3:1.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../../web/css/app.css", import.meta.url), "utf-8");

/** Tokens declared in the first block matching `selector` ("--name: #hex"). */
function tokens(selector) {
  const start = css.indexOf(selector);
  assert.ok(start >= 0, `missing ${selector}`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
}

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, minimum ratio]
const PAIRS = [
  ["ink", "bg", 4.5], ["ink-2", "bg", 4.5], ["ink-3", "bg", 4.5], ["ink-3", "surface", 4.5],
  ["accent-ink", "accent", 4.5], ["accent", "surface", 4.5], ["accent", "accent-soft", 4.5],
  ["ok", "ok-soft", 4.5], ["bad", "bad-soft", 4.5], ["over", "over-soft", 4.5],
  ["under", "under-soft", 4.5], ["neutral", "neutral-soft", 4.5],
  ["mark-ink", "mark", 4.5], ["evidence-ink", "evidence", 4.5],
  // topic bubbles (pages/home/cloud.js): name and count on the bubble, and the selected bubble
  ["ink", "accent-soft", 4.5], ["ink-2", "accent-soft", 4.5], ["ink-2", "surface", 4.5], ["bg", "ink", 4.5],
  ...[1, 2, 3, 4, 5].flatMap((n) => [["ink", `tint-${n}`, 4.5], ["ink-2", `tint-${n}`, 4.5]]),
];

const light = tokens(":root {");
const dark = { ...light, ...tokens(':root[data-theme="dark"]') };

for (const [name, theme] of [["light", light], ["dark", dark]]) {
  test(`${name} theme text meets WCAG AA contrast`, () => {
    const failures = PAIRS.filter(([fg, bg, min]) => contrast(theme[fg], theme[bg]) < min)
      .map(([fg, bg, min]) => `${fg} on ${bg}: ${contrast(theme[fg], theme[bg]).toFixed(2)} < ${min}`);
    assert.deepEqual(failures, []);
  });
}

test("contrast math matches known values", () => {
  assert.equal(contrast("#000000", "#ffffff").toFixed(1), "21.0");
  assert.equal(contrast("#ffffff", "#ffffff").toFixed(1), "1.0");
  assert.equal(contrast("#767676", "#ffffff").toFixed(2), "4.54");
});
