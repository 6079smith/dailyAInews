# Implementation brief: "Read later" (saved stories)

You are implementing a **Read later** feature in the `dailyAInews` repo. Read this whole brief first, then the files it references. The product decisions below are final, so don't change them.

## Context

- The repo is a static GitHub Pages dashboard of AI news. A GitHub Action runs `scripts/fetch_news.py` every hour, which writes `site/data/news.json`. The front end is plain HTML/CSS/JS with no framework and no build step:
  - `web/index.html`
  - `web/app.js`: a single IIFE (~260 lines)
  - `web/style.css`
- User preferences are stored in `localStorage` on each device. Follow the existing pattern in `web/app.js`:
  - keys are named `dailyAInews.<name>.v1`;
  - every read and write is wrapped in try/catch (see `loadSeen` / `saveSeen` near the top of the file).
- `news.json` stories have the shape `{ category, articles: [{ url, title, snippet, source, published, score }] }`. `view()` turns each story into `{ cat, rank, lead, also }`. `name(id)` maps a source id to its display name.
- Cards are built in `render()` → `card(s, hero)`. **The whole card is tappable** through a stretched link: `.card h3 a::after { position:absolute; inset:0; z-index:1 }`. Anything clickable inside a card must sit above that layer with `position:relative; z-index:2`, the way `.also` does.
- All click handling goes through one delegated `document.addEventListener("click", …)` that matches on `closest(...)`. Extend it rather than adding listeners per element.

> **Note (added later):** the dashboard now has a general read state. Tapping a card opens an expanded view, and closing it marks the story read: `dailyAInews.read.v1`, the `.read` class and the "Read ✓" chip with `data-unread`, via `setRead()` / `isRead()` in `web/app.js`. Card headline clicks no longer navigate. Reuse that read state for saved stories rather than adding a separate `readAt` flow; section 4 below predates it.

## Decisions (final)

| Topic | Decision |
|---|---|
| Storage | This device only, in `localStorage`. No backend and no sync. |
| How to save | A bookmark icon button on every card. |
| Where the list lives | A **Saved** button in the header that switches between the Feed and Saved views. |
| After reading | Mark the story as read and keep it (dimmed). Provide a **Clear read** action. |

Out of scope: syncing across devices, swipe or long-press gestures, expiry, email-digest integration, export/import.

## Spec

### 1. Storage (`web/app.js`)
- New key: `dailyAInews.saved.v1`. Its value is a JSON array of saved stories:
  `{ id, url, title, snippet, source, sourceName, cat, published, savedAt, readAt, also: [{ url, sourceName }] }`
  - `id` is the main (lead) article's URL.
  - `savedAt` and `readAt` are ISO strings. `readAt` is `null` until the story is opened.
- Store a **full copy** of each story, not just a reference. Stories drop out of `news.json` after the time window, and the saved list must still render on its own.
- Add helpers `loadSaved()` and `writeSaved(list)` that follow the existing try/catch pattern. If the stored value is corrupt or not an array, treat it as empty (`[]`).
- Keep an in-memory `Map` keyed by `id` for fast lookups during rendering.

### 2. Bookmark button on cards
- In `card()`, add the following inside the card:
  `<button class="bm" data-save="${esc(l.url)}" aria-pressed="${isSaved}" aria-label="${isSaved ? "Remove from saved" : "Save for later"}">`
  Use an inline SVG bookmark: outlined when unsaved, filled when saved.
- Put it at the top right of the card. The `.new` badge currently sits at `top:12px; right:12px`, so move it left far enough to clear the bookmark.
- `.bm` must have `position:relative; z-index:2` (or be absolutely positioned with `z-index:2`) so that tapping it **doesn't** open the article.
- Make the tap target at least 40×40px. Show a visible `:focus-visible` outline that matches the existing `.btn:focus-visible` style.
- Tapping it saves or unsaves the story. Update **only that button** (`aria-pressed`, label, icon) and the header badge. Don't re-render the whole feed, so the scroll position stays put.
- Add a short scale "pop" animation on save. The existing `prefers-reduced-motion` rule already turns animations off.

### 3. Saved button in the header (`web/index.html`)
- Add `<button id="openSaved" class="btn" aria-pressed="false">Saved <span id="savedCount" class="pill"></span></button>` inside `.actions`, between Refresh and Sources.
- `#savedCount` shows the number of **unread** saved stories and is hidden when that number is 0.
- Add a `mode` variable (`"feed"` or `"saved"`). Clicking the button toggles it and updates `aria-pressed`. In Saved mode the button text reads `← Feed`.
- **Saved view** (a new `renderSaved()` function that `render()` calls when `mode === "saved"`):
  - Hide `.drops` and any open panels.
  - Render the cards from the saved copies, newest `savedAt` first, in two sections using the existing `.sect` heading style: **Unread (n)** and **Read (n)**. Leave out an empty section.
  - Reuse the `card()` markup. Add a flag so the meta row shows "saved 2d ago" (use the existing `ago()`) and so no "Top story" hero card appears.
  - At the top, a **Clear read** button (`.btn small`). It asks `confirm("Remove N read stories?")`, then removes every item that has a `readAt`. Hide it when nothing has been read.
  - Empty state: reuse `#empty` with the text "Nothing saved yet. Tap the bookmark on any story."
  - Footer text: `"N saved · M unread"`.
- `loadData()` must not throw you out of Saved mode. After a refresh, re-render whichever view is active.
- Scroll to the top when switching views.

### 4. Mark read, keep
- In the delegated click handler, when the user clicks an `a` inside a `.card` (the headline or an "Also" link), look up the card's saved id. Add a `data-id` on the `<article>` to make this easy. If the story is saved and `readAt` is null, set `readAt = now`, save, and update the badge. Don't `preventDefault`, so the link still opens in a new tab.
- This applies in **both** views.
- Read cards get the `.read` class: `opacity:.6`. Add a small "✓ Read" chip in the meta row.
  - The chip is a `<button data-unread="id">`. Tapping it sets `readAt = null` (z-index 2, as above).
- In the main feed, cards for saved stories show the filled bookmark. A saved story that has been read also gets `.read`.

### 5. README
Add one bullet to the feature list in `README.md`:
"**Read later.** Tap the bookmark on any story to save it on this device; open *Saved* to see unread and read stories, and clear read ones."

## Constraints
- Use vanilla JS only, matching the existing terse style (arrow helpers, template strings, `esc()` on **every** interpolated value). Don't add libraries.
- Escape all stored fields with `esc()` when rendering. The saved data comes from third-party feeds.
- It must work at phone width (360px) without horizontal scrolling, and in both light and dark colour schemes. Use the existing CSS variables (`--acc`, `--mut`, `--bd`, etc.) and don't hard-code colours.
- Keep the existing behaviour of the sources sheet, the dropdowns, Escape handling and the focus trap unchanged.
- Expected size is roughly 80–100 lines of JS, about 15 lines of CSS and about 2 lines of HTML.

## How to verify
1. Build fixture data offline and serve it:
   ```
   python3 tests/make_fixtures.py
   python3 scripts/fetch_news.py --fixtures tests/fixtures
   cp web/* site/
   python3 -m http.server -d site 8000
   ```
2. Run a Playwright script with Chromium at `/opt/pw-browsers/chromium` (don't run `playwright install`) at a 390×844 viewport and check that:
   - tapping a bookmark fills it, the badge shows 1, and **no new tab/page opens**;
   - the story still shows as saved after a reload;
   - **Saved** lists it under Unread, and **← Feed** goes back;
   - clicking the headline in the Saved view moves it to Read, dims it and lowers the badge to 0;
   - "✓ Read" puts it back in Unread;
   - **Clear read** removes read items after you accept the confirm dialog;
   - a corrupt `localStorage["dailyAInews.saved.v1"] = "x"` doesn't break the page;
   - screenshots in light and dark mode show no overlap between the bookmark and the NEW badge.
3. Run the existing tests: `python3 tests/test_add_source.py` and `python3 tests/test_categories.py`.

## Delivery
Commit on the current feature branch with a clear message, for example "Add Read later: bookmark stories, Saved view, mark read". Push. Don't open a PR unless asked.
