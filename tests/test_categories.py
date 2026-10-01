"""Labelled examples for the story categoriser.  Run: python3 tests/test_categories.py
The first block are real headlines seen on the dashboard (some were misfiled by the old rules)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_news as f

CASES = [
 # (title, snippet, expected)
 ("The ugly economics of consumer AI",
  "There's a reason frontier labs have gotten gun-shy about consumer AI, and it's not because the tech isn't good enough.", "Business & Funding"),
 ("Forget 'superintelligence': error-prone AI nearly sparked world war three | Timnit Gebru and Emily M Bender",
  "The risks of AI aren't what we think they are, as a recent security incident between China and the United States reveals.", "AGI & Superintelligence"),
 ("US trade regulator opens investigation into AI giants including Anthropic and OpenAI",
  "FTC move is first official US enforcement action on rogue AI agents, following surge in incidents.", "Safety & Policy"),
 ("Anthropic brings Claude to civilian agencies as its fight with the Pentagon drags on",
  "Anthropic is now offering Claude for Government to US federal and state agencies. The platform runs in a FedRAMP High environment.", "Safety & Policy"),
 ("Trump's AI chatbot turns on its master",
  "The famously fact-averse president rolled out a new AI tool, but its answers don't conform to his version of reality.", "Products & Tools"),
 ("DraftKings is using AI to behaviorally target chronic gamblers",
  "565 points · 427 comments on Hacker News", "Society & Work"),
 ("Instinct's new product recommendations are giving some users the ick",
  "Instinct is rolling out human-curated product and travel recommendations, but some users aren't happy.", "Products & Tools"),
 # word-fragment regressions
 ("Impact of a new contact-tracing app", "A look at how the app works.", "Products & Tools"),
 ("Startup raises $200 million to build AI agents", "Funding round at a $1 billion valuation.", "Business & Funding"),
 ("NVIDIA ships new GPU cluster for AI data centers", "Gigawatt scale data centers promise lower inference cost.", "Chips & Infrastructure"),
 ("OpenAI unveils GPT-6 with stronger reasoning", "The new model tops every benchmark.", "Models & Releases"),
 ("Researchers publish paper on protein folding with transformers", "Scientists at a university report a breakthrough.", "Research"),
 ("AI is taking entry-level jobs, workers say", "Employment among graduates is falling.", "Society & Work"),
 ("EU lawmakers debate new AI safety regulation", "Parliament members argued over liability.", "Safety & Policy"),
 ("Is AGI two years away? Lab leaders disagree", "Superintelligence timelines are shrinking, some say.", "AGI & Superintelligence"),
 # nothing recognisable -> Other
 ("Weekend reading list", "A few links.", "Other"),
]
bad = 0
for title, snip, want in CASES:
    got = f.categorise(title, snip)
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"{want!r:28}", "" if ok else f"got {got!r}", "|", title[:60])
print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
