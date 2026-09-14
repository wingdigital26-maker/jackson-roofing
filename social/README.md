# Jackson Roofing — Social System

A Wing-owned, **draft-only** social media system for Jackson Roofing (family-run
Plano roofer, North Texas since 2000). This is a portfolio / win-back asset.
Chris Jackson is not an active client.

## Draft-only boundary (non-negotiable)

- **Nothing here posts or sends.** The engine only writes local JSON drafts.
- It touches **no** real Google Business Profile, Facebook, Instagram, Nextdoor,
  WordPress, or `jacksonroofingco.com` account or API.
- No phone-number CTAs (use "Contact Us" / the site link). No fabricated numbers
  or ratings. No em dashes. No status/live dots in any UI.

## Layout

```
social/
  STRATEGY.md          The roofing social playbook (pillars, cadence, geo, hashtags)
  README.md            This file
  data/
    schedule.json      Cadence + 4-week pillar rotation config (drives the engine)
    posts.json         Generated drafts (the shared queue the UI reads)
    posts.sample.json  Written instead of posts.json when posts.json already exists
  engine/
    draft_social.py    The drafting engine (stdlib only by default)
  posts/               (owned by the content/UI lane, not the engine)
  assets/              (owned by the asset lane, not the engine)
```

## Running the engine

```bash
# 4 weeks of drafts -> data/posts.json (or posts.sample.json if it exists)
python social/engine/draft_social.py

# preview counts only, write nothing
python social/engine/draft_social.py --dry-run

# fewer weeks
python social/engine/draft_social.py --weeks 2

# try the free-model router for captions (falls back to templates on any issue)
python social/engine/draft_social.py --use-router

# overwrite data/posts.json even if it already exists
python social/engine/draft_social.py --force
```

- **Dependency-light:** stdlib only in the default path. Fast (well under a
  second for 4 weeks / 40 drafts). No network calls unless `--use-router`.
- **Never hard-fails:** the deterministic template generator is the default and
  always produces valid JSON matching the schema below. `--use-router` degrades
  gracefully to templates if `ghl-cli/llm_router.py` is missing or errors.
- **Safe by default:** if `data/posts.json` already exists (another agent owns
  it this round), the engine writes `data/posts.sample.json` instead of
  overwriting it. Pass `--force` only when you intend to replace it.

## posts.json schema (shared contract)

Keep this exact shape so the command-center UI and content agents stay in sync:

```json
{
  "generated": "<iso timestamp>",
  "posts": [
    {
      "id": "string (unique, e.g. jr-2026-09-15-gbp-seasonal)",
      "platform": "gbp | facebook | instagram | nextdoor",
      "pillar": "storm | beforeafter | trust | education | community | reviews | seasonal",
      "date": "YYYY-MM-DD",
      "time": "HH:MM",
      "caption": "string (platform-native, no em dashes, no phone CTA)",
      "hashtags": ["#..."],
      "cta": "string",
      "image": { "src": "relative or https url", "alt": "string", "credit": "string" },
      "geo": "Plano TX"
    }
  ]
}
```

Notes:
- `hashtags` is empty for `gbp` and `nextdoor` (hashtags are noise there).
- `image.src` is a relative asset slot the UI/asset lane owns; the engine never
  fetches or embeds live media.
- Pillars and cadence are defined in `data/schedule.json`, not hardcoded, so the
  strategy and the engine cannot drift apart.
