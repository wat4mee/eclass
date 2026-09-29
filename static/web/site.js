// Page behavior shared by every page: intro, entrance motion, count-ups, live countdowns, the language menu,
// the theme toggle and the sync pill. Same behavior as the Mac dashboard; no inline scripts (CSP).
(() => {
  const root = document.documentElement;
  const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const T = JSON.parse(document.getElementById("js-t")?.textContent || "{}");

  // the intro overlay has done its job after ~1 s
  const intro = document.querySelector(".intro-screen");
  if (intro) setTimeout(() => intro.remove(), root.classList.contains("intro") ? 1100 : 0);

  // staggered entrance: every .reveal gets its position in the page as --i
  document.querySelectorAll(".reveal").forEach((el, i) => {
    if (!el.style.getPropertyValue("--i")) el.style.setProperty("--i", Math.min(i, 12));
  });

  // numbers count up from zero
  document.querySelectorAll("[data-count]").forEach(el => {
    const target = Number(el.dataset.count), suffix = el.dataset.suffix || "";
    if (REDUCED_MOTION || !target) { el.textContent = target + suffix; return; }
    const start = performance.now(), duration = 1300;
    const delay = 250 + (root.classList.contains("intro") ? 400 : 0);
    el.textContent = "0" + suffix;
    const tick = now => {
      const p = Math.min(1, Math.max(0, (now - start - delay) / duration));
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 4))) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });

  // spotlight that follows the pointer on .lift cards
  document.addEventListener("pointermove", e => {
    const card = e.target.closest && e.target.closest(".lift");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, { passive: true });

  // live countdowns: <div data-due="ISO">
  const countdowns = document.querySelectorAll("[data-due]");
  const pad = n => String(n).padStart(2, "0");
  const renderCountdowns = () => countdowns.forEach(el => {
    let s = Math.max(0, Math.floor((new Date(el.dataset.due) - Date.now()) / 1000));
    const d = Math.floor(s / 86400); s %= 86400;
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    el.innerHTML = (d ? `<b>${d}</b><i>${T.day_short || "d"}</i>` : "") + `<b>${pad(h)}</b><i>:</i><b>${pad(m)}</b><i>:</i><b>${pad(sec)}</b>`;
  });
  if (countdowns.length) { renderCountdowns(); setInterval(renderCountdowns, 1000); }

  // sync pill: spins while a sync runs, then the page reloads with the new data
  const syncBtn = document.getElementById("sync-btn");
  if (syncBtn) {
    const running = () => {
      syncBtn.classList.add("running");
      const label = syncBtn.querySelector(".sync-label");
      if (label && T.sync_running) label.textContent = T.sync_running;
    };
    syncBtn.form.addEventListener("submit", () => { running(); setTimeout(() => { syncBtn.disabled = true; }); });
    if (syncBtn.dataset.state === "running") {
      running();
      const poll = async () => {
        try {
          const resp = await fetch(syncBtn.dataset.url, { headers: { Accept: "application/json" } });
          if (resp.ok && (await resp.json()).state !== "running") { location.reload(); return; }
        } catch (e) { /* a network hiccup: try again */ }
        setTimeout(poll, 3000);
      };
      setTimeout(poll, 3000);
    }
  }

  // language menu
  const langBox = document.getElementById("lang");
  if (langBox) {
    const langBtn = langBox.querySelector(".lang-btn");
    const setLang = open => { langBox.classList.toggle("open", open); langBtn.setAttribute("aria-expanded", open); };
    langBtn.addEventListener("click", e => { e.stopPropagation(); setLang(!langBox.classList.contains("open")); });
    document.addEventListener("click", e => { if (!langBox.contains(e.target)) setLang(false); });
    document.addEventListener("keydown", e => { if (e.key === "Escape") setLang(false); });
  }

  // theme toggle: a wave spreads from the button; stars follow it into the night, a sun bursts at dawn
  const button = document.getElementById("theme");
  if (!button) return;
  const effective = () => root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const effects = (mode, x, y) => {
    if (REDUCED_MOTION) return;
    const nodes = [];
    if (mode === "dark") {
      const far = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
      for (let i = 0; i < 42; i++) {
        const star = document.createElement("span"), sx = Math.random() * innerWidth, sy = Math.random() * innerHeight;
        const size = 1.5 + Math.random() * 2.5;
        Object.assign(star.style, { left: `${sx}px`, top: `${sy}px`, width: `${size}px`, height: `${size}px`,
          animationDelay: `${Math.hypot(sx - x, sy - y) / far * 700 + Math.random() * 120}ms` });
        star.className = "fx-star";
        nodes.push(star);
      }
    } else {
      const sun = document.createElement("span");
      sun.className = "fx-sun";
      Object.assign(sun.style, { left: `${x}px`, top: `${y}px` });
      nodes.push(sun);
      for (let i = 0; i < 12; i++) {
        const ray = document.createElement("span");
        ray.className = "fx-ray";
        Object.assign(ray.style, { left: `${x}px`, top: `${y}px`, animationDelay: `${i % 2 * 60}ms` });
        ray.style.setProperty("--a", `${i * 30}deg`);
        nodes.push(ray);
      }
    }
    nodes.forEach(n => document.body.appendChild(n));
    setTimeout(() => nodes.forEach(n => n.remove()), 2400);
  };
  button.addEventListener("click", () => {
    const next = effective() === "dark" ? "light" : "dark";
    const r = button.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    const apply = () => {
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      effects(next, x, y);  // added inside the new state, so they appear within the spreading wave
    };
    button.classList.remove("pop"); void button.offsetWidth; button.classList.add("pop");
    if (!document.startViewTransition || REDUCED_MOTION) return apply();
    root.style.setProperty("--tx", `${x}px`);
    root.style.setProperty("--ty", `${y}px`);
    root.classList.add("theme-vt");
    document.startViewTransition(apply).finished.finally(() => root.classList.remove("theme-vt"));
  });
})();
