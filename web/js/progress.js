// Student progress as plain data, updated by pure functions (each returns a new object).
//
// Per confusion ("<table>:<confusion>"):
//   seen    questions that contained this trap
//   right   of those, answered correctly on the first pick
//   misses  times the student fell for this trap on the first pick
//   due     question index when it is due for spaced review
//
// Bandit reward (CLAUDE.md): after a first-pick miss on trap C, the chosen teaching action is
// "pending" on C. The next NEW question containing C settles it: reward 1 if that question is
// answered correctly on the first pick, else 0. Re-picks inside a question never count.

import { bucket, updateBandit } from "./bandit.js";

export const PROGRESS_VERSION = 1;
const HISTORY_LIMIT = 300;
const MAX_INTERVAL = 32;

export function emptyProgress() {
  return {
    version: PROGRESS_VERSION,
    qIndex: 0,
    seen: {},
    conf: {},
    pending: {},
    bandit: {},
    streak: 0,
    bestStreak: 0,
    totals: { answered: 0, firstTry: 0, solvedWithHints: 0, revealed: 0, hintsUsed: 0 },
    lean: { over: 0, under: 0, neutral: 0 },
    gap: { over: 0, under: 0 },
    evidence: { questions: 0, hit: 0, missed: 0, extra: 0 },
    daily: {},
    history: [],
  };
}

/** Confusion ids ("table:confusion") a scenario's wrong options test. */
export function scenarioConfusions(scenario) {
  const ids = scenario.options.filter((o) => !o.correct).map((o) => `${scenario.table}:${o.confusion}`);
  return [...new Set(ids)];
}

/** Stats for one confusion, with defaults. */
export function confStats(progress, confusion) {
  return progress.conf[confusion] ?? { seen: 0, right: 0, misses: 0, due: 0, interval: 0 };
}

/** First-pick accuracy on questions containing this trap, or null when unseen. */
export function accuracy(progress, confusion) {
  const s = confStats(progress, confusion);
  return s.seen ? s.right / s.seen : null;
}

/** Miss bucket the next miss on this trap would fall into (used to pick the teaching action). */
export function nextMissBucket(progress, confusion) {
  return bucket(confStats(progress, confusion).misses + 1);
}

/**
 * Spaced-review gap (in questions) after one more question containing a trap:
 *   fell for this trap          -> back after 1 question
 *   missed, but on another trap -> back after 2
 *   right on the first pick     -> double the gap (2, 4, 8 ... MAX_INTERVAL)
 */
export function reviewGap(interval, { fellFor, firstCorrect }) {
  if (fellFor) return 1;
  if (!firstCorrect) return 2;
  return Math.min(MAX_INTERVAL, Math.max(2, interval * 2));
}

function updateConf(stats, { fellFor, firstCorrect, qIndex }) {
  const gap = reviewGap(stats.interval, { fellFor, firstCorrect });
  return {
    seen: stats.seen + 1,
    right: stats.right + (firstCorrect ? 1 : 0),
    misses: stats.misses + (fellFor ? 1 : 0),
    interval: gap,
    due: qIndex + gap,
  };
}

function settleRewards(progress, scenario, confusions, firstCorrect) {
  let { bandit } = progress;
  const pending = { ...progress.pending };
  const settled = [];
  for (const c of confusions) {
    const p = pending[c];
    if (!p || p.scenarioId === scenario.id) continue;
    const reward = firstCorrect ? 1 : 0;
    bandit = updateBandit(bandit, c, p.bucket, p.action, reward);
    settled.push({ confusion: c, bucket: p.bucket, action: p.action, reward });
    delete pending[c];
  }
  return { bandit, pending, settled };
}

/**
 * Record a finished question.
 *
 * outcome = {
 *   firstOption,      the option object picked first
 *   hintsUsed,        0-3
 *   revealed,         the student asked for the answer
 *   action,           teaching action chosen after the first miss (or null)
 *   missBucket,       bucket used for that action
 *   evidence,         {hit, missed, extra} when the student marked sentences, else null
 *   date,             "YYYY-MM-DD"
 * }
 * Returns {progress, settled} where settled lists bandit rewards recorded by this question.
 */
export function recordOutcome(progress, scenario, outcome) {
  const firstCorrect = Boolean(outcome.firstOption.correct);
  const fellFor = firstCorrect ? null : `${scenario.table}:${outcome.firstOption.confusion}`;
  const confusions = scenarioConfusions(scenario);
  const qIndex = progress.qIndex + 1;

  const { bandit, pending, settled } = settleRewards(progress, scenario, confusions, firstCorrect);
  if (fellFor && outcome.action) {
    pending[fellFor] = { action: outcome.action, bucket: outcome.missBucket, scenarioId: scenario.id };
  }

  const conf = { ...progress.conf };
  for (const c of confusions) {
    conf[c] = updateConf(confStats(progress, c), {
      fellFor: c === fellFor,
      firstCorrect,
      qIndex,
    });
  }

  const lean = { ...progress.lean };
  const gap = { ...progress.gap };
  if (!firstCorrect) {
    const l = outcome.firstOption.lean ?? "neutral";
    lean[l] = (lean[l] ?? 0) + 1;
    const g = outcome.firstOption.gap;
    if (g && g.direction !== "none") gap[g.direction] = round3(gap[g.direction] + Math.abs(g.gap));
  }

  const evidence = outcome.evidence
    ? {
        questions: progress.evidence.questions + 1,
        hit: progress.evidence.hit + outcome.evidence.hit,
        missed: progress.evidence.missed + outcome.evidence.missed,
        extra: progress.evidence.extra + outcome.evidence.extra,
      }
    : progress.evidence;

  const streak = firstCorrect ? progress.streak + 1 : 0;
  const t = progress.totals;
  const totals = {
    answered: t.answered + 1,
    firstTry: t.firstTry + (firstCorrect ? 1 : 0),
    solvedWithHints: t.solvedWithHints + (!firstCorrect && !outcome.revealed ? 1 : 0),
    revealed: t.revealed + (outcome.revealed ? 1 : 0),
    hintsUsed: t.hintsUsed + outcome.hintsUsed,
  };

  const daily = { ...progress.daily, [outcome.date]: (progress.daily[outcome.date] ?? 0) + 1 };
  const entry = {
    id: scenario.id,
    q: qIndex,
    firstCorrect,
    confusion: fellFor,
    hints: outcome.hintsUsed,
    revealed: Boolean(outcome.revealed),
    action: outcome.action ?? null,
  };

  return {
    progress: {
      ...progress,
      qIndex,
      seen: { ...progress.seen, [scenario.id]: (progress.seen[scenario.id] ?? 0) + 1 },
      conf,
      pending,
      bandit,
      streak,
      bestStreak: Math.max(progress.bestStreak, streak),
      totals,
      lean,
      gap,
      evidence,
      daily,
      history: [...progress.history, entry].slice(-HISTORY_LIMIT),
    },
    settled,
  };
}

/**
 * Score the student's evidence marks per deciding detail.
 * bySlot = {slot: [sentence indexes that state it]}. A detail is found when any marked sentence states it;
 * `extra` counts marked sentences that state no deciding detail.
 */
export function evidenceScore(marked, bySlot) {
  const m = new Set(marked);
  const slots = Object.values(bySlot).filter((idx) => idx.length);
  const deciding = new Set(slots.flat());
  return {
    hit: slots.filter((idx) => idx.some((i) => m.has(i))).length,
    missed: slots.filter((idx) => !idx.some((i) => m.has(i))).length,
    extra: [...m].filter((i) => !deciding.has(i)).length,
  };
}

/** Overall lean from first-pick misses: "over", "under" or "balanced" (with counts). */
export function leanSummary(progress) {
  const { over, under } = progress.lean;
  if (over + under < 3 || Math.abs(over - under) <= 1) return { label: "balanced", over, under };
  return { label: over > under ? "over" : "under", over, under };
}

/** Restore a stored object, falling back to an empty progress when it is missing or outdated. */
export function migrate(stored) {
  if (!stored || stored.version !== PROGRESS_VERSION) return emptyProgress();
  const { calibration, ...rest } = stored; // removed with the Sure/Guessing control
  return { ...emptyProgress(), ...rest };
}

function round3(x) {
  return Math.round(x * 1000) / 1000;
}
