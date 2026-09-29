// Runs in <head> before the page paints (no inline scripts: see the CSP in web/__init__.py).
try { var saved = localStorage.getItem("theme"); if (saved) document.documentElement.dataset.theme = saved; } catch (e) {}
(function () {  // the intro plays on a reload or a fresh open, never on in-site navigation or back/forward
  var nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  var internal = document.referrer && document.referrer.indexOf(location.origin) === 0;
  var fresh = !nav || nav.type === "reload" || (nav.type === "navigate" && !internal);
  if (fresh && !matchMedia("(prefers-reduced-motion: reduce)").matches) document.documentElement.classList.add("intro");
})();
