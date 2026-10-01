#!/usr/bin/env python3
"""Fetch AI news from free sources, drop paywalled items, cluster duplicates and
categorise.  Writes site/data/news.json.  Standard library only.

    python3 scripts/fetch_news.py                 # live
    python3 scripts/fetch_news.py --fixtures tests/fixtures   # offline test
"""
import argparse, html, json, math, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
# Identities tried in turn for feeds; sites differ in what they accept, so keep the first that returns real XML.
FEED_UAS = [
    "Mozilla/5.0 (compatible; dailyAInews/1.0; +https://github.com/6079smith/dailyainews)",
    UA,
    "Feedly/1.0 (+http://www.feedly.com/fetcher.html; like FeedFetcher-Google)",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# ---- relevance + categories -------------------------------------------------
AI_TERMS = [
    r"\bai\b", r"\bagi\b", r"\basi\b", r"artificial intelligence", r"superintelligen", r"\bllms?\b",
    r"machine learning", r"deep learning", r"neural", r"chatgpt", r"\bgpt", r"openai", r"anthropic",
    r"claude", r"gemini", r"deepmind", r"copilot", r"\bllama\b", r"mistral", r"\bgrok\b", r"xai\b",
    r"hugging ?face", r"nvidia", r"foundation model", r"generative", r"chatbot", r"agentic",
    r"\bagents?\b", r"transformer", r"diffusion", r"deepseek", r"robot", r"alignment",
]
AI_RE = re.compile("|".join(AI_TERMS), re.I)

CATEGORIES = [  # (name, regex) -- first strongest match wins
    ("AGI & Superintelligence", r"\bagi\b|\basi\b|superintelligen|artificial general|frontier lab|existential|singularity|recursive self"),
    ("Safety & Policy", r"safety|regulat|\blaw\b|legislat|congress|senate|\beu\b|act\b|lawsuit|sue[sd]?\b|copyright|court|ban\b|ethic|alignment|policy|government|privacy|deepfake|misinformation|security|jailbreak"),
    ("Chips & Infrastructure", r"nvidia|\bgpu|chip|data ?cent|datacent|compute|semiconductor|tsmc|\bamd\b|tpu|megawatt|gigawatt|power grid|cluster|inference cost"),
    ("Business & Funding", r"funding|raises?\b|valuation|invest|acquir|acquisition|ipo\b|revenue|billion|million|startup|layoff|earnings|partnership|deal\b|market"),
    ("Models & Releases", r"launch|releas|introduc|unveil|new model|gpt-?\d|claude|gemini|llama|mistral|grok|deepseek|benchmark|open[- ]source|open[- ]weight|version \d|\bv\d\b|announce"),
    ("Research", r"research|paper|study|scientist|discover|arxiv|breakthrough|researchers|university|dataset|reasoning|training|fine-?tun"),
    ("Products & Tools", r"app\b|feature|tool|plugin|assistant|copilot|browser|integrat|api\b|developer|agent|coding|workflow|rolls? out"),
    ("Society & Work", r"jobs?|workers?|employ|education|school|student|health|medical|artist|creative|culture|creator|workforce|society|teen|children"),
]
CAT_RES = [(n, re.compile(p, re.I)) for n, p in CATEGORIES]
DEFAULT_CAT = "Other"

STOP = set("""a an the of to in on for and or with by at from as is are was were be been it its this that
these those new says say said will can could would has have had after over into about more how why what who
you your we our their than up out not but just now amid vs via also""".split())

# ---- helpers ---------------------------------------------------------------

def strip_html(s):
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def snippet(text, limit=230):
    text = strip_html(text)
    m = re.search(r"Points:\s*(\d+).*?Comments:\s*(\d+)", text)
    if text.startswith("Article URL:") and m:   # Hacker News boilerplate
        return f"{m.group(1)} points · {m.group(2)} comments on Hacker News"
    text = re.sub(r"(The post .{0,200}appeared first on .*|Continue reading.*|Read more.*|\[…\]|\[\.\.\.\])$", "", text, flags=re.I).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    # end on a sentence if one fits reasonably
    m = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if m > limit * 0.55:
        return cut[: m + 1]
    return cut.rstrip(",;:—- ") + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def host_of(url):
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def is_blocked(url, blocked):
    h = host_of(url)
    return any(h == b or h.endswith("." + b) for b in blocked)


def http_get(url, timeout=20, max_bytes=600_000, retries=2, ua=None):
    """GET with a browser-like identity; retries 429/5xx with a short back-off."""
    req = Request(url, headers={"User-Agent": ua or UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5", "Accept-Language": "en-US,en;q=0.9"})
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as r:
                return r.status, r.read(max_bytes), r.headers.get_content_charset() or "utf-8"
        except HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                try:
                    wait = min(float(e.headers.get("Retry-After", "")), 10)
                except ValueError:
                    wait = 2 * (attempt + 1)
                time.sleep(wait)
                continue
            raise


def looks_like_feed(raw):
    head = raw.lstrip(b"\xef\xbb\xbf \r\n\t")[:600].lower()
    return head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head or b"<rdf" in head


def fetch_feed(url, max_bytes=6_000_000):
    """Try each identity in FEED_UAS; return the first response that is really a feed."""
    last = None
    for ua in FEED_UAS:
        try:
            _, raw, _ = http_get(url, max_bytes=max_bytes, ua=ua)
        except Exception as e:
            last = e
            continue
        if looks_like_feed(raw):
            return raw
        last = ValueError("response was not a feed (HTML page?)")
    raise last or ValueError("no response")


def decode(b, cs):
    try:
        return b.decode(cs, errors="replace")
    except LookupError:
        return b.decode("utf-8", errors="replace")


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_bytes):
    """Return list of dicts: title, url, summary, published (RSS 2.0 and Atom)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        # cut-off or slightly malformed feed: keep every complete item/entry
        end = max(xml_bytes.rfind(b"</item>"), xml_bytes.rfind(b"</entry>"))
        if end < 0:
            raise
        atom = xml_bytes.rfind(b"</entry>") > xml_bytes.rfind(b"</item>")
        tail = b"</entry></feed>" if atom else b"</item></channel></rss>"
        cut = xml_bytes[: end + (8 if atom else 7)]
        root = ET.fromstring(cut + (b"</feed>" if atom else b"</channel></rss>"))
    items = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        d = {"title": "", "url": "", "summary": "", "published": None}
        content = ""
        for ch in el:
            t = local(ch.tag)
            txt = (ch.text or "").strip()
            if t == "title":
                d["title"] = strip_html(txt)
            elif t == "link":
                if txt:
                    d["url"] = txt
                elif ch.get("href") and ch.get("rel", "alternate") == "alternate":
                    d["url"] = ch.get("href")
            elif t in ("description", "summary"):
                d["summary"] = txt
            elif t in ("encoded", "content"):
                content = txt
            elif t in ("pubDate", "published", "updated", "date") and not d["published"]:
                d["published"] = parse_date(txt)
        if not d["summary"]:
            d["summary"] = content
        elif content and len(strip_html(d["summary"])) < 80:
            d["summary"] = content
        if d["title"] and d["url"]:
            items.append(d)
    return items


# ---- paywall check ----------------------------------------------------------
PAYWALL_MARKERS = re.compile(
    r"\"isAccessibleForFree\"\s*:\s*(false|\"false\")|"
    r"subscribe to (continue|read)|subscribers? only|subscriber-only|"
    r"to continue reading|sign in to read|for subscribers|premium (content|article)|"
    r"\bmeteredContent|data-paywall|class=\"[^\"]*\bpaywall\b", re.I)


def check_article(url, blocked, fixtures):
    """Return (ok, meta_description). ok False => paywalled/unreadable."""
    if is_blocked(url, blocked):
        return False, ""
    if fixtures:
        return True, ""
    try:
        status, body, cs = http_get(url, timeout=15, max_bytes=300_000)
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (401, 402):
            return False, ""
        return True, ""   # source is vetted-free; can't verify (bot block / timeout) -> keep
    page = decode(body, cs)
    if PAYWALL_MARKERS.search(page):
        return False, ""
    m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]*)"', page, re.I)
    return True, html.unescape(m.group(1)) if m else ""


# ---- scoring / clustering ---------------------------------------------------

def tokens(title):
    t = re.sub(r"[^a-z0-9\-\.\s]", " ", title.lower())
    def stem(w):
        w = w.strip("-.")
        if w.endswith("s") and not w.endswith("ss") and len(w) > 4:
            w = w[:-1]
        return w
    return {stem(w) for w in t.split() if w not in STOP and len(w) > 2}


def similar(a, b):
    inter = len(a & b)
    if inter < 2:
        return False
    jac = inter / len(a | b)
    ovl = inter / min(len(a), len(b))
    return jac >= 0.34 or (ovl >= 0.6 and inter >= 3)


def categorise(text):
    best, best_n = DEFAULT_CAT, 0
    for name, rx in CAT_RES:
        n = len(rx.findall(text))
        if n > best_n:
            best, best_n = name, n
    return best


def score_article(a, now):
    title_hits = len(AI_RE.findall(a["title"]))
    sum_hits = len(AI_RE.findall(a["snippet"]))
    age_h = max(0.0, (now - a["_dt"]).total_seconds() / 3600)
    recency = math.exp(-age_h / 30)
    richness = min(len(a["snippet"]), 230) / 230
    return round((1 + 1.5 * min(title_hits, 3) + 0.5 * min(sum_hits, 4) + richness) * a["_w"] * (0.35 + recency), 3)


def build(args):
    cfg = json.loads((ROOT / "sources.json").read_text())
    blocked = cfg["blocked_domains"]
    sources = {s["id"]: s for s in cfg["sources"]}
    now = datetime.now(timezone.utc)
    window = timedelta(hours=args.hours)
    fixtures = Path(args.fixtures) if args.fixtures else None

    def load(src):
        try:
            if fixtures:
                p = fixtures / f"{src['id']}.xml"
                if not p.exists():
                    return src["id"], [], "no fixture"
                raw = p.read_bytes()
            else:
                raw = fetch_feed(src["feed"])
            return src["id"], parse_feed(raw), None
        except Exception as e:
            return src["id"], [], f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(load, cfg["sources"]))

    status, candidates = {}, []
    for sid, items, err in results:
        src = sources[sid]
        kept = 0
        for it in items:
            dt = it["published"] or now
            if now - dt > window or dt > now + timedelta(hours=2):
                continue
            text = f'{it["title"]} {strip_html(it["summary"])}'
            if not src["ai_only"] and not AI_RE.search(text):
                continue
            if src["ai_only"] and sid == "hn" and not AI_RE.search(text):
                continue
            candidates.append({
                "source": sid, "title": it["title"], "url": it["url"].split("#")[0],
                "snippet": snippet(it["summary"]), "published": dt.isoformat(), "_dt": dt,
                "_w": src["weight"],
            })
            kept += 1
        status[sid] = {"ok": err is None, "error": err, "items": kept}

    # keep only one article per (source, near-duplicate title) -- "no deltas from same source"
    candidates.sort(key=lambda a: a["_dt"], reverse=True)
    for a in candidates:
        a["_tok"] = tokens(a["title"])
        a["score"] = score_article(a, now)

    # paywall check, concurrent
    def chk(a):
        ok, desc = check_article(a["url"], blocked, fixtures)
        return a, ok, desc
    with ThreadPoolExecutor(12) as ex:
        checked = list(ex.map(chk, candidates))
    free = []
    dropped = 0
    for a, ok, desc in checked:
        if not ok:
            dropped += 1
            continue
        if len(a["snippet"]) < 70 and desc:
            a["snippet"] = snippet(desc)
        free.append(a)

    # cluster
    clusters = []
    for a in sorted(free, key=lambda x: x["score"], reverse=True):
        for c in clusters:
            if any(similar(a["_tok"], m["_tok"]) for m in c):
                c.append(a)
                break
        else:
            clusters.append([a])

    out = []
    for i, c in enumerate(clusters):
        best_per_source = {}
        for a in c:   # already score-sorted desc
            best_per_source.setdefault(a["source"], a)
        arts = list(best_per_source.values())
        lead = arts[0]
        cat = categorise(" ".join(f'{a["title"]} {a["snippet"]}' for a in arts[:3]))
        out.append({
            "id": f"c{i}",
            "category": cat,
            "score": round(lead["score"] + 0.6 * (len(arts) - 1), 3),
            "articles": [{
                "source": a["source"], "title": a["title"], "url": a["url"],
                "snippet": a["snippet"], "published": a["published"], "score": a["score"],
            } for a in arts],
        })
    out.sort(key=lambda c: c["score"], reverse=True)

    data = {
        "generated": now.isoformat(),
        "window_hours": args.hours,
        "sources": [{"id": s["id"], "name": s["name"], "type": s["type"],
                     "default": s["id"] in cfg["default_sources"],
                     "items": status[s["id"]]["items"], "ok": status[s["id"]]["ok"]} for s in cfg["sources"]],
        "categories": [n for n, _ in CATEGORIES] + [DEFAULT_CAT],
        "stats": {"fetched": len(candidates), "paywalled_dropped": dropped, "stories": len(out)},
        "stories": out,
    }
    dest = ROOT / "site" / "data"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "news.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    failed = [f"{k}: {v['error']}" for k, v in status.items() if not v["ok"]]
    print(f"stories={len(out)} candidates={len(candidates)} paywall_dropped={dropped}")
    for f in failed:
        print("  feed failed ->", f, file=sys.stderr)
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--fixtures")
    build(ap.parse_args())
