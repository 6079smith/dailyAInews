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
# Tech desk categories: (title, snippet, expected)
TECH_CASES = [
 ("Apple unveils iPhone 18 with a bigger battery", "The new phone gets a brighter screen.", "Phones & Gadgets"),
 ("Samsung Galaxy Watch 8 review: the best Android smartwatch", "Battery life finally lasts two days.", "Phones & Gadgets"),
 ("Windows 12 update brings a redesigned Start menu", "Microsoft is rolling out the software to PCs.", "Computing & Software"),
 ("Hackers steal customer data in retailer breach", "Ransomware gang claims the cyber attack.", "Security & Privacy"),
 ("EU fines Apple over App Store rules in antitrust case", "Regulators said the company broke the law.", "Business & Policy"),
 ("SpaceX launches Starship on sixth test flight", "The rocket reached orbit.", "Science & Space"),
 ("Nintendo sets a date for its next games console", "Three new games launch alongside it.", "Gaming & Entertainment"),
 ("Tesla cuts prices of its electric cars in Europe", "EV competition heats up.", "Cars & Energy"),
 ("Weekend reading list", "A few links.", "Other"),
]
# Which desk an article from a general (not AI-only) feed lands on: (title, summary, expected)
DESK_CASES = [
 ("OpenAI launches a new ChatGPT voice mode", "", "ai"),
 ("Apple unveils iPhone 18", "The phone has a faster chip.", "tech"),
 ("Nvidia's new GeForce card is a gaming beast", "Ray tracing performance doubles.", "tech"),
 ("Samsung's new fridge", "It uses AI to track food and an LLM to suggest recipes.", "ai"),
 ("Robot vacuum review", "It maps your home.", "tech"),
]
bad = 0
for title, snip, want in TECH_CASES:
    got = f.categorise(title, snip, "tech")
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"tech {want!r:24}", "" if ok else f"got {got!r}", "|", title[:60])
for title, snip, want in DESK_CASES:
    got = f.article_desk(title, snip, False)
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"desk {want!r:24}", "" if ok else f"got {got!r}", "|", title[:60])
for title, snip, want in CASES:
    got = f.categorise(title, snip)
    ok = got == want
    bad += not ok
    print(("PASS" if ok else "FAIL"), f"{want!r:28}", "" if ok else f"got {got!r}", "|", title[:60])
total = len(CASES) + len(TECH_CASES) + len(DESK_CASES)
print(f"\n{total - bad}/{total} passed")
sys.exit(1 if bad else 0)
