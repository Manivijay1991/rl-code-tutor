// Contextual Thompson-sampling bandit that chooses HOW to teach after a wrong answer.
// Context = (confusion, miss bucket 1/2/3+). Reward = correct on the next NEW question with the
// same confusion (recorded by progress.js), never the immediate re-pick.
// State is a plain object {"<confusion>|<bucket>|<action>": [alpha, beta]}; updates return a new object.

export const ACTIONS = [
  "rule_refresh",
  "contrast_pair",
  "find_meat",
  "guiding_question",
  "walkthrough",
  "easier_case",
];

export const ACTION_LABELS = {
  rule_refresh: "Rule refresher",
  contrast_pair: "Contrast pair",
  find_meat: "Find the evidence",
  guiding_question: "Guiding question",
  walkthrough: "Step-by-step walkthrough",
  easier_case: "Easier case next",
};

const PRIOR = [1, 1];

/** Miss bucket used in the context: 1, 2 or 3 (3+). */
export function bucket(misses) {
  return misses <= 1 ? 1 : misses === 2 ? 2 : 3;
}

function key(confusion, b, action) {
  return `${confusion}|${b}|${action}`;
}

/** Return [alpha, beta] for one arm (the prior when unseen). */
export function counts(bandit, confusion, b, action) {
  return bandit[key(confusion, b, action)] ?? PRIOR;
}

function normal(rng) {
  // Box-Muller; 1 - rng() avoids log(0).
  return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
}

/** Gamma(shape, 1) sample (Marsaglia-Tsang; boosted for shape < 1). */
export function sampleGamma(shape, rng = Math.random) {
  if (shape <= 0) throw new RangeError(`shape must be > 0, got ${shape}`);
  if (shape < 1) return sampleGamma(shape + 1, rng) * Math.pow(1 - rng(), 1 / shape);
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x;
    let v;
    do {
      x = normal(rng);
      v = 1 + c * x;
    } while (v <= 0);
    v = v * v * v;
    const u = 1 - rng();
    if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}

/** Beta(alpha, beta) sample in (0, 1). */
export function sampleBeta(alpha, beta, rng = Math.random) {
  const x = sampleGamma(alpha, rng);
  return x / (x + sampleGamma(beta, rng));
}

// Shared (all-student) evidence is capped at this many pseudo-trials per arm, so it acts as a
// strong prior while each student's own results can still move the choice.
export const SHARED_CAP = 20;

/**
 * Combine this student's [alpha, beta] with shared [successes, failures] from the API.
 * Shared evidence above SHARED_CAP trials is scaled down, keeping its success rate.
 */
export function combinedCounts(bandit, shared, confusion, b, action) {
  const [alpha, beta] = counts(bandit, confusion, b, action);
  const [s, f] = shared?.[key(confusion, b, action)] ?? [0, 0];
  const n = s + f;
  const scale = n > SHARED_CAP ? SHARED_CAP / n : 1;
  return [alpha + s * scale, beta + f * scale];
}

/**
 * Pick the action with the highest posterior sample for this context.
 * `shared` = arms from GET /v1/policy ({key: [successes, failures]}) or null when offline.
 */
export function chooseAction(bandit, confusion, b, rng = Math.random, shared = null) {
  let best = ACTIONS[0];
  let bestDraw = -1;
  for (const a of ACTIONS) {
    const draw = sampleBeta(...combinedCounts(bandit, shared, confusion, b, a), rng);
    if (draw > bestDraw) [best, bestDraw] = [a, draw];
  }
  return best;
}

/** Return a new bandit state with one reward (1 or 0) recorded. */
export function updateBandit(bandit, confusion, b, action, reward) {
  if (!ACTIONS.includes(action)) throw new RangeError(`unknown action ${action}`);
  const [alpha, beta] = counts(bandit, confusion, b, action);
  const next = reward ? [alpha + 1, beta] : [alpha, beta + 1];
  return { ...bandit, [key(confusion, b, action)]: next };
}

/** Posterior mean success rate of every action in one context. */
export function posteriorMeans(bandit, confusion, b) {
  return Object.fromEntries(
    ACTIONS.map((a) => {
      const [alpha, beta] = counts(bandit, confusion, b, a);
      return [a, alpha / (alpha + beta)];
    }),
  );
}

/** Contexts with at least `minTrials` rewards: [{confusion, bucket, best, mean, trials}], most trials first. */
export function learnedContexts(bandit, minTrials = 2) {
  const byCtx = {};
  for (const [k, [alpha, beta]] of Object.entries(bandit)) {
    const [confusion, b, action] = k.split("|");
    const trials = alpha + beta - PRIOR[0] - PRIOR[1];
    const ctx = (byCtx[`${confusion}|${b}`] ??= { confusion, bucket: Number(b), trials: 0, best: null, mean: -1 });
    ctx.trials += trials;
    const mean = alpha / (alpha + beta);
    if (trials > 0 && mean > ctx.mean) Object.assign(ctx, { best: action, mean });
  }
  return Object.values(byCtx)
    .filter((c) => c.trials >= minTrials && c.best)
    .sort((x, y) => y.trials - x.trials);
}
