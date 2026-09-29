// Shahzod AI chat (same behavior as the Mac dashboard): sends the question with the CSRF token, remembers the last
// turns of the conversation, renders formulas with KaTeX and the cited sources.
(() => {
  const T = JSON.parse(document.getElementById("js-t").textContent);
  const CFG = JSON.parse(document.getElementById("chat-config").textContent);
  const CSRF = document.querySelector('meta[name="csrf-token"]').content;
  const TIMEOUT_MS = 90000;
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tr = (key, vars = {}) => (T[key] || key).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const shorten = (s, n = 40) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const chat = document.getElementById("chat"), question = document.getElementById("question");
  const send = document.getElementById("send");
  const history = [];  // [{q, a}] of this conversation; the server uses the last few turns
  let course = CFG.course, counter = 0, busy = false;

  document.querySelectorAll("#scope .pill").forEach(p => p.addEventListener("click", () => {
    document.querySelectorAll("#scope .pill").forEach(x => x.classList.toggle("on", x === p));
    course = p.dataset.course;
    history.length = 0;  // another course starts a new conversation
    window.history.replaceState(null, "", course ? `?course=${course}` : location.pathname);
  }));

  const grow = () => { question.style.height = "auto"; question.style.height = Math.min(question.scrollHeight, 180) + "px"; };
  question.addEventListener("input", grow);
  question.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  });
  document.getElementById("ask").addEventListener("submit", e => { e.preventDefault(); submit(); });

  // KaTeX finds a formula only inside one text node: line breaks inside a formula become spaces first.
  const MATH = /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$(?:[^$\n]|\n(?!\n))+?\$/g;
  const formatAnswer = (text, id) => esc(text)
    .replace(MATH, m => m.replace(/\s*\n\s*/g, " "))
    .split(/\n{2,}/).map(p => "<p>" + p
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>")
      .replace(/(?<!\\)\[(\d+)\]/g, `<a class="cite" href="#${id}-src-$1" data-src="${id}-src-$1">$1</a>`) + "</p>").join("");

  const renderMath = el => {
    if (!window.renderMathInElement) return;
    // a formula KaTeX cannot parse stays as its original text (never blank); the reason goes to the console
    renderMathInElement(el, { delimiters: [
      { left: "$$", right: "$$", display: true }, { left: "\\[", right: "\\]", display: true },
      { left: "$", right: "$", display: false }, { left: "\\(", right: "\\)", display: false } ],
      throwOnError: true, errorCallback: (msg, err) => console.warn(msg, err && err.message) });
  };

  const fileUrl = id => CFG.file.replace(/0$/, String(id));
  const pageLabel = s => s.pages && s.pages.length > 1 ? tr("pages", { n: s.pages.join(", ") }) : tr("page", { n: s.page });
  const renderSources = (sources, id) => !sources.length ? "" : `<div class="sources">${sources.map(s => `
    <details class="src" id="${id}-src-${s.n}">
      <summary><span class="src-n">${s.n}</span><span class="src-title" title="${esc(s.filename)}">${esc(shorten(s.filename))}</span>
        <span class="src-page">${esc(pageLabel(s))}</span></summary>
      <div class="src-body">
        <p class="snippet">${esc(s.text.replace(/\s+/g, " ").slice(0, 420))}${s.text.length > 420 ? "…" : ""}</p>
        <a class="btn small" href="${fileUrl(s.file_id)}#page=${Number(s.page)}" target="_blank" rel="noopener">${esc(T.open_source)}<svg class="ico"><use href="#i-external"/></svg></a>
      </div>
    </details>`).join("")}</div>`;

  const scrollDown = el => el.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "end" });
  const typing = () => `<div class="bot-name">Shahzod AI</div><div class="typing"><span></span><span></span><span></span></div>
    <div class="status">${esc(T.searching)}</div>`;

  function submit() {
    const text = question.value.trim();
    if (!text || busy) return;
    document.getElementById("welcome")?.remove();
    const id = "qa" + (++counter);
    chat.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
    chat.insertAdjacentHTML("beforeend", `<div class="msg bot" id="${id}">
      <div class="avatar"><svg class="ico"><use href="#i-sparkles"/></svg></div><div class="bubble"></div></div>`);
    question.value = ""; grow();
    ask(text, id, history.slice(-4));
  }

  async function ask(text, id, turns) {
    const bot = document.getElementById(id), bubble = bot.querySelector(".bubble");
    bubble.innerHTML = typing();
    scrollDown(bot);
    busy = true; send.disabled = true;
    const phase = setTimeout(() => { const s = bubble.querySelector(".status"); if (s) s.textContent = T.writing; }, 1600);
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), TIMEOUT_MS);
    try {
      const response = await fetch(CFG.url, {
        method: "POST", signal: abort.signal,
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ question: text, course_id: course || null, history: turns }),
      });
      let data;
      try { data = await response.json(); } catch (e) { throw new Error(T.network); }
      if (!response.ok) throw new Error(data.error || T.network);
      bubble.innerHTML = `<div class="bot-name">Shahzod AI</div>
        <div class="answer ${data.found ? "" : "not-found"}">${formatAnswer(data.answer, id)}</div>
        ${data.found && data.query ? `<div class="query">${esc(T.query)}: ${esc(data.query)}</div>` : ""}
        ${data.found ? renderSources(data.sources || [], id) : ""}`;
      renderMath(bubble);
      bubble.querySelectorAll(".cite").forEach(a => a.addEventListener("click", e => {
        e.preventDefault();
        const src = document.getElementById(a.dataset.src);
        if (src) { src.open = true; src.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "center" }); }
      }));
      history.push({ q: text, a: data.answer.replace(/\[\d+\]/g, "") });
    } catch (err) {
      const message = err.name === "AbortError" ? T.timeout : err instanceof TypeError ? T.network : err.message;
      bubble.innerHTML = `<div class="bot-name">Shahzod AI</div><div class="error"><p>${esc(message)}</p>
        <button class="btn small" type="button">${esc(T.retry)}</button></div>`;
      bubble.querySelector(".error .btn").onclick = () => ask(text, id, turns);
    } finally {
      clearTimeout(phase); clearTimeout(timer);
      busy = false; send.disabled = false;
      question.focus();
      scrollDown(bot);
    }
  }
})();
