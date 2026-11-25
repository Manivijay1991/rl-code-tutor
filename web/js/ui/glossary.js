// Plain-language meanings for the jargon students meet, shown as keyboard-reachable tooltips.

import { h } from "./dom.js";

export const GLOSSARY = {
  trap: "A common coding mistake that a question tests, such as missing the diabetes 'with' link.",
  lean: "Whether your misses tend to report too much (overcoding) or too little (undercoding).",
  overcoding: "Reporting a code or condition the documentation does not support.",
  undercoding: "Leaving out a code or condition the documentation does support.",
  HCC: "Hierarchical Condition Category: a CMS group of diagnoses used to calculate risk scores.",
  MEAT: "Monitor, Evaluate, Assess/Address, Treat: signs that a condition was addressed at the visit.",
};

/** A word with its glossary meaning as a keyboard-reachable tooltip. */
export function term(word, key = word) {
  const tip = GLOSSARY[key] ?? GLOSSARY[key.toLowerCase()];
  return h("span", { class: "term", tabindex: "0", "data-tip": tip, title: tip }, word);
}
