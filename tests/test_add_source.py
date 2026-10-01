"""Offline tests for scripts/add_source.py using a local mock web server.
Run: python3 tests/test_add_source.py"""
import http.server, json, os, shutil, sys, tempfile, threading
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

os.environ.update(ALLOW_LOCAL="1", DRY_RUN="1", ISSUE_NUMBER="7")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import add_source as a

PORT = 8897
BASE = f"http://127.0.0.1:{PORT}"
now = datetime.now(timezone.utc)

def feed(prefix, n=6, ai=True, age_days=1):
    items = "".join(
        f"<item><title>{'AI model' if ai else 'Gadget'} story {i}</title><link>{BASE}/{prefix}/a{i}</link>"
        f"<description>{'New AI chatbot' if ai else 'A new phone'} details {i}</description>"
        f"<pubDate>{format_datetime(now - timedelta(days=age_days, hours=i))}</pubDate></item>" for i in range(n))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'

PAGES = {
    "/good/": '<html><head><meta property="og:site_name" content="Good Site"><link rel="alternate" type="application/rss+xml" href="/good/feed.xml"></head></html>',
    "/good/feed.xml": feed("good"),
    "/paywall/": '<html><head><link rel="alternate" type="application/rss+xml" href="/paywall/feed.xml"></head></html>',
    "/paywall/feed.xml": feed("paywall"),
    "/stale/feed.xml": feed("stale", age_days=200),
    "/gen/feed.xml": feed("gen", ai=False),
}
for i in range(6):
    PAGES[f"/good/a{i}"] = "<html><body>free article</body></html>"
    PAGES[f"/gen/a{i}"] = "<html><body>free article</body></html>"
    PAGES[f"/stale/a{i}"] = "<html><body>x</body></html>"
    PAGES[f"/paywall/a{i}"] = '<html><script type="application/ld+json">{"isAccessibleForFree": false}</script></html>'

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())
    def log_message(self, *x): pass
srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# work on a scratch copy of sources.json
tmp = Path(tempfile.mkdtemp())
shutil.copy(a.SOURCES, tmp / "sources.json")
a.SOURCES = tmp / "sources.json"
blocked = json.loads(a.SOURCES.read_text())["blocked_domains"]

ok = lambda c: print("PASS" if c else "FAIL")

# 1. URL with <link rel=alternate> -> discovered, verified
r = a.find(BASE + "/good/")
print("auto-discovery:", end=" "); ok(len(r["ok"]) == 1 and r["ok"][0]["feed"].endswith("/good/feed.xml") and r["ok"][0]["ai_only"])

# 2. paywalled site is rejected
r = a.find(BASE + "/paywall/")
print("paywall rejected:", end=" "); ok(not r["ok"] and "paywalled" in r["rejected"][0]["reason"])

# 3. stale feed rejected
good, reason, _ = a.verify({"feed": BASE + "/stale/feed.xml"}, blocked)
print("stale rejected:", end=" "); ok(not good and "60" in reason)

# 4. general-tech feed -> ai_only False
good, _, info = a.verify({"feed": BASE + "/gen/feed.xml"}, blocked)
print("general feed not ai_only:", end=" "); ok(good and info["ai_only"] is False)

# 5. blocked domain
good, reason, _ = a.verify({"feed": "https://www.bloomberg.com/feed", "site": ""}, blocked)
print("block list:", end=" "); ok(not good and "block list" in reason)

_disc = a.discover_from_site
a.discover_from_site = lambda site: _disc(site) if site.startswith(BASE) else []   # keep tests offline
# 6. name search via (mocked) lookup -> two candidates, ambiguous -> not confident; exact -> confident
a.feedly_search = lambda q: [
    {"name": "Tom's Hardware", "feed": BASE + "/good/feed.xml", "site": BASE + "/good/"},
    {"name": "Tom's Hardware Forum", "feed": BASE + "/gen/feed.xml", "site": BASE + "/gen/"}]
r = a.find("Tom's Hardware")
print("name lookup finds 2:", end=" "); ok(len(r["ok"]) == 2)
print("close names => asks user to choose:", end=" "); ok(a.confident(r["ok"]) is None or r["ok"][0]["score"] - r["ok"][1]["score"] >= 0.15)
print("candidates comment renders:", end=" "); ok("/add 1" in a.render_candidates("Tom's Hardware", r) and a.MARKER in a.render_candidates("x", r))

# 7. add_source keeps file valid, unique ids, flags custom
pick = r["ok"][0]
e1 = a.add_source(pick); e2 = a.add_source(pick)
cfg = json.loads(a.SOURCES.read_text())
print("added + unique id + valid JSON:", end=" "); ok(e1["id"] != e2["id"] and cfg["sources"][-1]["custom"] and cfg["blocked_domains"])

# 8. SSRF guard (without ALLOW_LOCAL)
os.environ["ALLOW_LOCAL"] = "0"
print("private address refused:", end=" "); ok(not a.public_host("http://127.0.0.1/x") and not a.public_host("file:///etc/passwd"))

# 9. address-mode candidate takes the site's real name
os.environ["ALLOW_LOCAL"] = "1"
print("site name from og:site_name:", end=" "); ok(a.candidates_for(BASE + "/good/")[0]["name"] == "Good Site")

# 10. newly added source also becomes a default
print("added source is a default:", end=" "); ok(e1["id"] in json.loads(a.SOURCES.read_text())["default_sources"])
