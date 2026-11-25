// Content loading. The manifest is small and always fetched fresh; each topic's scenarios live in an
// immutable, content-hashed file (data/topics/<id>.<hash>.json) fetched only when needed and cached by the
// browser. A "view" merges the manifest with the loaded topic files into the shape the core logic reads:
// {topics, tables, codes, hccs, references, scenarios}. Shapes: schemas/bundle.schema.json.

export const DATA_URL = "data/";

/** Fetch the manifest; throws with the HTTP status on failure. */
export async function loadManifest(fetchFn = fetch, base = DATA_URL) {
  const res = await fetchFn(`${base}manifest.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`manifest: HTTP ${res.status}`);
  return res.json();
}

/** The topic ids a choice needs: one topic, or every topic for "all topics" (null). Unknown ids give []. */
export function topicIds(manifest, topic = null) {
  const ids = manifest.topics.map((t) => t.id);
  return topic === null ? ids : ids.filter((id) => id === topic);
}

/**
 * Resolve a saved or linked topic to a current topic id, or null. Older versions stored a table id
 * ("ckd_staging"); it maps to the topic that owns the table.
 */
export function resolveTopic(manifest, value) {
  if (!value) return null;
  const known = new Set(manifest.topics.map((t) => t.id));
  if (known.has(value)) return value;
  const owner = manifest.tables[value]?.topic;
  return owner && known.has(owner) ? owner : null;
}

/**
 * Fetch the topic files that are not in `cache` yet, in parallel. Returns a new cache {topic id: file}.
 * Throws when a topic is unknown or a file cannot be fetched.
 */
export async function loadTopics(manifest, ids, cache = {}, fetchFn = fetch, base = DATA_URL) {
  const missing = ids.filter((id) => !cache[id]);
  const loaded = await Promise.all(
    missing.map(async (id) => {
      const entry = manifest.topics.find((t) => t.id === id);
      if (!entry) throw new Error(`unknown topic ${id}`);
      const res = await fetchFn(`${base}${entry.file}`);
      if (!res.ok) throw new Error(`${id}: HTTP ${res.status}`);
      return [id, await res.json()];
    }),
  );
  return { ...cache, ...Object.fromEntries(loaded) };
}

/** Merge the manifest and loaded topic files into one view for the core logic (pure). */
export function buildView(manifest, files) {
  const loaded = Object.values(files);
  return {
    topics: manifest.topics,
    tables: manifest.tables,
    hccs: manifest.hccs,
    references: manifest.references,
    codes: Object.assign({}, ...loaded.map((f) => f.codes)),
    scenarios: loaded.flatMap((f) => f.scenarios),
  };
}

/** Totals for menus and the home page, from the manifest alone (no topic file needed). */
export function catalogStats(manifest) {
  const tables = Object.values(manifest.tables);
  return {
    topics: manifest.topics.length,
    scenarios: manifest.topics.reduce((n, t) => n + t.scenarios, 0),
    traps: tables.reduce((n, t) => n + Object.keys(t.confusions).length, 0),
  };
}
