// Home page: "How your next case is chosen", a passive directional diagram plus the pick order.

import { h, icon, svg } from "../../ui/dom.js";
import { reducedMotion } from "../../ui/motion.js";

// A passive, directional diagram (no clicks): answer → right (waits longer) or missed (coached, then the
// same trap comes back). Two layouts: wide for desktop, tall for phones. Dots travel the paths unless
// reduced motion is on. Below it, the order the next case is picked in.

const NODE = { w: 150, h: 56 };
const FLOW_NODES = {
  case: { icon: "book", text: "Next case" },
  answer: { icon: "marker", text: "You answer" },
  right: { icon: "check", text: "Right", kind: "ok" },
  miss: { icon: "x", text: "Missed", kind: "bad" },
  coach: { icon: "bulb", text: "Coached", kind: "accent" },
};
// Both branches loop straight back to "Next case" (dashed, the last two edges); what the selector does
// with the trap is a label on each loop, not a step: right → its review gap doubles; missed → the very
// next case is a new case with the same trap (selector.js priority 1).
const LOOP_LABELS = { ok: "Same trap later, in a new note: after 2 → 4 → 8 cases", accent: "Next case: same trap, in a new note" };
const LAYOUTS = {
  wide: {
    viewBox: "0 0 780 316",
    at: { case: [85, 150], answer: [280, 150], right: [490, 90], miss: [490, 210], coach: [690, 210] },
    edges: ["M160 150 H197", "M355 150 H385 V90 H407", "M355 150 H385 V210 H407", "M565 210 H607",
      "M565 90 H600 V30 H85 V114", "M690 238 V280 H85 V186"],
    labels: [{ x: 342, y: 16, cls: "ok" }, { x: 388, y: 300, cls: "accent" }],
    dots: [
      { path: "M85 150 H385 V90 H600 V30 H85 V150", cls: "ok", dur: 6 },
      { path: "M85 150 H385 V210 H690 V280 H85 V150", cls: "bad", dur: 7 },
    ],
  },
  tall: {
    viewBox: "0 0 360 416",
    at: { case: [180, 60], answer: [180, 150], right: [95, 256], miss: [265, 256], coach: [265, 356] },
    edges: ["M180 88 V114", "M180 178 V206 H95 V220", "M180 178 V206 H265 V220", "M265 284 V320",
      "M20 256 H8 V60 H97", "M340 356 H352 V60 H263"],
    labels: [{ x: 95, y: 304, cls: "ok", lines: ["Same trap, new note,", "after 2 → 4 → 8 cases"] },
      { x: 265, y: 400, cls: "accent", lines: ["Next: same trap,", "in a new note"] }],
    dots: [
      { path: "M180 60 V206 H95 V256 H8 V60 H180", cls: "ok", dur: 6 },
      { path: "M180 60 V206 H265 V356 H352 V60 H180", cls: "bad", dur: 7 },
    ],
  },
};

function loopLabel({ x, y, cls, lines }) {
  const t = svg("text", { x, y, class: `fl-label ${cls}`, "text-anchor": "middle", "dominant-baseline": "middle" });
  (lines ?? [LOOP_LABELS[cls]]).forEach((line, i) => {
    const span = svg("tspan", { x, dy: i ? 16 : lines ? -8 : 0 });
    span.textContent = line;
    t.append(span);
  });
  return t;
}

function flowSvg(name) {
  const L = LAYOUTS[name];
  const root = svg("svg", { viewBox: L.viewBox, class: `flow-svg ${name}`, "aria-hidden": "true" });
  root.append(svg("defs", {},
    svg("marker", { id: `fl-arrow-${name}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 9, markerHeight: 9, markerUnits: "userSpaceOnUse", orient: "auto" },
      svg("path", { d: "M0 0 L10 5 L0 10 z", class: "fl-head" }))));
  L.edges.forEach((d, i) => root.append(svg("path", { d, class: `fl-edge${i >= L.edges.length - 2 ? " loop" : ""}`, "marker-end": `url(#fl-arrow-${name})` })));
  // dots first, so the boxes drawn after them hide the dots: they show only on the connecting lines
  if (!reducedMotion()) {
    for (const d of L.dots) {
      const dot = svg("circle", { r: 6, class: `fl-dot ${d.cls}` });
      dot.append(svg("animateMotion", { dur: `${d.dur}s`, repeatCount: "indefinite", path: d.path, rotate: "0" }));
      root.append(dot);
    }
  }
  for (const [id, [cx, cy]] of Object.entries(L.at)) {
    const n = FLOW_NODES[id];
    const g = svg("g", { class: `fl-node ${n.kind ?? ""}` });
    g.append(svg("rect", { x: cx - NODE.w / 2, y: cy - NODE.h / 2, width: NODE.w, height: NODE.h, rx: 14 }));
    const ic = icon(n.icon, 18);
    ic.setAttribute("x", cx - NODE.w / 2 + 14);
    ic.setAttribute("y", cy - 9);
    g.append(ic);
    const t = svg("text", { x: cx - NODE.w / 2 + 40, y: cy, "dominant-baseline": "middle" });
    t.textContent = n.text;
    g.append(t);
    root.append(g);
  }
  L.labels.forEach((l) => root.append(loopLabel(l)));
  return root;
}

/** The section: diagram (wide and tall layouts) and the "Picks next" order. */
export function learningLoop() {
  const order = [["reset", "Re-test"], ["chart", "Due review"], ["target", "New trap"], ["x", "Weakest"]];
  return h("section", { class: "reveal", "aria-labelledby": "loop-title" },
    h("h2", { class: "section-title", id: "loop-title" }, "How your next case is chosen"),
    h("div", { class: "flowbox" },
      h("div", { class: "flow-figure", role: "img",
        "aria-label": "You answer a case. Right: you go to the next case, and that trap comes back later in a new note, after 2, then 4, then 8 cases. Missed: you are coached, and your next case is a new note with the same trap." },
        flowSvg("wide"), flowSvg("tall")),
      h("div", { class: "priority" },
        h("span", { class: "priority-k" }, "Picks next"),
        h("ol", { class: "priority-list" }, order.flatMap(([ic, label], i) => [
          i ? h("li", { class: "priority-arrow", "aria-hidden": "true" }, icon("arrow", 14)) : null,
          h("li", { class: "priority-item" }, h("span", { class: "priority-n" }, String(i + 1)), icon(ic, 14), label),
        ])))));
}
