#!/usr/bin/env python3
"""
Jackson Roofing SOCIAL PRESENCE - plan-stats summary (Wing-owned, DRAFT-ONLY).

A scheduler needs machine-readable files (see export.py); a client report and the
command-center header need plain PLAN STATS. This lane reads the curated draft queue
(../data/posts.json) plus the cadence config (../data/schedule.json) and writes a
single small file a UI or a report can consume:

  social/data/exports/summary.json

Everything in it is a COUNT of drafted posts, never a performance metric. There is no
reach, no impressions, no leads, no engagement here - those would be fabricated for a
draft-only portfolio asset. The "plan overview" line says exactly that in plain words.

Fields written:
  post_count          total posts in the queue
  date_range          {start, first, last} (first/last = earliest/latest post date)
  weeks               whole weeks the plan spans (inclusive)
  posts_per_week      post_count / weeks, rounded to 1 dp (planning cadence, not a metric)
  per_platform        {platform: count}
  per_pillar          {pillar: count}
  video_count         posts whose pillar is 'video' (short-form video / Reels)
  platforms           sorted list of distinct platforms
  pillars             sorted list of distinct pillars
  cadence_slots       number of weekly cadence slots defined in schedule.json (if present)
  plan_overview       one honest sentence describing the plan (counts, not results)

DRAFT-ONLY: reads posts.json/schedule.json, writes one local JSON file. Never posts,
sends, or touches any live account. No network. Stdlib only. Deterministic.

Run:  python social/engine/build_summary.py           (writes + prints a short summary)
      python social/engine/build_summary.py --json     (writes + prints the JSON it wrote)
"""

import datetime
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCIAL_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SOCIAL_DIR, "data")
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
SUMMARY_PATH = os.path.join(EXPORT_DIR, "summary.json")

VIDEO_PILLARS = {"video"}


def _sanitize(text):
    """No em/en dashes ever leak into generated text (brand rule)."""
    if text is None:
        return ""
    return str(text).replace("—", "-").replace("–", "-")


def load_posts(path):
    """Read posts.json robustly. Accepts {"posts":[...]} or a bare [...]. Never raises."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        if not raw:
            return []
        data = json.loads(raw)
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        posts = data.get("posts", [])
    elif isinstance(data, list):
        posts = data
    else:
        posts = []
    return [p for p in posts if isinstance(p, dict)]


def load_schedule(path):
    """Read schedule.json robustly. Returns a dict (possibly empty). Never raises."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        if not raw:
            return {}
        data = json.loads(raw)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_date(date_str):
    try:
        return datetime.datetime.strptime((date_str or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _counts(posts, key):
    out = {}
    for p in posts:
        val = _sanitize(p.get(key) or "unknown").strip() or "unknown"
        out[val] = out.get(val, 0) + 1
    # deterministic ordering: highest count first, then name
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def build_summary(posts, schedule):
    """Build the summary dict from posts + schedule config. Pure, no I/O."""
    post_count = len(posts)

    dates = sorted(d for d in (_parse_date(p.get("date")) for p in posts) if d)
    if dates:
        first, last = dates[0], dates[-1]
        span_days = (last - first).days
        weeks = max(1, (span_days // 7) + 1)
        date_range = {
            "start": first.isoformat(),
            "first": first.isoformat(),
            "last": last.isoformat(),
        }
    else:
        first = last = None
        weeks = 0
        date_range = None

    per_platform = _counts(posts, "platform")
    per_pillar = _counts(posts, "pillar")
    video_count = sum(1 for p in posts
                      if (_sanitize(p.get("pillar")).strip().lower() in VIDEO_PILLARS))

    posts_per_week = round(post_count / weeks, 1) if weeks else 0.0

    cadence = schedule.get("cadence") if isinstance(schedule, dict) else None
    cadence_slots = len(cadence) if isinstance(cadence, list) else None

    platforms = sorted(per_platform.keys())
    pillars = sorted(per_pillar.keys())

    if post_count == 0:
        overview = ("No posts drafted yet. This is a draft-only plan; all figures are "
                    "counts of drafted posts, not performance data.")
    else:
        span_txt = ""
        if date_range:
            span_txt = " from %s to %s (%d week%s)" % (
                date_range["first"], date_range["last"], weeks, "" if weeks == 1 else "s")
        overview = ("%d drafted posts across %d platform%s%s, about %s posts per week. "
                    "All figures are counts of drafted posts, not performance data."
                    % (post_count, len(platforms), "" if len(platforms) == 1 else "s",
                       span_txt, posts_per_week))

    return {
        "generated_by": "social/engine/build_summary.py",
        "source": "../data/posts.json",
        "draft_only": True,
        "post_count": post_count,
        "date_range": date_range,
        "weeks": weeks,
        "posts_per_week": posts_per_week,
        "per_platform": per_platform,
        "per_pillar": per_pillar,
        "video_count": video_count,
        "platforms": platforms,
        "pillars": pillars,
        "cadence_slots": cadence_slots,
        "plan_overview": overview,
    }


def write_summary(summary, path=SUMMARY_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")
    return path


def build(posts_path=None):
    """Read inputs, build + write summary.json. Returns (summary_dict, path)."""
    posts = load_posts(posts_path or POSTS_PATH)
    schedule = load_schedule(SCHEDULE_PATH)
    summary = build_summary(posts, schedule)
    path = write_summary(summary)
    return summary, path


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    summary, path = build()
    if as_json:
        print(json.dumps(summary, indent=2))
        return 0
    print("Jackson Roofing social plan summary (DRAFT-ONLY, counts not metrics)")
    print("  source        : %s" % POSTS_PATH)
    print("  posts          : %d" % summary["post_count"])
    dr = summary["date_range"]
    if dr:
        print("  date range     : %s to %s (%d weeks)"
              % (dr["first"], dr["last"], summary["weeks"]))
    print("  posts / week   : %s" % summary["posts_per_week"])
    print("  platforms      : %s" % ", ".join("%s %d" % (k, v)
                                              for k, v in summary["per_platform"].items()))
    print("  pillars        : %d (%s)" % (len(summary["pillars"]),
                                          ", ".join(summary["pillars"])))
    print("  video posts    : %d" % summary["video_count"])
    print("  summary.json   : %s" % path)
    print("\n  " + summary["plan_overview"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
