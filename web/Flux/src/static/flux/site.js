function setTheme(theme) {
  if (theme === "greyscale") theme = "black";

  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("flux-theme", theme);
  } catch {
    // Theme switching still works for the current page if storage is blocked.
  }

  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    const isSelected = button.dataset.themeChoice === theme;
    button.classList.toggle("is-selected", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  });
}

function setThemeMenuOpen(isOpen) {
  const options = document.querySelector("[data-theme-options]");
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!options || !toggle) return;

  options.hidden = !isOpen;
  toggle.setAttribute("aria-expanded", String(isOpen));
}

const liveCardCopyStages = new Map();
const liveCardCopyMessages = new Map();
const liveCardCopyMessageMs = 8000;
let liveRefreshTimerInterval = null;
let fluxWebPulseTimerInterval = null;
let pendingCompSurfaceFocusSelector = "";

document.addEventListener("htmx:afterSwap", (event) => {
  restoreLiveCardCopyMessages();
  initializeImportTreeCheckboxes();
  initializeLiveRefreshTimers();
  initializeFluxWebPulseBars();
  initializeCellPhoneSimulators();
  initializeBuildMapSelectors();
  initializePreviewDefaultInputs(event.detail && event.detail.target ? event.detail.target : document);
  initializeCopyableTables(event.detail && event.detail.target ? event.detail.target : document);
  focusCompSurfaceAfterSwap(event);
});

document.addEventListener("htmx:afterSettle", focusCompSurfaceAfterSwap);

document.addEventListener("htmx:configRequest", (event) => {
  const elt = event.detail && event.detail.elt;
  if (!elt || !elt.matches) return;
  if (elt.matches("[data-flux-web-pulse]")) {
    const currentPath = `${window.location.pathname}${window.location.search}`;
    elt.setAttribute("hx-get", currentPath);
    event.detail.path = currentPath;
    return;
  }
  if (elt.matches(".comp-card-mode-control")) {
    event.detail.path = mergeCurrentQueryPath(event.detail.path);
  }
});

function mergeCurrentQueryPath(path) {
  const requested = new URL(path || "", window.location.href);
  const merged = new URL(window.location.href);
  requested.searchParams.forEach((value, key) => merged.searchParams.set(key, value));
  return `${merged.pathname}${merged.search}${merged.hash}`;
}

document.addEventListener("click", (event) => {
  const modeControl = event.target.closest(".comp-card-mode-control");
  if (modeControl) {
    queueCompSurfaceFocus(modeControl.getAttribute("hx-target") || "[data-comp-surface]");
  }

  const themeToggle = event.target.closest("[data-theme-toggle]");
  if (themeToggle) {
    const options = document.querySelector("[data-theme-options]");
    setThemeMenuOpen(Boolean(options && options.hidden));
    return;
  }

  const themeButton = event.target.closest("[data-theme-choice]");
  if (themeButton) {
    setTheme(themeButton.dataset.themeChoice);
    setThemeMenuOpen(false);
    return;
  }

  const treeToggle = event.target.closest("[data-sim-tree-toggle]");
  if (treeToggle) {
    const node = treeToggle.closest(".sim-import-node");
    const children = node && node.querySelector(":scope > [data-sim-tree-children]");
    if (!children) return;
    const isExpanded = children.hidden;
    children.hidden = !isExpanded;
    treeToggle.textContent = isExpanded ? "v" : ">";
    treeToggle.setAttribute("aria-expanded", String(isExpanded));
    return;
  }

  const liveCardCopyButton = event.target.closest("[data-live-card-copy]");
  if (liveCardCopyButton) {
    copyLiveCardContext(liveCardCopyButton);
    return;
  }

  const bridgeCopyButton = event.target.closest("[data-bridge-copy]");
  if (bridgeCopyButton) {
    copyBridgeContext(bridgeCopyButton);
    return;
  }

  const fluxLinkCopyButton = event.target.closest("[data-flux-link-copy]");
  if (fluxLinkCopyButton) {
    copyFluxLinkContext(fluxLinkCopyButton);
    return;
  }

  const tableCopyButton = event.target.closest("[data-table-copy]");
  if (tableCopyButton) {
    copyTableContents(tableCopyButton);
    return;
  }

  const modeButton = event.target.closest("[data-sim-mode-choice]");
  if (modeButton) {
    applyTreeModeChoice(modeButton);
    return;
  }

  const buildMapNode = event.target.closest("[data-build-map-node]");
  if (buildMapNode) {
    toggleBuildMapComponent(buildMapNode.dataset.buildMapNode);
    return;
  }

  if (!event.target.closest("[data-theme-picker]")) {
    setThemeMenuOpen(false);
  }
});

document.addEventListener("change", (event) => {
  markFluxPulseFormDirty(event.target);

  const modeField = event.target.closest("[data-sim-mode-field]");
  if (modeField) {
    recordImportTreeModeField(modeField);
    return;
  }

  const buildCheckbox = event.target.closest("[data-build-component-checkbox]");
  if (buildCheckbox) {
    setBuildComponentSelected(buildCheckbox.value, buildCheckbox.checked);
    return;
  }

  const checkbox = event.target.closest("[data-sim-tree-checkbox]");
  if (!checkbox) return;

  const node = checkbox.closest(".sim-import-node");
  if (!node) return;
  checkbox.indeterminate = false;
  checkbox.dataset.indeterminate = "0";

  node.querySelectorAll(".sim-import-node [data-sim-tree-checkbox]").forEach((child) => {
    setTreeCheckboxState(child, checkbox.checked);
  });

  updateImportTreeAncestors(node);
  recordImportTreeSelection(checkbox);
});

document.addEventListener("input", (event) => {
  markFluxPulseFormDirty(event.target);

  const modeField = event.target.closest("[data-sim-mode-field]");
  if (modeField) recordImportTreeModeField(modeField);
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-flux-pulse-dirty]");
  if (form) delete form.dataset.fluxPulseDirty;
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setThemeMenuOpen(false);
});

document.addEventListener("DOMContentLoaded", () => {
  setTheme(document.documentElement.dataset.theme || "green");
  initializeImportTreeCheckboxes();
  initializeLiveRefreshTimers();
  initializeFluxWebPulseBars();
  initializeCellPhoneSimulators();
  initializeBuildMapSelectors();
  initializePreviewDefaultInputs();
  initializeCopyableTables();
});

window.addEventListener("hashchange", syncCellPhoneSimulatorsToHash);

function initializeLiveRefreshTimers() {
  document.querySelectorAll("[data-live-refresh-timer]").forEach((timer) => {
    timer.dataset.liveRefreshStartedAt = String(performance.now());
    timer.dataset.liveRefreshInitialCentiseconds = timer.dataset.nextReadCentiseconds || "";
  });
  updateLiveRefreshTimers();

  const hasCentisecondTimer = Boolean(document.querySelector('[data-live-refresh-timer][data-countdown-precision="centisecond"]'));
  if (hasCentisecondTimer && !liveRefreshTimerInterval) {
    liveRefreshTimerInterval = window.setInterval(updateLiveRefreshTimers, 10);
  } else if (!hasCentisecondTimer && liveRefreshTimerInterval) {
    window.clearInterval(liveRefreshTimerInterval);
    liveRefreshTimerInterval = null;
  }
}

function initializeFluxWebPulseBars() {
  document.querySelectorAll("[data-flux-web-pulse-timer]").forEach((bar) => {
    bar.dataset.fluxWebPulseStartedAt = String(performance.now());
  });
  updateFluxWebPulseBars();

  const hasPulseBar = Boolean(document.querySelector("[data-flux-web-pulse-timer]"));
  if (hasPulseBar && !fluxWebPulseTimerInterval) {
    fluxWebPulseTimerInterval = window.setInterval(updateFluxWebPulseBars, 500);
  } else if (!hasPulseBar && fluxWebPulseTimerInterval) {
    window.clearInterval(fluxWebPulseTimerInterval);
    fluxWebPulseTimerInterval = null;
  }
}

function updateFluxWebPulseBars() {
  document.querySelectorAll("[data-flux-web-pulse-timer]").forEach((bar) => {
    const countdown = bar.querySelector("[data-flux-web-pulse-countdown]");
    if (!countdown) return;
    const canRun = fluxDisplayPulseCanRun();
    bar.classList.toggle("is-paused", !canRun);
    if (!canRun) {
      bar.style.setProperty("--pulse-countdown-percent", "0%");
      countdown.textContent = "paused";
      return;
    }
    const refreshSeconds = Math.max(Number(bar.dataset.refreshSeconds || 5), 1);
    const startedAt = Number(bar.dataset.fluxWebPulseStartedAt || performance.now());
    const elapsedSeconds = (performance.now() - startedAt) / 1000;
    const remainingExact = Math.max(0, refreshSeconds - (elapsedSeconds % refreshSeconds));
    const remainingSeconds = Math.max(0, Math.floor(remainingExact));
    const percent = Math.max(0, Math.min(100, Math.round((remainingExact / refreshSeconds) * 100)));
    bar.style.setProperty("--pulse-countdown-percent", `${percent}%`);
    countdown.textContent = `${remainingSeconds}s`;
  });
}

function fluxDisplayPulseCanRun() {
  const pulse = document.querySelector("[data-flux-web-pulse]");
  if (!pulse) return false;
  if (pulse.querySelector('[data-comp-mode="configure"], [data-flux-pulse-pause], form:focus-within, form[data-flux-pulse-dirty="1"], input:focus, textarea:focus, select:focus, [contenteditable="true"]:focus')) {
    return false;
  }
  return !document.body.classList.contains("htmx-request");
}

window.fluxDisplayPulseCanRun = fluxDisplayPulseCanRun;

function markFluxPulseFormDirty(target) {
  const field = target && target.closest && target.closest("input, textarea, select");
  if (!field) return;
  const form = field.form || field.closest("form");
  if (form && form.closest("[data-flux-web-pulse]")) {
    form.dataset.fluxPulseDirty = "1";
  }
}

function initializeCellPhoneSimulators() {
  document.querySelectorAll("[data-cell-phone-simulator]").forEach((simulator) => {
    if (simulator.dataset.cellPhoneInitialized === "1") {
      return;
    }
    simulator.dataset.cellPhoneInitialized = "1";

    const cards = cellPhoneCards(simulator);
    if (!cards.length) {
      return;
    }
    simulator.dataset.cellPhoneIndex = String(initialCellPhoneIndex(cards));
    updateCellPhoneSimulator(simulator);

    const frame = simulator.querySelector("[data-cell-phone-frame]");
    if (frame) {
      wireCellPhoneFrame(frame, simulator);
    }

    simulator.querySelectorAll("[data-cell-phone-nav]").forEach((button) => {
      button.addEventListener("click", () => {
        changeCellPhoneProcess(simulator, button.dataset.cellPhoneNav === "next" ? 1 : -1);
      });
    });
  });
}

function initializeBuildMapSelectors() {
  document.querySelectorAll("[data-build-map-selector]").forEach((selector) => {
    if (selector.dataset.buildMapInitialized === "1") return;
    selector.dataset.buildMapInitialized = "1";
    selector.querySelectorAll("[data-build-component-checkbox]").forEach((checkbox) => {
      setBuildComponentSelected(checkbox.value, checkbox.checked, { updateCount: false });
    });
    updateBuildSelectedCounts();
  });
}

function initializeCopyableTables(root = document) {
  const tables = root.matches && root.matches("table")
    ? [root]
    : Array.from(root.querySelectorAll("table"));
  tables.forEach((table) => {
    if (table.dataset.tableCopyInitialized === "1") return;
    const copyDisabled = Boolean(table.closest("[data-no-table-copy]"));
    if (copyDisabled) return;
    table.dataset.tableCopyInitialized = "1";
    let wrapper = table.closest("[data-copyable-table]");
    if (!wrapper) {
      wrapper = document.createElement("div");
      wrapper.className = "copyable-table";
      wrapper.dataset.copyableTable = "1";
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
    if (!copyDisabled && !wrapper.querySelector(":scope > [data-table-copy]")) {
      const button = document.createElement("button");
      button.className = "copy-table-button";
      button.type = "button";
      button.dataset.tableCopy = "1";
      button.setAttribute("aria-label", "Copy table contents");
      button.title = "Copy table contents";
      wrapper.insertBefore(button, table);
    }
  });
}

function initializePreviewDefaultInputs(root = document) {
  const scopeInputs = root.matches && root.matches('input[name="live_scope"]')
    ? [root]
    : Array.from(root.querySelectorAll('input[name="live_scope"]'));
  scopeInputs.forEach((input) => {
    if (input.value === "Fluxolot" && input.placeholder === "Fluxolot" && !input.dataset.userEdited) {
      input.value = "";
    }
  });
}

function toggleBuildMapComponent(componentId) {
  const checkbox = document.querySelector(`[data-build-component-checkbox][value="${CSS.escape(componentId)}"]`);
  const selected = !(checkbox && checkbox.checked);
  setBuildComponentSelected(componentId, selected, { focusRow: true });
}

function setBuildComponentSelected(componentId, selected, options = {}) {
  document.querySelectorAll(`[data-build-component-checkbox][value="${CSS.escape(componentId)}"]`).forEach((checkbox) => {
    checkbox.checked = selected;
  });
  document.querySelectorAll(`[data-build-map-node="${CSS.escape(componentId)}"]`).forEach((node) => {
    node.classList.toggle("is-selected", selected);
    node.setAttribute("aria-pressed", String(selected));
  });
  document.querySelectorAll(`[data-build-component-row="${CSS.escape(componentId)}"]`).forEach((row) => {
    row.classList.toggle("is-selected", selected);
    if (options.focusRow) {
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
  if (options.updateCount !== false) updateBuildSelectedCounts();
}

function updateBuildSelectedCounts() {
  document.querySelectorAll("[data-build-map-selector]").forEach((selector) => {
    const selectedCount = selector.querySelectorAll("[data-build-component-checkbox]:checked").length;
    selector.querySelectorAll("[data-build-selected-count]").forEach((counter) => {
      counter.textContent = String(selectedCount);
    });
  });
}

function cellPhoneCards(simulator) {
  return Array.from(simulator.querySelectorAll("[data-cell-phone-card]"));
}

function initialCellPhoneIndex(cards) {
  const targetId = decodeURIComponent((window.location.hash || "").replace(/^#/, ""));
  if (targetId) {
    const hashIndex = cards.findIndex((card) => card.dataset.cellTargetId === targetId);
    if (hashIndex >= 0) return hashIndex;
  }
  const activeIndex = cards.findIndex((card) => card.classList.contains("is-active"));
  return activeIndex >= 0 ? activeIndex : 0;
}

function syncCellPhoneSimulatorsToHash() {
  document.querySelectorAll("[data-cell-phone-simulator]").forEach((simulator) => {
    const cards = cellPhoneCards(simulator);
    const nextIndex = initialCellPhoneIndex(cards);
    if (Number(simulator.dataset.cellPhoneIndex || 0) !== nextIndex) {
      simulator.dataset.cellPhoneIndex = String(nextIndex);
      updateCellPhoneSimulator(simulator);
    }
  });
}

function wireCellPhoneFrame(frame, simulator) {
  let startX = 0;
  let startY = 0;
  let pointerId = null;

  frame.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    startX = event.clientX;
    startY = event.clientY;
    pointerId = event.pointerId;
    frame.dataset.cellPhoneDragging = "1";
    if (frame.setPointerCapture) frame.setPointerCapture(event.pointerId);
  });

  frame.addEventListener("pointerup", (event) => {
    if (pointerId !== null && event.pointerId !== pointerId) return;
    const deltaX = event.clientX - startX;
    const deltaY = event.clientY - startY;
    delete frame.dataset.cellPhoneDragging;
    pointerId = null;
    handleCellPhoneSwipe(simulator, deltaX, deltaY);
  });

  frame.addEventListener("pointercancel", () => {
    delete frame.dataset.cellPhoneDragging;
    pointerId = null;
  });

  frame.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      changeCellPhoneProcess(simulator, 1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      changeCellPhoneProcess(simulator, -1);
    }
  });
}

function handleCellPhoneSwipe(simulator, deltaX, deltaY) {
  const threshold = 44;
  if (Math.abs(deltaX) < threshold || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) {
    return;
  }
  // Project convention for this phone simulation: right checks next, left checks previous.
  changeCellPhoneProcess(simulator, deltaX > 0 ? 1 : -1);
}

function changeCellPhoneProcess(simulator, direction) {
  const cards = cellPhoneCards(simulator);
  if (!cards.length) return;
  const currentIndex = Number(simulator.dataset.cellPhoneIndex || 0);
  const nextIndex = Math.max(0, Math.min(cards.length - 1, currentIndex + direction));
  if (nextIndex === currentIndex) return;
  simulator.dataset.cellPhoneIndex = String(nextIndex);
  simulator.dataset.cellPhoneDirection = direction > 0 ? "next" : "previous";
  updateCellPhoneSimulator(simulator);
}

function updateCellPhoneSimulator(simulator) {
  const cards = cellPhoneCards(simulator);
  const index = Math.max(0, Math.min(cards.length - 1, Number(simulator.dataset.cellPhoneIndex || 0)));
  simulator.dataset.cellPhoneIndex = String(index);
  simulator.dataset.cellPhonePosition = index === 0 ? "first" : index === cards.length - 1 ? "last" : "middle";

  cards.forEach((card, cardIndex) => {
    const active = cardIndex === index;
    card.hidden = !active;
    card.classList.toggle("is-active", active);
    card.setAttribute("aria-hidden", String(!active));
  });

  simulator.querySelectorAll("[data-cell-phone-nav]").forEach((button) => {
    const isPrevious = button.dataset.cellPhoneNav === "prev";
    button.disabled = isPrevious ? index === 0 : index === cards.length - 1;
  });
}

function updateLiveRefreshTimers() {
  document.querySelectorAll("[data-live-refresh-timer]").forEach((timer) => {
    if (!timer.dataset.liveRefreshInitialCentiseconds) return;
    const initialCentiseconds = Number(timer.dataset.liveRefreshInitialCentiseconds);
    if (!Number.isFinite(initialCentiseconds)) return;

    const startedAt = Number(timer.dataset.liveRefreshStartedAt || performance.now());
    const elapsedCentiseconds = Math.floor((performance.now() - startedAt) / 10);
    const remainingCentiseconds = Math.max(0, initialCentiseconds - elapsedCentiseconds);
    const intervalCentiseconds = Math.max(Number(timer.dataset.refreshIntervalCentiseconds || 0), 1);
    const percent = Math.max(0, Math.min(100, Math.round((remainingCentiseconds / intervalCentiseconds) * 100)));
    const precision = timer.dataset.countdownPrecision || "second";
    const value = timer.querySelector("[data-live-refresh-timer-value]");

    timer.style.setProperty("--countdown-percent", `${percent}%`);
    if (value) value.textContent = formatLiveRefreshTimerValue(remainingCentiseconds, precision);
  });
}

function formatLiveRefreshTimerValue(centiseconds, precision) {
  if (precision === "centisecond") return `${centiseconds}cs`;
  return `${Math.ceil(centiseconds / 100)}s`;
}

function initializeImportTreeCheckboxes() {
  document.querySelectorAll("[data-sim-tree-checkbox]").forEach((checkbox) => {
    checkbox.indeterminate = checkbox.dataset.indeterminate === "1";
    applyStagedTreeSelection(checkbox);
  });
  normalizeSimModeSymbols();
}

function normalizeSimModeSymbols() {
  document.querySelectorAll('[data-sim-mode-choice][data-sim-mode="random_range"]').forEach((choice) => {
    choice.dataset.simModeSymbol = "R[]";
    choice.textContent = choice.classList.contains("is-active") ? "[R[]]" : "R[]";
  });
}

function applyStagedTreeSelection(checkbox) {
  const path = checkbox.dataset.simTreePath;
  const form = checkbox.closest("[data-sim-output-form]");
  if (!path || !form) return;

  const staged = nearestSelectionDelta(form, path);
  if (staged) {
    setTreeCheckboxState(checkbox, staged.enabled);
    return;
  }

  const parentCheckbox = nearestLoadedParentCheckbox(checkbox);
  if (parentCheckbox && parentCheckbox.checked && !parentCheckbox.indeterminate) {
    setTreeCheckboxState(checkbox, true);
  }
}

function nearestSelectionDelta(form, path) {
  let nearest = null;
  form.querySelectorAll("[data-sim-selection-delta]").forEach((delta) => {
    const deltaPath = delta.dataset.simSelectionDelta || "";
    if (path !== deltaPath && !path.startsWith(`${deltaPath}/`)) return;
    if (nearest && deltaPath.length <= nearest.path.length) return;
    nearest = {
      path: deltaPath,
      enabled: delta.querySelector('[name="selection_enabled"]')?.value === "1",
    };
  });
  return nearest;
}

function nearestLoadedParentCheckbox(checkbox) {
  const node = checkbox.closest(".sim-import-node");
  const parentNode = node && node.parentElement.closest(".sim-import-node");
  return parentNode && parentNode.querySelector(":scope > .sim-import-row-wrap [data-sim-tree-checkbox]");
}

function setTreeCheckboxState(checkbox, checked) {
  checkbox.checked = checked;
  checkbox.indeterminate = false;
  checkbox.dataset.indeterminate = "0";
}

function applyTreeModeChoice(button) {
  const row = button.closest(".sim-import-row-wrap");
  if (!row) return;
  const rail = button.closest("[data-sim-mode-rail]");
  const checkbox = row.querySelector("[data-sim-tree-checkbox]");
  if (!rail || !checkbox) return;

  rail.dataset.currentMode = button.dataset.simMode || "estimate_live";
  rail.querySelectorAll("[data-sim-mode-choice]").forEach((choice) => {
    const active = choice === button;
    choice.classList.toggle("is-active", active);
    const symbol = choice.dataset.simModeSymbol || choice.textContent.replace(/[\[\]]/g, "");
    choice.textContent = active ? `[${symbol}]` : symbol;
  });
  row.querySelectorAll("[data-sim-mode-fields]").forEach((fields) => {
    fields.hidden = fields.dataset.simModeFields !== rail.dataset.currentMode;
  });
  checkbox.checked = true;
  checkbox.indeterminate = false;
  checkbox.dataset.indeterminate = "0";
  recordImportTreeSelection(checkbox);
}

function recordImportTreeModeField(field) {
  const row = field.closest(".sim-import-row-wrap");
  const checkbox = row && row.querySelector("[data-sim-tree-checkbox]");
  if (!checkbox) return;

  checkbox.checked = true;
  checkbox.indeterminate = false;
  checkbox.dataset.indeterminate = "0";
  recordImportTreeSelection(checkbox);
}

function recordImportTreeSelection(checkbox) {
  const path = checkbox.dataset.simTreePath;
  const form = checkbox.closest("[data-sim-output-form]");
  if (!form || !path) return;

  const deltas = form.querySelector("[data-sim-selection-deltas]");
  if (!deltas) return;
  let row = deltas.querySelector(`[data-sim-selection-delta="${CSS.escape(path)}"]`);
  if (!row) {
    row = document.createElement("span");
    row.dataset.simSelectionDelta = path;
    row.hidden = true;
    row.innerHTML = '<input name="selection_paths"><input name="selection_enabled"><input name="selection_modes"><input name="selection_configs">';
    deltas.append(row);
  }

  row.querySelector('[name="selection_paths"]').value = path;
  row.querySelector('[name="selection_enabled"]').value = checkbox.checked ? "1" : "0";
  const mode = currentTreeMode(checkbox);
  row.querySelector('[name="selection_modes"]').value = mode;
  row.querySelector('[name="selection_configs"]').value = mode ? JSON.stringify(currentTreeModeConfig(checkbox)) : "";
}

function currentTreeMode(checkbox) {
  const row = checkbox.closest(".sim-import-row-wrap");
  const rail = row && row.querySelector("[data-sim-mode-rail]");
  return (rail && rail.dataset.currentMode) || "";
}

function currentTreeModeConfig(checkbox) {
  const mode = currentTreeMode(checkbox);
  if (!mode) return {};
  const row = checkbox.closest(".sim-import-row-wrap");
  const config = { simulation_mode: mode };
  if (!row) return config;

  row.querySelectorAll(`[data-sim-mode-field][data-sim-mode="${CSS.escape(mode)}"]`).forEach((field) => {
    if (field.dataset.simFieldName) config[field.dataset.simFieldName] = field.value;
  });
  return config;
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function copyBridgeContext(button) {
  const card = button.closest(".readiness-card, .action-panel, .panel, .comp-focus");
  if (!card) return;

  const secondClick = button.dataset.copyStage === "llm";
  const template = card.querySelector(secondClick ? "[data-bridge-copy-llm]" : "[data-bridge-copy-table]");
  const text = template ? template.content.textContent.trim() : "";
  if (!text) return;

  await writeClipboardText(text);
  showCopyContextPopover(
    button,
    secondClick ? "Copied LLM Export." : "Copied Ignition Bridge Data. Click again for LLM export.",
    button.dataset.copyDocsUrl
  );
  button.dataset.copyStage = secondClick ? "table" : "llm";
  window.clearTimeout(button.copyStageTimer);
  button.copyStageTimer = window.setTimeout(() => {
    button.dataset.copyStage = "table";
  }, liveCardCopyMessageMs);
}

async function copyFluxLinkContext(button) {
  const card = button.closest(".readiness-card, .action-panel, .panel, .stage-card, .card");
  if (!card) return;

  const secondClick = button.dataset.copyStage === "llm";
  const template = card.querySelector(secondClick ? "[data-flux-link-copy-llm]" : "[data-flux-link-copy-table]");
  const text = template ? template.content.textContent.trim() : "";
  if (!text) return;

  await writeClipboardText(text);
  showCopyContextPopover(
    button,
    secondClick ? "Copied LLM Export." : "Copied Card Data. Click again for LLM export.",
    button.dataset.copyDocsUrl
  );
  button.dataset.copyStage = secondClick ? "table" : "llm";
  window.clearTimeout(button.copyStageTimer);
  button.copyStageTimer = window.setTimeout(() => {
    button.dataset.copyStage = "table";
  }, liveCardCopyMessageMs);
}

async function copyLiveCardContext(button) {
  const card = button.closest(".live-equipment-card");
  if (!card) return;

  const copyKey = liveCardCopyKey(card);
  const secondClick = liveCardCopyStages.get(copyKey) === "llm";
  const template = card.querySelector(secondClick ? "[data-live-card-copy-llm]" : "[data-live-card-copy-table]");
  const text = template ? template.content.textContent.trim() : "";
  if (!text) return;

  await writeClipboardText(text);

  showLiveCardCopyMessage(
    button,
    secondClick ? "Copied LLM Export" : "Copied Card Data. Click again for LLM export"
  );
  if (secondClick) {
    liveCardCopyStages.delete(copyKey);
  } else {
    liveCardCopyStages.set(copyKey, "llm");
    window.setTimeout(() => liveCardCopyStages.delete(copyKey), liveCardCopyMessageMs);
  }
}

async function copyTableContents(button) {
  const wrapper = button.closest("[data-copyable-table]");
  const table = wrapper && wrapper.querySelector("table");
  if (!table) return;

  await writeClipboardText(tableToMarkdown(table));
  showCopyContextPopover(button, "Copied table contents.");
}

function tableToMarkdown(table) {
  const rows = Array.from(table.querySelectorAll("tr"))
    .filter((row) => !row.hidden)
    .map((row) => Array.from(row.querySelectorAll("th, td")).map((cell) => markdownTableCellText(cell)))
    .filter((row) => row.length > 0);
  if (!rows.length) return "";

  const header = rows[0];
  const separator = header.map(() => "---");
  return [header, separator, ...rows.slice(1)]
    .map((row) => `| ${row.join(" | ")} |`)
    .join("\n");
}

function markdownTableCellText(cell) {
  return cell.textContent.trim().replace(/\s+/g, " ").replace(/\|/g, "\\|");
}

async function writeClipboardText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    fallbackCopyText(text);
  }
}

function liveCardCopyKey(card) {
  const heading = card.querySelector("h2");
  return heading ? heading.textContent.trim() : "";
}

function showLiveCardCopyMessage(button, message) {
  const card = button.closest(".live-equipment-card");
  const copyKey = card ? liveCardCopyKey(card) : "";
  if (copyKey) liveCardCopyMessages.set(copyKey, { message, expiresAt: Date.now() + liveCardCopyMessageMs });
  button.dataset.copyMessage = message;
  window.clearTimeout(button.copyMessageTimer);
  button.copyMessageTimer = window.setTimeout(() => {
    delete button.dataset.copyMessage;
    if (copyKey) liveCardCopyMessages.delete(copyKey);
  }, liveCardCopyMessageMs);
}

function showCopyContextPopover(button, message, docsUrl) {
  let popover = button.parentElement.querySelector(".copy-context-popover");
  if (!popover) {
    popover = document.createElement("div");
    popover.className = "copy-context-popover";
    popover.setAttribute("role", "status");
    button.insertAdjacentElement("afterend", popover);
  }
  popover.textContent = "";
  if (docsUrl) {
    popover.append(document.createTextNode(`${message} To find more information, visit: `));
    const link = document.createElement("a");
    link.href = docsUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = docsUrl;
    popover.append(link);
  } else {
    popover.append(document.createTextNode(message));
  }
  popover.hidden = false;
  window.clearTimeout(button.copyMessageTimer);
  button.copyMessageTimer = window.setTimeout(() => {
    popover.hidden = true;
  }, liveCardCopyMessageMs);
}

function restoreLiveCardCopyMessages() {
  const now = Date.now();
  liveCardCopyMessages.forEach((item, key) => {
    if (item.expiresAt <= now) liveCardCopyMessages.delete(key);
  });
  document.querySelectorAll(".live-equipment-card").forEach((card) => {
    const item = liveCardCopyMessages.get(liveCardCopyKey(card));
    const button = card.querySelector("[data-live-card-copy]");
    if (button && item) button.dataset.copyMessage = item.message;
  });
}

function focusCompSurfaceAfterSwap(event) {
  const target = event.detail && event.detail.target;
  const trigger = event.detail && event.detail.elt;
  const targetSurface = compSurfaceFromElement(target);
  const isCompSurfaceSwap = Boolean(targetSurface);
  const isCompModeControl = trigger && trigger.closest && trigger.closest(".comp-card-mode-controls");
  if (!isCompSurfaceSwap && !isCompModeControl && !pendingCompSurfaceFocusSelector) return;

  focusCurrentCompSurface(targetSurface ? `#${targetSurface.id}` : pendingCompSurfaceFocusSelector);
}

function queueCompSurfaceFocus(surfaceSelector) {
  pendingCompSurfaceFocusSelector = surfaceSelector;
  window.setTimeout(() => focusCurrentCompSurface(surfaceSelector), 50);
  window.setTimeout(() => focusCurrentCompSurface(surfaceSelector), 250);
}

function compSurfaceFromElement(element) {
  if (!element || !element.matches) return null;
  if (element.matches("[data-comp-surface]")) return element;
  return element.querySelector ? element.querySelector("[data-comp-surface]") : null;
}

function focusCurrentCompSurface(surfaceSelector) {
  const surface = document.querySelector(surfaceSelector || "[data-comp-surface]");
  if (!surface) return;
  const selectedCard = surface.dataset.selectedCard;
  const mode = surface.dataset.compMode || "summary";
  const focusTarget = mode === "summary"
    ? surface.querySelector(selectedCard ? `#${selectedCard}-comp-card` : "[data-comp-card]")
    : surface.querySelector("[data-comp-focus]");
  if (!focusTarget) return;

  if (!focusTarget.hasAttribute("tabindex")) {
    focusTarget.setAttribute("tabindex", "-1");
  }
  window.requestAnimationFrame(() => {
    focusTarget.focus({ preventScroll: true });
    focusTarget.scrollIntoView({ behavior: "smooth", block: "start" });
    if (document.activeElement === focusTarget) pendingCompSurfaceFocusSelector = "";
  });
}

function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function updateImportTreeAncestors(node) {
  let parentNode = node.parentElement.closest(".sim-import-node");
  while (parentNode) {
    const parentCheckbox = parentNode.querySelector(":scope > .sim-import-row-wrap [data-sim-tree-checkbox]");
    const childCheckboxes = Array.from(
      parentNode.querySelectorAll(":scope > [data-sim-tree-children] > .sim-import-tree > .sim-import-node > .sim-import-row-wrap [data-sim-tree-checkbox]")
    );
    if (parentCheckbox && childCheckboxes.length) {
      const allChecked = childCheckboxes.every((child) => child.checked && !child.indeterminate);
      const anyChecked = childCheckboxes.some((child) => child.checked || child.indeterminate);
      parentCheckbox.checked = allChecked;
      parentCheckbox.indeterminate = anyChecked && !allChecked;
      parentCheckbox.dataset.indeterminate = parentCheckbox.indeterminate ? "1" : "0";
    }
    parentNode = parentNode.parentElement.closest(".sim-import-node");
  }
}
