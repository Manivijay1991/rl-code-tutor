// Coach-mode hints. The bandit's teaching action picks a ladder of 3 escalating hints; the student
// re-picks after each. No hint ever names a correct code (CLAUDE.md): every text goes through
// scrub(), and hints are built only from slot labels, confusion descriptions and references.
// Think first: every hint opens with a question (`think`). Details (`body`, refs, the contrast, the
// highlight) sit behind a reveal (`reveal` = its button text) so the student tries on their own first.

export const LADDERS = {
  rule_refresh: ["rule", "spotlight", "narrow"],
  contrast_pair: ["contrast", "spotlight", "narrow"],
  find_meat: ["find", "rule", "narrow"],
  guiding_question: ["question", "spotlight", "narrow"],
  walkthrough: ["walk", "spotlight", "narrow"],
  easier_case: ["rule", "spotlight", "narrow"],
};

export const LEAN_MESSAGES = {
  over: "Does the note document everything your choice reports?",
  under: "Is something documented that your choice leaves out?",
  neutral: "Is your choice exactly as specific as the note?",
};

/** Replace every correct code (dotted or not, any case) with a neutral phrase. */
export function scrub(text, correctCodes) {
  let out = String(text ?? "");
  for (const code of correctCodes) {
    const plain = code.replace(".", "");
    for (const form of new Set([code, plain])) {
      out = out.replace(new RegExp(`(?<![\\w.])${form.replace(".", "\\.")}(?![\\w])`, "gi"), "the correct code");
    }
  }
  return out;
}

function slotInfo(table, scenario, slot) {
  const meta = table.slots[slot];
  return {
    slot,
    label: meta.label,
    value: scenario.slots[slot],
    valueLabel: meta.values[scenario.slots[slot]],
    choices: Object.entries(meta.values).map(([value, label]) => ({ value, label })),
  };
}

function hasEvidence(scenario, slots) {
  return scenario.evidence.some((sp) => slots.includes(sp.slot));
}

/**
 * Build one hint.
 * ctx = {kind, scenario, table, option (the wrong option just picked), correctCodes, step (1-3)}
 * Returns a plain object the UI renders; `kind` decides the widget.
 */
export function buildHint({ kind, scenario, table, option, correctCodes, step }) {
  const deciding = option.deciding?.length ? option.deciding : Object.keys(scenario.slots);
  const first = slotInfo(table, scenario, deciding[0]);
  const trap = table.confusions[option.confusion] ?? { description: "", lean: "neutral" };
  const base = { kind, step, lean: LEAN_MESSAGES[option.lean ?? "neutral"], deciding };
  const s = (text) => scrub(text, correctCodes);

  switch (kind) {
    case "rule":
      return {
        ...base,
        title: "Rule refresher",
        think: `Which coding rule decides "${first.label}" here? Try to recall it before you look.`,
        reveal: "Show the rule",
        body: s(`Common trap: ${trap.description}`),
        refs: scenario.refs.map(s),
      };
    case "contrast": {
      const p = option.pivot;
      const pivotLabel = p ? table.slots[p.slot].values[p.value] : null;
      return {
        ...base,
        title: "Contrast pair",
        think: p
          ? `Your choice is right for a different note. What would that note say about "${first.label}"? Does this note say that?`
          : `Which detail decides the codes here? Look at what the note says about "${first.label}".`,
        reveal: "Compare the two notes",
        body: s(
          p
            ? `Your choice would be right if the note said "${pivotLabel}" for "${first.label}". ` +
                "Check what this note actually says."
            : `The deciding detail is "${first.label}". If the note said something else here, the codes would change.`,
        ),
        current: first.valueLabel,
        pivotLabel,
        alternatives: first.choices.filter((c) => c.value !== first.value).map((c) => c.label),
      };
    }
    case "question":
      return {
        ...base,
        title: "Guiding question",
        think: "Answer this from the note, then pick again.",
        question: first,
      };
    case "walk":
      return {
        ...base,
        title: "Step-by-step walkthrough",
        think: "Break it into steps. Answer each one from the note, then pick again.",
        steps: deciding.map((slot) => slotInfo(table, scenario, slot)),
      };
    case "find":
      if (!hasEvidence(scenario, deciding)) return absence(base, first, s);
      return {
        ...base,
        title: "Find the evidence",
        think: `Which sentence in the note decides "${first.label}"? Tap it.`,
        slots: deciding,
      };
    case "spotlight":
      if (!hasEvidence(scenario, deciding)) return absence(base, first, s);
      return {
        ...base,
        title: "Spotlight",
        think: `Re-read the note. Which words decide "${first.label}"?`,
        reveal: "Highlight them for me",
        body: "The highlighted words decide the answer. Read them again before you pick.",
        slots: deciding,
      };
    case "narrow":
      return {
        ...base,
        title: "Narrow it down",
        think: "Some choices are now ruled out. For each one left, ask: does the note document every detail it needs?",
      };
    default:
      throw new RangeError(`unknown hint kind ${kind}`);
  }
}

function absence(base, first, s) {
  return {
    ...base,
    kind: "absence",
    title: "Read what is NOT there",
    think: `Find what the note says about "${first.label}". Is it actually written, or are you assuming it?`,
    reveal: "Show the tip",
    body: s(
      `Look at "${first.label}". The note is silent or neutral here, and that silence matters: ` +
        "code only what is documented, and do not assume what is not written.",
    ),
  };
}

/** Option indexes to remove for the "narrow" hint: keep the correct one and one untried wrong one. */
export function narrowRemovals(options, tried, rng = Math.random) {
  const untriedWrong = options.map((o, i) => ({ o, i })).filter(({ o, i }) => !o.correct && !tried.has(i));
  if (untriedWrong.length <= 1) return [];
  const keep = untriedWrong[Math.floor(rng() * untriedWrong.length)].i;
  return untriedWrong.map(({ i }) => i).filter((i) => i !== keep);
}

/** Every text a hint will show, for safety checks. */
export function hintTexts(hint) {
  const texts = [
    hint.title,
    hint.think,
    hint.reveal,
    hint.body,
    hint.lean,
    ...(hint.refs ?? []),
    hint.current,
    hint.pivotLabel,
    ...(hint.alternatives ?? []),
  ];
  for (const q of [hint.question, ...(hint.steps ?? [])].filter(Boolean)) {
    texts.push(q.label, q.valueLabel, ...q.choices.map((c) => c.label));
  }
  return texts.filter(Boolean);
}
