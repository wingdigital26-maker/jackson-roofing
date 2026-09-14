#!/usr/bin/env python3
"""
Jackson Roofing SOCIAL PRESENCE - shareable standalone plan (Wing-owned, DRAFT-ONLY).

The command center is great at the desk, but a pro often needs to EMAIL the plan to a
client who has no dev server and no tools. This lane turns the curated draft queue
(../data/posts.json, plus ../data/exports/summary.json if present) into ONE self-contained
file that IS the whole plan:

  social/data/exports/plan.html

That file opens with a double-click in any browser, on any machine, with NO dev server
and NO external requests: styles are inlined, fonts are a system stack (pulling a web
font would be an external request), there are NO <script>, NO <link>, and NO <img> tags
(imagery is referenced by concept + filename in text, so the file stays tiny and
emailable). Every post is grouped by week and rendered as a clean card: date, weekday,
platform, pillar, the full caption, hashtags, CTA, and the image concept (filename).

DRAFT-ONLY: reads local JSON, writes one local HTML file. Never posts, sends, or touches
any live account. No network. Stdlib only. Deterministic output.

Run:  python social/engine/build_plan_html.py            (writes plan.html + prints a line)
      python social/engine/build_plan_html.py --json      (writes + prints a small JSON stat)
"""

import datetime
import html
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCIAL_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SOCIAL_DIR, "data")
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
SUMMARY_PATH = os.path.join(EXPORT_DIR, "summary.json")
PLAN_PATH = os.path.join(EXPORT_DIR, "plan.html")

# Brand tokens (from the site DNA): cyan accent, ink text, paper ground.
BRAND_CYAN = "#1bc0ff"
BRAND_INK = "#0b0f14"
BRAND_PAPER = "#f6f8fa"

PLATFORM_LABEL = {
    "gbp": "Google Business Profile",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "nextdoor": "Nextdoor",
}

# Same publish-time hashtag convention export.py uses, so the plan reads truthfully.
NO_HASHTAG_PLATFORMS = {"gbp", "nextdoor"}
FB_MAX_HASHTAGS = 2

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _sanitize(text):
    """No em/en dashes ever leak into generated text (brand rule)."""
    if text is None:
        return ""
    return str(text).replace("—", "-").replace("–", "-")


def esc(text):
    """HTML-escape (after dash sanitize) so &, <, > in captions render correctly."""
    return html.escape(_sanitize(text), quote=True)


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


def load_summary(path):
    """Read summary.json if present. Returns a dict (possibly empty). Never raises."""
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


def _parse_time(time_str):
    try:
        return datetime.datetime.strptime((time_str or "").strip(), "%H:%M").time()
    except (ValueError, TypeError):
        return None


def _fmt_time(time_str):
    """12h label, e.g. '10:00 AM'. Falls back to the raw string if unparseable."""
    t = _parse_time(time_str)
    if not t:
        return _sanitize(time_str).strip()
    hh = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return "%d:%02d %s" % (hh, t.minute, ampm)


def platform_label(platform):
    p = (platform or "").lower()
    return PLATFORM_LABEL.get(p, (p.title() or "Post"))


def pillar_label(pillar):
    """Human label for a pillar slug ('storm-response' -> 'Storm response')."""
    s = _sanitize(pillar).strip().replace("_", " ").replace("-", " ")
    return s[:1].upper() + s[1:] if s else "General"


def hashtags_for_platform(platform, hashtags):
    """Hashtags a platform would actually publish, mirroring export.py convention."""
    platform = (platform or "").lower()
    tags = [_sanitize(h).strip() for h in (hashtags or []) if str(h).strip()]
    if platform in NO_HASHTAG_PLATFORMS:
        return []
    if platform == "facebook":
        return tags[:FB_MAX_HASHTAGS]
    return tags


def _week_key(day, anchor):
    """Zero-based week index of `day` relative to the Monday on/before `anchor`."""
    anchor_monday = anchor - datetime.timedelta(days=anchor.weekday())
    return (day - anchor_monday).days // 7


def _week_range_label(anchor, week_index):
    """'Week 1 - Sep 15 to Sep 21' style label for a week bucket."""
    anchor_monday = anchor - datetime.timedelta(days=anchor.weekday())
    start = anchor_monday + datetime.timedelta(days=7 * week_index)
    end = start + datetime.timedelta(days=6)
    return "Week %d - %s %d to %s %d" % (
        week_index + 1, MONTHS[start.month], start.day, MONTHS[end.month], end.day)


def group_by_week(posts):
    """Return an ordered list of (week_label, [posts]) grouped by calendar week.
    Posts with unparseable dates are collected into a trailing 'Undated' bucket."""
    dated = []
    undated = []
    for p in posts:
        d = _parse_date(p.get("date"))
        if d:
            dated.append((d, p))
        else:
            undated.append(p)
    if not dated and not undated:
        return []
    groups = []
    if dated:
        anchor = min(d for d, _ in dated)
        buckets = {}
        for d, p in dated:
            wk = _week_key(d, anchor)
            buckets.setdefault(wk, []).append((d, p))
        for wk in sorted(buckets):
            rows = sorted(buckets[wk], key=lambda dp: (
                dp[0], _sanitize(dp[1].get("time", "")), _sanitize(dp[1].get("id", ""))))
            groups.append((_week_range_label(anchor, wk), [p for _, p in rows]))
    if undated:
        groups.append(("Undated", undated))
    return groups


def _channel_mix(posts):
    """Ordered '21 Instagram . 17 Facebook ...' string, highest count first."""
    counts = {}
    for p in posts:
        lab = platform_label(p.get("platform"))
        counts[lab] = counts.get(lab, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return " . ".join("%d %s" % (n, lab) for lab, n in ordered)


def _date_range_text(posts, summary):
    dr = summary.get("date_range") if isinstance(summary, dict) else None
    if isinstance(dr, dict) and dr.get("first") and dr.get("last"):
        first = _parse_date(dr["first"])
        last = _parse_date(dr["last"])
    else:
        dates = sorted(d for d in (_parse_date(p.get("date")) for p in posts) if d)
        first = dates[0] if dates else None
        last = dates[-1] if dates else None
    if first and last:
        return "%s %d, %d to %s %d, %d" % (
            MONTHS[first.month], first.day, first.year,
            MONTHS[last.month], last.day, last.year)
    return "No dated posts yet"


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
STYLE = """
:root{{
  --cyan:{cyan}; --ink:{ink}; --paper:{paper};
  --line:#dce3ea; --muted:#5f6d7b; --paper2:#eef2f6;
}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink); background:var(--paper); line-height:1.5;
  -webkit-font-smoothing:antialiased; padding:0 0 64px;
}}
.wrap{{max-width:880px;margin:0 auto;padding:0 24px}}
.hero{{background:var(--ink);color:#fff;padding:44px 0 40px;margin-bottom:36px}}
.hero .wrap{{max-width:880px}}
.brandmark{{display:inline-block;font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--cyan);font-weight:700;margin-bottom:14px}}
h1{{font-size:34px;line-height:1.1;margin:0 0 6px;font-weight:800;letter-spacing:-.02em}}
.sub{{font-size:16px;color:#c7d2dc;margin:0 0 24px;font-weight:500}}
.meta{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px 28px;margin-top:8px}}
.meta .m{{border-left:3px solid var(--cyan);padding-left:12px}}
.meta .k{{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#8fa0ad;font-weight:700}}
.meta .v{{font-size:15px;color:#f3f6f8;font-weight:600;margin-top:2px}}
.note{{background:#e8faff;border:1px solid #b6ecff;border-radius:10px;
  padding:14px 16px;margin:0 0 34px;font-size:13.5px;color:#0b4a5e}}
.note b{{color:#083544}}
.week{{margin:0 0 40px}}
.week-h{{font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:800;
  color:var(--ink);border-bottom:2px solid var(--cyan);padding-bottom:8px;margin:0 0 18px}}
.week-h span{{color:var(--muted);font-weight:600;letter-spacing:0;text-transform:none;
  font-size:13px;margin-left:8px}}
.card{{border:1px solid var(--line);border-radius:12px;background:#fff;
  padding:18px 20px;margin:0 0 14px;page-break-inside:avoid;break-inside:avoid}}
.card-top{{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 12px;margin-bottom:10px}}
.chip{{font-size:11.5px;font-weight:700;letter-spacing:.04em;padding:3px 9px;border-radius:999px;
  background:var(--paper2);color:var(--ink)}}
.chip.plat{{background:var(--ink);color:#fff}}
.chip.pillar{{background:#e8faff;color:#0b4a5e}}
.when{{font-size:13px;color:var(--muted);font-weight:600;margin-left:auto}}
.caption{{font-size:15px;color:var(--ink);white-space:pre-wrap;margin:0 0 12px}}
.tags{{font-size:13.5px;color:#127a9c;font-weight:600;margin:0 0 12px;word-break:break-word}}
.rowmeta{{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px;
  border-top:1px dashed var(--line);padding-top:10px;margin-top:4px}}
.rowmeta .lk{{color:var(--muted);font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;font-size:10.5px;padding-top:2px}}
.rowmeta .lv{{color:var(--ink)}}
.empty{{border:1px dashed var(--line);border-radius:12px;background:#fff;
  padding:40px 24px;text-align:center;color:var(--muted);font-size:15px}}
.foot{{max-width:880px;margin:48px auto 0;padding:20px 24px 0;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--muted)}}
@media (max-width:560px){{
  .meta{{grid-template-columns:1fr}}
  h1{{font-size:27px}}
  .when{{margin-left:0;width:100%}}
}}
@media print{{
  body{{background:#fff;padding:0}}
  .hero{{background:#fff;color:var(--ink);border-bottom:3px solid var(--cyan);padding:0 0 20px}}
  .hero .sub{{color:var(--muted)}}
  .meta .v{{color:var(--ink)}} .meta .k{{color:var(--muted)}}
  .card{{border-color:#ccc}}
  @page{{margin:16mm}}
}}
""".format(cyan=BRAND_CYAN, ink=BRAND_INK, paper=BRAND_PAPER)


def _render_card(post):
    plat = platform_label(post.get("platform"))
    pillar = pillar_label(post.get("pillar"))
    d = _parse_date(post.get("date"))
    when_bits = []
    if d:
        when_bits.append("%s, %s %d" % (WEEKDAYS[d.weekday()], MONTHS[d.month], d.day))
    tm = _fmt_time(post.get("time"))
    if tm:
        when_bits.append(tm)
    when = " . ".join(when_bits)

    caption = esc(post.get("caption", "")).strip()
    tags = hashtags_for_platform(post.get("platform"), post.get("hashtags"))
    cta = esc(post.get("cta", "")).strip()
    geo = esc(post.get("geo", "")).strip()

    image = post.get("image") or {}
    if isinstance(image, dict):
        img_src = _sanitize(image.get("src", "")).strip()
        img_alt = _sanitize(image.get("alt", "")).strip()
    else:
        img_src, img_alt = "", ""
    img_name = os.path.basename(img_src) if img_src else ""

    parts = ['<article class="card">']
    parts.append('<div class="card-top">')
    parts.append('<span class="chip plat">%s</span>' % esc(plat))
    parts.append('<span class="chip pillar">%s</span>' % esc(pillar))
    if when:
        parts.append('<span class="when">%s</span>' % esc(when))
    parts.append('</div>')
    if caption:
        parts.append('<p class="caption">%s</p>' % caption)
    if tags:
        parts.append('<p class="tags">%s</p>' % esc(" ".join(tags)))
    parts.append('<div class="rowmeta">')
    if cta:
        parts.append('<div class="lk">CTA</div><div class="lv">%s</div>' % cta)
    concept = esc(img_alt) if img_alt else "See image concept notes"
    if img_name:
        parts.append('<div class="lk">Image</div><div class="lv">%s <em>(%s)</em></div>'
                     % (concept, esc(img_name)))
    elif img_alt:
        parts.append('<div class="lk">Image</div><div class="lv">%s</div>' % concept)
    if geo:
        parts.append('<div class="lk">Area</div><div class="lv">%s</div>' % geo)
    parts.append('</div>')
    parts.append('</article>')
    return "".join(parts)


def render_html(posts, summary):
    total = len(posts)
    channel_mix = _channel_mix(posts) if posts else "No posts yet"
    date_range = _date_range_text(posts, summary)
    groups = group_by_week(posts)
    weeks = len([g for g in groups if g[0] != "Undated"]) if groups else 0
    today = datetime.date.today()
    prepared = "%s %d, %d" % (MONTHS[today.month], today.day, today.year)

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en"><head>')
    out.append('<meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>Jackson Roofing - Social Content Plan</title>")
    out.append("<style>%s</style>" % STYLE)
    out.append("</head><body>")

    # Hero / title block
    out.append('<header class="hero"><div class="wrap">')
    out.append('<span class="brandmark">Prepared by Wing Digital</span>')
    out.append("<h1>Jackson Roofing</h1>")
    out.append('<p class="sub">Social Content Plan</p>')
    out.append('<div class="meta">')
    out.append('<div class="m"><div class="k">Date range</div><div class="v">%s</div></div>'
               % esc(date_range))
    out.append('<div class="m"><div class="k">Total posts</div><div class="v">%d</div></div>'
               % total)
    out.append('<div class="m"><div class="k">Channel mix</div><div class="v">%s</div></div>'
               % esc(channel_mix))
    out.append('<div class="m"><div class="k">Weeks planned</div><div class="v">%d</div></div>'
               % weeks)
    out.append('</div>')
    out.append('</div></header>')

    out.append('<div class="wrap">')
    out.append('<p class="note"><b>Draft plan.</b> This is a Wing Digital draft for '
               "Jackson Roofing. Nothing here has been posted or scheduled to any live "
               "account. Captions, timing, and imagery are proposals for review. All "
               "figures are counts of planned posts, not performance results.</p>")

    if not posts:
        out.append('<div class="empty">No posts have been drafted yet. Once the content '
                   "queue is populated, this plan fills in automatically.</div>")
    else:
        for label, week_posts in groups:
            out.append('<section class="week">')
            out.append('<h2 class="week-h">%s<span>%d post%s</span></h2>' % (
                esc(label), len(week_posts), "" if len(week_posts) == 1 else "s"))
            for post in week_posts:
                out.append(_render_card(post))
            out.append('</section>')
    out.append('</div>')

    out.append('<div class="foot">Jackson Roofing is a family-run North Texas roofer '
               "(Plano, since 2000). This social content plan was prepared by Wing "
               "Digital as a draft for review. Prepared %s. Draft-only: no posts have "
               "been published.</div>" % esc(prepared))

    out.append("</body></html>")
    return "\n".join(out)


def write_plan(html_text, path=PLAN_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(html_text)
        if not html_text.endswith("\n"):
            fh.write("\n")
    return path


def build(posts_path=None):
    """Read inputs, render + write plan.html. Returns (path, post_count)."""
    posts = load_posts(posts_path or POSTS_PATH)
    summary = load_summary(SUMMARY_PATH)
    posts.sort(key=lambda p: (
        _sanitize(p.get("date", "")),
        _sanitize(p.get("time", "")),
        _sanitize(p.get("id", "")),
    ))
    html_text = render_html(posts, summary)
    path = write_plan(html_text)
    return path, len(posts)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    path, count = build()
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    if as_json:
        print(json.dumps({
            "generated_by": "social/engine/build_plan_html.py",
            "source": "../data/posts.json",
            "draft_only": True,
            "plan_html": path,
            "post_count": count,
            "bytes": size,
        }, indent=2))
        return 0
    print("Jackson Roofing standalone social plan (DRAFT-ONLY, self-contained)")
    print("  source     : %s" % POSTS_PATH)
    print("  posts       : %d" % count)
    print("  plan.html   : %s" % path)
    print("  size        : %d bytes" % size)
    if count == 0:
        print("  NOTE: no posts found - wrote a valid empty-state plan, exiting 0.")
    else:
        print("  Open it in any browser with a double-click. No server, no external requests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
