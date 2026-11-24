"""Shared sample posts and a builder for Gemini-style output used by the tests."""

POST_A = (
    "Slow drains in Knoxville? Here is what is usually behind them. \U0001F6BF\n\n"
    "Grease, hair, and roots build up inside the line over time. A quick camera look shows what is really going on. \U0001F527\n\n"
    "Send us a note about your drain and we will suggest a next step."
)
POST_B = (
    "Roots in the sewer line are one of the most common causes of repeat clogs. \U0001F333 "
    "Our crew locates the blockage, clears it, and shows you the camera footage afterward.\n\n"
    "We serve homes across Knox County. ✅\n\n"
    "Take a look at the service page for the full list of drain services."
)
POST_C = (
    "Gurgling pipes, slow sinks, and strange smells all point to a line that needs attention. \U0001F6B0 "
    "We inspect first, then clear only what needs clearing.\n\n"
    "Our team works across Knox County. \u2705\n\n"
    "Tell us what you are seeing and we will help you sort out the cause."
)


POST_QA = (
    "Q: Why does my drain keep clogging? \U0001F6BF\n"
    "A: Hair and grease build up inside the line over time.\n\n"
    "Q: Can tree roots cause it? \U0001F333\n"
    "A: Yes, roots can work their way into older sewer lines.\n\n"
    "Q: What should I do first?\n"
    "A: Send us the details and we will suggest a next step."
)
QA_LAYOUT = "Mini Q&A (3 or 4 question and answer lines)"


def make_output(post, filename, layout="Problem, then solution", status="Match", pct=92,
                cta="https://example.com/drain-cleaning", notes=None):
    out = f"""A. Image and CTA Match Analysis
Match Status: {status}
Match Percentage: {pct}%
Reason: The photo shows a plumber at a sink and the page covers drain cleaning. It does not show a finished repair.

B. GBP Post Details
Post Type: Update
Post Text:
```
{post}
```
CTA URL: {cta}

C. Image Filename
```
{filename}
```

D. Layout Used
Layout: {layout}: the post is structured around that pattern.
Last used: Never used for this client.
Approx. Character Count: {len(post)} (short)
"""
    if notes:
        out += "\nNotes:\n" + "\n".join(f"- {n}" for n in notes) + "\n"
    return out


MISMATCH_OUTPUT = """A. Image and CTA Match Analysis
Match Status: Mismatch
Match Percentage: 20%
Reason: The photo shows a kitchen remodel but the page covers drain cleaning.

Options:
1. Send a different image that fits the page
2. Send a different CTA page that fits the image
3. Proceed anyway (not recommended)
"""
