(() => {
  const KEY = "dailyAInews.sources.v1";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let data, sel = new Set(), cat = "All", q = "", srcF = null;
  let selectionInitialised = false, draftSel = null, lastFocus = null;

  // Read the old array format too, so existing visitors keep their choices.
  const load = () => {
    try {
      const value = JSON.parse(localStorage.getItem(KEY));
      if (Array.isArray(value)) return { ids: value, intentionalEmpty: false };
      return Array.isArray(value && value.ids) ? { ids: value.ids, intentionalEmpty: value.intentionalEmpty === true } : null;
    } catch { return null; }
  };
  const SEEN = "dailyAInews.seen.v1";
  const loadSeen = () => { try { const a = JSON.parse(localStorage.getItem(SEEN)); return Array.isArray(a) ? new Set(a) : null; } catch { return null; } };
  const saveSeen = (ids) => { try { localStorage.setItem(SEEN, JSON.stringify(ids)); } catch {} };
  const save = (intentionalEmpty = false) => {
    try { localStorage.setItem(KEY, JSON.stringify({ ids: [...sel], intentionalEmpty: intentionalEmpty && !sel.size })); } catch {}
  };

  const ago = (iso) => {
    const m = Math.max(1, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 60) return m + "m ago";
    const h = Math.round(m / 60);
    return h < 24 ? h + "h ago" : Math.round(h / 24) + "d ago";
  };

  let busy = false;
  function setUpdated(extra) {
    $("#updated").textContent = "Updated " + ago(data.generated) + (extra ? " · " + extra : "");
  }

  // manual=true: user pressed refresh (keep their selection, report the outcome)
  function loadData(manual) {
    if (busy) return Promise.resolve();
    busy = true;
    document.body.classList.add("loading");
    $("#feed").setAttribute("aria-busy", "true");
    return fetch("data/news.json?t=" + Date.now(), { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then((d) => {
      const prev = data && data.generated;
      const prevCount = data ? data.stats.stories : 0;
      data = d;
      const valid = new Set(d.sources.filter((s) => s.ok).map((s) => s.id));
      if (!selectionInitialised) {
        const saved = load();
        const preferred = saved && (saved.ids.length || saved.intentionalEmpty) ? saved.ids : d.sources.filter((s) => s.default).map((s) => s.id);
        sel = new Set(preferred.filter((id) => valid.has(id)));
        selectionInitialised = true;
      } else sel = new Set([...sel].filter((id) => valid.has(id)));
      // a source you added since your last visit switches itself on once
      const seen = loadSeen();
      const newCustom = seen ? d.sources.filter((x) => x.custom && x.ok && !seen.has(x.id)) : [];
      if (newCustom.length) { newCustom.forEach((x) => sel.add(x.id)); save(); }
      saveSeen(d.sources.map((x) => x.id));
      render();
      if (!manual) setUpdated();
      else if (prev === d.generated) setUpdated("already the latest");
      else setUpdated(Math.max(0, d.stats.stories - prevCount) + " new");
    }).catch(() => {
      if (!data) {
        $("#updated").textContent = "Couldn't load news";
        $("#feed").innerHTML = '<section class="load-error" role="alert"><strong>News could not be loaded.</strong><span>Check your connection, then try again.</span><button id="retry" class="btn primary">Try again</button></section>';
        $("#foot").textContent = "";
      }
      else setUpdated("refresh failed, check connection");
    }).finally(() => { busy = false; document.body.classList.remove("loading"); $("#feed").setAttribute("aria-busy", "false"); });
  }
  loadData(false);

  // Re-check when you come back to the tab/app after a while
  let hiddenAt = 0;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) hiddenAt = Date.now();
    else if (data && hiddenAt && Date.now() - hiddenAt > 20 * 60 * 1000) loadData(true);
  });

  // Pick best article among selected sources; others (one per source) become "Also covered by".
  function view(only) {
    const out = [];
    for (const s of data.stories) {
      const arts = s.articles.filter((a) => sel.has(a.source) && (!only || a.source === only)).sort((a, b) => b.score - a.score);
      if (!arts.length) continue;
      out.push({ cat: s.category, rank: arts[0].score + 0.6 * (arts.length - 1), lead: arts[0], also: arts.slice(1) });
    }
    return out.sort((a, b) => b.rank - a.rank);
  }

  const HUES = { "AGI & Superintelligence": 280, "Safety & Policy": 8, "Chips & Infrastructure": 188, "Business & Funding": 150, "Models & Releases": 222, Research: 38, "Products & Tools": 330, "Society & Work": 95 };
  const hue = (c) => HUES[c] ?? 220;
  const shash = (t) => [...t].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);
  const initial = (t) => (t.replace(/^The /i, "")[0] || "?").toUpperCase();
  const name = (id) => (data.sources.find((s) => s.id === id) || {}).name || id;

  function render() {
    if (srcF && !sel.has(srcF)) srcF = null;
    const all = view(srcF);
    const counts = {};
    all.forEach((s) => (counts[s.cat] = (counts[s.cat] || 0) + 1));
    if (cat !== "All" && !counts[cat]) cat = "All";
    $("#srcCount").textContent = sel.size;
    $("#catLabel").textContent = cat;
    $("#srcLabel").textContent = srcF ? name(srcF) : "All (" + sel.size + ")";

    // Category dropdown: counts reflect the current source filter
    $("#panelCat").innerHTML = [["All", all.length], ...data.categories.filter((c) => counts[c]).map((c) => [c, counts[c]])].map(([c, n]) =>
      `<button class="row" aria-pressed="${c === cat}" data-pick-cat="${esc(c)}"><span class="ck">${c === cat ? "✓" : ""}</span><span class="t">${esc(c)}</span><span class="n">${n}</span></button>`).join("");

    // Source dropdown: counts reflect the current category
    const sc = {};
    for (const st of data.stories) {
      if (cat !== "All" && st.category !== cat) continue;
      for (const a of st.articles) if (sel.has(a.source)) sc[a.source] = (sc[a.source] || 0) + 1;
    }
    const total = Object.values(sc).length ? view(null).filter((s) => cat === "All" || s.cat === cat).length : 0;
    const mine = data.sources.filter((x) => sel.has(x.id)).sort((x, y) => (sc[y.id] || 0) - (sc[x.id] || 0) || x.name.localeCompare(y.name));
    $("#panelSrc").innerHTML =
      `<button class="row" aria-pressed="${!srcF}" data-pick-src=""><span class="ck">${!srcF ? "✓" : ""}</span><span class="t">All my sources</span><span class="n">${total}</span></button>` +
      mine.map((x) => `<button class="row ${sc[x.id] ? "" : "dim"}" aria-pressed="${srcF === x.id}" data-pick-src="${esc(x.id)}"><span class="ck">${srcF === x.id ? "✓" : ""}</span><span class="t">${esc(x.name)}</span><span class="n">${sc[x.id] || 0}</span></button>`).join("") +
      `<button class="row manage" id="manage">Add or remove sources…</button>`;

    const shown = cat === "All" ? all : all.filter((s) => s.cat === cat);
    let n = 0;
    const card = (s, hero) => {
      const l = s.lead, fresh = Date.now() - new Date(l.published) < 3 * 3600 * 1000;
      return `<article class="card${hero ? " hero" : ""}${fresh ? " fresh" : ""}" style="--h:${hue(s.cat)};--i:${Math.min(n++, 10)}">
      ${hero ? `<span class="kick">Top story · ${esc(s.cat)}</span>` : ""}
      <div class="m"><span class="av" style="background:hsl(${shash(l.source)} 60% 45%)" aria-hidden="true">${esc(initial(name(l.source)))}</span><span class="who"><span class="sn">${esc(name(l.source))}</span><span class="age">${ago(l.published)}</span></span></div>${fresh ? '<span class="new">NEW</span>' : ""}
      <h3><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.title)}</a></h3>
      ${l.snippet ? `<p>${esc(l.snippet)}</p>` : ""}
      ${s.also.length ? `<div class="also"><span class="lbl">Also:</span>${s.also.map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(name(a.source))}</a>`).join("")}</div>` : ""}
    </article>`;
    };
    let html = "";
    if (cat === "All") {
      const [top, ...rest] = shown;
      if (top) html += card(top, true);
      for (const c of data.categories) {
        const g = rest.filter((s) => s.cat === c);
        if (g.length) html += `<h2 class="sect" style="--h:${hue(c)}">${esc(c)}<span class="n">${g.length}</span></h2>` + g.map((s) => card(s)).join("");
      }
    } else html = shown.map((s) => card(s)).join("");
    $("#feed").innerHTML = html;
    $("#empty").textContent = "No stories match these filters. Try another category or source.";
    $("#empty").hidden = shown.length > 0;
    const st = data.stats;
    $("#foot").textContent = `Showing ${shown.length} ${shown.length === 1 ? "story" : "stories"} from ${sel.size} ${sel.size === 1 ? "source" : "sources"} · ${st.stories} stories considered · ${st.paywalled_dropped} paywalled items excluded · last ${data.window_hours}h`;
  }

  function renderPicker() {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const hay = (s) => (s.name + " " + s.type + " " + s.id + " " + (s.site || "")).toLowerCase();
    const list = data.sources.filter((s) => words.every((w) => hay(s).includes(w)));
    const groups = {};
    list.forEach((s) => (groups[s.type] = groups[s.type] || []).push(s));
    const order = Object.keys(groups).sort((a, b) => (a === "Custom") - (b === "Custom") || a.localeCompare(b));
    $("#srcList").innerHTML = list.length ? order.map((t) =>
      `<div class="srcgrp">${esc(t)}</div>` + groups[t].map((s) =>
        `<label class="src ${s.ok ? "" : "off"}"><input type="checkbox" value="${esc(s.id)}" ${draftSel.has(s.id) ? "checked" : ""} ${s.ok ? "" : "disabled"}><span>${esc(s.name)}</span><em>${s.ok ? s.items + (s.items === 1 ? " item" : " items") : "unavailable"}</em></label>`).join("")).join("")
      : `<p class="nomatch">No match in the catalog for “${esc(q)}”.</p>`;
    const term = q.trim();
    const add = $("#addNew");
    add.hidden = $("#addHelp").hidden = term.length < 2;
    if (term.length >= 2) {
      add.textContent = (list.length ? "Not listed? " : "") + "Add “" + term + "” as a new source";
      add.href = "https://github.com/" + data.repo + "/issues/new?title=" + encodeURIComponent("Add source: " + term) +
        "&body=" + encodeURIComponent("Created from the dashboard. Just press “Submit new issue”. An automatic job will find the feed, check it is free to read, and add it (or list matches to choose with /add 1).");
    }
  }
  const setPicker = (ids) => { draftSel = new Set(ids); renderPicker(); };

  function openSheet() {
    lastFocus = document.activeElement;
    draftSel = new Set(sel);
    q = "";
    $("#srcSearch").value = "";
    renderPicker();
    $("#sheet").hidden = false;
    $("#srcSearch").focus();
  }
  function closeSheet() {
    $("#sheet").hidden = true;
    draftSel = null;
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
    lastFocus = null;
  }

  // pointer glow + gentle tilt on desktop (not touch, not reduced-motion)
  const fine = matchMedia("(hover:hover) and (pointer:fine)").matches && !matchMedia("(prefers-reduced-motion:reduce)").matches;
  if (fine) {
    let raf = 0;
    $("#feed").addEventListener("pointermove", (e) => {
      const c = e.target.closest(".card:not(.sk)");
      if (!c || raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const r = c.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        c.style.setProperty("--mx", x * 100 + "%"); c.style.setProperty("--my", y * 100 + "%");
        c.style.setProperty("--ry", (x - .5) * 5 + "deg"); c.style.setProperty("--rx", (.5 - y) * 4 + "deg");
      });
    });
    $("#feed").addEventListener("pointerout", (e) => {
      const c = e.target.closest(".card");
      if (c && !c.contains(e.relatedTarget)) { c.style.removeProperty("--rx"); c.style.removeProperty("--ry"); }
    });
  }

  // dropdown panels: one open at a time; click outside or Esc closes
  function closePanels() {
    ["Cat", "Src"].forEach((k) => { $("#panel" + k).hidden = true; $("#drop" + k).setAttribute("aria-expanded", "false"); });
  }
  function togglePanel(k) {
    const open = $("#panel" + k).hidden;
    closePanels();
    if (open) { $("#panel" + k).hidden = false; $("#drop" + k).setAttribute("aria-expanded", "true"); }
  }
  document.addEventListener("click", (e) => { if (!e.target.closest(".drops,.panel")) closePanels(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!$("#sheet").hidden) closeSheet();
      else closePanels();
      return;
    }
    if (e.key === "Tab" && !$("#sheet").hidden) {
      const focusable = $$("#sheet button, #sheet input, #sheet a[href]").filter((el) => !el.disabled && el.offsetParent !== null);
      const first = focusable[0], last = focusable.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-pick-cat],[data-pick-src],#dropCat,#dropSrc,#manage,[data-close],#refresh,#retry,#openPicker,#selAll,#selNone,#selDefault,#saveSrc");
    if (!t) return;
    if (t.id === "refresh" || t.id === "retry") { loadData(true); return; }
    if (!data) return;
    if ("pickCat" in t.dataset) { cat = t.dataset.pickCat; closePanels(); render(); scrollTo({ top: 0 }); }
    else if ("pickSrc" in t.dataset) { srcF = t.dataset.pickSrc || null; closePanels(); render(); scrollTo({ top: 0 }); }
    else if (t.id === "dropCat" || t.id === "dropSrc") togglePanel(t.id === "dropCat" ? "Cat" : "Src");
    else if (t.id === "manage") { closePanels(); openSheet(); }
    else if (t.id === "openPicker") openSheet();
    else if ("close" in t.dataset) closeSheet();
    else if (t.id === "saveSrc") { sel = new Set(draftSel); save(true); render(); closeSheet(); }
    else if (t.id === "selAll") setPicker(data.sources.filter((s) => s.ok).map((s) => s.id));
    else if (t.id === "selNone") setPicker([]);
    else if (t.id === "selDefault") setPicker(data.sources.filter((s) => s.default && s.ok).map((s) => s.id));
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "srcSearch" && data) { q = e.target.value; renderPicker(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("#srcList input")) {
      e.target.checked ? draftSel.add(e.target.value) : draftSel.delete(e.target.value);
    }
  });

  document.addEventListener("scroll", () => document.body.classList.toggle("scrolled", scrollY > 24), { passive: true });
})();
