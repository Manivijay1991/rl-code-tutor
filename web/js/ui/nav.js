// Links between the two pages.

/** URL of the assessment page, optionally for one topic. */
export function practiceUrl(topic = null) {
  return topic ? `practice.html?topic=${encodeURIComponent(topic)}` : "practice.html";
}
