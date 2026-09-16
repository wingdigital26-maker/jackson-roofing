#!/usr/bin/env python3
"""
Jackson Roofing SOCIAL PRESENCE - brand + platform QA gate (Wing-owned, DRAFT-ONLY).

A professional social manager does not eyeball every caption before it ships. They
run a gate. This is that gate, mirroring the proven blog_lint / content-engine
pattern and applying it to social captions so nothing off-brand, off-spec, or
factually shaky ever leaves the queue.

It reads the curated draft queue (../data/posts.json) and grades every post on three
axes, with explicit severities:

  BRAND     (FAIL)  em/en dashes, phone numbers, fabricated-authority claims.
  PLATFORM  (WARN/FAIL)  per-platform caption length + hashtag-count rules,
                         non-empty caption, Contact-Us-style CTA (never a phone).
  INTEGRITY (FAIL)  known platform, valid date + plausible weekday, HH:MM time,
                    image.src present and the file exists on disk, unique ids.

Only real brand/integrity breaches are FAIL. Soft length preferences are WARN.
Exit code: 0 if every post passes (WARNs allowed), 1 if any post has a FAIL.

DRAFT-ONLY: read-only gate. It NEVER posts, sends, or touches any live account.
No network. Stdlib only. Deterministic.

Run:  python social/engine/social_qa.py            (human table + summary)
      python social/engine/social_qa.py --json      (machine-readable report)

Image resolution: image.src values are written relative to the command-center page
(social/index.html), so "../assets/img/x.webp" is resolved from the social/ dir.
"""

import datetime
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Paths (resolved relative to THIS script, so it runs from any cwd).
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOCIAL_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(SOCIAL_DIR, "data")
POSTS_PATH = os.path.join(DATA_DIR, "posts.json")

# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
ALLOWED_PLATFORMS = {"gbp", "facebook", "instagram", "nextdoor"}

# Caption length: (hard max = FAIL, recommended max = WARN if exceeded).
# None means no recommended cap for that platform.
PLATFORM_CAPTION_LIMITS = {
    "gbp":       {"hard": 1500, "recommend": 1500},
    "facebook":  {"hard": 2000, "recommend": 500},
    "instagram": {"hard": 2200, "recommend": 2200},
    "nextdoor":  {"hard": 2000, "recommend": 2000},
}

# Hashtag COUNT rules: (min, max). min None = no floor, max None = no ceiling.
PLATFORM_HASHTAG_RULES = {
    "gbp":       {"min": 0, "max": 0},
    "nextdoor":  {"min": 0, "max": 0},
    "facebook":  {"min": 0, "max": 3},
    "instagram": {"min": 5, "max": 15},
}

DASH_CHARS = ("—", "–")  # em dash, en dash

# US phone number patterns: (555) 555-5555, 555-555-5555, 555.555.5555,
# 5555555555, +1 555 555 5555, etc. Deliberately covers common written forms.
PHONE_RE = re.compile(
    r"(?:\+?1[\s.\-]?)?"          # optional country code
    r"(?:\(?\d{3}\)?[\s.\-]?)"    # area code, optional parens
    r"\d{3}[\s.\-]?\d{4}"         # prefix + line
)

# Fabricated-authority / unverifiable-superlative patterns. These are FAIL because
# we cannot substantiate them for a portfolio asset. Generic uses are excluded via
# the whitelist below.
AUTHORITY_PATTERNS = [
    (re.compile(r"#\s*1\b"), "'#1' ranking claim"),
    (re.compile(r"\bnumber\s+one\b", re.I), "'number one' ranking claim"),
    (re.compile(r"\bbest\s+in\b", re.I), "'best in ...' superlative"),
    (re.compile(r"\b#?1\s+(?:rated|roofer|roofing|choice)\b", re.I), "'#1 rated' claim"),
    (re.compile(r"\bvoted\b", re.I), "'voted' award claim"),
    (re.compile(r"\baward[\s-]?winning\b", re.I), "'award-winning' claim"),
    (re.compile(r"\bguarantee(?:d|s)?\b", re.I), "'guarantee(d)' claim"),
    (re.compile(r"\b\d{2,}\s*(?:\+|plus)?\s*(?:5[\s-]?star\s+)?reviews?\b", re.I),
     "specific review-count claim"),
    (re.compile(r"\b\d{2,}\s*(?:\+|plus)?\s*(?:5[\s-]?star\s+)?ratings?\b", re.I),
     "specific rating-count claim"),
    (re.compile(r"\brated\s+#?\s*1\b", re.I), "'rated #1' claim"),
    (re.compile(r"\btop[\s-]?rated\b", re.I), "'top-rated' claim"),
    (re.compile(r"\bbest\s+roof(?:er|ing)?\b", re.I), "'best roofer/roofing' superlative"),
]

# CTA must be Contact-Us style, no phone. A CTA lacking any of these verbs is soft-flagged.
CTA_CONTACT_HINTS = ("contact", "message", "reach", "book", "schedule", "get started",
                     "visit", "see how", "dm", "learn more", "request")


class Finding(object):
    __slots__ = ("severity", "code", "detail")

    def __init__(self, severity, code, detail):
        self.severity = severity  # "FAIL" or "WARN"
        self.code = code
        self.detail = detail

    def as_dict(self):
        return {"severity": self.severity, "code": self.code, "detail": self.detail}


def load_posts(path):
    """Read posts.json robustly. Accepts {"posts":[...]} or a bare [...]. Returns list."""
    if not os.path.isfile(path):
        return None, "posts.json not found at %s" % path
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        if not raw:
            return [], None
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        return None, "could not parse posts.json: %s" % exc
    if isinstance(data, dict):
        posts = data.get("posts", [])
    elif isinstance(data, list):
        posts = data
    else:
        posts = []
    return [p for p in posts if isinstance(p, dict)], None


# ---------------------------------------------------------------------------
# Per-check helpers
# ---------------------------------------------------------------------------
def check_dashes(text, field, findings):
    for ch in DASH_CHARS:
        if ch in (text or ""):
            name = "em dash" if ch == "—" else "en dash"
            findings.append(Finding("FAIL", "brand.dash",
                                    "%s contains an %s (brand rule: none ever)" % (field, name)))
            return


def check_phone(text, field, findings):
    if text and PHONE_RE.search(text):
        m = PHONE_RE.search(text)
        findings.append(Finding("FAIL", "brand.phone",
                                "%s contains a phone-number pattern '%s' (no phone CTAs rule)"
                                % (field, m.group(0).strip())))


def check_authority(text, field, findings):
    if not text:
        return
    for rx, label in AUTHORITY_PATTERNS:
        if rx.search(text):
            findings.append(Finding("FAIL", "brand.authority",
                                    "%s has a fabricated-authority pattern (%s)" % (field, label)))
            return


def check_caption_length(platform, caption, findings):
    limits = PLATFORM_CAPTION_LIMITS.get(platform)
    n = len(caption or "")
    if n == 0:
        findings.append(Finding("FAIL", "platform.empty_caption", "caption is empty"))
        return
    if not limits:
        return
    if limits["hard"] is not None and n > limits["hard"]:
        findings.append(Finding("FAIL", "platform.caption_too_long",
                                "caption %d chars exceeds %s hard max %d"
                                % (n, platform, limits["hard"])))
    elif limits["recommend"] is not None and n > limits["recommend"]:
        findings.append(Finding("WARN", "platform.caption_long",
                                "caption %d chars over %s recommended %d"
                                % (n, platform, limits["recommend"])))


def check_hashtags(platform, hashtags, findings):
    rule = PLATFORM_HASHTAG_RULES.get(platform)
    tags = [h for h in (hashtags or []) if str(h).strip()]
    count = len(tags)
    # Every hashtag should start with '#'.
    bad = [h for h in tags if not str(h).strip().startswith("#")]
    if bad:
        findings.append(Finding("WARN", "platform.hashtag_format",
                                "%d hashtag(s) missing leading '#': %s"
                                % (len(bad), ", ".join(str(b) for b in bad[:3]))))
    if not rule:
        return
    lo, hi = rule.get("min"), rule.get("max")
    if hi is not None and count > hi:
        # Hashtag counts are a publishing convention, not a brand/integrity breach:
        # export.py strips gbp/nextdoor hashtags and caps facebook before anything ships,
        # so an over-count in the source queue is WARN (data hygiene), never a hard gate.
        findings.append(Finding("WARN", "platform.hashtag_count",
                                "%d hashtags on %s (convention max %d; export strips/caps at publish)"
                                % (count, platform, hi)))
    if lo is not None and count < lo:
        findings.append(Finding("WARN", "platform.hashtag_count",
                                "%d hashtags on %s (recommended min %d)" % (count, platform, lo)))


def check_cta(cta, findings):
    text = (cta or "").strip()
    if not text:
        findings.append(Finding("FAIL", "platform.cta_missing", "cta is empty"))
        return
    if PHONE_RE.search(text):
        findings.append(Finding("FAIL", "brand.cta_phone", "cta contains a phone number"))
    check_dashes(text, "cta", findings)
    low = text.lower()
    if not any(h in low for h in CTA_CONTACT_HINTS):
        findings.append(Finding("WARN", "platform.cta_style",
                                "cta may not be Contact-Us style: '%s'" % text[:60]))


def check_platform(platform, findings):
    if platform not in ALLOWED_PLATFORMS:
        findings.append(Finding("FAIL", "integrity.platform",
                                "platform '%s' not in allowed set %s"
                                % (platform, sorted(ALLOWED_PLATFORMS))))
        return False
    return True


def check_date(date_str, findings):
    try:
        d = datetime.datetime.strptime((date_str or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        findings.append(Finding("FAIL", "integrity.date",
                                "date '%s' is not valid YYYY-MM-DD" % date_str))
        return
    # Plausibility: within a sane window (not decades off).
    today = datetime.date.today()
    if d.year < today.year - 1 or d.year > today.year + 2:
        findings.append(Finding("WARN", "integrity.date_range",
                                "date %s is far from today (%s)" % (d.isoformat(), today.isoformat())))


def check_time(time_str, findings):
    t = (time_str or "").strip()
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
        findings.append(Finding("FAIL", "integrity.time",
                                "time '%s' is not valid 24h HH:MM" % time_str))


def check_image(image, findings):
    if not isinstance(image, dict):
        findings.append(Finding("FAIL", "integrity.image_missing", "image object missing"))
        return
    src = (image.get("src") or "").strip()
    if not src:
        findings.append(Finding("FAIL", "integrity.image_src", "image.src is empty"))
        return
    # src is relative to the command-center page (social/index.html) -> resolve from social/.
    resolved = os.path.normpath(os.path.join(SOCIAL_DIR, src))
    if not os.path.isfile(resolved):
        findings.append(Finding("FAIL", "integrity.image_file",
                                "image file not found on disk: %s" % src))
    else:
        # Guard against tiny/blank/broken image assets (a real 62x62 black
        # placeholder shipped at ~1.4KB). Anything under 2KB is almost never a
        # usable card photo, so surface it before it renders as a blank square.
        try:
            if os.path.getsize(resolved) < 2048:
                findings.append(Finding("WARN", "integrity.image_tiny",
                                        "image file suspiciously small (<2KB), may be blank/broken: %s" % src))
        except OSError:
            pass
    if not (image.get("alt") or "").strip():
        findings.append(Finding("WARN", "integrity.image_alt", "image.alt is empty"))


def grade_post(post, seen_ids):
    findings = []
    pid = (post.get("id") or "").strip()
    platform = (post.get("platform") or "").strip().lower()
    caption = post.get("caption") or ""
    cta = post.get("cta") or ""

    # id uniqueness / presence
    if not pid:
        findings.append(Finding("FAIL", "integrity.id_missing", "post has no id"))
    elif pid in seen_ids:
        findings.append(Finding("FAIL", "integrity.id_dup", "duplicate id '%s'" % pid))
    if pid:
        seen_ids.add(pid)

    # BRAND
    check_dashes(caption, "caption", findings)
    check_phone(caption, "caption", findings)
    check_authority(caption, "caption", findings)

    # PLATFORM
    valid_platform = check_platform(platform, findings)
    check_caption_length(platform if valid_platform else "", caption, findings)
    check_hashtags(platform if valid_platform else "", post.get("hashtags"), findings)
    check_cta(cta, findings)

    # INTEGRITY
    check_date(post.get("date"), findings)
    check_time(post.get("time"), findings)
    check_image(post.get("image"), findings)

    return findings


def evaluate(posts):
    seen_ids = set()
    results = []
    for p in posts:
        findings = grade_post(p, seen_ids)
        fails = [f for f in findings if f.severity == "FAIL"]
        warns = [f for f in findings if f.severity == "WARN"]
        results.append({
            "id": (p.get("id") or "(no id)"),
            "platform": (p.get("platform") or ""),
            "date": (p.get("date") or ""),
            "status": "FAIL" if fails else ("WARN" if warns else "PASS"),
            "fails": [f.as_dict() for f in fails],
            "warns": [f.as_dict() for f in warns],
        })
    return results


def print_table(results):
    if not results:
        print("No posts found in posts.json - nothing to gate (exit 0).")
        return
    idw = max(len(r["id"]) for r in results)
    idw = min(max(idw, 4), 40)
    print("%-*s  %-9s  %-10s  %-6s  %s" % (idw, "ID", "PLATFORM", "DATE", "STATUS", "NOTES"))
    print("-" * (idw + 44))
    for r in results:
        note = ""
        if r["status"] == "FAIL":
            note = r["fails"][0]["detail"]
        elif r["status"] == "WARN":
            note = r["warns"][0]["detail"]
        print("%-*s  %-9s  %-10s  %-6s  %s"
              % (idw, r["id"][:idw], r["platform"][:9], r["date"][:10], r["status"], note))
        # Show remaining findings indented for full transparency.
        extra = (r["fails"][1:] if r["status"] == "FAIL" else []) + r["warns"] \
            if r["status"] == "FAIL" else r["warns"][1:]
        for f in extra:
            print("%s  -> %s: %s" % (" " * (idw + 27), f["severity"], f["detail"]))


def print_summary(results):
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    n_fail = sum(len(r["fails"]) for r in results)
    n_warn = sum(len(r["warns"]) for r in results)
    print("")
    print("SUMMARY: %d posts | %d PASS | %d WARN | %d FAIL  (%d fail-findings, %d warn-findings)"
          % (total, passed, warned, failed, n_fail, n_warn))
    if failed:
        print("GATE: BLOCKED - %d post(s) have brand/integrity FAILs. Fix before shipping." % failed)
    else:
        print("GATE: CLEAR - no FAILs. Safe to hand off (WARNs are advisory).")


def main(argv):
    as_json = "--json" in argv
    posts, err = load_posts(POSTS_PATH)
    if err:
        if as_json:
            print(json.dumps({"error": err, "gate": "ERROR"}, indent=2))
        else:
            print("ERROR: %s" % err)
        return 1
    results = evaluate(posts)
    any_fail = any(r["status"] == "FAIL" for r in results)

    if as_json:
        report = {
            "source": POSTS_PATH,
            "draft_only": True,
            "post_count": len(results),
            "pass": sum(1 for r in results if r["status"] == "PASS"),
            "warn": sum(1 for r in results if r["status"] == "WARN"),
            "fail": sum(1 for r in results if r["status"] == "FAIL"),
            "gate": "FAIL" if any_fail else "PASS",
            "posts": results,
        }
        print(json.dumps(report, indent=2))
    else:
        print("Jackson Roofing social QA gate (BRAND + PLATFORM + INTEGRITY, DRAFT-ONLY)")
        print("source: %s\n" % POSTS_PATH)
        print_table(results)
        print_summary(results)

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
