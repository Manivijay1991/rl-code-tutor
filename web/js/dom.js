// Tiny DOM helpers. Text is always inserted as text nodes (never innerHTML): notes are LLM-written.

/**
 * Create an element. attrs: {class, text, on: {event: fn}, dataset: {...}, aria-*, ...}.
 * Children may be nodes, strings, numbers, arrays, or null/false (skipped).
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "on") for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style") el.style.cssText = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** SVG element with attributes. */
export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  for (const c of children.flat(Infinity)) if (c) el.append(c);
  return el;
}

/** Replace an element's children. */
export function mount(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

/** Inline icon from a small set (stroke icons, 20x20). */
export function icon(name, size = 18) {
  const paths = {
    flame: "M10 2c1 3 4 4.5 4 8.5A4 4 0 0 1 6 10.5c0-1.5.7-2.6 1.5-3.4.2 1.4 1 2.2 1.9 2.4C9 7.5 9.2 4.5 10 2Z",
    chart: "M4 16V9M10 16V4M16 16v-5",
    sun: "M10 4V2M10 18v-2M4 10H2M18 10h-2M5.6 5.6 4.2 4.2M15.8 15.8l-1.4-1.4M5.6 14.4l-1.4 1.4M15.8 4.2l-1.4 1.4M13 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
    moon: "M16 12.5A6.5 6.5 0 0 1 7.5 4a6.5 6.5 0 1 0 8.5 8.5Z",
    marker: "m12 3 5 5-8 8H4v-5l8-8ZM10 5l5 5",
    key: "M3 6h14v9H3zM6 9h1M9 9h1M12 9h1M6 12h8",
    check: "m4 10 4 4 8-8",
    x: "m5 5 10 10M15 5 5 15",
    bulb: "M7 14h6M8 17h4M10 3a5 5 0 0 0-3 9c.6.5 1 1.2 1 2h4c0-.8.4-1.5 1-2a5 5 0 0 0-3-9Z",
    arrow: "M4 10h12M11 5l5 5-5 5",
    target: "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    book: "M4 4h5a2 2 0 0 1 2 2v10a2 2 0 0 0-2-2H4zM16 4h-5a2 2 0 0 0-2 2v10a2 2 0 0 1 2-2h5z",
    reset: "M4 10a6 6 0 1 0 2-4.5M4 3v3.5h3.5",
  };
  return svg(
    "svg",
    { width: size, height: size, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", "stroke-width": 1.7, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "icon" },
    svg("path", { d: paths[name] ?? "" }),
  );
}
