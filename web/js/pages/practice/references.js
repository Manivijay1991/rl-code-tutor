// Reference chips: links to the official guidelines when the manifest has them.

import { h } from "../../ui/dom.js";
import { app } from "./state.js";

/** A reference chip: a link to the official source (with its title) when the bundle has one, else plain text. */
export function refChip(id) {
  const ref = app.view.references?.[id];
  if (!ref) return h("span", { class: "ref" }, id);
  return h("a", { class: "ref ref-link", href: ref.url, target: "_blank", rel: "noopener noreferrer" },
    h("b", {}, id), h("span", { class: "ref-title" }, ref.title),
    h("span", { "aria-hidden": "true" }, "↗"), h("span", { class: "sr-only" }, " (opens the official source in a new tab)"));
}
