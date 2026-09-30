// Study pack page (same behavior as the Mac dashboard): tabs with a sliding indicator, a flashcard deck,
// a one-question-at-a-time quiz with a score ring, formulas rendered by KaTeX and the "studied" toggle.
(() => {
  const T = JSON.parse(document.getElementById("js-t").textContent);
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tr = (key, vars = {}) => (T[key] || key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

  // ---- segmented tabs with a sliding indicator
  const segs = [...document.querySelectorAll(".seg")], ind = document.querySelector(".seg-ind");
  const moveInd = btn => { ind.style.width = btn.offsetWidth + "px"; ind.style.transform = `translateX(${btn.offsetLeft}px)`; };
  const openTab = name => {
    segs.forEach(s => s.classList.toggle("on", s.dataset.tab === name));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("on", p.id === "p-" + name));
    moveInd(segs.find(s => s.dataset.tab === name));
    history.replaceState(null, "", name === "summary" ? location.pathname : "#" + name);
    if (name === "cards") document.getElementById("deck").focus({ preventScroll: true });
  };
  segs.forEach(s => s.addEventListener("click", () => openTab(s.dataset.tab)));
  const initial = ["cards", "quiz"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "summary";
  requestAnimationFrame(() => { ind.style.transition = "none"; openTab(initial); requestAnimationFrame(() => { ind.style.transition = ""; }); });
  addEventListener("resize", () => moveInd(document.querySelector(".seg.on")));
  addEventListener("hashchange", () => {
    const name = location.hash.slice(1);
    if (["summary", "cards", "quiz"].includes(name)) openTab(name);
  });
  if (document.fonts) document.fonts.ready.then(() => moveInd(document.querySelector(".seg.on")));

  // ---- flashcard deck: click or Space flips, arrows or a swipe move
  const cards = [...document.querySelectorAll(".fcard")];
  const cur = document.getElementById("cur"), deckbar = document.getElementById("deckbar");
  let idx = 0, swiped = false;
  const show = (n, dir) => {
    if (!cards.length) return;
    cards[idx].classList.remove("active", "flipped", "from-left");
    idx = (n + cards.length) % cards.length;
    const card = cards[idx];
    card.classList.toggle("from-left", dir < 0);
    void card.offsetWidth;  // restart the entrance animation
    card.classList.add("active");
    cur.textContent = idx + 1;
    deckbar.style.width = ((idx + 1) / cards.length * 100) + "%";
  };
  cards.forEach(c => c.addEventListener("click", () => { if (!swiped) c.classList.toggle("flipped"); swiped = false; }));
  document.getElementById("prev").onclick = () => show(idx - 1, -1);
  document.getElementById("next").onclick = () => show(idx + 1, 1);
  document.addEventListener("keydown", e => {
    if (!document.getElementById("p-cards").classList.contains("on") || e.target.closest("input, textarea")) return;
    if (e.key === "ArrowRight") show(idx + 1, 1);
    else if (e.key === "ArrowLeft") show(idx - 1, -1);
    else if ((e.key === " " || e.key === "Enter") && cards.length) { e.preventDefault(); cards[idx].classList.toggle("flipped"); }
  });
  const stage = document.getElementById("stage");
  let startX = null;
  stage.addEventListener("pointerdown", e => { startX = e.clientX; });
  stage.addEventListener("pointerup", e => {
    if (startX === null) return;
    const dx = e.clientX - startX; startX = null;
    if (Math.abs(dx) > 50) { swiped = true; show(idx + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1); }
  });
  show(0, 1);

  // ---- quiz, one question at a time
  const qcards = [...document.querySelectorAll(".qcard")], total = qcards.length;
  const qnext = document.getElementById("qnext"), qlabel = document.getElementById("qlabel");
  const qscore = document.getElementById("qscore"), qbar = document.getElementById("qbar");
  const RING = 339.29;
  let q = 0, right = 0;
  const updateTop = () => {
    qlabel.textContent = q < total ? tr("q_of", { i: q + 1, n: total }) : T.result;
    qscore.textContent = tr("correct", { n: right });
    qbar.style.width = (total ? Math.min(q, total) / total * 100 : 0) + "%";
  };
  qcards.forEach(card => card.querySelectorAll(".opt").forEach(opt => opt.addEventListener("click", () => {
    const answer = Number(card.dataset.answer), picked = Number(opt.dataset.i);
    card.querySelectorAll(".opt").forEach((o, i) => {
      o.disabled = true;
      if (i === answer) o.classList.add("right");
      else if (i === picked) { o.classList.add("wrong"); o.querySelector("use").setAttribute("href", "#i-x"); }
      else o.classList.add("dim");
    });
    if (picked === answer) right++;
    card.classList.add("answered");
    qscore.textContent = tr("correct", { n: right });
    qnext.disabled = false;
    qnext.focus({ preventScroll: true });
  })));
  qnext.addEventListener("click", () => {
    qcards[q].classList.remove("active");
    q++;
    qnext.disabled = true;
    if (q < total) { qcards[q].classList.add("active"); updateTop(); return; }
    finish();
  });
  function finish() {
    updateTop();
    document.getElementById("qactions").style.display = "none";
    document.getElementById("qresult").classList.add("on");
    const ring = document.getElementById("rring");
    requestAnimationFrame(() => requestAnimationFrame(() => { ring.style.strokeDashoffset = RING * (1 - right / total); }));
    const num = document.getElementById("rnum");
    let n = 0;
    const step = () => { num.textContent = n; if (n++ < right) setTimeout(step, 1400 / Math.max(right, 1)); };
    step();
    document.getElementById("rmsg").textContent = right === total ? T.perfect : right >= total * .6 ? T.good : T.low;
    if (right === total) setTimeout(confetti, 700);
  }
  document.getElementById("qrestart").addEventListener("click", () => {
    q = 0; right = 0;
    qcards.forEach(card => {
      card.classList.remove("answered", "active");
      card.querySelectorAll(".opt").forEach(o => {
        o.disabled = false; o.classList.remove("right", "wrong", "dim");
        o.querySelector("use").setAttribute("href", "#i-check");
      });
    });
    document.getElementById("qresult").classList.remove("on");
    document.getElementById("rring").style.strokeDashoffset = "";
    document.getElementById("qactions").style.display = "";
    if (qcards.length) qcards[0].classList.add("active");
    updateTop();
  });
  updateTop();

  function confetti() {
    if (REDUCED_MOTION) return;
    const colors = ["#fbbf24", "#2dd4bf", "#f97360", "#60a5fa", "#a78bfa", "#84cc16", "#f472b6"];
    for (let i = 0; i < 140; i++) {
      const p = document.createElement("span");
      p.className = "confetti";
      p.style.left = (50 + (Math.random() - .5) * 12) + "vw";
      p.style.background = colors[i % colors.length];
      document.body.appendChild(p);
      const dx = (Math.random() - .5) * innerWidth * .9, up = -(180 + Math.random() * 260), rot = (Math.random() - .5) * 1080;
      p.animate([
        { transform: "translate(0, 0) rotate(0deg)", opacity: 1 },
        { transform: `translate(${dx * .6}px, ${up}px) rotate(${rot * .5}deg)`, opacity: 1, offset: .35 },
        { transform: `translate(${dx}px, ${innerHeight * .6}px) rotate(${rot}deg)`, opacity: 0 },
      ], { duration: 1800 + Math.random() * 1000, easing: "cubic-bezier(.2,.7,.3,1)" }).onfinish = () => p.remove();
    }
  }

  // ---- "studied" toggle
  const studied = document.querySelector(".studied-btn");
  studied?.addEventListener("click", async () => {
    const want = !studied.classList.contains("on");
    try {
      const resp = await fetch(studied.dataset.url, { method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF }, body: JSON.stringify({ studied: want }) });
      if (!resp.ok) throw new Error();
      studied.classList.toggle("on", want);
      studied.querySelector("span").textContent = want ? T.studied_done : T.studied_mark;
    } catch (e) { studied.animate([{ transform: "translateX(-4px)" }, { transform: "translateX(4px)" }, { transform: "none" }], 300); }
  });

  // ---- formulas: one that KaTeX cannot parse stays as its original text (never blank)
  if (window.renderMathInElement) {
    renderMathInElement(document.querySelector("main"), { delimiters: [
      { left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false }, { left: "\\(", right: "\\)", display: false } ],
      throwOnError: true, errorCallback: (msg, err) => console.warn(msg, err && err.message) });
  }
})();
