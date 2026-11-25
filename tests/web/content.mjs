// Test helper: the exported delivery files (web/data/manifest.json + one file per topic), read the way the
// app reads them. Not shipped to the browser.

import { existsSync, readFileSync } from "node:fs";

import { buildView } from "../../web/js/data/catalog.js";

const DATA = new URL("../../web/data/", import.meta.url);
const readJSON = (url) => JSON.parse(readFileSync(url, "utf-8"));

/** True when `coding-tutor-export-ui` has written the manifest. */
export const exported = existsSync(new URL("manifest.json", DATA));

export function readManifest() {
  return readJSON(new URL("manifest.json", DATA));
}

/** Topic id -> topic file content, for every topic in the manifest. */
export function readTopicFiles(manifest = readManifest()) {
  return Object.fromEntries(manifest.topics.map((t) => [t.id, readJSON(new URL(t.file, DATA))]));
}

/** Everything merged, as the practice page sees it with "All topics". */
export function readView() {
  const manifest = readManifest();
  return buildView(manifest, readTopicFiles(manifest));
}
