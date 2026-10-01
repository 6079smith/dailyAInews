# Daily AI News

Phone-friendly dashboard (+ optional email digest) of the latest AI / AGI / ASI news.

- **Free to read only.** Only free sources are configured (`sources.json`); known paywalled domains are blocked, and every article page is checked for paywall markers (`isAccessibleForFree: false`, "subscribe to continue", etc.) before it's shown.
- **Categorised & de-duplicated.** Stories about the same subject are clustered; each cluster shows the most relevant article (one per source, never several from the same outlet) plus "Also: …" links to other sources.
- **Source picker.** Tap *Sources* to choose outlets; the choice is saved on your device and becomes your default.
- **Auto-refresh.** A GitHub Action rebuilds it every 3 hours.

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
Offline test with synthetic data: `python3 tests/make_fixtures.py && python3 scripts/fetch_news.py --fixtures tests/fixtures`.

Add/remove outlets by editing `sources.json` (only add sources that are fully free).
