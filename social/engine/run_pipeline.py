#!/usr/bin/env python3
"""
Jackson Roofing SOCIAL PRESENCE - one-command pipeline (Wing-owned, DRAFT-ONLY).

This is the single, fail-closed entrypoint a pro relies on: it turns the curated
draft queue (../data/posts.json) into scheduler-ready files, and it will NEVER let
an off-brand or off-spec post through to the exports.

Order of operations (fail closed):

  1. QA GATE   run the brand + platform + integrity gate (social_qa) against
               data/posts.json.
  2. EXPORT    ONLY if the gate reports 0 FAIL, regenerate data/exports/
               (schedule.csv + calendar.ics + index.json) via export.py.
  3. BLOCK     if the gate reports ANY FAIL (or cannot read the queue), print the
               failures and EXIT NONZERO WITHOUT writing any export. Never ship a
               post that fails the brand/integrity gate.

DRAFT-ONLY: this orchestrator only reads posts.json and writes local export files.
It never posts, sends, or touches any live account. No network. Stdlib only.

A normal run also refreshes data/exports/summary.json (plan stats: counts, not
metrics) for the command-center header and client reports. The --all (alias
--with-thumbs) flag additionally rebuilds card thumbnails via the asset lane's
make_thumbs.py, so one command turns the queue into everything a scheduler and a
report need. The thumbnail step is optional and non-fatal; a FAIL gate does none of it.

Run:  python social/engine/run_pipeline.py           (gate -> export + summary)
      python social/engine/run_pipeline.py --all      (gate -> thumbs + export + summary)
      python social/engine/run_pipeline.py --json     (machine-readable report)
      python social/engine/run_pipeline.py --posts <path>   (gate a specific file;
               used for fail-closed testing - export always regenerates from the
               canonical data/posts.json, and only runs when the gate is clean)
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import social_qa      # noqa: E402  (sibling module in engine/)
import export         # noqa: E402  (sibling module in engine/)
import build_summary  # noqa: E402  (sibling module in engine/)

# Thumbnail tool lives in the ASSET lane, not the engine. We INVOKE it as a
# subprocess (never import/edit it) and treat it as optional: if it is absent or
# fails, we report and keep going. The gate + export are the load-bearing steps.
SOCIAL_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
THUMB_TOOL = os.path.join(SOCIAL_DIR, "assets", "tools", "make_thumbs.py")


def run_gate(posts_path):
    """Run the QA gate against posts_path. Returns (report_dict, gate_ok).

    gate_ok is True only when the queue loaded AND zero posts have a FAIL.
    A load/parse error is treated as a FAIL (fail closed)."""
    posts, err = social_qa.load_posts(posts_path)
    if err:
        return {
            "source": posts_path,
            "loaded": False,
            "error": err,
            "post_count": 0,
            "pass": 0, "warn": 0, "fail": 0,
            "gate": "ERROR",
            "posts": [],
        }, False

    results = social_qa.evaluate(posts)
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_warn = sum(1 for r in results if r["status"] == "WARN")
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    report = {
        "source": posts_path,
        "loaded": True,
        "error": None,
        "post_count": len(results),
        "pass": n_pass, "warn": n_warn, "fail": n_fail,
        "gate": "FAIL" if n_fail else "PASS",
        "posts": results,
    }
    return report, (n_fail == 0)


def run_export(quiet=False):
    """Run export.py's main() in-process. Returns (rc, export_summary_dict).

    export.main() writes data/exports/ and returns 0. We read the manifest it
    writes (index.json) to report exactly what landed, so the pipeline summary is
    grounded in the real output files, not assumptions. When quiet=True (e.g. under
    --json) export.py's own human print output is suppressed so stdout stays valid JSON."""
    if quiet:
        import io as _io
        import contextlib
        with contextlib.redirect_stdout(_io.StringIO()):
            rc = export.main()
    else:
        rc = export.main()
    summary = {"schedule_csv_rows": None, "calendar_ics_events": None,
               "post_count": None, "index_json": export.INDEX_PATH}
    try:
        with open(export.INDEX_PATH, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        summary["schedule_csv_rows"] = manifest.get("csv_rows")
        summary["calendar_ics_events"] = manifest.get("ics_events")
        summary["post_count"] = manifest.get("post_count")
    except (OSError, ValueError):
        pass
    return rc, summary


def run_summary(quiet=False):
    """Refresh data/exports/summary.json via build_summary. Returns (ok, summary_dict).

    Plan stats (counts, never metrics) for a UI header or a client report. Non-fatal:
    if it cannot be built we report it but do not sink the whole run, since the
    load-bearing scheduler outputs are the CSV/ICS."""
    try:
        summary, _path = build_summary.build()
        return True, summary
    except Exception as exc:  # never let a stats refresh crash the pipeline
        if not quiet:
            print("  SUMMARY: WARN - could not build summary.json (%s)" % exc)
        return False, {"error": str(exc)}


def run_thumbs(quiet=False):
    """Invoke the asset lane's make_thumbs.py as a subprocess. Returns a dict:
      {"ran": bool, "ok": bool, "returncode": int|None, "detail": str}

    OPTIONAL by contract: a missing or failing thumb tool is reported but never
    crashes the run. Thumbs are a performance nicety; the schedule/summary are not.
    We do NOT edit or import the tool - only run it."""
    if not os.path.isfile(THUMB_TOOL):
        detail = "thumb tool not found at %s (skipped)" % THUMB_TOOL
        if not quiet:
            print("  THUMBS : SKIPPED - %s" % detail)
        return {"ran": False, "ok": True, "returncode": None, "detail": detail}
    try:
        proc = subprocess.run(
            [sys.executable, THUMB_TOOL],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as exc:  # subprocess failed to launch / timed out
        detail = "thumb tool could not run: %s" % exc
        if not quiet:
            print("  THUMBS : WARN - %s" % detail)
        return {"ran": True, "ok": False, "returncode": None, "detail": detail}

    ok = (proc.returncode == 0)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    detail = out if out else err
    if not quiet:
        if ok:
            print("  THUMBS : DONE (make_thumbs.py exit 0)")
        else:
            print("  THUMBS : WARN - make_thumbs.py exited %d" % proc.returncode)
        if detail:
            for line in detail.splitlines():
                print("           | %s" % line)
    return {"ran": True, "ok": ok, "returncode": proc.returncode, "detail": detail}


def run(posts_path=None, as_json=False, with_thumbs=False):
    """Execute the full pipeline. Returns (exit_code, report_dict).

    Order (fail closed): gate -> (only if 0 FAIL) thumbs [--all] + export + summary.
    exit_code is 0 only when the gate is clean AND the export succeeded. A FAIL/ERROR
    gate writes NOTHING (no thumbs, no export, no summary). The thumbnail step and the
    summary refresh are non-fatal: a nonzero exit is driven only by export failure."""
    gate_source = posts_path or social_qa.POSTS_PATH

    gate_report, gate_ok = run_gate(gate_source)

    report = {
        "draft_only": True,
        "with_thumbs": with_thumbs,
        "gate": gate_report,
        "thumbs": None,
        "exported": False,
        "export": None,
        "summary": None,
        "exit_code": None,
    }

    if not gate_ok:
        report["exit_code"] = 1
        if not as_json:
            _print_blocked(gate_report)
        return 1, report

    # Gate clean -> safe to (optionally thumbnail and) regenerate outputs.
    if not as_json:
        _print_gate_clear(gate_report)
        print("")  # spacer before the step output

    if with_thumbs:
        report["thumbs"] = run_thumbs(quiet=as_json)

    export_rc, export_summary = run_export(quiet=as_json)
    report["exported"] = (export_rc == 0)
    report["export"] = export_summary

    summary_ok, summary = run_summary(quiet=as_json)
    report["summary"] = summary

    report["exit_code"] = 0 if export_rc == 0 else 1

    if not as_json:
        _print_exported(export_summary, summary, report["exit_code"])
    return report["exit_code"], report


def _print_blocked(gate_report):
    print("Jackson Roofing social pipeline (DRAFT-ONLY)")
    print("  source : %s" % gate_report["source"])
    if not gate_report["loaded"]:
        print("  QA GATE: ERROR - %s" % gate_report.get("error"))
        print("  EXPORT : BLOCKED - queue unreadable, nothing exported.")
        print("\nRESULT: BLOCKED (exit 1). No files written.")
        return
    print("  posts  : %d  |  PASS %d  WARN %d  FAIL %d"
          % (gate_report["post_count"], gate_report["pass"],
             gate_report["warn"], gate_report["fail"]))
    print("  QA GATE: FAIL - %d post(s) failed the brand/integrity gate:"
          % gate_report["fail"])
    for r in gate_report["posts"]:
        if r["status"] != "FAIL":
            continue
        for f in r["fails"]:
            print("    x [%s] %s: %s" % (r["id"], f["code"], f["detail"]))
    print("  EXPORT : BLOCKED - off-brand posts never reach the schedule.")
    print("\nRESULT: BLOCKED (exit 1). data/exports/ was NOT regenerated.")


def _print_gate_clear(gate_report):
    print("Jackson Roofing social pipeline (DRAFT-ONLY)")
    print("  source : %s" % gate_report["source"])
    print("  posts  : %d  |  PASS %d  WARN %d  FAIL %d"
          % (gate_report["post_count"], gate_report["pass"],
             gate_report["warn"], gate_report["fail"]))
    print("  QA GATE: CLEAR - 0 FAIL (WARNs are advisory). Proceeding to export.")


def _print_exported(export_summary, summary, exit_code):
    print("")
    if exit_code == 0:
        print("  EXPORT : DONE - schedule.csv %s rows, calendar.ics %s events"
              % (export_summary.get("schedule_csv_rows"),
                 export_summary.get("calendar_ics_events")))
        if isinstance(summary, dict) and summary.get("post_count") is not None:
            print("  SUMMARY: DONE - summary.json (%s posts, ~%s / week across %d platforms)"
                  % (summary.get("post_count"), summary.get("posts_per_week"),
                     len(summary.get("platforms") or [])))
        print("\nRESULT: OK (exit 0). Scheduler-ready files written to data/exports/.")
    else:
        print("  EXPORT : FAILED (exit %d)." % exit_code)
        print("\nRESULT: ERROR (exit %d)." % exit_code)


def main(argv):
    as_json = "--json" in argv
    with_thumbs = ("--all" in argv) or ("--with-thumbs" in argv)
    posts_path = None
    if "--posts" in argv:
        i = argv.index("--posts")
        if i + 1 < len(argv):
            posts_path = argv[i + 1]
        else:
            print("ERROR: --posts requires a path argument", file=sys.stderr)
            return 2

    exit_code, report = run(posts_path=posts_path, as_json=as_json,
                            with_thumbs=with_thumbs)
    if as_json:
        print(json.dumps(report, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
