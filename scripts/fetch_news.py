#!/usr/bin/env python3
"""Fetch AI news from free sources, drop paywalled items, cluster duplicates and
categorise.  Writes site/data/news.json.  Standard library only.

    python3 scripts/fetch_news.py                 # live
    python3 scripts/fetch_news.py --fixtures tests/fixtures   # offline test
"""
import argparse, html, json, math, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
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
# Stricter set for deciding the desk of an article from a general feed: leaves out words that are just as
# common in ordinary tech stories (a GeForce card, a robot vacuum, "agents" of a company...).
WEAK_AI = {r"nvidia", r"robot", r"\bagents?\b", r"transformer", r"diffusion", r"alignment", r"neural", r"generative"}
AI_DESK_RE = re.compile("|".join(t for t in AI_TERMS if t not in WEAK_AI), re.I)
# "Is this a tech story at all?" -- only applied to general-news feeds marked topic_check (e.g. BBC Tech,
# which also carries some non-tech items).
TECH_TERMS = [
    r"\btech\w*", r"\bapps?\b", r"\bsoftware\b", r"\b(smart)?phones?\b", r"\biphone", r"\bandroid\b", r"\bapple\b",
    r"\bgoogle\b", r"\bmicrosoft\b", r"\bamazon\b", r"\bmeta\b", r"\bsamsung\b", r"\bcomputers?\b", r"\blaptops?\b",
    r"\bpcs?\b", r"\bchips?\b", r"\binternet\b", r"\bonline\b", r"\bcyber\w*", r"\bhack\w*", r"\bdata\b", r"\bdigital\b",
    r"\bspace\b", r"\brockets?\b", r"\bnasa\b", r"\bspacex\b", r"\bsatellites?\b", r"\belectric (car|vehicle)s?\b", r"\bevs?\b",
    r"\btesla\b", r"\bbatter(y|ies)\b", r"\bgam(e|es|ing|ers?)\b", r"\bconsoles?\b", r"\bplaystation\b", r"\bxbox\b",
    r"\bnintendo\b", r"\bstreaming\b", r"\bnetflix\b", r"\bsocial media\b", r"\btiktok\b", r"\binstagram\b", r"\bcrypto\w*",
    r"\bbitcoin\b", r"\bstartups?\b", r"\bbroadband\b", r"\b5g\b", r"\bquantum\b", r"\bgadgets?\b", r"\bwearables?\b",
    r"\bsmartwatch\w*", r"\bheadsets?\b", r"\bprivacy\b", r"\bencrypt\w*", r"\boutages?\b", r"\bwebsites?\b", r"\bdevices?\b",
    r"\bonline safety\b", r"\bsemiconductors?\b", r"\bscam\w*", r"\bpasswords?\b", r"\bbreach\w*",
]
TECH_RE = re.compile("|".join(TECH_TERMS), re.I)

# Category rules: (whole-word regex, weight).  A pattern scores weight x 2 if it appears in a headline and
# weight x 1 if it appears only in the snippet; the highest-scoring category wins (ties: earlier in the list).
# Below MIN_SCORE the story goes to "Other".  Whole words only: "investigation" must not look like "invest".
CATEGORIES = [
    ("AGI & Superintelligence", [
        (r"\bagi\b|\basi\b|superintelligen\w*|artificial general intelligence", 4),
        (r"singularity|recursive self[- ]improv\w*|intelligence explosion|p\(doom\)", 3),
        (r"existential (risk|threat)s?|human[- ]level|race to (agi|superintelligence)", 3),
        (r"frontier (labs?|models?)", 1)]),
    ("Safety & Policy", [
        (r"\bregulat\w*|\blegislat\w*|\blawmakers?\b|\bsanctions?\b|\bexport controls?\b|\btariffs?\b", 3),
        (r"\bsue[sd]?\b|\blawsuits?\b|\bcourt\b|\bjudge\b|\bruling\b|\bcopyright\w*|\binvestigat\w*", 3),
        (r"\bsafety\b|\bsafeguards?\b|\bethic\w*|\balignment\b|\bpolic(y|ies)\b|\bgovernment\w*", 2),
        (r"\bcongress\b|\bsenate\b|\bparliament\b|\bwhite house\b|\bpentagon\b|\bfederal\b|\bftc\b|\bdoj\b|\bsec\b|\bEU\b", 2),
        (r"\bbans?\b|\bbanned\b|\bbanning\b|\bprivacy\b|\bsurveillance\b|\bdeepfakes?\b|\bmisinformation\b|\bdisinformation\b", 2),
        (r"\bsecurity\b|\bjailbreak\w*|\bvulnerabilit\w*|\bhack\w*|\bbreach\w*|\bcyber\w*|\belections?\b|\bcompliance\b", 2)]),
    ("Chips & Infrastructure", [
        (r"\bgpus?\b|\bchips?\b|\bsemiconductors?\b|\btpus?\b|\bdata ?cent(er|re)s?\b|\bsupercomputer\w*", 3),
        (r"\bnvidia\b|\btsmc\b|\bamd\b|\bintel\b|\bbroadcom\b|\bcerebras\b|\bgroq\b|\bcompute\b|\bcluster\b|\bhardware\b", 2),
        (r"\b(mega|giga)watts?\b|\bpower grid\b|\belectricity\b|\bnuclear\b|\benergy\b|\bcapex\b|\binference\b", 2)]),
    ("Business & Funding", [
        (r"\braises?\b|\braised\b|\bfunding\b|\bvaluation\b|\bipo\b|\bseries [a-e]\b|\bacqui(re|res|red|sition|sitions)\b", 3),
        (r"\binvest(s|ed|ment|ments|ors?|ing)?\b|\brevenue\b|\bearnings\b|\bprofits?\b|\bstock\b|\bshares\b|\bwall street\b", 2),
        (r"\bstartups?\b|\bpartnership\b|\bdeal\b|\beconomics\b|\bpricing\b|\bbubble\b|\bmarket (share|cap)\b|\blayoffs?\b", 2),
        (r"\bbillions?\b|\bceo\b", 1)]),
    ("Models & Releases", [
        (r"\bnew model\b|\bopen[- ](source|weights?)\b|\breasoning models?\b|\bmultimodal\b|\bcontext window\b", 3),
        (r"\b(launch|launches|launched|releases?|released|unveil\w*|introduc\w*|debuts?)\b|\bbenchmarks?\b|\bgpt-?\d\S*", 2),
        (r"\b(claude|gemini|llama|mistral|grok|deepseek|qwen|sonnet|opus|haiku)\b|\bmodels?\b|\bversion \d|\bv\d(\.\d)?\b", 1)]),
    ("Research", [
        (r"\bresearch\w*|\bpapers?\b|\barxiv\b|\bstud(y|ies)\b|\bscientists?\b|\bbreakthroughs?\b|\bdiscover\w*", 2),
        (r"\bprotein\w*|\bphysics\b|\bmath(s|ematics)?\b|\balgorithms?\b|\bdatasets?\b", 2),
        (r"\buniversity\b|\bstanford\b|\bberkeley\b|\btraining\b|\bfine-?tun\w*", 1)]),
    ("Products & Tools", [
        (r"\bapps?\b|\bfeatures?\b|\bassistants?\b|\bbrowsers?\b|\bplugins?\b|\bextensions?\b|\bintegrat\w*|\brecommendations?\b", 2),
        (r"\brolls? out\b|\brolled out\b|\brolling out\b|\bcopilot\b|\bchatgpt\b|\bchatbots?\b", 2),
        (r"\btools?\b|\bapi\b|\bsdk\b|\bdevelopers?\b|\bcoding\b|\bagents?\b|\bworkflows?\b|\bsubscribers?\b", 1)]),
    ("Society & Work", [
        (r"\bjobs?\b|\bworkers?\b|\bemploy\w*|\bworkforce\b|\bcareers?\b|\bgambl\w*|\bmental health\b|\bloneliness\b", 3),
        (r"\bschools?\b|\bstudents?\b|\bteachers?\b|\beducation\b|\bhealth\w*|\bmedical\b|\bdoctors?\b|\bpatients?\b", 2),
        (r"\bartists?\b|\bcreators?\b|\bmusic\b|\bfilms?\b|\bhollywood\b|\bwriters?\b|\bauthors?\b|\bcompanions?\b|\brelationships?\b", 2),
        (r"\bculture\b|\bsociety\b|\bkids?\b|\bchildren\b|\bteens?\b|\bpeople\b|\bhumans?\b", 1)]),
]
# Categories for the Tech desk (everything that isn't about AI), same rule format.
TECH_CATEGORIES = [
    ("Phones & Gadgets", [
        (r"\b(smart)?phones?\b|\biphone\w*|\bipad\w*|\bpixel\b|\bgalaxy\b|\bsmartwatch\w*|\bwearables?\b|\bearbuds\b|\bairpods\b", 3),
        (r"\bgadgets?\b|\bheadphones?\b|\bcameras?\b|\btablets?\b|\bfoldables?\b|\bvr\b|\bheadsets?\b|\bvision pro\b|\bhands[- ]on\b|\breview\b", 2),
        (r"\bapple\b|\bsamsung\b|\bandroid\b|\bios\b|\bwatch\b|\bdevices?\b", 1)]),
    ("Computing & Software", [
        (r"\bwindows\b|\bmacos\b|\blinux\b|\blaptops?\b|\bpcs?\b|\bcpus?\b|\bgpus?\b|\bprocessors?\b|\bsemiconductors?\b|\bchips?\b", 3),
        (r"\bsoftware\b|\bupdates?\b|\bbrowsers?\b|\bopen[- ]source\b|\bdevelopers?\b|\bprogramming\b|\bcloud\b|\bservers?\b|\bquantum\b", 2),
        (r"\bapps?\b|\bmicrosoft\b|\bintel\b|\bamd\b|\bnvidia\b|\bstorage\b|\bmonitors?\b|\bkeyboards?\b", 1)]),
    ("Security & Privacy", [
        (r"\bhack\w*|\bbreach\w*|\bransomware\b|\bmalware\b|\bvulnerabilit\w*|\bexploit\w*|\bzero[- ]day\b|\bcyber\w*|\bphishing\b", 3),
        (r"\bprivacy\b|\bsecurity\b|\bscam\w*|\bspyware\b|\bpasswords?\b|\bencrypt\w*|\bsurveillance\b|\bleak\w*|\bpatch\w*", 2)]),
    ("Business & Policy", [
        (r"\bantitrust\b|\bregulat\w*|\blawsuits?\b|\bcourt\b|\bjudge\b|\bfines?d?\b|\bbans?\b|\btariffs?\b|\bftc\b|\bdoj\b|\bEU\b", 3),
        (r"\bacqui(re|res|red|sition)\b|\bmerger\b|\blayoffs?\b|\bearnings\b|\brevenue\b|\bipo\b|\braises?\b|\bfunding\b|\bvaluation\b", 3),
        (r"\bstartups?\b|\bceo\b|\bstock\b|\bshares\b|\bdeal\b|\bprices?\b|\bsubscriptions?\b|\bgovernment\b|\blaw\b", 1)]),
    ("Science & Space", [
        (r"\bspace\w*|\brockets?\b|\bnasa\b|\bspacex\b|\bstarship\b|\bsatellites?\b|\borbit\w*|\bmoon\b|\bmars\b|\btelescope\b|\bastronaut\w*", 3),
        (r"\bscien\w*|\bresearch\w*|\bstud(y|ies)\b|\bphysics\b|\bclimate\b|\bfusion\b|\bdiscover\w*", 2)]),
    ("Gaming & Entertainment", [
        (r"\bgam(e|es|ing|ers?)\b|\bconsoles?\b|\bplaystation\b|\bps5\b|\bxbox\b|\bnintendo\b|\bswitch 2\b|\bsteam\b|\besports\b", 3),
        (r"\bstreaming\b|\bnetflix\b|\bspotify\b|\byoutube\b|\btv\b|\bfilms?\b|\bmovies?\b|\bmusic\b|\bdisney\b|\btiktok\b|\bsocial media\b", 2)]),
    ("Cars & Energy", [
        (r"\belectric (cars?|vehicles?|trucks?)\b|\bevs?\b|\btesla\b|\brivian\b|\bbyd\b|\bself[- ]driving\b|\brobotaxi\w*|\bwaymo\b", 3),
        (r"\bbatter(y|ies)\b|\bcharging\b|\bsolar\b|\bgrid\b|\benergy\b|\bcars?\b|\bvehicles?\b|\bdrones?\b|\be-?bikes?\b", 2)]),
]
CAT_RULES = [(n, [(re.compile(p, re.I), w) for p, w in rules]) for n, rules in CATEGORIES]
TECH_RULES = [(n, [(re.compile(p, re.I), w) for p, w in rules]) for n, rules in TECH_CATEGORIES]
DESK_CATEGORIES = {"ai": [n for n, _ in CATEGORIES], "tech": [n for n, _ in TECH_CATEGORIES]}
DEFAULT_CAT = "Other"
MAX_PER_DESK = 60   # story clusters kept per desk, so news.json stays small
MIN_SCORE = 3

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


def web_url(u):
    """Absolute http(s) URL or "" (keeps javascript:/data: etc. out of the page)."""
    u = html.unescape((u or "").strip())
    if u.startswith("//"):
        u = "https:" + u
    return u if re.match(r"https?://[^\s\"'<>]+$", u) else ""


def first_img(markup):
    """First real <img> in feed HTML (skips 1px tracking pixels)."""
    for tag in re.findall(r"<img\b[^>]*>", markup or "", re.I):
        m = re.search(r"\bsrc=[\"']([^\"']+)", tag, re.I)
        if m and not re.search(r"\b(width|height)=[\"']?[01]\b", tag, re.I) and web_url(m.group(1)):
            return web_url(m.group(1))
    return ""


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


def is_image(el):
    return bool(el.get("url")) and (el.get("type") or el.get("medium") or "image").lower().startswith("image")


def parse_feed(xml_bytes):
    """Return list of dicts: title, url, summary, body, image, published (RSS 2.0 and Atom)."""
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
        d = {"title": "", "url": "", "summary": "", "body": "", "image": "", "published": None}
        content = ""
        img = ""
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
            elif t in ("thumbnail", "enclosure") or (t == "content" and ch.get("url")):   # media:/enclosure images
                if not img and is_image(ch):
                    img = web_url(ch.get("url"))
            elif t == "group":   # <media:group><media:content url=… /></media:group>
                img = img or next((web_url(g.get("url")) for g in ch if local(g.tag) in ("content", "thumbnail") and is_image(g)), "")
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
        # longer text for the expanded view: whichever of summary / full content says more
        d["body"] = max((d["summary"], content), key=lambda x: len(strip_html(x)))
        d["image"] = img or first_img(content) or first_img(d["summary"])
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
    """Return (ok, meta_description, og_image, why). ok False => paywalled/unreadable; why says what caught it."""
    if is_blocked(url, blocked):
        return False, "", "", "blocked domain"
    if fixtures:
        return True, "", "", ""
    try:
        status, body, cs = http_get(url, timeout=15, max_bytes=300_000)
    except Exception as e:
        code = getattr(e, "code", None)
        if code in (401, 402):
            return False, "", "", f"HTTP {code}"
        return True, "", "", ""   # source is vetted-free; can't verify (bot block / timeout) -> keep
    page = decode(body, cs)
    pw = PAYWALL_MARKERS.search(page)
    if pw:
        return False, "", "", "marker " + repr(pw.group(0)[:40])
    m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+content="([^"]*)"', page, re.I)
    im = re.search(r'<meta[^>]+(?:property="og:image"|name="twitter:image")[^>]+content="([^"]*)"', page, re.I)
    return True, html.unescape(m.group(1)) if m else "", web_url(urljoin(url, html.unescape(im.group(1)))) if im else "", ""


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


def categorise(titles, body="", desk="ai"):
    """Pick the best category from headline text and snippet text (CATEGORIES, or TECH_CATEGORIES for desk "tech")."""
    best, best_n = DEFAULT_CAT, MIN_SCORE - 1
    for name, rules in (TECH_RULES if desk == "tech" else CAT_RULES):
        n = sum(w * (2 * bool(rx.search(titles)) + bool(rx.search(body))) for rx, w in rules)
        if n > best_n:
            best, best_n = name, n
    return best


def article_desk(title, summary, ai_only):
    """"ai" for AI-only feeds, or when a general feed's story is clearly about AI; otherwise "tech"."""
    if ai_only:
        return "ai"
    return "ai" if AI_DESK_RE.search(title) or len(AI_DESK_RE.findall(summary)) >= 2 else "tech"


def score_article(a, now):
    # relevance to its own desk: AI terms for AI stories, tech terms for the rest
    rx = TECH_RE if a.get("desk") == "tech" else AI_RE
    title_hits = len(rx.findall(a["title"]))
    sum_hits = len(rx.findall(a["snippet"]))
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
            plain = strip_html(it["summary"])
            text = f'{it["title"]} {plain}'
            if src["ai_only"] and sid == "hn" and not AI_RE.search(text):
                continue
            desk = article_desk(it["title"], plain, src["ai_only"])
            if desk == "tech" and src.get("topic_check") and not TECH_RE.search(text):
                continue   # general news feed: skip items that aren't about tech at all
            candidates.append({
                "desk": desk,
                "source": sid, "title": it["title"], "url": it["url"].split("#")[0],
                "snippet": snippet(it["summary"]), "summary": snippet(it["body"], 1000), "image": it["image"], "published": dt.isoformat(), "_dt": dt,
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
        ok, desc, img, why = check_article(a["url"], blocked, fixtures)
        a["image"] = a["image"] or img
        a["_why"] = why
        return a, ok, desc
    with ThreadPoolExecutor(12) as ex:
        checked = list(ex.map(chk, candidates))
    free = []
    dropped = 0
    drop_log = {}   # source -> {"checked": n, "reasons": Counter, "example": url}, printed below for diagnosis
    for a, ok, desc in checked:
        d = drop_log.setdefault(a["source"], {"checked": 0, "reasons": Counter(), "example": ""})
        d["checked"] += 1
        if not ok:
            dropped += 1
            d["reasons"][a["_why"]] += 1
            d["example"] = d["example"] or a["url"]
            continue
        if len(a["snippet"]) < 70 and desc:
            a["snippet"] = snippet(desc)
            if len(a["summary"]) < len(desc):
                a["summary"] = snippet(desc, 1000)
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
        n_ai = sum(a["desk"] == "ai" for a in arts)
        desk = "ai" if n_ai * 2 >= len(arts) else "tech"   # majority of its articles; a tie goes to AI
        cat = categorise(" | ".join(a["title"] for a in arts[:3]), " ".join(a["snippet"] for a in arts[:3]), desk)
        out.append({
            "id": f"c{i}",
            "desk": desk,
            "category": cat,
            "score": round(lead["score"] + 0.6 * (len(arts) - 1), 3),
            "articles": [{
                "source": a["source"], "title": a["title"], "url": a["url"],
                "snippet": a["snippet"], "published": a["published"], "score": a["score"],
                # longer text and a thumbnail for the expanded view; omitted when they add nothing
                **({"summary": a["summary"]} if len(a["summary"]) > len(a["snippet"]) else {}),
                **({"image": a["image"]} if a["image"] else {}),
            } for a in arts],
        })
    out.sort(key=lambda c: c["score"], reverse=True)
    kept, per_desk = [], {}
    for c in out:
        per_desk[c["desk"]] = per_desk.get(c["desk"], 0) + 1
        if per_desk[c["desk"]] <= MAX_PER_DESK:
            kept.append(c)
    out = kept

    data = {
        "generated": now.isoformat(),
        "repo": os.environ.get("GITHUB_REPOSITORY", "6079smith/dailyAInews"),
        "window_hours": args.hours,
        "sources": [{"id": s["id"], "name": s["name"], "type": s["type"], "desk": "ai" if s["ai_only"] else "mixed",
                     "default": s["id"] in cfg["default_sources"], "custom": bool(s.get("custom")), "site": s.get("site", ""),
                     "items": status[s["id"]]["items"], "ok": status[s["id"]]["ok"]} for s in cfg["sources"]],
        # flat list kept for pages still running an older app.js; desk_categories is what the app uses now
        "categories": DESK_CATEGORIES["ai"] + DESK_CATEGORIES["tech"] + [DEFAULT_CAT],
        "desk_categories": {d: names + [DEFAULT_CAT] for d, names in DESK_CATEGORIES.items()},
        "stats": {"fetched": len(candidates), "paywalled_dropped": dropped, "stories": len(out),
                  "desks": {d: sum(c["desk"] == d for c in out) for d in DESK_CATEGORIES}},
        "stories": out,
    }
    dest = ROOT / "site" / "data"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "news.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    failed = [f"{k}: {v['error']}" for k, v in status.items() if not v["ok"]]
    print(f"stories={len(out)} candidates={len(candidates)} paywall_dropped={dropped}")
    for f in failed:
        print("  feed failed ->", f, file=sys.stderr)
    # which sources lose articles to the paywall check, and what caught them (for spotting false positives)
    for sid, d in sorted(drop_log.items(), key=lambda kv: -sum(kv[1]["reasons"].values())):
        n = sum(d["reasons"].values())
        if n:
            why = ", ".join(f"{r} x{c}" for r, c in d["reasons"].most_common())
            print(f"  paywall-dropped {sid}: {n}/{d['checked']} ({why}) e.g. {d['example']}")
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--fixtures")
    build(ap.parse_args())
