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

  if (!event.target.closest("[data-theme-picker]")) {
    setThemeMenuOpen(false);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setThemeMenuOpen(false);
});

document.addEventListener("DOMContentLoaded", () => {
  setTheme(document.documentElement.dataset.theme || "green");
});
