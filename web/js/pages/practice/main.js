// Entry point of the assessment page (practice.html): boot, static buttons, keyboard, and wiring the
// `ui` registry so feature modules can call each other without import cycles.
import * as live from "./live.js";
import * as topics from "./topics.js";
import * as question from "./question.js";
import * as note_view from "./note-view.js";
import * as workbench from "./workbench.js";
import * as hint_card from "./hint-card.js";
import * as references from "./references.js";
import * as debrief from "./debrief.js";
import * as drawer from "./drawer.js";
import * as overlays from "./overlays.js";

import { h, icon, mount, trapFocus } from "../../ui/dom.js";
import { applyTheme, toggleTheme } from "../../ui/theme.js";
import { migrate } from "../../core/progress.js";
import { loadManifest, resolveTopic } from "../../data/catalog.js";
import { loadJSON, PROGRESS_KEY } from "../../data/store.js";
import { app, $, savePrefs, ui } from "./state.js";

async function boot() {
  app.progress = migrate(loadJSON(PROGRESS_KEY, null));
  applyTheme(app.prefs, $("btn-theme"));
  staticButtons();
  try {
    app.manifest = await loadManifest();
    const params = new URLSearchParams(location.search);
    app.prefs.topic = resolveTopic(app.manifest, params.has("topic") ? params.get("topic") : app.prefs.topic);
    savePrefs();
    await ui.useTopic(app.prefs.topic);
  } catch (e) {
    mount($("bench-inner"), h("div", { class: "card empty" }, h("h2", { text: "No scenarios found" }),
      h("p", {}, "Run ", h("code", { text: "coding-tutor-export-ui" }), " and serve this folder with ",
        h("code", { text: "coding-tutor-serve" }), "."), h("p", { class: "note-small", text: String(e) })));
    return;
  }
  const cs = app.manifest.code_set;
  if (cs?.icd10cm) $("code-set").textContent = `Code set: ${cs.icd10cm}; ${cs.hcc_map}.`;
  ui.renderTopics();
  document.addEventListener("keydown", onKey);
  ui.nextQuestion();
  if (location.hash === "#progress") ui.openDrawer();
  ui.connectApi();
}

function staticButtons() {
  mount($("btn-progress"), icon("chart"));
  mount($("btn-keys"), icon("key"));
  mount($("btn-drawer-close"), icon("x"));
  $("btn-progress").addEventListener("click", ui.openDrawer);
  $("btn-keys").addEventListener("click", ui.showKeys);
  $("btn-theme").addEventListener("click", () => toggleTheme(app.prefs, $("btn-theme")));
  $("btn-drawer-close").addEventListener("click", ui.closeDrawer);
  $("drawer").addEventListener("click", (e) => e.target === $("drawer") && ui.closeDrawer());
  $("btn-marker").addEventListener("click", ui.toggleMarker);
  $("note").addEventListener("click", ui.onNoteClick);
  $("note").addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.closest(".sent[role='button']")) {
      e.preventDefault();
      e.stopPropagation();
      const i = e.target.closest(".sent").dataset.i;
      ui.onNoteClick(e);
      document.querySelector(`.sent[data-i="${i}"]`)?.focus();
    }
  });
  $("drawer").addEventListener("keydown", (e) => trapFocus($("drawer"), e));
  $("overlay").addEventListener("keydown", (e) => trapFocus($("overlay"), e));
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.matches("input, textarea, select")) return;
  const overlayOpen = !$("overlay").hidden;
  const drawerOpen = !$("drawer").hidden;
  if (e.key === "Escape") {
    if (overlayOpen) $("overlay").hidden = true;
    if (drawerOpen) ui.closeDrawer();
    return;
  }
  if (overlayOpen) return;
  const k = e.key.toLowerCase();
  if (!app.prefs.shortcuts && k.length === 1) return; // single-character shortcuts are switched off
  if (k === "p") return drawerOpen ? ui.closeDrawer() : ui.openDrawer();
  if (drawerOpen) return;
  if (k === "?") return ui.showKeys();
  const q = app.q;
  if (!q) return;
  if (/^[1-9]$/.test(k)) {
    const idx = q.order[Number(k) - 1];
    if (idx !== undefined) ui.select(idx);
    return;
  }
  if (k === "enter") {
    if (e.target.closest?.("button")) return; // let the focused button handle it
    e.preventDefault();
    return q.phase === "done" ? ui.nextQuestion() : ui.submit();
  }
  if (k === "n" && q.phase === "done") return ui.nextQuestion();
  if (k === "m") return ui.toggleMarker();
  if (k === "d") {
    app.prefs.showDesc = !app.prefs.showDesc;
    savePrefs();
    ui.renderBench();
  }
}

// Every feature module's exported functions, reachable as ui.<name> from any module.
Object.assign(ui, live, topics, question, note_view, workbench, hint_card, references, debrief, drawer, overlays);

boot();
