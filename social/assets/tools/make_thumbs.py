#!/usr/bin/env python3
"""Downscale the card photos used by the Social Command Center into small,
web-optimized thumbnails so the preview cards load fast.

Wing-owned, DRAFT-ONLY tooling. Reads which images the queue references from
social/data/posts.json, downscales each unique source (which live in the site
root at ../assets/img/) to a card-appropriate width, and writes .webp thumbs to
social/assets/thumbs/. The full-resolution originals are never modified and stay
available for any lightbox / full-view use.

Safe to re-run: only rewrites a thumb when the source is newer or the thumb is
missing. Requires Pillow; if Pillow is absent the command center still works
(the UI falls back to the original photo when a thumb is missing).

Usage:
    python make_thumbs.py            # build/refresh thumbs
    python make_thumbs.py --force    # rebuild every thumb
    python make_thumbs.py --dry-run  # report only, write nothing
"""
import json
import os
import sys

MAX_W = 900          # cards are <=600px CSS wide; 900 covers ~1.5x DPR crisply
QUALITY = 80         # webp quality; visually indistinguishable in a small card

HERE = os.path.dirname(os.path.abspath(__file__))          # social/assets/tools
ASSETS = os.path.dirname(HERE)                             # social/assets
SOCIAL = os.path.dirname(ASSETS)                           # social
SITE_ROOT = os.path.dirname(SOCIAL)                        # repo root (has assets/img)
POSTS = os.path.join(SOCIAL, "data", "posts.json")
THUMBS = os.path.join(ASSETS, "thumbs")


def load_srcs():
    """Return the set of unique image.src values referenced by the queue."""
    try:
        with open(POSTS, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    posts = data if isinstance(data, list) else (data.get("posts", []) if isinstance(data, dict) else [])
    srcs = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        img = p.get("image") or {}
        src = img.get("src") if isinstance(img, dict) else None
        if src:
            srcs.append(src)
    # also the fixed logo avatar the cards use
    srcs.append("../assets/img/logo.webp")
    seen, out = set(), []
    for s in srcs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def resolve(src):
    """Map an image.src (as the page uses it, e.g. ../assets/img/x.jpg) to a
    real file on disk, and the thumb path/name we will write."""
    rel = src.lstrip("./")
    while rel.startswith("../"):
        rel = rel[3:]
    disk = os.path.normpath(os.path.join(SITE_ROOT, rel))
    base = os.path.splitext(os.path.basename(rel))[0]
    return disk, base + ".webp"


def main():
    force = "--force" in sys.argv
    dry = "--dry-run" in sys.argv

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping thumbnails. The command center falls "
              "back to full-size photos. Install with: pip install Pillow")
        return 0

    srcs = load_srcs()
    if not srcs:
        print("No image sources found in posts.json; nothing to do.")
        return 0
    if not dry:
        os.makedirs(THUMBS, exist_ok=True)

    before = after = built = skipped = missing = 0
    for src in srcs:
        disk, thumb_name = resolve(src)
        if not os.path.isfile(disk):
            missing += 1
            print("  MISSING source, skipped: %s" % src)
            continue
        src_bytes = os.path.getsize(disk)
        before += src_bytes
        out_path = os.path.join(THUMBS, thumb_name)

        if not force and os.path.isfile(out_path) and os.path.getmtime(out_path) >= os.path.getmtime(disk):
            after += os.path.getsize(out_path)
            skipped += 1
            continue
        if dry:
            built += 1
            continue

        try:
            im = Image.open(disk)
            im = im.convert("RGB") if im.mode in ("RGBA", "P", "LA") else im
            if im.width > MAX_W:
                h = round(im.height * MAX_W / im.width)
                im = im.resize((MAX_W, h), Image.LANCZOS)
            im.save(out_path, "WEBP", quality=QUALITY, method=6)
            after += os.path.getsize(out_path)
            built += 1
        except Exception as e:  # noqa: BLE001 - never let one bad file abort the run
            print("  FAILED %s: %s" % (src, e))
            after += src_bytes  # falls back to original at runtime

    print("thumbs: built %d, up-to-date %d, missing %d" % (built, skipped, missing))
    if before:
        print("source total: %d KB  ->  thumb total: %d KB  (%.0f%% smaller)"
              % (before // 1024, after // 1024, (1 - after / before) * 100 if before else 0))
    if dry:
        print("(dry-run: no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
