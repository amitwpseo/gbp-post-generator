# GBP Post Generator

A small local web app that writes Google Business Profile posts with the Gemini API, using your system prompt
(`system_prompt.txt`). It sends the photo, the CTA page text and the client's post history with every request, so
Gemini rotates layouts, openers, closers and filenames. Everything runs on your own computer.

## Quick start

1. Install Python 3.10 or newer.
2. In this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (Windows)      source .venv/bin/activate   (Mac/Linux)
   pip install -r requirements.txt
   ```
3. Get a free key at https://aistudio.google.com/apikey, then copy `.env.example` to `.env` and paste the key
   after `GEMINI_API_KEY=`.
4. Start it:
   ```
   python app.py
   ```
5. Open http://127.0.0.1:5000

## Using it

1. Top bar: pick a client, or click **Add client** (name, address, phone, website, GBP link). Use **Rules for this
   business** for things that always apply, for example "real estate buyer" or "chiropractor: no result claims".
   **Edit client** changes or deletes it.
2. Left side, **Post details**: enter the page the button links to (the **Copy** button next to it copies the link), add the photo (click, drop, or paste it), and press
   **Generate post** (or Ctrl+Enter). **Start new post** (top of the form, and on each result) clears the link, photo,
   notes and result so you can begin the next one. Your style choices stay. The page text is fetched for you. If a page cannot be read, the paste box opens.
3. Right side, **Result**: the top shows the post type, the layout and when that layout was last used for the
   client, plus a line with the style choices you asked for. Below that come numbered steps in the order Google Business Profile asks for them.
   - **1 Photo**: a short SEO file name (main service keyword, city, state), shown as the title and as the real file
     name in lowercase with hyphens (for example `drain-cleaning-knoxville-tn.jpg`). **Copy name** copies the file name
     and **Download photo** saves the photo under it.
   - For an Offer or Event post, an extra step lists the offer or event details (title, dates, coupon code, terms),
     each with **Copy**, because Google asks for them in separate fields.
   - **2 Post text**: editable. Your edits save by themselves and the rules are checked again. **Copy text**.
   - **3 Button link**: **Copy link** or **Open page**.
   Each step gets a yellow tick and highlight when you copy it, so you can see what is already pasted.
4. **Generate another** makes a new post with a different layout, opener, closer and filename.
5. Under the post text, **Emojis** shows each emoji as a button. Click one to replace it, or press **+ Add emoji** to
   insert one **at your cursor** (click in the text where you want it first; the panel shows where it will go, and the
   cursor moves after each new emoji so you can add several in a row). To choose the emoji:
   - **Describe the emoji you want** and press **Find emoji**: Gemini returns the 8 best matches (one small request on
     your free key, no post rewrite).
   - **Ideas for this post**: mostly recent emoji (Unicode 12 to 15.1) matched to the business type; **More ideas**
     shows the next set.
   - **Type or paste** any emoji yourself (Windows: Win + . opens the emoji picker).
   Edits save by themselves and the rules are checked again.
6. **Paragraphs** rewrites the post with exactly 3, 4, 5 or 6 paragraphs. **Change layout** rewrites it in any of the
   20 layouts (or **Random layout**, which skips this post's layout, the client's recent ones and the story layout),
   keeping the photo, facts and link. **Change something** has one-click chips (shorter, longer, new opening line, and so on) and a box for your own
   wording.
7. If the photo does not fit the page, nothing is written or saved. You choose: another photo, another page, or write
   it anyway.
8. **History** lists the client's earlier posts with thumbnails and search. Open, copy or delete any of them.

The **Style** bar sits right under the top bar: post type, layout, length, opener, closer, tone and emojis in one row. Any option
not on Auto gets a teal outline and dot, and the summary next to "Style" counts what you set. On a phone the bar folds
into one line; tap **Change** to open it. Your choices are remembered.

## Post options

In the **Style** bar there are seven options. Each one has **Auto** (Gemini decides, the default), **Random** (the app picks),
or a specific choice. **Randomize all** sets every option to Random, **Reset** sets them back to Auto.

| Option | Choices |
|---|---|
| Post type | Update (What's New), Offer, Event (no Random, see below) |
| Layout | any of the 20 layouts in your prompt |
| Length | Short (250 to 450), Standard (500 to 800), Long (900 to 1200 characters) |
| Opener | plain statement, question hook, three fragments, scene from the photo, "Did you know" |
| Closer | point to the page, invite details, reassurance, short question, short command |
| Tone | friendly, professional, educational, direct |
| Emojis | exactly 1, 2, 3 or 4 |

- **Random layout** avoids the client's last 3 layouts and the last 3 used for any client, and never picks the
  "patient or customer story" layout, because that one needs a real story as source material.
- **Post type** has no Random. Your prompt only allows an Offer when the page has a real offer with dates, and an
  Event only for a real dated event, so a random pick would push Gemini to invent one. **Randomize all** leaves post
  type alone.
  - Choosing **Offer** or **Event** opens a details box in the form (title, start, end, plus coupon code and terms for
    offers). What you type is sent to Gemini as confirmed facts and must be used, otherwise the auto-fix runs.
  - Leave the box empty and Gemini writes an Offer or Event only if the page has a real one. If not, it writes an
    Update and says so, and the app shows a yellow warning instead of an error.
  - **Update** forces a regular update even if the page mentions a sale.
- **Random opener** skips the question hook if one of the last 3 posts opened with a question.
- The app chooses random values itself and tells Gemini exactly what to use, then checks the result. If Gemini ignores
  a choice (wrong layout, wrong length, wrong emoji count), it is asked to fix it. The result lists
  "Your style choices" under Layout and post type, with random picks marked.
- A layout you choose yourself may repeat the client's last layout. That shows a yellow warning instead of an error.
- **Generate another** keeps your options. With Random they are picked again, so every click gives something new.

## What the app checks after Gemini answers

Gemini is asked to follow the rules, and the server then verifies them. If a check fails, the app sends Gemini a short
"fix this" message (up to `MAX_FIX_ATTEMPTS`, default 2) before showing you anything.

- At least 3 paragraphs, with a blank line between each (every post, every layout, also after edits)
- No em dashes or en dashes
- No phone numbers, emails, URLs or domain names in the post body
- No markdown (asterisks, backticks, headers)
- No "Learn More" or "Call Now"
- 1 to 4 emojis, none stacked, post under 1,500 characters
- Image filename: short and SEO optimized, Title Case, 3 to 5 words and under 45 characters, no filler words (the, and,
  in, for, your, best), no hyphens, underscores or extension, never reused for that client. The downloaded photo and
  **Copy name** use the SEO form: lowercase with hyphens. Older, longer names in your history are left alone.
- Layout differs from the client's most recent post
- Does not open with a question if one of the last 3 posts did
- Closing and opening lines are not near-copies of the last 3 posts

A post that still fails is shown with a red banner and kept out of the history sent to Gemini until you click
**Keep anyway**. Price mentions, long or short posts and layouts reused within 3 posts show as yellow warnings.

## How repeats are avoided

For each client the app stores layout, opener, closer, filename and length. Every request includes the client's last 5
posts, every filename ever used for that client, and the last 3 layouts used across all clients. Delete a post from the
history if you did not publish it, so it does not count against future rotation.

## Settings (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Your key from Google AI Studio |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Main model (optional, see "Models" below) |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Tried if the main model is rate limited or unavailable |
| `GEMINI_TEMPERATURE` | `0.9` | 0.8 to 1.0 gives good variety |
| `MAX_FIX_ATTEMPTS` | `2` | Automatic fix rounds per post |
| `GBP_DATA_DIR` | `./data` | Where the history database and photos live |

To change the writing rules, edit `system_prompt.txt` and restart. The layout names the app recognizes are read from
the "Layout library" list in that file.

## Free tier notes

- Google no longer publishes per-model free limits in its docs. Your limits are shown in the AI Studio rate-limit
  console. Free keys are limited to a handful of requests per minute, so the app waits and retries on rate-limit
  errors and then tries the fallback model. If you see a quota message, wait a minute (or until the next day).
- On the free tier, Google may use your prompts and responses to improve its products. Business names, addresses and
  public page text are fine for most agencies, but do not send photos of customers or patients, or anything
  confidential, through a free key. A paid key does not have this restriction.
- Not every key has free quota for every model. A model with no free quota for your key is skipped automatically.

## Models

Google retires models regularly (Gemini 2.5 Flash and Flash-Lite were shut down in 2026). The app copes with this:

1. It tries `GEMINI_MODEL`, then the fallbacks.
2. If none exist for your key, it asks the API which Flash models your key can call and tries the best ones, newest
   stable full Flash first.
3. It remembers the model that worked until you restart.
4. If nothing works, the error lists what it tried and what your key can use.

Run `python list_models.py` to see exactly what your key can use. You can then pin one with `GEMINI_MODEL=` in `.env`,
or remove both model lines from `.env` and let the app choose.

## Files

- `app.py`: web server and API
- `service.py`: prompt building, Gemini call, auto-fix loop, saving
- `gemini_client.py`: Gemini SDK call, retries, model fallback and discovery
- `list_models.py`: shows which models your key can use
- `options.py`: the layout, length, opener, closer, tone and emoji options and the random picker
- `output_parser.py`, `validators.py`, `layouts.py`: reading Gemini's output and checking the rules
- `db.py`: SQLite storage (`data/history.db`)
- `scraper.py`: fetches and cleans the CTA page, fixes URL typos like `hhttps://`
- `images.py`: fixes rotation and shrinks photos before sending
- `templates/index.html`: the interface
- `tests/`: automated tests (`python -m unittest discover -s tests -t .`), which use a fake Gemini and need no key

## Backups

Copy the `data` folder. It holds `history.db` and the photos used for edits.

## Random options and sitemap links

- **Auto is now random for variety.** Layout, opener, closer, length and tone left on **Auto** are picked at random by the
  app (avoiding the client's recent layouts and the last layouts used for any client), so a client's first post no longer
  always comes out in the same layout. Set `GBP_RANDOMIZE_AUTO=0` in `.env` to let Gemini decide again.
- **Sitemap in the CTA box.** Paste a sitemap link (for example `https://client-site.com/sitemap.xml`) instead of a page
  link. The app reads it, asks Gemini to pick the page that best fits the photo (avoiding pages the client's recent posts
  used), and uses that page as the button link. The other close matches are listed in the Notes. This costs one extra
  Gemini request per post.
