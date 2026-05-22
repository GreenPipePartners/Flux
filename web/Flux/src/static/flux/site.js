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

document.addEventListener("htmx:afterSwap", (event) => {
  restoreLiveCardCopyMessages();
});

document.addEventListener("htmx:afterSettle", focusCompSurfaceAfterSwap);

document.addEventListener("click", (event) => {
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

  if (!event.target.closest("[data-theme-picker]")) {
    setThemeMenuOpen(false);
  }
});

document.addEventListener("change", (event) => {
  const checkbox = event.target.closest("[data-sim-tree-checkbox]");
  if (!checkbox) return;

  const node = checkbox.closest(".sim-import-node");
  if (!node) return;
  checkbox.indeterminate = false;
  checkbox.dataset.indeterminate = "0";

  node.querySelectorAll(".sim-import-node [data-sim-tree-checkbox]").forEach((child) => {
    child.checked = checkbox.checked;
    child.indeterminate = false;
    child.dataset.indeterminate = "0";
  });

  updateImportTreeAncestors(node);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setThemeMenuOpen(false);
});

document.addEventListener("DOMContentLoaded", () => {
  setTheme(document.documentElement.dataset.theme || "green");
  initializeImportTreeCheckboxes();
});

function initializeImportTreeCheckboxes() {
  document.querySelectorAll("[data-sim-tree-checkbox]").forEach((checkbox) => {
    checkbox.indeterminate = checkbox.dataset.indeterminate === "1";
  });
}

async function copyBridgeContext(button) {
  const card = button.closest(".readiness-card, .action-panel");
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
  popover.append(document.createTextNode(`${message} To find more information, visit: `));
  if (docsUrl) {
    const link = document.createElement("a");
    link.href = docsUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = docsUrl;
    popover.append(link);
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
  const isCompSurfaceSwap = target && target.id === "dashboard-comp-surface";
  const isCompModeControl = trigger && trigger.closest && trigger.closest(".comp-card-mode-controls");
  if (!isCompSurfaceSwap && !isCompModeControl) return;

  const surface = document.querySelector("#dashboard-comp-surface");
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
