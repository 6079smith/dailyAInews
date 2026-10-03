# Daily Tech News

Phone-friendly dashboard (+ optional email digest) of the latest tech news, with AI (AI / AGI / ASI) kept on its own desk.

- **Two desks: AI and Tech.** A switch under the header flips between AI news and everything else in tech (phones, computing, security, space, gaming, EVs…), each with its own top story and categories. AI-only feeds go to the AI desk; stories from general tech feeds go to the AI desk when they're clearly about AI, otherwise to Tech. The app remembers your last desk, and the email digest has a section for each.
- **Free to read only.** Only free sources are configured (`sources.json`); known paywalled domains are blocked, and every article page is checked for paywall markers (`isAccessibleForFree: false`, "subscribe to continue", etc.) before it's shown.
- **Categorised & de-duplicated.** Stories about the same subject are clustered; each cluster shows the most relevant article (one per source, never several from the same outlet) plus "Also: …" links to other sources.
- **Tap to expand.** Tapping a story opens it full-size in place, with a longer summary, a thumbnail when the feed or article has one, the link to the full article and the other outlets covering it. Close it and the card greys out as read (remembered on this device); tap its *Read ✓* chip to mark it unread. Ctrl/⌘-click still opens the article directly.
- **Source picker.** Tap *Sources* to choose outlets; the choice is saved on your device and becomes your default.
- **Add your own source.** In *Sources*, type a name or website. It filters the built-in catalog; if it isn't there, tap **Add “…” as a new source**. That opens a pre-filled GitHub issue (just press *Submit new issue*). A workflow (`add-source.yml`) then finds the feed, checks it is readable, recent and free of paywalls, and either adds it (new sources are on by default) or lists matches for you to choose by replying `/add 2`. Only issues/comments from the repo owner are acted on.
- **Read later.** Tap the bookmark on any story to save it on this device; open *Saved* to see unread and read stories, and clear read ones.
- **Auto-refresh.** A GitHub Action rebuilds it every hour.

## Setup
1. Repo **Settings → Pages → Source: GitHub Actions** (a private repo needs a plan that supports Pages).
2. Run the *Update AI news* workflow once (Actions tab → Run workflow). Your dashboard is at `https://<user>.github.io/<repo>/`.
3. *(Optional email)* add repo secrets `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`. It sends daily at 06:xx UTC. Tune `config/email.json` (sources, story count, dashboard link).

## Local
```
python3 scripts/fetch_news.py        # needs open internet
cp web/* site/ && python3 scripts/build_email.py
python3 -m http.server -d site       # http://localhost:8000
```
Tests: `python3 tests/test_add_source.py` (offline, mock web server), `python3 tests/test_categories.py`, `python3 tests/test_paywall.py`.
Offline pipeline test with synthetic data: `python3 tests/make_fixtures.py && python3 scripts/fetch_news.py --fixtures tests/fixtures`.

Add/remove outlets by editing `sources.json` (only add sources that are fully free).
