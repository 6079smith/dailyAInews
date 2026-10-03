"""Paywall detection on article pages.  Run: python3 tests/test_paywall.py
The "free" cases are snippets of what wrongly flagged whole free sites in the live run of 2026-10-03."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_news as f

CASES = [
 # (description, page html, free_site, expected paywalled?)
 ("TechRadar / Tom's Hardware nav label", '<nav><a href="/pro">Premium Content</a></nav><article>Nvidia news</article>', False, False),
 ("Ars Technica menu link", '<li><a href="/store/">Subscribers only</a></li><article>Apple changes permissions</article>', False, False),
 ("9to5Mac article text", "<p>Apple TV added classic movies, free for subscribers this month.</p>", False, False),
 ("ordinary 'continue reading' link", '<a class="more">Continue reading</a>', False, False),
 ("The Register template class (known-free site)", '<div class="media paywall-hide">x</div>', True, False),
 ("publisher's own not-free flag", '<script type="application/ld+json">{"isAccessibleForFree": false}</script>', False, True),
 ("not-free flag as a string", '{"isAccessibleForFree":"false"}', False, True),
 ("not-free flag beats free_site", '{"isAccessibleForFree":false}', True, True),
 ("metered content", '<meta name="x" content="meteredContent">', False, True),
 ("subscribe wall", "<p>Subscribe to continue reading this article.</p>", False, True),
 ("continue-reading wall", "<p>To continue reading, please subscribe.</p>", False, True),
 ("sign-in wall", "<p>Sign in to read the full story.</p>", False, True),
 ("paywall markup on an unknown site", '<div class="article paywall">teaser</div>', False, True),
 ("data-paywall attribute", "<div data-paywall>teaser</div>", False, True),
]
bad = 0
for desc, page, free_site, want in CASES:
    got = bool(f.paywall_marker(page, free_site))
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), "paywalled" if want else "free     ", "|", desc)
print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
