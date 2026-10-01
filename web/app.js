(() => {
  const KEY = "dailyAInews.sources.v1";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let data, sel = new Set(), cat = "All", q = "", srcF = null;

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } };
  const SEEN = "dailyAInews.seen.v1";
  const loadSeen = () => { try { const a = JSON.parse(localStorage.getItem(SEEN)); return Array.isArray(a) ? new Set(a) : null; } catch { return null; } };
  const saveSeen = (ids) => { try { localStorage.setItem(SEEN, JSON.stringify(ids)); } catch {} };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...sel])); } catch {} };

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
    return fetch("data/news.json?t=" + Date.now(), { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then((d) => {
      const prev = data && data.generated;
      const prevCount = data ? data.stats.stories : 0;
      data = d;
      const valid = new Set(d.sources.map((s) => s.id));
      if (!sel.size) {
        const saved = load();
        sel = new Set((saved || d.sources.filter((s) => s.default).map((s) => s.id)).filter((id) => valid.has(id)));
        if (!sel.size) sel = new Set(d.sources.filter((s) => s.default).map((s) => s.id));
      } else sel = new Set([...sel].filter((id) => valid.has(id)));
      // a source you added since your last visit switches itself on once
      const seen = loadSeen();
      if (seen) { d.sources.filter((x) => x.custom && !seen.has(x.id)).forEach((x) => sel.add(x.id)); save(); }
      saveSeen(d.sources.map((x) => x.id));
      render();
      if (!manual) setUpdated();
      else if (prev === d.generated) setUpdated("already the latest");
      else setUpdated(Math.max(0, d.stats.stories - prevCount) + " new");
    }).catch(() => {
      if (!data) $("#updated").textContent = "Couldn't load news";
      else setUpdated("refresh failed, check connection");
    }).finally(() => { busy = false; document.body.classList.remove("loading"); });
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
      `<button class="row" role="option" aria-selected="${c === cat}" data-pick-cat="${esc(c)}"><span class="ck">${c === cat ? "✓" : ""}</span><span class="t">${esc(c)}</span><span class="n">${n}</span></button>`).join("");

    // Source dropdown: counts reflect the current category
    const sc = {};
    for (const st of data.stories) {
      if (cat !== "All" && st.category !== cat) continue;
      for (const a of st.articles) if (sel.has(a.source)) sc[a.source] = (sc[a.source] || 0) + 1;
    }
    const total = Object.values(sc).length ? view(null).filter((s) => cat === "All" || s.cat === cat).length : 0;
    const mine = data.sources.filter((x) => sel.has(x.id)).sort((x, y) => (sc[y.id] || 0) - (sc[x.id] || 0) || x.name.localeCompare(y.name));
    $("#panelSrc").innerHTML =
      `<button class="row" role="option" aria-selected="${!srcF}" data-pick-src=""><span class="ck">${!srcF ? "✓" : ""}</span><span class="t">All my sources</span><span class="n">${total}</span></button>` +
      mine.map((x) => `<button class="row ${sc[x.id] ? "" : "dim"}" role="option" aria-selected="${srcF === x.id}" data-pick-src="${esc(x.id)}"><span class="ck">${srcF === x.id ? "✓" : ""}</span><span class="t">${esc(x.name)}</span><span class="n">${sc[x.id] || 0}</span></button>`).join("") +
      `<button class="row manage" id="manage">Add or remove sources…</button>`;

    const shown = cat === "All" ? all : all.filter((s) => s.cat === cat);
    const card = (s) => `<article class="card">
      <div class="meta"><b>${esc(name(s.lead.source))}</b><span>·</span><span>${ago(s.lead.published)}</span></div>
      <h3><a href="${esc(s.lead.url)}" target="_blank" rel="noopener noreferrer">${esc(s.lead.title)}</a></h3>
      ${s.lead.snippet ? `<p>${esc(s.lead.snippet)}</p>` : ""}
      ${s.also.length ? `<div class="also">Also: ${s.also.map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(name(a.source))}</a>`).join("")}</div>` : ""}
    </article>`;
    let html = "";
    if (cat === "All") {
      for (const c of data.categories) {
        const g = shown.filter((s) => s.cat === c);
        if (g.length) html += `<h2 class="sect">${esc(c)}</h2>` + g.map(card).join("");
      }
    } else html = shown.map(card).join("");
    $("#feed").innerHTML = html;
    $("#empty").hidden = shown.length > 0;
    const st = data.stats;
    $("#foot").textContent = `${st.stories} stories · ${st.paywalled_dropped} paywalled items excluded · last ${data.window_hours}h`;
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
        `<label class="src ${s.ok ? "" : "off"}"><input type="checkbox" value="${esc(s.id)}" ${sel.has(s.id) ? "checked" : ""}><span>${esc(s.name)}</span><em>${s.ok ? s.items + (s.items === 1 ? " item" : " items") : "unavailable"}</em></label>`).join("")).join("")
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
  const setAll = (ids) => { sel = new Set(ids); renderPicker(); render(); save(); };

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
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanels(); });

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-pick-cat],[data-pick-src],#dropCat,#dropSrc,#manage,[data-close],#refresh,#openPicker,#selAll,#selNone,#selDefault,#saveSrc");
    if (!t) return;
    if (t.id === "refresh") { loadData(true); return; }
    if (!data) return;
    if ("pickCat" in t.dataset) { cat = t.dataset.pickCat; closePanels(); render(); scrollTo({ top: 0 }); }
    else if ("pickSrc" in t.dataset) { srcF = t.dataset.pickSrc || null; closePanels(); render(); scrollTo({ top: 0 }); }
    else if (t.id === "dropCat" || t.id === "dropSrc") togglePanel(t.id === "dropCat" ? "Cat" : "Src");
    else if (t.id === "manage") { closePanels(); q = ""; $("#srcSearch").value = ""; renderPicker(); $("#sheet").hidden = false; }
    else if (t.id === "openPicker") { q = ""; $("#srcSearch").value = ""; renderPicker(); $("#sheet").hidden = false; }
    else if ("close" in t.dataset || t.id === "saveSrc") { if (t.id === "saveSrc") save(); $("#sheet").hidden = true; }
    else if (t.id === "selAll") setAll(data.sources.map((s) => s.id));
    else if (t.id === "selNone") setAll([]);
    else if (t.id === "selDefault") setAll(data.sources.filter((s) => s.default).map((s) => s.id));
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "srcSearch" && data) { q = e.target.value; renderPicker(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("#srcList input")) {
      e.target.checked ? sel.add(e.target.value) : sel.delete(e.target.value);
      save(); render();
    }
  });
})();
