(() => {
  const KEY = "dailyAInews.sources.v1";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let data, sel = new Set(), cat = "All", q = "", srcF = null;
  let selectionInitialised = false, draftSel = null, lastFocus = null;
  let openS = null, readerFocus = null, closing = false;

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
  const SAVED = "dailyAInews.saved.v1";
  const loadSaved = () => { try { const a = JSON.parse(localStorage.getItem(SAVED)); return Array.isArray(a) ? a.filter((x) => x && typeof x.id === "string" && typeof x.url === "string") : []; } catch { return []; } };
  const writeSaved = (list) => { try { localStorage.setItem(SAVED, JSON.stringify(list)); } catch {} };
  const saved = new Map(loadSaved().map((x) => [x.id, x]));
  const persist = () => writeSaved([...saved.values()]);
  const cards = new Map();   // lead URL -> story shown on that card
  let mode = "feed", n = 0;
  // Two desks: AI news, and everything else in tech. The last one you looked at is remembered.
  const DESK = "dailyAInews.desk.v1", DESK_NAME = { ai: "AI", tech: "Tech" };
  let desk = (() => { try { return localStorage.getItem(DESK) === "tech" ? "tech" : "ai"; } catch { return "ai"; } })();
  // How stories are listed: grouped by category (default) or one flat list, newest first. Remembered.
  const ORDER = "dailyAInews.order.v1";
  let order = (() => { try { return localStorage.getItem(ORDER) === "latest" ? "latest" : "category"; } catch { return "category"; } })();
  const deskOf = (st) => (st.desk === "tech" ? "tech" : "ai");   // stories from before the split are AI
  // Stories you've opened, by article URL (all sources in the story), so the greyed-out state survives refreshes.
  // A saved story's readAt is kept in step, so the Saved view's Unread/Read split agrees with the feed.
  const READ = "dailyAInews.read.v1";
  const readSet = (() => { try { const a = JSON.parse(localStorage.getItem(READ)); return new Set(Array.isArray(a) ? a : []); } catch { return new Set(); } })();
  const urlsOf = (s) => [s.lead, ...(s.also || [])].map((a) => a.url);
  const asStory = (x) => ({ cat: x.cat, desk: x.desk, lead: x, also: x.also || [] });   // saved copy -> card shape
  const isRead = (s) => urlsOf(s).some((u) => readSet.has(u) || (saved.get(u) || {}).readAt);
  function setRead(s, on) {
    if (!s) return;
    let changed = false;
    urlsOf(s).forEach((u) => {
      readSet.delete(u); if (on) readSet.add(u);
      const it = saved.get(u);
      if (it && !!it.readAt !== on) { it.readAt = on ? new Date().toISOString() : null; changed = true; }
    });
    try { localStorage.setItem(READ, JSON.stringify([...readSet].slice(-1500))); } catch {}
    if (changed) { persist(); badge(); }
    if (mode === "saved") renderSaved(); else $$(".card[data-id]").forEach(syncCard);
  }
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
      badge();
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

  // Re-check when you come back to the tab/app after a while. Paused: set AUTO_RELOAD = true to resume.
  const AUTO_RELOAD = false;
  let hiddenAt = 0;
  document.addEventListener("visibilitychange", () => {
    if (!AUTO_RELOAD) return;
    if (document.hidden) hiddenAt = Date.now();
    else if (data && hiddenAt && Date.now() - hiddenAt > 20 * 60 * 1000) loadData(true);
  });

  // Pick best article among selected sources; others (one per source) become "Also covered by".
  function view(only, d = desk) {
    const out = [];
    for (const s of data.stories) {
      if (deskOf(s) !== d) continue;
      const arts = s.articles.filter((a) => sel.has(a.source) && (!only || a.source === only)).sort((a, b) => b.score - a.score);
      if (!arts.length) continue;
      out.push({ cat: s.category, desk: deskOf(s), rank: arts[0].score + 0.6 * (arts.length - 1), lead: arts[0], also: arts.slice(1) });
    }
    return out.sort((a, b) => b.rank - a.rank);
  }

  const HUES = { "AGI & Superintelligence": 280, "Safety & Policy": 8, "Chips & Infrastructure": 188, "Business & Funding": 150, "Models & Releases": 222, Research: 38, "Products & Tools": 330, "Society & Work": 95,
    "Phones & Gadgets": 200, "Computing & Software": 230, "Security & Privacy": 0, "Business & Policy": 140, "Science & Space": 265, "Gaming & Entertainment": 310, "Cars & Energy": 100 };
  const deskCats = () => (data.desk_categories && data.desk_categories[desk]) || data.categories;
  const hue = (c) => HUES[c] ?? 220;
  const shash = (t) => [...t].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);
  const initial = (t) => (t.replace(/^The /i, "")[0] || "?").toUpperCase();
  const name = (id) => (data.sources.find((s) => s.id === id) || {}).name || id;
  const nm = (x) => x.sourceName || name(x.source);
  const avatar = (a) => `<span class="av" style="background:hsl(${shash(a.source || nm(a))} 60% 45%)" aria-hidden="true">${esc(initial(nm(a)))}</span>`;
  const cardOf = (s) => s && $$(".card[data-id]").find((el) => el.dataset.id === s.lead.url);

  // Expanded view: the tapped card grows to fill most of the window; closing it greys the card out as read.
  const day = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }); };
  const motion = () => !matchMedia("(prefers-reduced-motion:reduce)").matches;
  const fromRect = (box, el) => {
    const a = el.getBoundingClientRect(), b = box.getBoundingClientRect();
    return `translate(${a.left - b.left}px,${a.top - b.top}px) scale(${a.width / b.width},${a.height / b.height})`;
  };
  function openReader(el) {
    const s = cards.get(el.dataset.id), l = s.lead;
    const img = [l, ...s.also].map((a) => a.image).find((u) => /^https?:\/\//.test(u || ""));
    // lead's own text, unless it's a short blurb and another outlet in the story has a fuller summary
    const txt = (a) => a.summary || a.snippet || "";
    const best = [l, ...s.also].reduce((x, a) => (txt(a).length > txt(x).length ? a : x), l);
    const from = txt(l).length < 300 && txt(best).length > txt(l).length + 120 ? best : l, text = txt(from);
    $("#readerBody").innerHTML = `<span class="kick">${esc(s.cat)}</span>
      <div class="m">${avatar(l)}<span class="who"><span class="sn">${esc(nm(l))}</span><span class="age">${ago(l.published)}</span></span></div>
      ${day(l.published) ? `<p class="pub">Published <time datetime="${esc(l.published)}">${day(l.published)}</time></p>` : ""}
      <h2 id="readerTitle">${esc(l.title)}</h2>
      ${img ? `<figure class="thumb"><img src="${esc(img)}" alt="" referrerpolicy="no-referrer" decoding="async"></figure>` : ""}
      ${text ? `<p class="rtext">${esc(text)}</p>` : ""}${from !== l ? `<p class="via">Summary from ${esc(nm(from))}</p>` : ""}
      <a class="btn primary go" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">Read the full article on ${esc(nm(l))} <span aria-hidden="true">↗</span></a>
      ${s.also.length ? `<div class="ralso"><span class="lbl">Also covered by</span>${s.also.map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(nm(a))}</b>${a.title ? `<span>${esc(a.title)}</span>` : ""}</a>`).join("")}</div>` : ""}`;
    const im = $("#readerBody img");
    if (im) im.onerror = () => im.closest("figure").remove();
    openS = s;
    readerFocus = el.querySelector("h3 a");
    closePanels();
    $("#reader").style.setProperty("--h", hue(s.cat));
    $("#reader").hidden = false;
    document.documentElement.classList.add("reading");
    const box = $(".reader-card");
    box.scrollTop = 0;
    if (motion()) {
      const ease = { duration: 340, easing: "cubic-bezier(.2,.8,.2,1)" };
      box.animate([{ transform: fromRect(box, el), transformOrigin: "0 0", borderRadius: "20px" }, { transform: "none", transformOrigin: "0 0" }], ease);
      $("#readerBody").animate([{ opacity: 0 }, { opacity: 0, offset: .45 }, { opacity: 1 }], ease);
      $(".reader-bg").animate([{ opacity: 0 }, { opacity: 1 }], ease);
    }
    box.focus({ preventScroll: true });
  }
  function closeReader() {
    if ($("#reader").hidden || closing) return;
    const s = openS, el = cardOf(s), box = $(".reader-card");
    const done = () => {
      closing = false;
      $("#reader").hidden = true;
      document.documentElement.classList.remove("reading");
      openS = null;
      if (s) setRead(s, true);
      const f = el && el.querySelector("h3 a");
      if (f) f.focus({ preventScroll: true }); else if (readerFocus && document.contains(readerFocus)) readerFocus.focus({ preventScroll: true });
      readerFocus = null;
    };
    const r = el && el.getBoundingClientRect();
    if (!motion() || !r || r.bottom < 0 || r.top > innerHeight) return done();
    closing = true;
    const ease = { duration: 260, easing: "cubic-bezier(.4,0,.2,1)" };
    $("#readerBody").animate([{ opacity: 1 }, { opacity: 0, offset: .4 }, { opacity: 0 }], ease);
    $(".reader-bg").animate([{ opacity: 1 }, { opacity: 0 }], ease);
    box.animate([{ transform: "none", transformOrigin: "0 0" }, { transform: fromRect(box, el), transformOrigin: "0 0", borderRadius: "20px", opacity: .7 }], ease).onfinish = done;
  }

  const BM = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" stroke-width="2" stroke-linejoin="round"/></svg>';
  const toSaved = (s) => ({ id: s.lead.url, url: s.lead.url, title: s.lead.title, snippet: s.lead.snippet || "", summary: s.lead.summary || "", image: s.lead.image || "", source: s.lead.source, sourceName: nm(s.lead), cat: s.cat, desk: s.desk || "ai", published: s.lead.published, savedAt: new Date().toISOString(), readAt: isRead(s) ? new Date().toISOString() : null,
    also: s.also.map((a) => ({ url: a.url, sourceName: nm(a), title: a.title || "", summary: a.summary || a.snippet || "", image: a.image || "" })) });
  const badge = () => {
    const u = [...saved.values()].filter((x) => !isRead(asStory(x))).length;
    $("#savedCount").textContent = u; $("#savedCount").hidden = !u;
  };
  // bring one card's bookmark and greyed-out read state in line with storage
  function syncCard(el) {
    const it = saved.get(el.dataset.id), b = el.querySelector(".bm");
    b.setAttribute("aria-pressed", !!it); b.setAttribute("aria-label", it ? "Remove from saved" : "Save for later");
    el.classList.toggle("read", isRead(cards.get(el.dataset.id)));
  }
  const card = (s, hero, sv) => {
    const l = s.lead, it = saved.get(l.url), fresh = !sv && Date.now() - new Date(l.published) < 3 * 3600 * 1000, read = isRead(s);
    cards.set(l.url, s);
    return `<article class="card${hero ? " hero" : ""}${fresh ? " fresh" : ""}${read ? " read" : ""}" data-id="${esc(l.url)}" style="--h:${hue(s.cat)};--i:${Math.min(n++, 10)}">
      ${hero ? `<span class="kick">Top story · ${esc(s.cat)}</span>` : ""}
      <div class="m">${avatar(l)}<span class="who"><span class="sn">${esc(nm(l))}</span><span class="age">${sv ? "saved " + ago(it.savedAt) : ago(l.published)}${sv ? `<span class="dk">${DESK_NAME[deskOf(s)]}</span>` : ""}${fresh ? '<span class="new">NEW</span>' : ""}</span><button class="rd" data-unread aria-label="Read. Mark as unread" title="Mark as unread">✓ Read</button></span></div>
      <button class="bm" data-save="${esc(l.url)}" aria-pressed="${!!it}" aria-label="${it ? "Remove from saved" : "Save for later"}">${BM}</button>
      <h3><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.title)}</a></h3>
      ${l.snippet ? `<p>${esc(l.snippet)}</p>` : ""}
      ${s.also.length ? `<div class="also"><span class="lbl">Also:</span>${s.also.map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(nm(a))}</a>`).join("")}</div>` : ""}
    </article>`;
  };

  function renderSaved() {
    n = 0; cards.clear();
    const all = [...saved.values()].sort((a, b) => String(b.savedAt).localeCompare(String(a.savedAt)));
    const unread = all.filter((x) => !isRead(asStory(x))), read = all.filter((x) => isRead(asStory(x)));
    const sect = (t, h, l) => l.length ? `<h2 class="sect" style="--h:${h}">${t} (${l.length})</h2>` + l.map((x) => card(asStory(x), false, true)).join("") : "";
    $("#feed").innerHTML = (read.length ? '<div class="tools"><button id="clearRead" class="btn small">Clear read</button></div>' : "") + sect("Unread", 222, unread) + sect("Read", 150, read);
    $("#empty").textContent = "Nothing saved yet. Tap the bookmark on any story.";
    $("#empty").hidden = all.length > 0;
    $("#foot").textContent = `${all.length} saved · ${unread.length} unread`;
  }

  badge();

  function render() {
    if (srcF && !sel.has(srcF)) srcF = null;
    const all = view(srcF);
    const counts = {};
    all.forEach((s) => (counts[s.cat] = (counts[s.cat] || 0) + 1));
    if (cat !== "All" && !counts[cat]) cat = "All";
    $("#srcCount").textContent = sel.size;
    $("#catLabel").textContent = cat;
    $("#srcLabel").textContent = srcF ? name(srcF) : "All (" + sel.size + ")";
    $(".drops").hidden = $(".desks").hidden = $(".orders").hidden = mode === "saved";
    $$(".ord").forEach((b) => b.setAttribute("aria-pressed", b.dataset.order === order));
    document.body.dataset.desk = mode === "saved" ? "" : desk;
    $$(".desk").forEach((b) => {
      b.setAttribute("aria-pressed", b.dataset.desk === desk);
      b.querySelector(".n").textContent = view(srcF, b.dataset.desk).length;
    });
    if (mode === "saved") { closePanels(); return renderSaved(); }
    n = 0; cards.clear();

    // Category dropdown: counts reflect the current source filter
    $("#panelCat").innerHTML = [["All", all.length], ...deskCats().filter((c) => counts[c]).map((c) => [c, counts[c]])].map(([c, n]) =>
      `<button class="row" aria-pressed="${c === cat}" data-pick-cat="${esc(c)}"><span class="ck">${c === cat ? "✓" : ""}</span><span class="t">${esc(c)}</span><span class="n">${n}</span></button>`).join("");

    // Source dropdown: counts reflect the current category
    const sc = {};
    for (const st of data.stories) {
      if (deskOf(st) !== desk || (cat !== "All" && st.category !== cat)) continue;
      for (const a of st.articles) if (sel.has(a.source)) sc[a.source] = (sc[a.source] || 0) + 1;
    }
    const total = Object.values(sc).length ? view(null).filter((s) => cat === "All" || s.cat === cat).length : 0;
    const mine = data.sources.filter((x) => sel.has(x.id)).sort((x, y) => (sc[y.id] || 0) - (sc[x.id] || 0) || x.name.localeCompare(y.name));
    $("#panelSrc").innerHTML =
      `<button class="row" aria-pressed="${!srcF}" data-pick-src=""><span class="ck">${!srcF ? "✓" : ""}</span><span class="t">All my sources</span><span class="n">${total}</span></button>` +
      mine.map((x) => `<button class="row ${sc[x.id] ? "" : "dim"}" aria-pressed="${srcF === x.id}" data-pick-src="${esc(x.id)}"><span class="ck">${srcF === x.id ? "✓" : ""}</span><span class="t">${esc(x.name)}</span><span class="n">${sc[x.id] || 0}</span></button>`).join("") +
      `<button class="row manage" id="manage">Add or remove sources…</button>`;

    const shown = cat === "All" ? all : all.filter((s) => s.cat === cat);
    let html = "";
    if (order === "latest") {
      html = shown.slice().sort((a, b) => new Date(b.lead.published) - new Date(a.lead.published)).map((s) => card(s)).join("");
    } else if (cat === "All") {
      const [top, ...rest] = shown;
      if (top) html += card(top, true);
      for (const c of deskCats()) {
        const g = rest.filter((s) => s.cat === c);
        if (g.length) html += `<h2 class="sect" style="--h:${hue(c)}">${esc(c)}<span class="n">${g.length}</span></h2>` + g.map((s) => card(s)).join("");
      }
    } else html = shown.map((s) => card(s)).join("");
    $("#feed").innerHTML = html;
    $("#empty").textContent = `No ${DESK_NAME[desk]} stories match these filters. Try another category or source.`;
    $("#empty").hidden = shown.length > 0;
    const st = data.stats;
    $("#foot").textContent = `Showing ${shown.length} ${DESK_NAME[desk]} ${shown.length === 1 ? "story" : "stories"} from ${sel.size} ${sel.size === 1 ? "source" : "sources"} · ${st.stories} stories considered · ${st.paywalled_dropped} paywalled items excluded · last ${data.window_hours}h`;
  }

  function renderPicker() {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const hay = (s) => (s.name + " " + s.type + " " + s.id + " " + (s.site || "")).toLowerCase();
    const list = data.sources.filter((s) => words.every((w) => hay(s).includes(w)));
    const groups = {};
    const grp = (s) => (s.type === "Custom" ? "Custom" : (s.desk === "ai" ? "AI · " : "Tech · ") + s.type);
    list.forEach((s) => (groups[grp(s)] = groups[grp(s)] || []).push(s));
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
      if (!$("#reader").hidden) closeReader();
      else if (!$("#sheet").hidden) closeSheet();
      else closePanels();
      return;
    }
    const trap = !$("#reader").hidden ? "#reader" : !$("#sheet").hidden ? "#sheet" : null;
    if (e.key === "Tab" && trap) {
      const focusable = $$(`${trap} button, ${trap} input, ${trap} a[href]`).filter((el) => !el.disabled && el.offsetParent !== null);
      const first = focusable[0], last = focusable.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-close-reader]")) { closeReader(); return; }
    // tapping a story opens the expanded view; ctrl/cmd/shift/middle-click still open the page directly
    const link = e.target.closest(".card[data-id] h3 a");
    if (link && !(e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button)) { e.preventDefault(); openReader(link.closest(".card")); return; }
    const a = e.target.closest(".card a");   // headline (modified click) or an "Also" outlet: opens the page, counts as read
    if (a) { setRead(cards.get(a.closest(".card").dataset.id), true); return; }
    const t = e.target.closest(".desk,[data-save],[data-unread],#openSaved,#clearRead,[data-pick-cat],[data-pick-src],#dropCat,#dropSrc,#manage,.ord,[data-close],#refresh,#retry,#openPicker,#selAll,#selNone,#selDefault,#saveSrc");
    if (!t) return;
    if (t.id === "refresh" || t.id === "retry") { loadData(true); return; }
    if (!data) return;
    if (t.classList.contains("ord")) {
      if (t.dataset.order === order) return;
      order = t.dataset.order;
      try { localStorage.setItem(ORDER, order); } catch {}
      render(); scrollTo({ top: 0 });
    }
    else if (t.classList.contains("desk")) {
      if (t.dataset.desk === desk) return;
      desk = t.dataset.desk;
      try { localStorage.setItem(DESK, desk); } catch {}
      cat = "All";
      if (srcF && !view(srcF).length) srcF = null;   // keep a source filter only if it has stories on this desk
      closePanels(); render(); scrollTo({ top: 0 });
    }
    else if ("save" in t.dataset) {
      const id = t.dataset.save, s = cards.get(id);
      if (saved.has(id)) saved.delete(id); else if (s) saved.set(id, toSaved(s));
      persist(); badge(); syncCard(t.closest(".card"));
      if (saved.has(id)) { t.classList.remove("pop"); void t.offsetWidth; t.classList.add("pop"); }
    }
    else if ("unread" in t.dataset) setRead(cards.get(t.closest(".card").dataset.id), false);
    else if (t.id === "openSaved") {
      mode = mode === "feed" ? "saved" : "feed";
      t.setAttribute("aria-pressed", mode === "saved"); t.firstChild.textContent = mode === "saved" ? "← Feed " : "Saved ";
      render(); scrollTo({ top: 0 });
    }
    else if (t.id === "clearRead") {
      const r = [...saved.values()].filter((x) => isRead(asStory(x)));
      if (r.length && confirm(`Remove ${r.length} read ${r.length === 1 ? "story" : "stories"}?`)) { r.forEach((x) => saved.delete(x.id)); persist(); badge(); renderSaved(); }
    }
    else if ("pickCat" in t.dataset) { cat = t.dataset.pickCat; closePanels(); render(); scrollTo({ top: 0 }); }
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
