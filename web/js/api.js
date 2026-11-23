// Client for the live bandit API. Everything here is optional: with no API configured, or when the
// network fails, the app keeps working offline with the student's own bandit.
//
// Sent per event: {confusion, bucket, action, reward}. Nothing else: no ids, answers or notes.
// Unsent events wait in an outbox (localStorage) and are retried on the next flush.

export const CLIENT = "web/0.1";
export const OUTBOX_LIMIT = 500;
export const BATCH = 50;

/** Read web/config.json ({"api": "https://..." | null}); returns {api: null} when missing or invalid. */
export async function loadConfig(fetchFn = fetch, url = "config.json") {
  try {
    const res = await fetchFn(url, { cache: "no-cache" });
    if (!res.ok) return { api: null };
    const cfg = await res.json();
    const api = typeof cfg.api === "string" && /^https?:\/\//.test(cfg.api) ? cfg.api.replace(/\/+$/, "") : null;
    return { api };
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

/** Turn settled rewards (from progress.recordOutcome) into API events. */
export function toEvents(settled) {
  return settled.map((s) => ({ confusion: s.confusion, bucket: s.bucket, action: s.action, reward: s.reward }));
}

/** Return a new outbox with events appended, keeping only the newest OUTBOX_LIMIT. */
export function enqueue(outbox, events) {
  return [...outbox, ...events].slice(-OUTBOX_LIMIT);
}

/**
 * POST queued events in batches. Returns the events still unsent.
 * Stops at the first failure (offline, rate limited) and keeps the rest; drops a batch the server
 * rejects as invalid (400) so one bad event cannot block the queue forever.
 */
export async function flush(api, outbox, fetchFn = fetch) {
  if (!api || !outbox.length) return outbox;
  let rest = [...outbox];
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
