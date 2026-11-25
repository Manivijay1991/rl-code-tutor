// Split a clinical note into headings and sentences with character offsets, so the UI can mark
// sentences, highlight evidence spans and check which sentences hold deciding details.

const SECTION =
  /^(chief complaint|cc|hpi|history of present illness|history|medications?|medication list|current medications|exam|physical exam(ination)?|vitals?|assessment|plan|assessment and plan|assessment\/plan|problem list|review of systems|ros|subjective|objective)\s*:?\s*$/i;
// Do not end a sentence after a list number at the start ("1.") or a common abbreviation ("Mr.").
const NO_SPLIT_BEFORE = /(?:^\s*\d+|(?:^|\s)(?:mr|mrs|ms|dr|vs|e\.g|i\.e|approx))\.$/i;

/** True if a line is a known section name, or a short label ending in ":" ("Social History:"). */
export function isHeading(line) {
  const t = line.trim();
  if (!t) return false;
  return SECTION.test(t) || /^[A-Za-z][A-Za-z /&-]{1,30}:$/.test(t);
}

function splitSentences(text, offset) {
  const out = [];
  let start = 0;
  const re = /[.!?](?=\s+[A-Z0-9(])/g;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    const candidate = text.slice(start, m.index + 1);
    if (NO_SPLIT_BEFORE.test(candidate)) continue;
    out.push({ text: candidate, start: offset + start, end: offset + m.index + 1 });
    start = m.index + 1;
    while (start < text.length && /\s/.test(text[start])) start++;
  }
  if (start < text.length) out.push({ text: text.slice(start), start: offset + start, end: offset + text.length });
  return out
    .map((s) => trimSegment(s))
    .filter((s) => s.text);
}

function trimSegment(s) {
  const lead = s.text.length - s.text.trimStart().length;
  const text = s.text.trim();
  return { text, start: s.start + lead, end: s.start + lead + text.length };
}

/**
 * Return blocks: [{type: "heading", text, start, end} | {type: "para", sentences: [{i, text, start, end}]}].
 * Sentence `i` numbers every sentence in the note from 0.
 */
export function segment(note) {
  const blocks = [];
  let i = 0;
  let offset = 0;
  for (const line of note.split("\n")) {
    const lineStart = offset;
    offset += line.length + 1;
    if (!line.trim()) continue;
    const headingMatch = line.match(/^\s*([A-Za-z /]{2,40}):\s+(\S.*)$/);
    if (headingMatch && SECTION.test(headingMatch[1] + ":")) {
      // "Assessment: text on the same line"
      const head = headingMatch[1];
      const headStart = lineStart + line.indexOf(head);
      blocks.push({ type: "heading", text: head, start: headStart, end: headStart + head.length });
      const restStart = lineStart + line.indexOf(headingMatch[2]);
      const sentences = splitSentences(headingMatch[2], restStart).map((s) => ({ ...s, i: i++ }));
      blocks.push({ type: "para", sentences });
    } else if (isHeading(line)) {
      blocks.push({ type: "heading", ...trimSegment({ text: line.replace(/:\s*$/, ""), start: lineStart, end: offset - 1 }) });
    } else {
      const sentences = splitSentences(line, lineStart).map((s) => ({ ...s, i: i++ }));
      blocks.push({ type: "para", sentences });
    }
  }
  return blocks;
}

/** Every sentence of segmented blocks, in order. */
export function sentences(blocks) {
  return blocks.flatMap((b) => (b.type === "para" ? b.sentences : []));
}

/** Indexes of sentences that overlap any of the spans (optionally only spans for `slots`). */
export function sentencesWithEvidence(blocks, spans, slots = null) {
  const wanted = spans.filter((sp) => !slots || slots.includes(sp.slot));
  return sentences(blocks)
    .filter((s) => wanted.some((sp) => sp.start < s.end && sp.end > s.start))
    .map((s) => s.i);
}

/** Map each slot that has evidence to the sentence indexes stating it: {slot: [i, ...]}. */
export function evidenceBySlot(blocks, spans) {
  const out = {};
  for (const slot of new Set(spans.map((sp) => sp.slot))) out[slot] = sentencesWithEvidence(blocks, spans, [slot]);
  return out;
}

/** Split one sentence into plain and evidence pieces: [{text, slot|null}], for rendering marks. */
export function pieces(sentence, spans) {
  const inside = spans
    .filter((sp) => sp.start < sentence.end && sp.end > sentence.start)
    .map((sp) => ({ start: Math.max(sp.start, sentence.start), end: Math.min(sp.end, sentence.end), slot: sp.slot }))
    .sort((a, b) => a.start - b.start);
  const out = [];
  let pos = sentence.start;
  for (const sp of inside) {
    if (sp.start < pos) continue; // overlapping span already covered
    if (sp.start > pos) out.push({ text: sentence.text.slice(pos - sentence.start, sp.start - sentence.start), slot: null });
    out.push({ text: sentence.text.slice(sp.start - sentence.start, sp.end - sentence.start), slot: sp.slot });
    pos = sp.end;
  }
  if (pos < sentence.end) out.push({ text: sentence.text.slice(pos - sentence.start), slot: null });
  return out;
}
