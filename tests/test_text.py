"""Cleaning feed text into plain card text.  Run: python3 tests/test_text.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_news as f

CASES = [
 # (feed text, expected plain text)
 ("<p>A new model</p>", "A new model"),
 ("&lt;p&gt;A new model &amp;amp; more&lt;/p&gt;", "A new model & more"),          # escaped twice
 ("&lt;p&gt;&lt;a href=&quot;https://x&quot;&gt;Apple&lt;/a&gt; said&lt;/p&gt;", "Apple said"),
 ("&lt;!-- wp:paragraph --&gt;Hello", "Hello"),
 ("Prices fell 5% &lt; last year", "Prices fell 5% < last year"),                  # a real "<" stays
 ("Tom &amp; Jerry", "Tom & Jerry"),
]
bad = 0
for raw, want in CASES:
    got = f.strip_html(raw)
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), repr(raw)[:60], "" if ok else f"-> got {got!r}, want {want!r}")
print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
