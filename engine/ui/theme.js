// Applies the saved theme before first paint (no flash). "system" = follow the OS.
try {
  var t = localStorage.getItem("veloce-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) { /* storage blocked: follow the OS */ }
