(() => {
  const KEY = "dailyAInews.sources.v1";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let data, sel = new Set(), cat = "All", q = "";

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
  function view() {
    const out = [];
    for (const s of data.stories) {
      const arts = s.articles.filter((a) => sel.has(a.source)).sort((a, b) => b.score - a.score);
      if (!arts.length) continue;
      out.push({ cat: s.category, rank: arts[0].score + 0.6 * (arts.length - 1), lead: arts[0], also: arts.slice(1) });
    }
    return out.sort((a, b) => b.rank - a.rank);
  }

  const name = (id) => (data.sources.find((s) => s.id === id) || {}).name || id;

  function render() {
    const all = view();
    const counts = {};
    all.forEach((s) => (counts[s.cat] = (counts[s.cat] || 0) + 1));
    const cats = ["All", ...data.categories.filter((c) => counts[c])];
    if (!cats.includes(cat)) cat = "All";
    $("#cats").innerHTML = cats.map((c) => `<button class="chip" aria-pressed="${c === cat}" data-cat="${esc(c)}">${esc(c)}<small>${c === "All" ? all.length : counts[c]}</small></button>`).join("");
    $("#srcCount").textContent = sel.size;

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

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-cat],[data-close],#refresh,#openPicker,#selAll,#selNone,#selDefault,#saveSrc");
    if (!t) return;
    if (t.id === "refresh") { loadData(true); return; }
    if (!data) return;
    if (t.dataset.cat) { cat = t.dataset.cat; render(); scrollTo({ top: 0 }); }
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
