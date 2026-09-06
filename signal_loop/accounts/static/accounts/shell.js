document.addEventListener("htmx:afterSettle", function (event) {
  if (event.detail?.target?.id === "application-shell") {
    document.getElementById("main-content")?.focus();
  }
});

document.addEventListener("htmx:historyRestore", function () {
  document.getElementById("main-content")?.focus();
});

function updatePersonalCounters() {
  document.querySelectorAll("textarea[data-codepoint-limit]").forEach(function (field) {
    const counter = document.querySelector('[data-count-for="' + field.id + '"]');
    if (counter) {
      const length = Array.from(field.value.replace(/\r\n?/g, "\n")).length;
      counter.textContent = length + " of " + field.dataset.codepointLimit + " characters";
    }
  });
  document.querySelectorAll("form[data-week-end]").forEach(function (form) {
    const selected = Array.from(form.querySelectorAll("input[data-closes-at]:checked"));
    const preview = form.querySelector("[data-draft-expiry]");
    if (!preview) return;
    if (selected.length < 1 || selected.length > 3) {
      preview.textContent = "Choose one to three projects to see your exact expiry.";
      return;
    }
    const expiry = Math.min(Date.parse(form.dataset.weekEnd), ...selected.map(field => Date.parse(field.dataset.closesAt)));
    preview.textContent = new Date(expiry).toISOString().replace("T", " ").replace(".000Z", " UTC");
  });
}
document.addEventListener("input", updatePersonalCounters);
document.addEventListener("DOMContentLoaded", updatePersonalCounters);
document.addEventListener("htmx:load", updatePersonalCounters);

document.addEventListener("htmx:responseError", function () {
  const errors = document.getElementById("form-errors");
  if (errors) {
    errors.textContent = "This page could not be loaded. Refresh to check your project access.";
  }
});

document.addEventListener("htmx:sendError", function () {
  const errors = document.getElementById("form-errors");
  if (errors) {
    errors.textContent = "Unable to connect. Check your connection and try again.";
  }
});
