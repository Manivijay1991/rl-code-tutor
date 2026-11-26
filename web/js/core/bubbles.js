// Floating topic bubbles (pure, no DOM): bubble size from the number of questions, a random start inside a box,
// and one physics step at a time (random wandering, bounces off the walls and off each other). Every function
// takes an `rng` so tests are reproducible; pages/home/cloud.js draws the result.

const MAX_DT = 0.05; // seconds; longer frames (tab switches) are cut so nothing jumps

/**
 * Radii that fill `density` of a width x height box: area grows with the count (radius ~ sqrt), the smallest
 * topic still gets 45% of the biggest one's radius, and no bubble is smaller than `minR`.
 * @param {number[]} counts  questions per topic (non-numbers and negatives count as 0)
 */
export function fitRadii(counts, width, height, { density = 0.34, minR = 18 } = {}) {
  if (!(width > 0 && height > 0)) throw new RangeError(`box must have a positive size (got ${width} x ${height})`);
  if (!(density > 0 && density < 1)) throw new RangeError(`density must be between 0 and 1 (got ${density})`);
  const safe = counts.map((c) => (Number.isFinite(c) && c > 0 ? c : 0));
  const max = Math.max(0, ...safe);
  const raw = safe.map((c) => 0.45 + 0.55 * (max ? Math.sqrt(c / max) : 0));
  const area = raw.reduce((s, x) => s + Math.PI * x * x, 0);
  const k = area ? Math.sqrt((density * width * height) / area) : 0;
  const cap = Math.min(width, height) / 4;
  return raw.map((x) => Math.min(cap, Math.max(minR, x * k)));
}

/**
 * Font size in px for a bubble label: about r/4.2, but small enough that the longest word fits across the bubble
 * (words are never broken), clamped to 9-14px.
 */
export function labelSize(r, label) {
  const longest = Math.max(1, ...String(label).split(/\s+/).map((w) => w.length));
  const fitWord = (2 * r * 0.8) / (longest * 0.58); // ~0.58em average glyph width
  return Math.max(9, Math.min(14, r / 4.2, fitWord));
}

/** Bubbles smaller than this (px radius) show the short name; the full name appears on hover or focus. */
export const SHORT_BELOW = 36;

/**
 * A short name for a small bubble: the part before the first comma, colon, "and", "vs" or "with"
 * ("Sepsis and opportunistic infections" -> "Sepsis"), at most two words, never empty.
 */
export function shortLabel(title) {
  const text = String(title).trim();
  const head = text.split(/\s*(?:,|:|\band\b|\bvs\b|\bwith\b)\s*/i).find((part) => part) ?? text;
  return head.split(/\s+/).slice(0, 2).join(" ");
}

const MINOR = new Set(["and", "or", "of", "the", "vs", "with", "in", "for", "to", "a", "an"]);

/**
 * Initials for a bubble on a narrow screen: a leading acronym as is ("COPD and respiratory failure" -> "COPD"),
 * else the first letter of up to three significant words ("Chronic kidney disease" -> "CKD"); a single word keeps
 * its first two letters ("Diabetes" -> "Di") so similar topics stay apart; a short single word stays whole ("HIV").
 */
export function initials(title) {
  const words = String(title).replace(/[^\p{L}\p{N}\s'-]/gu, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const first = words[0];
  if (/^[A-Z0-9]{2,5}$/.test(first)) return first;
  const major = words.filter((w) => !MINOR.has(w.toLowerCase()));
  if (major.length <= 1) {
    const w = major[0] ?? first;
    return w.length <= 4 ? w : w.slice(0, 1).toUpperCase() + w.slice(1, 2).toLowerCase();
  }
  return major.slice(0, 3).map((w) => w[0].toUpperCase()).join("");
}

/**
 * Initials for a whole list, made unique so no two bubbles look alike: a real leading acronym keeps its letters;
 * clashing single words all grow to three letters ("Dem", "Dep"); clashing multi-word names try two, then four
 * word initials ("Head injury, ..." -> "HI"); anything still clashing gets a number.
 */
export function uniqueInitials(titles) {
  const codes = titles.map(initials);
  const isAcronym = (t) => /^[A-Z0-9]{2,5}$/.test(String(t).split(/[\s,:]+/)[0] ?? "");
  const major = (t) => String(t).replace(/[^\p{L}\p{N}\s'-]/gu, " ").split(/\s+/).filter((w) => w && !MINOR.has(w.toLowerCase()));
  const clashes = () => codes.map((c, i) => c && codes.some((d, j) => j !== i && d.toLowerCase() === c.toLowerCase()));
  for (const width of [3, 2, 4]) {
    const clash = clashes();
    titles.forEach((t, i) => {
      if (!clash[i] || isAcronym(t)) return;
      const words = major(t);
      if (words.length <= 1) codes[i] = (words[0] ?? "").slice(0, 3).replace(/^./, (c) => c.toUpperCase());
      else if (width !== 3) codes[i] = words.slice(0, width).map((w) => w[0].toUpperCase()).join("");
    });
  }
  const seen = new Map();
  return codes.map((c) => {
    const key = c.toLowerCase();
    seen.set(key, (seen.get(key) ?? 0) + 1);
    return seen.get(key) > 1 ? `${c}${seen.get(key)}` : c;
  });
}

/** Boxes narrower than this (px) show initials on every bubble; the name appears on hover, tap or focus. */
export const INITIALS_BELOW = 600;

/** The x/y range a bubble's centre may use: `inset` times its radius stays clear of each wall for hover growth. */
export function bounds(r, width, height, inset = 0.3) {
  const m = r * (1 + inset);
  return { x0: m, x1: Math.max(m, width - m), y0: m, y1: Math.max(m, height - m) };
}

/**
 * Random, non-overlapping start positions (biggest first; after many failed tries a bubble is placed anyway and
 * the physics pushes it free), each with a random heading.
 * @returns {{x: number, y: number, r: number, vx: number, vy: number, heading: number}[]}  in input order
 */
export function scatter(radii, width, height, rng, { gap = 4, inset = 0.3 } = {}) {
  const order = radii.map((r, i) => i).sort((a, b) => radii[b] - radii[a] || a - b);
  const placed = [];
  for (const i of order) {
    const r = radii[i];
    const { x0, x1, y0, y1 } = bounds(r, width, height, inset);
    let spot = null;
    for (let t = 0; t < 2000 && !spot; t += 1) {
      const x = x0 + rng() * (x1 - x0), y = y0 + rng() * (y1 - y0);
      if (placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + r + gap)) spot = { x, y };
    }
    spot ??= { x: x0 + rng() * (x1 - x0), y: y0 + rng() * (y1 - y0) };
    placed[i] = { ...spot, r, vx: 0, vy: 0, heading: rng() * 2 * Math.PI };
  }
  return placed;
}

/**
 * Advance the bubbles by `dt` seconds and return new objects (inputs are not changed).
 * Each free bubble wanders: its heading turns a little at random and its velocity eases toward that heading
 * (small bubbles move a bit faster); `cohesion` (0-1) adds a pull toward the centre that gathers them into a
 * cloud. Walls reflect; overlapping bubbles are pushed apart and bounce. Bubbles in
 * `frozen` (indexes: hovered or focused) do not move and push others away as if fixed.
 */
export function step(
  bodies, dt, width, height, rng, { speed = 14, turn = 1.2, gap = 4, inset = 0.3, cohesion = 0, frozen = new Set() } = {},
) {
  const t = Math.min(Math.max(dt, 0), MAX_DT);
  const out = bodies.map((b) => ({ ...b }));
  if (t === 0) return out;
  const cx = width / 2, cy = height / 2;
  out.forEach((b, i) => {
    if (frozen.has(i)) {
      b.vx = 0;
      b.vy = 0;
      return;
    }
    b.heading += (rng() - 0.5) * 2 * turn * t;
    const v = speed * Math.sqrt(24 / Math.max(b.r, 1));
    // Cloud: a pull toward the centre on an oval the shape of the box (0 = no pull), on top of the wandering.
    const px = (-(b.x - cx) / cx) * cohesion * speed * 2.2, py = (-(b.y - cy) / cy) * cohesion * speed * 2.2;
    const ease = Math.min(1, t * 1.5);
    b.vx += (Math.cos(b.heading) * v + px - b.vx) * ease;
    b.vy += (Math.sin(b.heading) * v + py - b.vy) * ease;
    b.x += b.vx * t;
    b.y += b.vy * t;
  });
  for (let i = 0; i < out.length; i += 1) {
    for (let j = i + 1; j < out.length; j += 1) collide(out, i, j, gap, frozen);
  }
  out.forEach((b, i) => {
    if (!frozen.has(i)) wall(b, width, height, inset);
  });
  return out;
}

/** Run `seconds` of simulation at 60 steps per second (e.g. to show a cloud already formed, or a still one). */
export function settle(bodies, seconds, width, height, rng, opts = {}) {
  let out = bodies;
  for (let k = 0; k < Math.round(seconds * 60); k += 1) out = step(out, 1 / 60, width, height, rng, opts);
  return out;
}

/** Push two overlapping bubbles apart (by area-weighted mass) and swap their speeds along the contact line. */
function collide(out, i, j, gap, frozen) {
  const a = out[i], b = out[j];
  let dx = b.x - a.x, dy = b.y - a.y;
  let d = Math.hypot(dx, dy);
  const need = a.r + b.r + gap;
  if (d >= need) return;
  if (d < 1e-6) [dx, dy, d] = [1, 0, 1]; // same spot: separate sideways
  const nx = dx / d, ny = dy / d, overlap = need - d;
  const fa = frozen.has(i), fb = frozen.has(j);
  if (fa && fb) return;
  // Share of the push each one takes: a frozen bubble is immovable; otherwise the lighter (smaller) one moves more.
  const ma = a.r * a.r, mb = b.r * b.r;
  const sa = fa ? 0 : fb ? 1 : mb / (ma + mb), sb = 1 - sa;
  a.x -= nx * overlap * sa;
  a.y -= ny * overlap * sa;
  b.x += nx * overlap * sb;
  b.y += ny * overlap * sb;
  const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
  if (rel < 0) {
    if (sa) [a.vx, a.vy] = [a.vx + nx * rel, a.vy + ny * rel];
    if (sb) [b.vx, b.vy] = [b.vx - nx * rel, b.vy - ny * rel];
  }
  if (sa) a.heading = Math.atan2(a.vy - ny, a.vx - nx);
  if (sb) b.heading = Math.atan2(b.vy + ny, b.vx + nx);
}

/** Keep a bubble inside the box, reflecting its velocity and heading at the walls. */
function wall(b, width, height, inset) {
  const { x0, x1, y0, y1 } = bounds(b.r, width, height, inset);
  if (b.x < x0 || b.x > x1) {
    b.x = Math.min(x1, Math.max(x0, b.x));
    b.vx = -b.vx;
    b.heading = Math.PI - b.heading;
  }
  if (b.y < y0 || b.y > y1) {
    b.y = Math.min(y1, Math.max(y0, b.y));
    b.vy = -b.vy;
    b.heading = -b.heading;
  }
}
