# Implementation brief: Read later (saved stories)

This brief describes how **Read later** works today, so you can change it safely. Read all of it before you edit anything, then read the code it points to. Read later is already built and live; this is not a plan for a new feature. If you're asked for a change, keep everything below working unless the request says otherwise.

## The app in brief
- **Daily Tech News**, a static GitHub Pages dashboard. Every hour a GitHub Action (`.github/workflows/update.yml`, "Update AI news") runs `scripts/fetch_news.py`, which writes `site/data/news.json`.
- The front end is plain HTML/CSS/JS with no framework and no build step:
  - `web/index.html`
  - `web/app.js`: one IIFE
  - `web/style.css`
- **Two desks.** A switch (`.desk` buttons, `desk` variable, stored in `dailyAInews.desk.v1`) flips the feed between **AI** and **Tech**. Each story in `news.json` has `desk: "ai" | "tech"`; `deskOf()` treats a missing value as `"ai"`.
- **Tapping a card** opens the **expanded view** (`openReader()`). Closing it (`closeReader()`) marks the story read. Ctrl/⌘-click opens the article directly.
- `news.json` story shape:

  ```
  { desk, category, articles: [{ url, title, snippet, summary?, image?, source, published, score }] }
  ```

  `view()` turns each story into the card shape `{ cat, desk, lead, also }`. `name(id)` gives a source's display name. `nm(x)` gives `x.sourceName`, falling back to `name(x.source)`.

## What the user sees
- **Bookmark:** every card has a bookmark button at its top right (`.bm`). Tapping it saves or unsaves the story, with a small "pop" animation. It never opens the story.
- **Saved button:** the header's **Saved** button (`#openSaved`) shows how many saved stories are unread (`#savedCount`, hidden at 0). Tapping it switches to the **Saved view**, and the button then reads **← Feed**.
- **Saved view:**
  - The desk switch and dropdowns (`.drops`) are hidden.
  - Saved stories from **both desks** appear in **Unread (n)** and **Read (n)** sections, newest save first.
  - Each card shows "saved 2h ago" and an **AI**/**Tech** chip (`.dk`).
  - A **Clear read** button asks for confirmation, then removes saved stories that have been read.
  - When nothing is saved: "Nothing saved yet. Tap the bookmark on any story." The footer reads "N saved · M unread".
- **Read state is shared by the whole app, not just Saved:**
  - Closing the expanded view marks a story read, and so does opening one of its **Also** links.
  - A read card is greyed out (`.card.read`: grayscale and dimmed) and shows a **✓ Read** chip (`.rd`, `data-unread`). Tapping the chip marks the story unread.
  - Read cards can still be opened.
  - The feed and the Saved view always agree about what is read.

## Storage (`localStorage`, this device only)
All keys follow `dailyAInews.<name>.v1`, and every read and write is wrapped in try/catch. A corrupt value must never break the page.

| Key | Contents |
|---|---|
| `dailyAInews.saved.v1` | JSON array of saved stories (below). `loadSaved()` drops any entry without a string `id` and `url`, and treats anything that isn't an array as `[]`. |
| `dailyAInews.read.v1` | JSON array of **article URLs** that have been read. Every article URL in a story is stored, so the read state survives a change of lead source. The list is trimmed to the last 1500. |
| `dailyAInews.desk.v1` | `"ai"` or `"tech"`. |

A saved story is a **full copy**, because stories drop out of `news.json` after 48 hours:

```
{ id, url, title, snippet, summary, image, source, sourceName, cat, desk, published, savedAt, readAt,
  also: [{ url, sourceName, title, summary, image }] }
```
- `id` is the lead article's URL.
- `savedAt` and `readAt` are ISO strings; `readAt` is `null` while unread.
- Saved copies made before the desks or the expanded view existed may lack `desk`, `summary`, `image` or the `also[].title` field. Always fall back: `deskOf()`, `|| ""`, and so on.

## Code map (`web/app.js`)
| What | Where |
|---|---|
| State | `saved` (a Map keyed by `id`), `persist()`, `cards` (a Map from lead URL to the story on that card, rebuilt on every render), `mode` (`"feed"` or `"saved"`) |
| Read state | `readSet`, `urlsOf(s)`, `isRead(s)` (true if **any** article URL is in `readSet` **or** a saved copy has `readAt`), `setRead(s, on)` (updates `readSet` **and** every matching saved copy's `readAt`, then re-renders the Saved view or calls `syncCard` on every card) |
| Saved copy → card | `asStory(x)` and `toSaved(s)`. `toSaved` copies `readAt` from `isRead(s)` at save time. |
| Cards | `card(s, hero, sv)`. `sv=true` gives the Saved-view variant (saved time and desk chip, no NEW badge, never a hero card). Every card has `data-id` = lead URL. |
| Updating one card in place | `syncCard(el)` sets the bookmark's `aria-pressed` and label, and toggles `.read`. Use it rather than a full re-render, so the scroll position is kept. |
| Badge | `badge()` counts saved stories where `!isRead(asStory(x))`. |
| Saved view | `renderSaved()`, which `render()` calls when `mode === "saved"` |
| Clicks | One delegated `document` click listener. Order: close the expanded view → open a card's headline (expand) → any other `.card a` (mark read) → `closest(".desk,[data-save],[data-unread],#openSaved,#clearRead,…")`. Extend this listener; don't add listeners per element. **Don't** match a bare `[data-desk]`, because `<body>` carries `data-desk`. |

## Rules to keep
1. Anything clickable inside a card must sit above the stretched headline link (`.card h3 a::after` has `z-index:1`). Give it `position:relative` or `absolute` and `z-index:2`, as `.bm`, `.rd` and `.also` do.
2. Pass **every** value interpolated into HTML through `esc()`. Saved data comes from third-party feeds.
3. Don't call `preventDefault` on real links, except the headline-to-expand case that already exists.
4. Change the read state only through `setRead()`, so the feed, the Saved view and the badge stay in step.
5. Keep the expanded view, the focus traps (expanded view and source sheet), Esc handling, the desk switch and the dropdowns working.
6. Use vanilla JS in the existing terse style (arrow helpers, template strings), with no libraries. Use the existing CSS variables (`--acc`, `--mut`, `--bd`, `--accbg`, …) and don't hard-code colours. The result must work in light and dark mode, and at 360px wide with no horizontal scroll.

## Out of scope unless asked
Sync across devices, swipe or long-press gestures, expiry of saved stories, saved stories in the email digest, export/import.

## How to verify
1. Build the offline fixtures and serve them:
   ```
   python3 tests/make_fixtures.py
   python3 scripts/fetch_news.py --fixtures tests/fixtures
   cp web/* site/
   python3 -m http.server -d site 8000
   ```
2. Run Playwright with Chromium at `/opt/pw-browsers/chromium` (don't run `playwright install`). Test at 390×844 and 1280×800, in light and dark mode. Headless frames are slow, so wait at least 1.5 s after anything animated. Check that:
   - the bookmark fills, the badge shows 1, and neither the expanded view nor a new tab opens;
   - the story is still saved after a reload;
   - **Saved** lists it under Unread with its desk chip, and **← Feed** goes back;
   - opening it in the Saved view and closing it moves it to Read, greys it and drops the badge to 0;
   - **✓ Read** moves it back to Unread;
   - reading a story in the feed also greys it in Saved, and the other way round;
   - **Clear read** removes read items after you accept the confirm dialog;
   - a Tech-desk story can be saved, and shows the **Tech** chip;
   - setting `localStorage["dailyAInews.saved.v1"] = "x"` and `localStorage["dailyAInews.read.v1"] = "{bad"` doesn't break the page;
   - there are no page errors and no horizontal scroll.
3. Run `python3 tests/test_add_source.py` and `python3 tests/test_categories.py`.

## Delivery
Follow `CLAUDE.md`:
1. Commit on the working branch and push.
2. Open a PR into `main` and merge it once it's green.
3. Confirm that the "Update AI news" workflow run succeeded.

Don't include model names in commits or PR text.
