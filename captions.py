"""Caption generation. Uses the Claude API if ANTHROPIC_API_KEY is set, else a plain template."""
import os

MODEL = "claude-sonnet-5-5"

PROMPT = """You write Instagram captions for a nightly sports recap account.

Date: {date}
Results (the ONLY facts you may use; never invent stats, quotes, injuries, or context):
{digest}

Write one caption:
- First line: a punchy hook (max 90 chars) built around the single most notable result.
- Then 3-6 short lines of the biggest storylines, using only the facts above.
- A closing line inviting people to comment on who had the night.
- Then 8-12 relevant hashtags on a final line.
- Under 1500 characters total. No logos/trademark symbols. Light emoji use only.
Return only the caption text."""


def fallback_caption(digest, date_label):
    lines = [f"Nightly Recap | {date_label}", ""] + digest.splitlines()[:12]
    lines += ["", "Who had the night? Tell us below.", "", "#sports #nightlyrecap #scores #highlights"]
    return "\n".join(lines)


def make_caption(digest, date_label):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback_caption(digest, date_label)
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=900,
            messages=[{"role": "user", "content": PROMPT.format(date=date_label, digest=digest)}],
        )
        return msg.content[0].text.strip()
    except Exception as e:  # network, auth, model name, etc.
        print(f"  ! Claude caption failed ({e}); using template caption")
        return fallback_caption(digest, date_label)
