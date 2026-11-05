// CyberGen gallery: theme switch, stage filter, rail highlight and the image viewer.
// The page works without this script (every picture links to its full size).
(() => {
  const root = document.documentElement;
  const body = document.body;
  const hashId = () => decodeURIComponent(location.hash.slice(1));

  // A link to a log entry made before the showcase became the front page.
  if (body.dataset.page === "showcase" && location.hash && !document.getElementById(hashId())) {
    location.replace("log.html" + location.hash);
    return;
  }

  // ---- Theme: auto (follow the system), light, dark -----------------------
  const themeBtn = document.getElementById("theme");
  const THEMES = ["auto", "light", "dark"];
  let theme = "auto";
  try { theme = localStorage.getItem("cg-theme") || "auto"; } catch (e) { /* storage blocked */ }
  if (!THEMES.includes(theme)) theme = "auto";
  function applyTheme(t) {
    theme = t;
    if (t === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", t);
    (themeBtn.querySelector(".theme-val") || themeBtn).textContent = t;
    try { if (t === "auto") localStorage.removeItem("cg-theme"); else localStorage.setItem("cg-theme", t); } catch (e) { /* ignore */ }
  }
  applyTheme(theme);
  themeBtn.addEventListener("click", () => applyTheme(THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]));

  // ---- Stage filter --------------------------------------------------------
  const filterBtns = [...document.querySelectorAll("[data-filter]")];
  const staged = [...document.querySelectorAll(".stage, .rail nav > a, .strip .cells a")];
  const msLists = [...document.querySelectorAll(".rail .ms-list")];
  function setFilter(f) {
    body.dataset.filter = f;
    filterBtns.forEach((b) => {
      const on = b.dataset.filter === f;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
    staged.forEach((el) => el.classList.toggle("match", el.dataset.stage === f));
    msLists.forEach((el) => el.classList.toggle("match", el.previousElementSibling?.dataset.stage === f));
    if (f !== "all") document.querySelectorAll(".rail nav > a").forEach((a) => a.classList.toggle("on", a.dataset.stage === f));
  }
  const hero = document.querySelector(".hero");
  filterBtns.forEach((b) => b.addEventListener("click", () => {
    const f = b.dataset.filter;
    setFilter(f);
    // Scrolled down into the gallery: jump to the top of the stage just chosen.
    const target = document.getElementById("stage-" + f);
    if (target && hero && window.scrollY > hero.offsetTop + hero.offsetHeight) target.scrollIntoView({ block: "start" });
  }));
  // A link to something the filter hides shows everything again first.
  function reveal(id, scroll) {
    const el = id && document.getElementById(id);
    if (el && el.offsetParent === null && body.dataset.filter !== "all") {
      setFilter("all");
      if (scroll) el.scrollIntoView({ block: "start" });
    }
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (a) reveal(decodeURIComponent(a.getAttribute("href").slice(1)), false);
  });
  window.addEventListener("hashchange", () => reveal(hashId(), true));
  reveal(hashId(), true);

  // ---- Rail: highlight the stage in view ------------------------------------
  const railLinks = [...document.querySelectorAll(".rail nav > a")];
  if ("IntersectionObserver" in window && railLinks.length) {
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        railLinks.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + en.target.id));
      });
    }, { rootMargin: "-80px 0px -65% 0px" });
    document.querySelectorAll(".stage").forEach((s) => spy.observe(s));
  }

  // ---- Usage panel: every device added up, or each device apart ---------------
  const usage = document.getElementById("usage");
  if (usage) {
    // Times in the viewer's own zone (the page carries them in UTC).
    usage.querySelectorAll("time[datetime]").forEach((t) => {
      const d = new Date(t.getAttribute("datetime"));
      if (!isNaN(d)) t.textContent = d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    });
    const more = document.getElementById("usage-more");
    const models = document.getElementById("usage-models");
    more.addEventListener("click", () => {
      const open = models.hidden;
      models.hidden = !open;
      more.classList.toggle("on", open);
      more.setAttribute("aria-expanded", String(open));
    });
    const toggle = document.getElementById("usage-toggle");
    const devices = document.getElementById("usage-devices");
    toggle.addEventListener("click", () => {
      const on = usage.dataset.view !== "devices";
      usage.dataset.view = on ? "devices" : "all";
      toggle.classList.toggle("on", on);
      toggle.setAttribute("aria-pressed", String(on));
      devices.hidden = !on;
    });
  }

  // ---- Day and night slider ---------------------------------------------------
  document.querySelectorAll(".compare").forEach((c) => {
    const handle = c.querySelector(".cmp-handle");
    let pos = 50;
    let dragging = false;
    const set = (p) => {
      pos = Math.max(0, Math.min(100, p));
      c.style.setProperty("--pos", pos + "%");
      if (handle) handle.setAttribute("aria-valuenow", String(Math.round(pos)));
    };
    const at = (x) => { const r = c.getBoundingClientRect(); set(((x - r.left) / r.width) * 100); };
    c.addEventListener("pointerdown", (e) => { dragging = true; c.setPointerCapture(e.pointerId); at(e.clientX); });
    c.addEventListener("pointermove", (e) => { if (dragging) at(e.clientX); });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((n) => c.addEventListener(n, () => { dragging = false; }));
    if (handle) handle.addEventListener("keydown", (e) => {
      const step = { ArrowLeft: -5, ArrowRight: 5, PageDown: -25, PageUp: 25 }[e.key];
      if (step !== undefined) { e.preventDefault(); set(pos + step); }
      else if (e.key === "Home") { e.preventDefault(); set(0); }
      else if (e.key === "End") { e.preventDefault(); set(100); }
    });
  });

  // ---- Image viewer -----------------------------------------------------------
  const lb = document.getElementById("lb");
  if (!lb || typeof lb.showModal !== "function") return;
  const lbImg = lb.querySelector(".lb-img img");
  const lbTitle = lb.querySelector("figcaption h3");
  const lbText = lb.querySelector("figcaption p");
  const lbSrc = lb.querySelector(".lb-src");
  const lbTags = lb.querySelector(".lb-tags");
  const lbCount = lb.querySelector(".lb-count");
  let current = null;

  const visible = () => [...document.querySelectorAll(".entry")]
    .filter((el) => el.offsetParent !== null && el.querySelector("a.shot"));

  function show(entry) {
    current = entry;
    const shot = entry.querySelector("a.shot");
    const list = visible();
    lbImg.src = shot.getAttribute("href");
    lbImg.alt = entry.querySelector(".entry-title").textContent;
    lbTitle.textContent = lbImg.alt;
    lbText.textContent = (entry.querySelector(".cap") || entry.querySelector("figcaption")).textContent;
    lbSrc.href = shot.dataset.src;
    lbTags.replaceChildren(...[...entry.querySelectorAll(".entry-head > *")].map((n) => n.cloneNode(true)));
    lbTags.dataset.stage = entry.dataset.stage;
    lbCount.textContent = (list.indexOf(entry) + 1) + " / " + list.length;
    // Warm the neighbours so stepping through is instant.
    [step(1, true), step(-1, true)].forEach((n) => { if (n) new Image().src = n.querySelector("a.shot").getAttribute("href"); });
  }
  function step(d, peek) {
    const list = visible();
    const i = list.indexOf(current);
    const next = list[(i + d + list.length) % list.length];
    if (!peek && next) show(next);
    return next;
  }
  function close() {
    lb.close();
  }
  lb.addEventListener("close", () => {
    if (current) history.replaceState(null, "", "#" + current.id);
    lbImg.removeAttribute("src");
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest("a.shot");
    if (!a || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    show(a.closest(".entry"));
    lb.showModal();
  });
  lb.addEventListener("click", (e) => {
    const b = e.target.closest("[data-lb]");
    if (b) {
      if (b.dataset.lb === "close") close(); else step(b.dataset.lb === "next" ? 1 : -1);
      return;
    }
    // A click on the dark space around the picture closes the viewer.
    if (e.target === lb || e.target.classList.contains("lb-img")) close();
  });
  lb.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
  });
  let touchX = null;
  lb.addEventListener("touchstart", (e) => { touchX = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
  lb.addEventListener("touchend", (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 60) step(dx < 0 ? 1 : -1);
  });
})();
