<div align="center">

# 📍 GBP Post Generator

### Google Business Profile posts that never look the same twice.

A small local web app that turns **a photo + a page link** into a ready-to-paste Google Business Profile post,
using the Gemini API and your own writing rules.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini%20API-free%20tier%20ready-4285F4?logo=google&logoColor=white)
![Runs locally](https://img.shields.io/badge/runs-100%25%20locally-2ea44f)
![Tests](https://img.shields.io/badge/tests-112%20passing-brightgreen)

[Quick start](#-quick-start) · [How it works](#-how-it-works) · [Style options](#-style-options) · [Rule checks](#-rule-checks) · [Settings](#-settings) · [FAQ](#-faq)

</div>

---

## ✨ Why you will like it

| | |
|---|---|
| 🎲 **Always fresh** | Layout, opener, closer, length and tone rotate at random, so a client's posts never repeat a structure. |
| 🗺️ **Sitemap smart** | Paste a sitemap link and the app picks the page that best fits your photo. |
| 🛡️ **Rule checked** | Every post is verified in code (no dashes, no phone numbers, paragraph count, filename rules) and auto-fixed if it fails. |
| 🧠 **Remembers each client** | Stores past layouts, openers, closers and filenames per client, and sends them to Gemini to avoid repeats. |
| 📋 **Paste-ready steps** | Photo name, post text and button link come in the order Google Business Profile asks for them, each with a copy button. |
| 🔒 **Private** | Everything runs on your computer. Your key and history never leave it (except the Gemini request itself). |

---

## 🚀 Quick start

> You need **Python 3.10+** and a free Gemini key from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
# 1. Create an environment and install
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Mac / Linux
pip install -r requirements.txt

# 2. Add your key
copy .env.example .env            # Windows   (Mac / Linux: cp .env.example .env)
# open .env and paste your key after GEMINI_API_KEY=

# 3. Run
python app.py
```

Then open **http://127.0.0.1:5000** 🎉

---

## 🧭 How it works

```
 ┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ 1. Pick a   │ → │ 2. Add page  │ → │ 3. Generate  │ → │ 4. Copy 3    │
 │    client   │   │    link and  │   │    (Ctrl +   │   │    steps into│
 │             │   │    photo     │   │     Enter)   │   │    Google    │
 └─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### The result panel gives you three steps

| Step | What you get | Buttons |
|---|---|---|
| **1 · Photo** | A short SEO file name, for example `drain-cleaning-knoxville-tn.jpg` | Copy name, Download photo |
| **2 · Post text** | Editable text. Edits save by themselves and the rules re-check | Copy text |
| **3 · Button link** | The page the post points to | Copy link, Open page |

Each step gets a ✅ tick when you copy it, so you always know what is already pasted.
For **Offer** and **Event** posts, an extra step lists the title, dates, coupon code and terms, each with its own copy button.

### Smart tools under the post

- 😀 **Emojis**: click one to swap it, or **+ Add emoji** at your cursor. Describe what you want and Gemini suggests 8 matches.
- ¶ **Paragraphs**: rewrite with exactly 3, 4, 5 or 6 paragraphs.
- 🔀 **Change layout**: rewrite in any of the 20 layouts, or hit **Random layout**.
- ✏️ **Change something**: one-click chips (shorter, longer, new opening line) or type your own wording.
- 🕘 **History**: every client's earlier posts, with thumbnails and search.

### 🗺️ Sitemap links

Paste a sitemap instead of a page link, for example `https://client-site.com/sitemap.xml`.
The app reads it (including sitemap indexes), asks Gemini to choose the page that fits your photo, avoids pages the client's recent
posts already used, and uses that page as the button link. Other close matches are listed in the Notes.
This costs one extra Gemini request per post.

### 🖼️ Photo and page don't match?

Nothing is written or saved. You choose: **another photo**, **another page**, or **write it anyway**.

---

## 🎛️ Style options

The **Style** bar sits under the top bar. Each option can be **Auto**, **Random** or a specific choice.
Options you set get a teal outline, and your choices are remembered.

| Option | Choices |
|---|---|
| **Post type** | Update (What's New), Offer, Event |
| **Layout** | Any of the 20 layouts in `system_prompt.txt` |
| **Length** | Short (250 to 450) · Standard (500 to 800) · Long (900 to 1200 characters) |
| **Opener** | Plain statement · Question hook · Three fragments · Scene from the photo · "Did you know" |
| **Closer** | Point to the page · Invite details · Reassurance · Short question · Short command |
| **Tone** | Friendly · Professional · Educational · Direct |
| **Emojis** | Exactly 1, 2, 3 or 4 |

> **🎲 Auto is random.** Layout, opener, closer, length and tone left on Auto are picked by the app, avoiding the client's
> recent layouts and the last layouts used for any client. Set `GBP_RANDOMIZE_AUTO=0` to let Gemini decide instead.

**Randomize all** sets everything to Random. **Reset** sets everything back to Auto.

<details>
<summary><b>More about random picks and post types</b></summary>

- **Random layout** avoids the client's last 3 layouts and the last 3 used for any client. It never picks the "patient or customer story" layout, because that needs a real story as source material.
- **Post type has no Random.** An Offer needs a real offer with dates, and an Event needs a real dated event, so a random pick would push Gemini to invent one.
- Choosing **Offer** or **Event** opens a details box. What you type is sent as confirmed facts and must be used.
- Leave the box empty and Gemini writes an Offer or Event only if the page has a real one. Otherwise it writes an Update and shows a yellow warning.
- **Update** forces a regular update even if the page mentions a sale.
- **Random opener** skips the question hook if one of the last 3 posts opened with a question.
- A layout you choose yourself may repeat the client's last layout. That shows a yellow warning, not an error.
- **Generate another** keeps your options. With Random they are picked again.

</details>

---

## ✅ Rule checks

Gemini is asked to follow your rules, then the server **verifies them in code**. If a check fails, the app asks Gemini to fix it
(up to `MAX_FIX_ATTEMPTS`, default 2) before you see anything.

| Check | Rule |
|---|---|
| ¶ Paragraphs | At least 3, with a blank line between each |
| ✂️ Dashes | No em dashes or en dashes |
| 📵 Contact info | No phone numbers, emails, URLs or domain names in the post body |
| 🔤 Formatting | No markdown (asterisks, backticks, headers) |
| 🚫 Banned phrases | No "Learn More" or "Call Now" |
| 😀 Emojis | 1 to 4, none stacked, post under 1,500 characters |
| 🏷️ Filename | 3 to 5 words, under 45 characters, Title Case, no filler words, no hyphens or extension, never reused for that client |
| 🔁 Layout | Differs from the client's most recent post |
| 🎤 Opener and closer | No question opener if one of the last 3 did, and no near-copies of recent openers or closers |

A post that still fails shows a **red banner** and stays out of the history sent to Gemini until you click **Keep anyway**.
Price mentions, very long or short posts and recently used layouts show **yellow warnings**.

### 🔁 How repeats are avoided

For each client the app stores layout, opener, closer, filename and length. Every request includes the client's last 5 posts,
every filename ever used for that client, and the last 3 layouts used across all clients.
Delete a post from History if you did not publish it, so it does not count against future rotation.

---

## ⚙️ Settings

Copy `.env.example` to `.env`. **Never commit `.env`.**

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | none | Your key from Google AI Studio |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Main model (optional) |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Tried if the main model is rate limited or unavailable |
| `GEMINI_TEMPERATURE` | `0.9` | 0.8 to 1.0 gives good variety |
| `MAX_FIX_ATTEMPTS` | `2` | Automatic fix rounds per post |
| `GBP_RANDOMIZE_AUTO` | `1` | `0` lets Gemini decide options left on Auto |
| `GBP_DATA_DIR` | `./data` | Where the history database and photos live |

✏️ **To change the writing rules, edit `system_prompt.txt` and restart.** The layout names the app recognizes are read from the
"Layout library" list in that file.

<details>
<summary><b>Free tier notes</b></summary>

- Google no longer publishes per-model free limits in its docs. Your limits are shown in the AI Studio rate-limit console. Free keys allow only a handful of requests per minute, so the app waits, retries, then tries the fallback model. If you see a quota message, wait a minute or until the next day.
- On the free tier, Google may use your prompts and responses to improve its products. Business names, addresses and public page text are fine for most agencies, but do not send photos of customers or patients, or anything confidential, through a free key. A paid key does not have this restriction.
- Not every key has free quota for every model. A model with no free quota for your key is skipped automatically.

</details>

<details>
<summary><b>Models and retirements</b></summary>

Google retires models regularly. The app copes with this:

1. It tries `GEMINI_MODEL`, then the fallbacks.
2. If none exist for your key, it asks the API which Flash models your key can call and tries the best ones.
3. It remembers the model that worked until you restart.
4. If nothing works, the error lists what it tried and what your key can use.

Run `python list_models.py` to see exactly what your key can use, then pin one with `GEMINI_MODEL=` in `.env`.

</details>

---

## 🗂️ Project structure

```
├── app.py               Web server and API
├── service.py           Prompt building, Gemini call, auto-fix loop, saving
├── gemini_client.py     Gemini SDK call, retries, model fallback and discovery
├── sitemap.py           Reads a sitemap and picks the page that fits the photo
├── options.py           Layout, length, opener, closer, tone, emoji options and the random picker
├── validators.py        Server-side rule checks
├── output_parser.py     Reads Gemini's output
├── layouts.py           Layout library, read from system_prompt.txt
├── scraper.py           Fetches and cleans the CTA page, fixes URL typos like hhttps://
├── images.py            Fixes photo rotation and shrinks photos before sending
├── emoji_ai.py          Emoji suggestions
├── db.py                SQLite storage (data/history.db)
├── list_models.py       Shows which models your key can use
├── system_prompt.txt    Your writing rules and the 20 layouts
├── templates/index.html The interface
└── tests/               Automated tests, no API key needed
```

---

## 🧪 Tests

The tests use a fake Gemini, so they need no key and no internet.

```bash
python -m unittest discover -s tests -t .
```

---

## 💾 Backups

Copy the `data` folder. It holds `history.db` and the photos used for edits.

---

## ❓ FAQ

**Is my API key safe?**
It lives only in your local `.env`, which is git-ignored. The app talks to Google directly from your computer.

**Why did my post get a red banner?**
It broke one of the rule checks even after the auto-fix attempts. Read the banner, edit the text (the checks re-run as you type), or click **Keep anyway**.

**Can I use my own rules?**
Yes. Edit `system_prompt.txt`, restart, and the app picks up your new rules and layout list.

**Why does a sitemap post use more requests?**
One request picks the page, a second writes the post. On the free tier that counts toward your daily limit.

---

<div align="center">

Built for local SEO agencies who write a lot of Google Business Profile posts. ⭐ Star the repo if it saves you time.

</div>
