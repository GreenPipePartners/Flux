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
