#!/usr/bin/env python3
"""Find, verify and add a user-requested news source.  Driven by
.github/workflows/add-source.yml (GitHub issue titled "Add source: <name or URL>").

    add_source.py find      # reads ISSUE_TITLE; adds the source or posts candidates
    add_source.py choose    # reads COMMENT_BODY ("/add 2"); adds that candidate

Only free-to-read feeds are accepted: the feed must parse, be recent, not be on
the paywall block list, and sampled articles must pass the paywall check.
Standard library only.  Writes sources.json; comments on the issue via the API.
"""
import difflib, ipaddress, json, os, re, socket, sys
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

ROOT = fn.ROOT
SOURCES = ROOT / "sources.json"
MARKER = "<!--candidates:"
FEED_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/feeds/all", "/index.xml"]
LINK_RE = re.compile(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', re.I)
MAX_CANDIDATES = 6


# ---------------------------------------------------------------- helpers
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def looks_like_url(q):
    return bool(re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(:\d+)?(/\S*)?$", q.strip())) and " " not in q.strip()


def public_host(url):
    """Refuse non-http(s) and private/loopback targets (we fetch user-supplied URLs)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    if os.environ.get("ALLOW_LOCAL") == "1":
        return True
    try:
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except OSError:
        return False
    return True


def stem(url):
    h = fn.host_of(url)
    return h.rsplit(".", 1)[0].split(".")[-1]


def probe(url):
    """True if url really serves a feed (single quick request)."""
    try:
        _, raw, _ = fn.http_get(url, timeout=10, max_bytes=300_000, retries=0)
        return fn.looks_like_feed(raw)
    except Exception:
        return False


def discover_from_site(site):
    """Feed URLs for a site (or [site] if it already is a feed). Empty if the site is unreachable."""
    if not public_host(site):
        return []
    try:
        fn.fetch_feed(site)
        return [site]
    except Exception:
        pass
    try:
        _, body, cs = fn.http_get(site, max_bytes=400_000)
        html = fn.decode(body, cs)
    except Exception:
        return []   # unreachable: don't invent feed addresses
    found = []
    for tag in LINK_RE.findall(html):
        m = re.search(r'href=["\']([^"\']+)', tag)
        if m:
            found.append(urljoin(site, unescape(m.group(1))))
    if not found:   # no <link> tags: keep only well-known paths that really return a feed
        found = [u for u in (urljoin(site, p) for p in FEED_PATHS) if probe(u)]
    out = []
    for f in found:
        if f not in out and public_host(f):
            out.append(f)
    return out[:4]


def feedly_search(q):
    try:
        _, b, cs = fn.http_get("https://cloud.feedly.com/v3/search/feeds?count=8&query=" + quote(q))
        data = json.loads(fn.decode(b, cs))
    except Exception:
        return []
    res = []
    for r in data.get("results", []):
        fid = r.get("feedId", "")
        if fid.startswith("feed/"):
            res.append({"name": r.get("title") or stem(fid[5:]), "feed": fid[5:], "site": r.get("website") or ""})
    return res


def site_name(site):
    """Human name for a site: og:site_name, else <title> up to the first separator, else the domain."""
    try:
        _, body, cs = fn.http_get(site, timeout=10, max_bytes=200_000, retries=0)
        html = fn.decode(body, cs)
        m = re.search(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if m and m.group(1).strip():
            return unescape(m.group(1)).strip()
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            t = unescape(re.sub(r"\s+", " ", m.group(1))).strip()
            t = re.split(r"\s[-|–—:]\s", t)[0].strip()
            if 2 <= len(t) <= 40:
                return t
    except Exception:
        pass
    h = fn.host_of(site)
    return (h.split(".")[0] if h.count(".") else h).replace("-", " ").title()


def candidates_for(query):
    q = query.strip()
    cands = []
    if looks_like_url(q):
        site = q if q.startswith("http") else "https://" + q
        for f in discover_from_site(site):
            cands.append({"name": site_name(site), "feed": f, "site": site, "score": 1.0, "via": "address"})
    else:
        for r in feedly_search(q):
            sc = max(difflib.SequenceMatcher(None, norm(q), norm(r["name"])).ratio(),
                     difflib.SequenceMatcher(None, norm(q), norm(stem(r["feed"]))).ratio())
            cands.append({**r, "score": round(sc, 2), "via": "search"})
        slug = norm(q)
        if slug:
            for tld in ("com", "net", "org", "io", "ai"):
                site = f"https://www.{slug}.{tld}"
                feeds = discover_from_site(site)
                for f in feeds:
                    cands.append({"name": q, "feed": f, "site": site, "score": 0.9, "via": "guess"})
                if feeds:
                    break
    seen, uniq = set(), []
    for c in sorted(cands, key=lambda c: -c["score"]):
        k = re.sub(r"^https?://(www\.)?|/+$", "", c["feed"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq[:MAX_CANDIDATES]


def verify(c, blocked, now=None):
    """Return (ok, reason, info)."""
    now = now or datetime.now(timezone.utc)
    if fn.is_blocked(c["feed"], blocked) or (c.get("site") and fn.is_blocked(c["site"], blocked)):
        return False, "on the paywalled-sites block list", {}
    try:
        raw = fn.fetch_feed(c["feed"])
        items = fn.parse_feed(raw)[:20]
    except Exception as e:
        return False, f"couldn't read the feed ({type(e).__name__})", {}
    if not items:
        return False, "feed has no articles", {}
    dates = [i["published"] for i in items if i["published"]]
    if dates and now - max(dates) > timedelta(days=60):
        return False, "feed hasn't been updated in 60+ days", {}
    if any(fn.is_blocked(i["url"], blocked) for i in items[:5]):
        return False, "links point at paywalled sites", {}
    idx = sorted({0, len(items) // 2, len(items) - 1})
    bad = [items[i]["url"] for i in idx if not fn.check_article(items[i]["url"], blocked, None)[0]]
    if bad:
        return False, f"{len(bad)} of {len(idx)} sample articles look paywalled", {}
    ai = sum(1 for i in items if fn.AI_RE.search(f'{i["title"]} {fn.strip_html(i["summary"])}'))
    share = ai / len(items)
    return True, "ok", {"items": len(items), "ai_share": round(share, 2), "ai_only": share >= 0.7,
                        "newest": max(dates).date().isoformat() if dates else ""}


def find(query):
    cfg = json.loads(SOURCES.read_text())
    known = {re.sub(r"^https?://(www\.)?|/+$", "", s["feed"]): s["name"] for s in cfg["sources"]}
    ok, rejected = [], []
    for c in candidates_for(query):
        key = re.sub(r"^https?://(www\.)?|/+$", "", c["feed"])
        if key in known:
            return {"already": known[key]}
        good, reason, info = verify(c, cfg["blocked_domains"])
        (ok if good else rejected).append({**c, **info, "reason": reason})
    return {"ok": ok, "rejected": rejected}


def confident(ok):
    if not ok:
        return None
    top = ok[0]
    if len(ok) == 1 and top["score"] >= 0.6:
        return top
    if top["score"] >= 0.8 and (len(ok) == 1 or top["score"] - ok[1]["score"] >= 0.15 or top["via"] == "address"):
        return top
    return None


def add_source(c):
    text = SOURCES.read_text()
    cfg = json.loads(text)
    ids = {s["id"] for s in cfg["sources"]}
    base = norm(c["name"]) or "custom"
    sid, n = base, 2
    while sid in ids:
        sid, n = f"{base}{n}", n + 1
    entry = {"id": sid, "name": c["name"], "feed": c["feed"], "ai_only": bool(c.get("ai_only")),
             "weight": 0.9, "type": "Custom", "custom": True, "site": c.get("site", "")}
    tail = '\n  ],\n  "blocked_domains"'
    assert tail in text, "unexpected sources.json layout"
    text = text.replace(tail, ",\n    " + json.dumps(entry, ensure_ascii=False) + tail, 1)
    text = re.sub(r'("default_sources":\s*\[)([^\]]*)(\])', lambda m: m.group(1) + m.group(2) + ', ' + json.dumps(sid) + m.group(3), text, count=1)
    json.loads(text)
    SOURCES.write_text(text)
    return entry


# ---------------------------------------------------------------- GitHub API
def api(method, path, body=None):
    req = Request("https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + path, method=method,
                  data=json.dumps(body).encode() if body is not None else None,
                  headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json", "User-Agent": "dailyAInews"})
    with urlopen(req, timeout=30) as r:
        data = r.read()
        return json.loads(data) if data else None


def comment(issue, text):
    if os.environ.get("DRY_RUN"):
        print("--- comment ---\n" + text)
        return
    api("POST", f"/issues/{issue}/comments", {"body": text})


def close(issue):
    if not os.environ.get("DRY_RUN"):
        api("PATCH", f"/issues/{issue}", {"state": "closed", "state_reason": "completed"})


def render_candidates(query, res):
    lines = [f"Here's what I found for **{query}** (all verified readable and free of paywalls):", ""]
    for i, c in enumerate(res["ok"], 1):
        lines.append(f"{i}. **{c['name']}**: {c.get('site') or c['feed']}  \n   feed `{c['feed']}`, {c['items']} recent articles, "
                     f"newest {c['newest'] or 'unknown'}, {'AI-focused (AI desk)' if c['ai_only'] else 'general tech (AI stories go to the AI desk, the rest to Tech)'}")
    lines += ["", "Reply with `/add 1` (or the number you want) and I'll add it."]
    if res["rejected"]:
        lines += ["", "<details><summary>Skipped</summary>", ""]
        lines += [f"- {c['name']} ({c['feed']}): {c['reason']}" for c in res["rejected"]]
        lines += ["", "</details>"]
    lines.append(MARKER + json.dumps(res["ok"], ensure_ascii=False).replace("--", "- -") + "-->")
    return "\n".join(lines)


def set_output(**kw):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def main(mode):
    issue = os.environ["ISSUE_NUMBER"]
    title = os.environ.get("ISSUE_TITLE", "")
    query = re.sub(r"^\s*add source:\s*", "", title, flags=re.I).strip()
    if mode == "find":
        if not query:
            comment(issue, "I need a name or web address after “Add source:”.")
            return
        res = find(query)
        if "already" in res:
            comment(issue, f"**{res['already']}** is already in the catalog. Open Sources and search for it.")
            close(issue)
            return
        pick = confident(res["ok"])
        if pick:
            e = add_source(pick)
            comment(issue, f"Added **{e['name']}** ({pick['feed']}). It'll appear in your Sources list in about a minute "
                           f"after the dashboard rebuilds. Closing this request.")
            close(issue)
            set_output(changed="true")
        elif res["ok"]:
            comment(issue, render_candidates(query, res))
        else:
            why = "\n".join(f"- {c['name']} ({c['feed']}): {c['reason']}" for c in res["rejected"]) or "- no feed found"
            comment(issue, f"I couldn't find a free-to-read feed for **{query}**.\n\n{why}\n\n"
                           "Try again with the site's web address (e.g. `tomshardware.com`) in a new request.")
    elif mode == "choose":
        m = re.match(r"\s*/add\s+(\d+)", os.environ.get("COMMENT_BODY", ""))
        if not m:
            return
        cands = None
        comments = api("GET", f"/issues/{issue}/comments?per_page=100") or []
        for c in reversed(comments):
            if MARKER in c["body"]:
                cands = json.loads(c["body"].split(MARKER, 1)[1].rsplit("-->", 1)[0].replace("- -", "--"))
                break
        n = int(m.group(1))
        if not cands or not 1 <= n <= len(cands):
            comment(issue, "I couldn't match that number to a candidate. Use one of the numbers listed above.")
            return
        e = add_source(cands[n - 1])
        comment(issue, f"Added **{e['name']}**. It'll appear in your Sources list in about a minute after the rebuild.")
        close(issue)
        set_output(changed="true")


if __name__ == "__main__":
    main(sys.argv[1])
