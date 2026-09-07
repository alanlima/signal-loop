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

function updateJourneyClock() {
  document.querySelectorAll("[data-journey-deadline]").forEach(function (element) {
    const remaining = Math.max(0, Math.ceil((Date.parse(element.dataset.journeyDeadline) - Date.now()) / 1000));
    const label = element.querySelector("[data-journey-remaining]");
    if (label) label.textContent = remaining ? remaining + " seconds remaining." : "Question time ended. Save your current answers to review; no new questions will be offered.";
  });
}
document.addEventListener("DOMContentLoaded", updateJourneyClock);
document.addEventListener("htmx:load", updateJourneyClock);
setInterval(updateJourneyClock, 1000);

function unsavedForms() { return Array.from(document.querySelectorAll('form.personal-form[data-unsaved="true"]')); }
function explainUnsaved() {
  const errors = document.getElementById("form-errors");
  if (errors) errors.textContent = "Save your edited answers before continuing. Your text is still on this page.";
}
document.addEventListener("input", function (event) {
  const form = event.target.closest("form.personal-form");
  if (form) form.dataset.unsaved = "true";
});
document.addEventListener("submit", function (event) {
  const discard = event.submitter?.value === "discard";
  if (!discard && unsavedForms().some(form => form !== event.target)) {
    event.preventDefault(); event.stopImmediatePropagation(); explainUnsaved(); return;
  }
  if (!event.target.hasAttribute("hx-post")) {
    if (discard) unsavedForms().forEach(form => delete form.dataset.unsaved);
    else delete event.target.dataset.unsaved;
  }
}, true);
document.addEventListener("click", function (event) {
  if (event.target.closest("a[hx-get]") && unsavedForms().length) {
    event.preventDefault(); event.stopImmediatePropagation(); explainUnsaved();
  }
}, true);
window.addEventListener("beforeunload", function (event) {
  if (unsavedForms().length) { event.preventDefault(); event.returnValue = ""; }
});

document.addEventListener("htmx:responseError", function () {
  const errors = document.getElementById("form-errors");
  if (errors) {
    errors.textContent = "We could not save or load this page. Your entered text is still here; retry before leaving.";
  }
});

document.addEventListener("htmx:sendError", function () {
  const errors = document.getElementById("form-errors");
  if (errors) {
    errors.textContent = "Unable to connect. Check your connection and try again.";
  }
});
