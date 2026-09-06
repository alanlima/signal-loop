document.addEventListener("htmx:afterSettle", function (event) {
  if (event.detail.target.id === "application-shell") {
    document.getElementById("main-content")?.focus();
  }
});

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
