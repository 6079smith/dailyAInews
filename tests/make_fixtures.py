"""Generates synthetic RSS fixtures (fake stories) for offline pipeline tests."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
out = Path(__file__).parent / "fixtures"
now = datetime.now(timezone.utc)
def feed(items):
    x = '<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>t</title>'
    for title, url, desc, hrs, *img in items:   # optional 5th value: thumbnail URL (media:thumbnail)
        media = f'<media:thumbnail url="{img[0]}"/>' if img else ""
        x += f"<item><title>{title}</title><link>{url}</link><description><![CDATA[<p>{desc}</p>]]></description>{media}<pubDate>{format_datetime(now - timedelta(hours=hrs))}</pubDate></item>"
    return x + "</channel></rss>"
data = {
 "openai": [("OpenAI unveils TestModel 7 with stronger reasoning", "https://openai.com/a", "TestModel 7 is a new reasoning model released today with benchmark gains across coding and math tasks. It is available to all users. "
   "The company says the model was trained with a new reinforcement learning recipe that rewards careful, step-by-step answers, and that it makes fewer factual errors than its predecessor. "
   "Developers can call it through the API from today, with higher rate limits arriving next month. Independent researchers cautioned that benchmark scores do not always translate into real-world reliability, "
   "and said they would publish their own evaluations over the coming weeks. Pricing is unchanged from the previous generation.", 3,
   "https://picsum.photos/seed/testmodel7/800/450")],
 "techcrunch": [
   ("OpenAI unveils TestModel 7, a reasoning model", "https://techcrunch.com/a", "The new model beats previous benchmarks.", 2),
   ("OpenAI launches TestModel 7 reasoning model update", "https://techcrunch.com/a2", "A follow-up take on the same launch from the same source.", 1),
   ("Nintendo sets a release date for its next games console", "https://techcrunch.com/n", "The company said the console will launch in March with three new games.", 6),
   ("Startup Foo raises $200 million to build AI agents", "https://techcrunch.com/b", "Foo, a startup building agentic workflow tools, closed a funding round at a $1 billion valuation.", 5)],
 "verge": [("OpenAI's TestModel 7 reasoning model is here", "https://www.theverge.com/a", "Everything to know about the new OpenAI model and what it means for ChatGPT users.", 2.5),
           ("Apple unveils iPhone 18 with a bigger battery and brighter screen", "https://www.theverge.com/b", "The new phone also gets a faster chip and a redesigned camera bump.", 4)],
 # Tech desk: general feeds now keep non-AI stories
 "9to5mac": [("iPhone 18 unveiled: Apple's new phone gets a bigger battery", "https://9to5mac.com/a", "Apple announced the iPhone 18 today with all-day battery life and a brighter display.", 3.5)],
 "electrek": [("Tesla cuts prices of its electric cars in Europe", "https://electrek.co/a", "The carmaker lowered prices on two models as EV competition heats up.", 7)],
 "ars": [("EU lawmakers debate new AI safety regulation", "https://arstechnica.com/c", "European Parliament members argued over liability rules for frontier AI developers.", 8),
         ("SpaceX launches Starship on its sixth test flight", "https://arstechnica.com/s", "The rocket reached space and the booster was caught by the launch tower.", 5)],
 "guardian": [("EU parliament debates AI safety regulation for frontier models", "https://www.theguardian.com/c", "Lawmakers in Brussels clashed over how to regulate the most capable AI systems.", 9)],
 "bbc": [("Local council announces bin collection changes", "https://www.bbc.co.uk/x", "Not about AI at all.", 4),
         ("Retailer hit by cyber attack as hackers steal customer data", "https://www.bbc.co.uk/h", "A data breach exposed names and addresses of millions of shoppers.", 2),
         ("Teachers adopt AI chatbots in classrooms", "https://www.bbc.co.uk/d", "Schools are using AI tools to help students and reduce workload for teachers.", 6, "https://picsum.photos/seed/classroom/800/450")],
 "venturebeat": [("Paywalled analysis of AI chips", "https://www.bloomberg.com/p", "Blocked domain should be dropped.", 3),
                 ("NVIDIA ships new GPU cluster for AI data centers", "https://venturebeat.com/e", "New chips promise lower inference cost at gigawatt scale data centers.", 7)],
 "importai": [("Researchers show superintelligence timelines may shrink", "https://importai.substack.com/f", "A new paper on AGI progress and recursive self-improvement argues that timelines could compress.", 12)],
}
for k, v in data.items():
    (out / f"{k}.xml").write_text(feed(v))
