#!/usr/bin/env python3
"""Job Hunter — daily run.

    python src/main.py            # fetch, score, write docs/jobs.json
    python src/main.py --demo     # no network: write sample data so you can
                                  # open the dashboard immediately
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fetchers import fetch_all            # noqa: E402
from scoring import score_job             # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "jobs.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

QUERIES = [
    "AML", "compliance", "financial crime", "KYC", "fraud",
    "risk", "chief of staff", "business operations", "founding",
]


def load_cfg() -> dict:
    """The same config.json the browser loads — one file, no drift."""
    with open(DOCS / "config.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_previous() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return {j["id"]: j for j in data.get("jobs", [])}
    except Exception:  # noqa: BLE001
        return {}


def demo_jobs() -> list[dict]:
    return [
        {"id": "demo-1", "title": "Founding Compliance Manager (MLRO track)",
         "company": "Nimbus Pay", "location": "Munich, Germany", "remote": False,
         "url": "https://example.com/job/1", "source": "Demo",
         "posted_at": datetime.now(timezone.utc).date().isoformat(),
         "salary_raw": "€75,000 - €95,000 + equity", "tags": ["fintech", "seed"],
         "description": "Series A B2B SaaS payments startup. Founding team member, "
                        "own AML, KYC, CDD and sanctions end to end. Stock options."},
        {"id": "demo-2", "title": "Chief of Staff — Risk & Operations",
         "company": "Lumen Ledger", "location": "Remote, Europe", "remote": True,
         "url": "https://example.com/job/2", "source": "Demo",
         "posted_at": datetime.now(timezone.utc).date().isoformat(),
         "salary_raw": "", "tags": ["b2b saas", "series b"],
         "description": "Scale-up regtech. Special projects across compliance, "
                        "business operations and go-to-market. High growth."},
        {"id": "demo-3", "title": "Senior AML Analyst",
         "company": "Bancorp Legacy", "location": "Bucharest, Romania", "remote": False,
         "url": "https://example.com/job/3", "source": "Demo",
         "posted_at": datetime.now(timezone.utc).date().isoformat(),
         "salary_raw": "", "tags": [],
         "description": "Global leader, multinational bank. Transaction monitoring "
                        "and enhanced due diligence."},
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use sample data, no network")
    args = ap.parse_args()

    cfg = load_cfg()
    raw = demo_jobs() if args.demo else fetch_all(cfg, QUERIES)

    scored = [s for s in (score_job(j, cfg) for j in raw) if s]
    min_score = cfg["output"].get("min_score", 0)
    scored = [j for j in scored if j["score"] >= min_score]
    log.info("scored above threshold: %d", len(scored))

    # merge with history so postings stay visible and "new" is meaningful
    previous = load_previous()
    today = datetime.now(timezone.utc).date().isoformat()
    merged: dict[str, dict] = {}
    for j in scored:
        old = previous.get(j["id"])
        j["first_seen"] = old["first_seen"] if old and old.get("first_seen") else today
        j["is_new"] = j["first_seen"] == today
        merged[j["id"]] = j
    for jid, old in previous.items():
        if jid not in merged:
            old["is_new"] = False
            merged[jid] = old

    cutoff = (datetime.now(timezone.utc) -
              timedelta(days=cfg["output"].get("keep_days", 30))).date().isoformat()
    jobs = [j for j in merged.values() if j.get("first_seen", today) >= cutoff]
    jobs.sort(key=lambda j: (-j.get("score", 0), j.get("first_seen", "")), reverse=False)
    jobs = jobs[: cfg["output"].get("max_jobs", 400)]

    DOCS.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(jobs),
        "new_today": sum(1 for j in jobs if j.get("is_new")),
        "jobs": jobs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    log.info("wrote %s (%d jobs, %d new)", OUT, len(jobs),
             sum(1 for j in jobs if j.get("is_new")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
