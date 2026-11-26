// Client for the live bandit API. Everything here is optional: with no API configured, or when the
// network fails, the app keeps working offline with the student's own bandit.
//
// Sent per event: {confusion, miss_level, action, reward}. Nothing else: no ids, answers or notes.
// Unsent events wait in an outbox (localStorage) and are retried on the next flush.

export const CLIENT = "web/0.1";
export const OUTBOX_LIMIT = 500;
export const BATCH = 50;

/**
 * Read web/config.json: {"api": "https://host" | "/api" | null}. A path starting with "/" means the
 * API is on the same origin (Vercel, or `coding-tutor-serve --with-api`). Returns {api: null} when
 * missing or invalid.
 */
export async function loadConfig(fetchFn = fetch, url = "config.json") {
  try {
    const res = await fetchFn(url, { cache: "no-cache" });
    if (!res.ok) return { api: null };
    const cfg = await res.json();
    const ok = typeof cfg.api === "string" && (/^https?:\/\//.test(cfg.api) || /^\/[\w/-]*$/.test(cfg.api));
    return { api: ok ? cfg.api.replace(/\/+$/, "") || null : null };
  } catch {
    return { api: null };
  }
}

/** GET /v1/policy; returns {arms, events} or null on any failure. */
export async function fetchPolicy(api, fetchFn = fetch) {
  if (!api) return null;
  try {
    const res = await fetchFn(`${api}/v1/policy`);
    if (!res.ok) return null;
    const body = await res.json();
    return body && typeof body.arms === "object" ? { arms: body.arms, events: body.events ?? 0 } : null;
  } catch {
    return null;
  }
}

// The shared policy is refreshed in the background at most this often (never at the moment of choosing).
export const POLICY_REFRESH_MS = 10 * 60 * 1000;

/** True when the policy was never checked or the last check (successful or not) is at least maxAge old. */
export function policyIsStale(checkedAt, now, maxAge = POLICY_REFRESH_MS) {
  return checkedAt == null || now - checkedAt >= maxAge;
}

/**
 * Re-fetch the policy when it is stale. Returns {shared, checkedAt} to store, or null when it is still fresh.
 * A failed fetch keeps the last good `shared` (null only if there never was one) and still counts as a
 * check, so an unreachable API is retried every POLICY_REFRESH_MS, not after every question.
 */
export async function refreshPolicy({ api, shared, checkedAt }, now, fetchFn = fetch) {
  if (!api || !policyIsStale(checkedAt, now)) return null;
  const fresh = await fetchPolicy(api, fetchFn);
  return { shared: fresh ?? shared, checkedAt: now };
}

/** Turn settled rewards (from progress.recordOutcome) into API events. */
export function toEvents(settled) {
  return settled.map((s) => ({ confusion: s.confusion, miss_level: s.missLevel, action: s.action, reward: s.reward }));
}

/** Rewrite an event queued before the rename (`bucket`) to the current shape (`miss_level`). */
export function upgradeEvent(e) {
  if (!("bucket" in e)) return e;
  const { bucket, ...rest } = e;
  return { ...rest, miss_level: rest.miss_level ?? bucket };
}

/** Return a new outbox with events appended, keeping only the newest OUTBOX_LIMIT. */
export function enqueue(outbox, events) {
  return [...outbox.map(upgradeEvent), ...events].slice(-OUTBOX_LIMIT);
}

/**
 * POST queued events in batches. Returns the events still unsent.
 * Stops at the first failure (offline, rate limited) and keeps the rest; drops a batch the server
 * rejects as invalid (400) so one bad event cannot block the queue forever.
 */
export async function flush(api, outbox, fetchFn = fetch) {
  if (!api || !outbox.length) return outbox;
  let rest = outbox.map(upgradeEvent);
  while (rest.length) {
    const batch = rest.slice(0, BATCH);
    let res;
    try {
      res = await fetchFn(`${api}/v1/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: batch, client: CLIENT }),
        keepalive: true,
      });
    } catch {
      return rest;
    }
    if (res.ok || res.status === 400) rest = rest.slice(batch.length);
    else return rest;
  }
  return rest;
}
