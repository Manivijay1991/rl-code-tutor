// Random helpers. Every function that needs randomness takes an `rng` (() => number in [0, 1)),
// so tests can pass a seeded generator and the app can pass Math.random.

/** Seeded generator (mulberry32) for tests and reproducible runs. */
export function makeRng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Return a shuffled copy (Fisher-Yates). */
export function shuffled(items, rng = Math.random) {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Return one item, or undefined for an empty list. */
export function pick(items, rng = Math.random) {
  return items.length ? items[Math.floor(rng() * items.length)] : undefined;
}
