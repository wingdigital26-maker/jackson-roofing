#!/usr/bin/env python3
"""
Jackson Roofing SOCIAL PRESENCE - scheduler-handoff export (Wing-owned, DRAFT-ONLY).

A pro social manager cannot load a JSON queue into Buffer, Hootsuite, Later, Metricool,
Google Calendar or Apple Calendar. This lane turns the curated draft queue
(../data/posts.json) into two files they can actually use:

  1. schedule.csv  - one row per post, ready to import into any scheduler.
  2. calendar.ics  - a valid iCalendar with one VEVENT per post, importable into
                     Google/Apple Calendar so Jack has a real posting calendar.
  3. index.json    - a small manifest listing the exports + counts.

DRAFT-ONLY: this script ONLY writes local files. It never posts, sends, or touches
any live account. No network calls. Stdlib only, deterministic.

Run:  python social/engine/export.py
"""

import csv
import io
import json
import os
import sys

# ---------------------------------------------------------------------------
# Paths (resolved relative to THIS script, so it runs from any cwd).
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "data"))
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

CSV_PATH = os.path.join(EXPORT_DIR, "schedule.csv")
ICS_PATH = os.path.join(EXPORT_DIR, "calendar.ics")
INDEX_PATH = os.path.join(EXPORT_DIR, "index.json")

TIMEZONE = "America/Chicago"
DURATION_MIN = 15

# Platforms that should NOT carry hashtags in their published caption.
NO_HASHTAG_PLATFORMS = {"gbp", "nextdoor"}
# Facebook: keep it light (0-2 hashtags). Instagram: all of them.
FB_MAX_HASHTAGS = 2

PLATFORM_LABEL = {
    "gbp": "Google Business Profile",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "nextdoor": "Nextdoor",
}


def _sanitize(text):
    """No em dashes or en dashes ever leak into generated text (brand rule)."""
    if text is None:
        return ""
    return str(text).replace("\u2014", "-").replace("\u2013", "-")


def _csv_cell(text):
    """CSV-injection guard: neutralize cells a spreadsheet could read as a formula
    (leading = + - @ tab CR) by prefixing a single quote. Also strips dashes."""
    s = _sanitize(text)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def load_posts(path):
    """Read posts.json robustly. Accepts {"posts":[...]} or a bare [...] list.
    Returns a list (possibly empty). Never raises on missing/empty/bad file."""
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


def hashtags_for_platform(platform, hashtags):
    """Return the hashtag list appropriate for a platform's published caption."""
    platform = (platform or "").lower()
    tags = [_sanitize(h).strip() for h in (hashtags or []) if str(h).strip()]
    if platform in NO_HASHTAG_PLATFORMS:
        return []
    if platform == "facebook":
        return tags[:FB_MAX_HASHTAGS]
    return tags  # instagram + anything else: all of them


def full_caption(post):
    """Caption text with hashtags appended per-platform convention."""
    caption = _sanitize(post.get("caption", "")).strip()
    tags = hashtags_for_platform(post.get("platform"), post.get("hashtags"))
    if tags:
        return (caption + "\n\n" + " ".join(tags)).strip()
    return caption


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def write_csv(posts, path):
    header = ["date", "time", "platform", "pillar", "caption",
              "hashtags", "cta", "image", "geo"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        for p in posts:
            tags = hashtags_for_platform(p.get("platform"), p.get("hashtags"))
            image = p.get("image") or {}
            writer.writerow([
                _sanitize(p.get("date", "")),
                _sanitize(p.get("time", "")),
                _sanitize(p.get("platform", "")),
                _sanitize(p.get("pillar", "")),
                _csv_cell(full_caption(p)),
                _csv_cell(" ".join(tags)),
                _csv_cell(p.get("cta", "")),
                _sanitize(image.get("src", "")) if isinstance(image, dict) else "",
                _sanitize(p.get("geo", "")),
            ])
    return len(posts)


# ---------------------------------------------------------------------------
# ICS (iCalendar)
# ---------------------------------------------------------------------------
def _ics_escape(text):
    """Escape per RFC 5545 for TEXT values: backslash, comma, semicolon, newline."""
    text = _sanitize(text)
    text = text.replace("\\", "\\\\")
    text = text.replace("\n", "\\n").replace("\r", "")
    text = text.replace(",", "\\,").replace(";", "\\;")
    return text


def _fold_line(line):
    """Fold long lines to <=75 octets per RFC 5545 (continuation starts with a space)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    out = []
    chunk = b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > 74:  # leave room for leading space on next line
            out.append(chunk.decode("utf-8"))
            chunk = b
        else:
            chunk += b
    if chunk:
        out.append(chunk.decode("utf-8"))
    return ("\r\n ").join(out)


def _dtstart(date_str, time_str):
    """Return YYYYMMDDTHHMMSS from date (YYYY-MM-DD) and time (HH:MM). Robust to blanks."""
    d = "".join(c for c in (date_str or "") if c.isdigit())  # YYYYMMDD
    t = "".join(c for c in (time_str or "") if c.isdigit())  # HHMM
    if len(d) != 8:
        return None
    t = (t + "0000")[:6] if t else "090000"
    if len(t) == 4:
        t = t + "00"
    return d + "T" + t


def _dtend(dtstart):
    """dtstart + DURATION_MIN, keeping same day (posts are morning/afternoon slots)."""
    date_part, time_part = dtstart.split("T")
    hh = int(time_part[0:2])
    mm = int(time_part[2:4])
    ss = time_part[4:6]
    total = hh * 60 + mm + DURATION_MIN
    hh2 = (total // 60) % 24
    mm2 = total % 60
    return "%sT%02d%02d%s" % (date_part, hh2, mm2, ss)


def write_ics(posts, path):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wing Digital//Jackson Roofing Social//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Jackson Roofing Social (draft)",
        "X-WR-TIMEZONE:" + TIMEZONE,
    ]
    count = 0
    for p in posts:
        dtstart = _dtstart(p.get("date"), p.get("time"))
        if dtstart is None:
            continue  # skip malformed dates, keep file valid
        count += 1
        platform = (p.get("platform") or "").lower()
        label = PLATFORM_LABEL.get(platform, platform.title() or "Post")
        pillar = _sanitize(p.get("pillar", "")).strip()
        summary = "[%s] %s" % (label, pillar) if pillar else "[%s]" % label
        uid = _sanitize(p.get("id") or ("post-%d" % count)) + "@jackson-roofing.wing"
        lines.extend([
            "BEGIN:VEVENT",
            _fold_line("UID:" + uid),
            "DTSTAMP:20260914T000000Z",
            _fold_line("DTSTART;TZID=%s:%s" % (TIMEZONE, dtstart)),
            _fold_line("DTEND;TZID=%s:%s" % (TIMEZONE, _dtend(dtstart))),
            _fold_line("SUMMARY:" + _ics_escape(summary)),
            _fold_line("DESCRIPTION:" + _ics_escape(full_caption(p))),
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(lines) + "\r\n")
    return count


# ---------------------------------------------------------------------------
# index.json
# ---------------------------------------------------------------------------
def write_index(posts, csv_rows, ics_events, path):
    platform_mix = {}
    for p in posts:
        plat = (p.get("platform") or "unknown").lower()
        platform_mix[plat] = platform_mix.get(plat, 0) + 1
    dates = sorted(_sanitize(p.get("date", "")) for p in posts if p.get("date"))
    manifest = {
        "generated_by": "social/engine/export.py",
        "source": "../data/posts.json",
        "draft_only": True,
        "post_count": len(posts),
        "csv_rows": csv_rows,
        "ics_events": ics_events,
        "date_range": {"start": dates[0], "end": dates[-1]} if dates else None,
        "platform_mix": platform_mix,
        "timezone": TIMEZONE,
        "files": [
            {"file": "schedule.csv", "kind": "csv", "rows": csv_rows,
             "use": "Import into any social scheduler (Buffer, Later, Metricool, Hootsuite)."},
            {"file": "calendar.ics", "kind": "ics", "events": ics_events,
             "use": "Import into Google Calendar or Apple Calendar to follow the posting plan."},
        ],
    }
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")


def main():
    import time
    t0 = time.time()
    os.makedirs(EXPORT_DIR, exist_ok=True)
    posts = load_posts(POSTS_PATH)

    # Deterministic order: by date, then time, then id.
    posts.sort(key=lambda p: (
        _sanitize(p.get("date", "")),
        _sanitize(p.get("time", "")),
        _sanitize(p.get("id", "")),
    ))

    csv_rows = write_csv(posts, CSV_PATH)
    ics_events = write_ics(posts, ICS_PATH)
    write_index(posts, csv_rows, ics_events, INDEX_PATH)

    elapsed = time.time() - t0
    print("Jackson Roofing social export (DRAFT-ONLY, no posting)")
    print("  source     : %s" % POSTS_PATH)
    print("  posts read : %d" % len(posts))
    print("  schedule.csv rows  : %d" % csv_rows)
    print("  calendar.ics events: %d" % ics_events)
    print("  index.json written : %s" % INDEX_PATH)
    print("  runtime    : %.3fs" % elapsed)
    if not posts:
        print("  NOTE: no posts found - wrote empty-but-valid files, exiting 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
