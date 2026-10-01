(() => {
  const KEY = "dailyAInews.sources.v1";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let data, sel = new Set(), cat = "All";

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...sel])); } catch {} };

  const ago = (iso) => {
    const m = Math.max(1, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 60) return m + "m ago";
    const h = Math.round(m / 60);
    return h < 24 ? h + "h ago" : Math.round(h / 24) + "d ago";
  };

  fetch("data/news.json", { cache: "no-cache" }).then((r) => r.json()).then((d) => {
    data = d;
    const saved = load();
    const valid = new Set(d.sources.map((s) => s.id));
    sel = new Set((saved || d.sources.filter((s) => s.default).map((s) => s.id)).filter((id) => valid.has(id)));
    if (!sel.size) sel = new Set(d.sources.filter((s) => s.default).map((s) => s.id));
    $("#updated").textContent = "Updated " + ago(d.generated);
    render();
  }).catch(() => { $("#updated").textContent = "Couldn't load news"; });

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
    const groups = {};
    data.sources.forEach((s) => (groups[s.type] = groups[s.type] || []).push(s));
    $("#srcList").innerHTML = Object.entries(groups).map(([t, list]) =>
      `<div class="srcgrp">${esc(t)}</div>` + list.map((s) =>
        `<label class="src ${s.ok ? "" : "off"}"><input type="checkbox" value="${esc(s.id)}" ${sel.has(s.id) ? "checked" : ""}><span>${esc(s.name)}</span><em>${s.ok ? s.items + (s.items === 1 ? " item" : " items") : "unavailable"}</em></label>`).join("")).join("");
  }
  const setAll = (ids) => { sel = new Set(ids); renderPicker(); render(); save(); };

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-cat],[data-close],#openPicker,#selAll,#selNone,#selDefault,#saveSrc");
    if (!t || !data) return;
    if (t.dataset.cat) { cat = t.dataset.cat; render(); scrollTo({ top: 0 }); }
    else if (t.id === "openPicker") { renderPicker(); $("#sheet").hidden = false; }
    else if ("close" in t.dataset || t.id === "saveSrc") { if (t.id === "saveSrc") save(); $("#sheet").hidden = true; }
    else if (t.id === "selAll") setAll(data.sources.map((s) => s.id));
    else if (t.id === "selNone") setAll([]);
    else if (t.id === "selDefault") setAll(data.sources.filter((s) => s.default).map((s) => s.id));
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches("#srcList input")) {
      e.target.checked ? sel.add(e.target.value) : sel.delete(e.target.value);
      save(); render();
    }
  });
})();
