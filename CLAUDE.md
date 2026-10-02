# CLAUDE.md

## Delivery: always push, merge and run the workflows
When a change is finished and tested, do the whole delivery without asking:
1. Commit and push to the working branch.
2. Open a pull request into `main` (or reuse the open one for that branch), then merge it once its checks pass. If a check fails, fix it and push again before merging.
3. Make sure the GitHub Actions workflows that build or deploy the change have run, and report whether each run succeeded. `Update AI news` (`.github/workflows/update.yml`) runs on every push to `main`; if it didn't start, trigger it with workflow_dispatch.

Still ask first before anything destructive or irreversible: force-pushing, rewriting history, deleting branches or data, or merging when checks are failing.

## Project notes
- Static GitHub Pages dashboard. `scripts/fetch_news.py` writes `site/data/news.json`; the front end is plain HTML/CSS/JS in `web/` with no framework and no build step.
- User preferences live in `localStorage` under `dailyAInews.<name>.v1` keys, with every read and write wrapped in try/catch.
- Before pushing, run:
  - `python3 tests/test_add_source.py`
  - `python3 tests/test_categories.py`
  - Offline pipeline: `python3 tests/make_fixtures.py && python3 scripts/fetch_news.py --fixtures tests/fixtures`, then `cp web/* site/ && python3 -m http.server -d site`.
- For browser checks, use Playwright with Chromium at `/opt/pw-browsers/chromium`; don't run `playwright install`.
