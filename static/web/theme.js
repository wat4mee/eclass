// Apply the saved light/dark theme before the page paints (loaded in <head>, no inline scripts: see CSP).
try { var saved = localStorage.getItem("theme"); if (saved) document.documentElement.dataset.theme = saved; } catch (e) {}
