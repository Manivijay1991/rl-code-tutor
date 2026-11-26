// "Report a problem" with the current question: a small form, sent to POST /v1/feedback (data/api.js).
// No account and no email; the name is optional. Reports are private to the maintainer.

import { FEEDBACK_LIMITS, feedbackPayload, sendFeedback } from "../../data/api.js";
import { h } from "../../ui/dom.js";
import { app, ui } from "./state.js";

const KINDS = [
  ["wrong_answer", "The answer key is wrong"],
  ["explanation", "The explanation or reference is wrong"],
  ["note", "The clinical note is unrealistic or unclear"],
  ["other", "Something else"],
];

const MESSAGES = {
  sent: "Thank you: your report was sent to the maintainer.",
  full: "Thank you. Too many reports today; please try again tomorrow.",
  rejected: "The report could not be accepted. Please check the comment and try again.",
  failed: "Could not send the report (offline?). Please try again later.",
};

export function openFeedback() {
  const scenario = app.q?.scenario;
  if (!scenario) return;
  ui.showOverlay((close) => {
    const status = h("p", { class: "note-small fb-status", role: "status" });
    const comment = h("textarea", { id: "fb-comment", rows: "4", maxlength: String(FEEDBACK_LIMITS.comment), required: true });
    const expected = h("input", { id: "fb-expected", type: "text", maxlength: String(FEEDBACK_LIMITS.expected), autocomplete: "off" });
    const name = h("input", { id: "fb-name", type: "text", maxlength: String(FEEDBACK_LIMITS.name), autocomplete: "off" });
    const send = h("button", { class: "btn", type: "submit" }, "Send report");
    const submit = async (e) => {
      e.preventDefault();
      if (comment.value.trim().length < 3) {
        status.textContent = "Please describe the problem in a few words.";
        comment.focus();
        return;
      }
      send.disabled = true;
      status.textContent = "Sending…";
      const kind = e.target.querySelector("input[name=fb-kind]:checked")?.value ?? "other";
      const result = await sendFeedback(app.api, feedbackPayload(scenario.id, { kind, expected: expected.value, comment: comment.value, name: name.value }));
      if (result === "sent" || result === "full") {
        close();
        ui.toast(MESSAGES[result]);
      } else {
        status.textContent = MESSAGES[result];
        send.disabled = false;
      }
    };
    return [
      h("h2", { id: "fb-title" }, "Report a problem"),
      h("p", { class: "note-small" }, `Question ${scenario.id}. Reports go privately to the maintainer. No account or email needed; please do not include patient or personal information.`),
      h("form", { class: "fb-form", on: { submit } },
        h("fieldset", { class: "fb-kinds" }, h("legend", {}, "What is wrong?"),
          KINDS.map(([value, label], i) => h("label", {}, h("input", { type: "radio", name: "fb-kind", value, checked: i === 0 }), label))),
        h("label", { for: "fb-comment" }, "What should it be, and why? (guideline or code book reference helps)"), comment,
        h("label", { for: "fb-expected" }, "Expected code(s), optional"), expected,
        h("label", { for: "fb-name" }, "Your name or credential, optional (e.g. J. Doe, CRC)"), name,
        status,
        h("div", { class: "actions" }, h("span", { class: "spacer" }),
          h("button", { class: "btn ghost", type: "button", on: { click: close } }, "Cancel"), send)),
    ];
  });
}
