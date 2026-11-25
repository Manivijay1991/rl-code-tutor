// What to practice next: simple rules, not RL (CLAUDE.md).
// Order: 1) settle a pending bandit reward (same trap, NEW case), 2) spaced review that is due,
// 3) a trap never seen, 4) the weakest trap. A focus trap or topic narrows the pool first.

import { pick } from "./random.js";
import { accuracy, confStats, scenarioConfusions } from "./progress.js";

export const REASONS = {
  reward: "Same trap, new case: show what you learned",
  easier: "An easier case with the same trap",
  review: "Spaced review",
  new: "A trap you have not met yet",
  weakest: "Your weakest trap",
  focus: "Focused practice",
  any: "Practice",
};

function codeCount(s) {
  return s.options.find((o) => o.correct).codes.length;
}

/** Least-seen scenarios first (random tie-break); `prefer` re-orders before the tie-break. */
function leastSeen(cands, progress, rng, prefer = null) {
  const seen = (s) => progress.seen[s.id] ?? 0;
  const minSeen = Math.min(...cands.map(seen));
  let best = cands.filter((s) => seen(s) === minSeen);
  if (prefer) {
    const top = Math.min(...best.map(prefer));
    best = best.filter((s) => prefer(s) === top);
  }
  return pick(best, rng);
}

function withConfusion(pool, confusion) {
  return pool.filter((s) => scenarioConfusions(s).includes(confusion));
}

function withoutCurrent(pool, excludeId) {
  const rest = pool.filter((s) => s.id !== excludeId);
  return rest.length ? rest : pool;
}

/**
 * Choose the next scenario.
 * options = {topic: table id or null, focus: confusion id or null, excludeId, rng}
 * Returns {scenario, reason, confusion} or null when the pool is empty.
 */
export function nextScenario(bundle, progress, { topic = null, focus = null, excludeId = null, rng = Math.random } = {}) {
  let pool = bundle.scenarios.filter((s) => !topic || s.table === topic);
  if (focus) pool = withConfusion(pool, focus);
  pool = withoutCurrent(pool, excludeId);
  if (!pool.length) return null;

  // 1) pending reward: a NEW case with the trap the student just missed
  const pendings = Object.entries(progress.pending).filter(([c]) => withConfusion(pool, c).length);
  for (const [confusion, p] of pendings) {
    const cands = withConfusion(pool, confusion).filter((s) => s.id !== p.scenarioId);
    if (!cands.length) continue;
    const easier = p.action === "easier_case";
    return { scenario: leastSeen(cands, progress, rng, easier ? codeCount : null), reason: easier ? "easier" : "reward", confusion };
  }

  const traps = [...new Set(pool.flatMap(scenarioConfusions))];
  if (focus) return { scenario: leastSeen(pool, progress, rng), reason: "focus", confusion: focus };

  // 2) spaced review that is due, weakest first
  const due = traps.filter((c) => confStats(progress, c).seen && confStats(progress, c).due <= progress.qIndex);
  if (due.length) {
    const confusion = weakest(due, progress, rng);
    return { scenario: leastSeen(withConfusion(pool, confusion), progress, rng), reason: "review", confusion };
  }

  // 3) a trap never seen
  const unseen = traps.filter((c) => !confStats(progress, c).seen);
  if (unseen.length) {
    const confusion = pick(unseen, rng);
    return { scenario: leastSeen(withConfusion(pool, confusion), progress, rng), reason: "new", confusion };
  }

  // 4) the weakest trap
  if (traps.length) {
    const confusion = weakest(traps, progress, rng);
    return { scenario: leastSeen(withConfusion(pool, confusion), progress, rng), reason: "weakest", confusion };
  }
  return { scenario: leastSeen(pool, progress, rng), reason: "any", confusion: null };
}

/**
 * The upcoming traps in the same priority order nextScenario uses, for showing a queue.
 * Deterministic: unseen traps follow `order` (defaults to bundle order) and ties sort by id.
 * Returns [{confusion, reason}] with at most `n` entries.
 */
export function queuePreview(bundle, progress, n = 4, { topic = null, order = null } = {}) {
  const pool = bundle.scenarios.filter((s) => !topic || s.table === topic);
  const traps = order ?? [...new Set(pool.flatMap(scenarioConfusions))];
  const acc = (c) => accuracy(progress, c) ?? 0;
  const byWeakness = (a, b) => acc(a) - acc(b) || a.localeCompare(b);
  const out = [];
  const add = (confusion, reason) => {
    if (out.length < n && !out.some((q) => q.confusion === confusion)) out.push({ confusion, reason });
  };
  for (const [c, p] of Object.entries(progress.pending)) {
    if (withConfusion(pool, c).some((s) => s.id !== p.scenarioId)) add(c, p.action === "easier_case" ? "easier" : "reward");
  }
  const seen = traps.filter((c) => confStats(progress, c).seen);
  seen.filter((c) => confStats(progress, c).due <= progress.qIndex).sort(byWeakness).forEach((c) => add(c, "review"));
  traps.filter((c) => !confStats(progress, c).seen).forEach((c) => add(c, "new"));
  [...seen].sort(byWeakness).forEach((c) => add(c, "weakest"));
  return out;
}

/** The trap with the lowest first-pick accuracy (random tie-break). */
export function weakest(confusions, progress, rng = Math.random) {
  const acc = (c) => accuracy(progress, c) ?? 0;
  const low = Math.min(...confusions.map(acc));
  return pick(confusions.filter((c) => acc(c) === low), rng);
}
