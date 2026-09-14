#!/usr/bin/env python3
"""
draft_social.py - Jackson Roofing social content engine (Wing-owned, DRAFT-ONLY).

Reads social/data/schedule.json (cadence + 4-week pillar rotation) and writes
platform-native post DRAFTS to social/data/posts.json in the shared schema that
the command-center UI and other content agents rely on.

HARD BOUNDARY: this never posts or sends anything. It only writes local JSON.
It references no real GBP/Facebook/Instagram/Nextdoor account or API. If a live
account were ever passed as a post target, that is out of scope for this tool.

Design:
  - stdlib only in the default path (fast, dependency-light, always valid JSON).
  - Deterministic local template generator is the DEFAULT, so a run never needs
    network access and never hard-fails.
  - Optional --use-router degrades gracefully to templates if the free-model
    router (ghl-cli/llm_router.py) is unavailable or errors. Never hard-fails.
  - If social/data/posts.json already exists (another agent owns it this round),
    we do NOT overwrite it: we write social/data/posts.sample.json instead.

Usage:
  python social/engine/draft_social.py                 # 4 weeks of drafts -> posts.json (or .sample.json)
  python social/engine/draft_social.py --weeks 2       # fewer weeks
  python social/engine/draft_social.py --dry-run       # counts only, writes nothing
  python social/engine/draft_social.py --use-router    # try free-model captions, fall back to templates
  python social/engine/draft_social.py --force         # overwrite posts.json even if it exists
"""

import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOCIAL_DIR = os.path.dirname(HERE)
DATA_DIR = os.path.join(SOCIAL_DIR, "data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")
SAMPLE_PATH = os.path.join(DATA_DIR, "posts.sample.json")

WEEKDAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

GEO_HASHTAG = {
    "Plano TX": "#PlanoTX", "Allen TX": "#AllenTX", "McKinney TX": "#McKinneyTX",
    "Frisco TX": "#FriscoTX", "Wylie TX": "#WylieTX",
}
TRADE_TAGS = ["#Roofing", "#RoofRepair", "#RoofReplacement", "#HailDamage",
              "#StormDamage", "#RoofingContractor"]
TRUST_TAGS = ["#FamilyOwned", "#LocalBusiness", "#Since2000", "#NorthTexas", "#DFW"]

# Deterministic caption templates per pillar. {city} is filled per post.
# No em dashes, no phone-number CTAs, no fabricated numbers.
TEMPLATES = {
    "storm": [
        "Storms moved through {city} again. If you heard hail on the roof, it is worth a look before small dents turn into leaks. We have been checking North Texas roofs since 2000 and can walk you through what we find. Contact us on the site to set up an inspection.",
        "After a hail event in {city}, the damage is not always something you can see from the ground. A quick, honest inspection tells you whether you have a real claim or nothing to worry about. Reach out through our site and we will take a look.",
    ],
    "beforeafter": [
        "Another {city} roof, done right. Worn shingles and tired flashing on the way in, a clean, sealed roof on the way out. Family run since 2000 and still proud of every job. See more of our work and contact us on the site.",
        "Before and after from a recent {city} replacement. Same house, very different roof. This is the kind of work two decades in North Texas teaches you to do right the first time.",
    ],
    "trust": [
        "We have been on North Texas roofs since 2000, and we are still a family business in {city}. That means the person who looks at your roof is the person who stands behind the work. Contact us on the site anytime.",
        "Roofing is a trust business. In {city} and across North Texas, our name has been on the work since 2000. No pressure, no surprises, just honest answers about your roof.",
    ],
    "education": [
        "Homeowner tip: after a {city} hail storm, check your gutters and downspouts for shingle granules that look like coarse sand. A lot of buildup can be an early sign of hail damage. Not sure what you are seeing? Contact us on the site.",
        "Repair or replace? In {city} it usually comes down to the age of the roof and how widespread the damage is. A roof under ten years old with isolated damage is often a repair. We will give you a straight answer, not a sales pitch.",
    ],
    "community": [
        "Proud to work in {city} and the neighborhoods around it. Family run, North Texas since 2000. If a neighbor ever asks who to trust with a roof, we would be glad to help. Contact us on the site.",
        "{city} has been part of our story for years. We like being the roofer your neighbors already know. Say hello or ask a question through our site anytime.",
    ],
    "reviews": [
        "Nothing means more than hearing a {city} homeowner felt taken care of. Reviews like that are why we have kept at this since 2000. Thank you for trusting us with your roof.",
        "A recent note from a {city} customer reminded us why we do this. Honest work, clear communication, and a roof that holds up. If you want that experience, contact us on the site.",
    ],
    "seasonal": [
        "Seasonal reminder for {city} homeowners: a quick roof check now can save you a headache when the next North Texas storm rolls in. Loose flashing and lifted shingles are easy to miss. We are happy to take a look, contact us on the site.",
        "This is a good time of year in {city} to clear gutters and check for any lifted or missing shingles before the weather turns. Small fixes now beat big repairs later. Questions? Reach us through the site.",
    ],
}

# Deterministic image picks per pillar (relative to the social command center).
# These reference local asset slots the UI/asset agent owns, not live URLs.
IMAGE_BY_PILLAR = {
    "storm": ("assets/img/storm-roof.jpg", "Storm clouds over a North Texas neighborhood roofline"),
    "beforeafter": ("assets/img/before-after.jpg", "Before and after of a completed roof replacement"),
    "trust": ("assets/img/crew.jpg", "Jackson Roofing crew on a residential job"),
    "education": ("assets/img/inspection.jpg", "Close inspection of shingles for hail damage"),
    "community": ("assets/img/neighborhood.jpg", "Residential North Texas neighborhood street"),
    "reviews": ("assets/img/review-card.jpg", "Homeowner review highlight card"),
    "seasonal": ("assets/img/gutter-check.jpg", "Seasonal roof and gutter maintenance check"),
}

CTA_BY_PLATFORM = {
    "gbp": "Learn more on our site",
    "facebook": "Contact Us on our site",
    "instagram": "Contact Us via the link in bio",
    "nextdoor": "Contact Us on our site",
}


def log(msg):
    print(msg, file=sys.stderr)


def load_schedule():
    with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def next_date_for_weekday(start, weekday_name):
    """First date on/after `start` that falls on the given weekday."""
    target = WEEKDAY_INDEX[weekday_name]
    delta = (target - start.weekday()) % 7
    return start + dt.timedelta(days=delta)


def build_hashtags(platform, pillar, city):
    if platform in ("gbp", "nextdoor"):
        return []  # hashtags are noise on these surfaces
    tags = []
    geo = GEO_HASHTAG.get(city)
    if geo:
        tags.append(geo)
    # rotate trade tags by pillar so blocks are not identical every time
    pillar_seed = sum(ord(c) for c in pillar)
    tags.append(TRADE_TAGS[pillar_seed % len(TRADE_TAGS)])
    tags.append(TRADE_TAGS[(pillar_seed + 2) % len(TRADE_TAGS)])
    tags.append(TRUST_TAGS[pillar_seed % len(TRUST_TAGS)])
    if platform == "facebook":
        tags = tags[:2]  # keep Facebook light
    # de-dupe, preserve order
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def strip_em_dashes(text):
    return text.replace("—", ", ").replace("–", "-").replace(" -- ", ", ")


def template_caption(pillar, city, variant):
    opts = TEMPLATES.get(pillar) or TEMPLATES["community"]
    return opts[variant % len(opts)].format(city=city)


def router_caption(pillar, city, platform, fallback):
    """Try the free-model router for a caption; fall back to template on any issue."""
    try:
        sys.path.insert(0, os.path.join(os.path.expanduser("~"), "ghl-cli"))
        import llm_router  # noqa
    except Exception as e:
        log(f"  router unavailable ({str(e)[:60]}), using template")
        return fallback
    system = ("You write short, honest social captions for a family-run North Texas "
              "roofer (Jackson Roofing, serving since 2000). No em dashes. No phone "
              "numbers. No fabricated numbers or ratings. End by pointing to the site "
              "to Contact Us. Plain, local, trustworthy voice.")
    prompt = (f"Platform: {platform}. Pillar: {pillar}. City: {city}. "
              f"Write one caption of 2-4 sentences. Draft only.")
    try:
        res = llm_router.generate("voice", prompt, system=system, temperature=0.7, max_tokens=220)
        out = (res or {}).get("output", "").strip()
        if not out or "error" in (res or {}):
            return fallback
        return strip_em_dashes(out)
    except Exception as e:
        log(f"  router error ({str(e)[:60]}), using template")
        return fallback


def generate_posts(schedule, weeks, use_router):
    cadence = schedule["cadence"]
    geo = schedule.get("geo", ["Plano TX"])
    today = dt.date.today()
    # anchor to the Monday of the current week
    week0_monday = today - dt.timedelta(days=today.weekday())

    posts = []
    for w in range(weeks):
        week_monday = week0_monday + dt.timedelta(weeks=w)
        for i, slot in enumerate(cadence):
            platform = slot["platform"]
            pillar = slot["pillar"]
            post_date = next_date_for_weekday(week_monday, slot["weekday"])
            # rotate city across the 4-week cycle and slot index so coverage spreads
            city = geo[(w + i) % len(geo)]
            variant = (w + i)
            fallback = template_caption(pillar, city, variant)
            caption = router_caption(pillar, city, platform, fallback) if use_router else fallback
            caption = strip_em_dashes(caption)
            img_src, img_alt = IMAGE_BY_PILLAR.get(pillar, IMAGE_BY_PILLAR["community"])
            posts.append({
                "id": f"jr-{post_date.isoformat()}-{platform}-{pillar}",
                "platform": platform,
                "pillar": pillar,
                "date": post_date.isoformat(),
                "time": slot["time"],
                "caption": caption,
                "hashtags": build_hashtags(platform, pillar, city),
                "cta": CTA_BY_PLATFORM.get(platform, "Contact Us on our site"),
                "image": {"src": img_src, "alt": img_alt, "credit": "Jackson Roofing"},
                "geo": city,
            })
    posts.sort(key=lambda p: (p["date"], p["time"]))
    return posts


def summarize(posts):
    by_platform, by_pillar = {}, {}
    for p in posts:
        by_platform[p["platform"]] = by_platform.get(p["platform"], 0) + 1
        by_pillar[p["pillar"]] = by_pillar.get(p["pillar"], 0) + 1
    return by_platform, by_pillar


def main():
    ap = argparse.ArgumentParser(description="Jackson Roofing social content engine (draft-only).")
    ap.add_argument("--weeks", type=int, default=4, help="Weeks of drafts to generate (default 4).")
    ap.add_argument("--dry-run", action="store_true", help="Print counts, write nothing.")
    ap.add_argument("--use-router", action="store_true", help="Try free-model captions, fall back to templates.")
    ap.add_argument("--force", action="store_true", help="Overwrite posts.json even if it exists.")
    args = ap.parse_args()

    if not os.path.exists(SCHEDULE_PATH):
        log(f"ERROR: schedule not found at {SCHEDULE_PATH}")
        return 1

    schedule = load_schedule()
    posts = generate_posts(schedule, max(1, args.weeks), args.use_router)
    doc = {"generated": dt.datetime.now().astimezone().isoformat(), "posts": posts}

    by_platform, by_pillar = summarize(posts)
    log(f"Generated {len(posts)} drafts over {args.weeks} week(s).")
    log(f"  by platform: {by_platform}")
    log(f"  by pillar:   {by_pillar}")

    if args.dry_run:
        log("Dry run: nothing written.")
        print(json.dumps({"count": len(posts), "by_platform": by_platform, "by_pillar": by_pillar}))
        return 0

    # Never clobber posts.json if another agent already owns it this round.
    if os.path.exists(POSTS_PATH) and not args.force:
        out_path = SAMPLE_PATH
        log(f"posts.json exists; writing to {out_path} instead (use --force to overwrite).")
    else:
        out_path = POSTS_PATH

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    log(f"Wrote {len(posts)} drafts to {out_path}")
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
