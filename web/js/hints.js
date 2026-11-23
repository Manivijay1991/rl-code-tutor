// Coach-mode hints. The bandit's teaching action picks a ladder of 3 escalating hints; the student
// re-picks after each. No hint ever names a correct code (CLAUDE.md): every text goes through
// scrub(), and hints are built only from slot labels, confusion descriptions and references.

export const LADDERS = {
  rule_refresh: ["rule", "spotlight", "narrow"],
  contrast_pair: ["contrast", "spotlight", "narrow"],
  find_meat: ["find", "rule", "narrow"],
  guiding_question: ["question", "spotlight", "narrow"],
  walkthrough: ["walk", "spotlight", "narrow"],
  easier_case: ["rule", "spotlight", "narrow"],
};

export const LEAN_MESSAGES = {
  over: "That choice reports more than the note supports (overcoding).",
  under: "That choice leaves out something the note supports (undercoding).",
  neutral: "That choice codes the right idea at the wrong level of detail.",
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
        body: s(`Common trap: ${trap.description}`),
        refs: scenario.refs.map(s),
      };
    case "contrast": {
      const p = option.pivot;
      const pivotLabel = p ? table.slots[p.slot].values[p.value] : null;
      return {
        ...base,
        title: "Contrast pair",
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
        body: s(`What does the note say about "${first.label}"?`),
        question: first,
      };
    case "walk":
      return {
        ...base,
        title: "Step-by-step walkthrough",
        body: "Answer each step from the note, then pick again.",
        steps: deciding.map((slot) => slotInfo(table, scenario, slot)),
      };
    case "find":
      if (!hasEvidence(scenario, deciding)) return absence(base, first, s);
      return {
        ...base,
        title: "Find the evidence",
        body: "Tap the sentence in the note that decides this. The codes depend on it.",
        slots: deciding,
      };
    case "spotlight":
      if (!hasEvidence(scenario, deciding)) return absence(base, first, s);
      return {
        ...base,
        title: "Spotlight",
        body: "The highlighted words in the note decide the answer. Read them again before you pick.",
        slots: deciding,
      };
    case "narrow":
      return {
        ...base,
        title: "Narrow it down",
        body: "Some choices are now ruled out. One of the remaining choices is correct.",
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
