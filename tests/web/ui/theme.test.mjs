import assert from "node:assert/strict";
import { test } from "node:test";

import { isDark } from "../../../web/js/ui/theme.js";

test("an explicit theme decides dark mode", () => {
  assert.equal(isDark("dark"), true);
  assert.equal(isDark("light"), false);
});

test("without a choice the system setting decides", () => {
  globalThis.matchMedia = (q) => ({ matches: q === "(prefers-color-scheme: dark)" });
  try {
    assert.equal(isDark(null), true);
  } finally {
    delete globalThis.matchMedia;
  }
});
