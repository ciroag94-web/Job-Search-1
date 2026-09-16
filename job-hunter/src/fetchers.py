"""Job source fetchers.

Every fetcher returns a list of raw dicts with a common shape:
    id, title, company, location, remote, url, description, posted_at, source,
    salary_raw (optional), company_size (optional), tags (list)

All of them fail soft: a dead API logs a warning and returns [] so one broken
source never takes the whole run down.
"""
from __future__ import annotations

import html
import os
import re
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger("fetchers")
UA = {"User-Agent": "job-hunter/1.0 (+https://github.com/)"}
TIMEOUT = 30


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get(url: str, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _iso(value) -> str:
    """Best-effort normalisation to an ISO date string."""
    if not value:
        return datetime.now(timezone.utc).date().isoformat()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
        except Exception:
            return datetime.now(timezone.utc).date().isoformat()
    s = str(value)[:10]
    return s if re.match(r"\d{4}-\d{2}-\d{2}", s) else datetime.now(timezone.utc).date().isoformat()


def _safe(name):
    """Decorator-ish wrapper used by fetch_all."""
    def runner(fn, *a, **kw):
        try:
            jobs = fn(*a, **kw)
            log.info("%s: %d jobs", name, len(jobs))
            return jobs
        except Exception as exc:  # noqa: BLE001
            log.warning("%s failed: %s", name, exc)
            return []
    return runner


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def fetch_remotive(queries: list[str]) -> list[dict]:
    out = []
    for q in queries:
        data = _get("https://remotive.com/api/remote-jobs",
                    params={"search": q, "limit": 100}).json()
        for j in data.get("jobs", []):
            out.append({
                "id": f"remotive-{j['id']}",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location") or "Remote",
                "remote": True,
                "url": j.get("url", ""),
                "description": strip_html(j.get("description"))[:4000],
                "posted_at": _iso(j.get("publication_date")),
                "source": "Remotive",
                "salary_raw": j.get("salary") or "",
                "tags": j.get("tags", []) or [],
            })
    return out


def fetch_remoteok(_queries=None) -> list[dict]:
    data = _get("https://remoteok.com/api").json()
    out = []
    for j in data:
        if not isinstance(j, dict) or "id" not in j:
            continue  # first element is a legal notice
        salary = ""
        if j.get("salary_min") and j.get("salary_max"):
            salary = f"${int(j['salary_min']):,} - ${int(j['salary_max']):,}"
        out.append({
            "id": f"remoteok-{j['id']}",
            "title": j.get("position") or j.get("title", ""),
            "company": j.get("company", ""),
            "location": j.get("location") or "Remote",
            "remote": True,
            "url": j.get("url", ""),
            "description": strip_html(j.get("description"))[:4000],
            "posted_at": _iso(j.get("date")),
            "source": "RemoteOK",
            "salary_raw": salary,
            "tags": j.get("tags", []) or [],
        })
    return out


def fetch_arbeitnow(_queries=None, pages: int = 4) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        data = _get("https://www.arbeitnow.com/api/job-board-api",
                    params={"page": page}).json()
        rows = data.get("data", [])
        if not rows:
            break
        for j in rows:
            out.append({
                "id": f"arbeitnow-{j.get('slug')}",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("location") or "",
                "remote": bool(j.get("remote")),
                "url": j.get("url", ""),
                "description": strip_html(j.get("description"))[:4000],
                "posted_at": _iso(j.get("created_at")),
                "source": "Arbeitnow",
                "salary_raw": "",
                "tags": (j.get("tags") or []) + (j.get("job_types") or []),
            })
    return out


def fetch_jobicy(_queries=None) -> list[dict]:
    data = _get("https://jobicy.com/api/v2/remote-jobs",
                params={"count": 100}).json()
    out = []
    for j in data.get("jobs", []):
        out.append({
            "id": f"jobicy-{j.get('id')}",
            "title": j.get("jobTitle", ""),
            "company": j.get("companyName", ""),
            "location": j.get("jobGeo") or "Remote",
            "remote": True,
            "url": j.get("url", ""),
            "description": strip_html(j.get("jobExcerpt") or j.get("jobDescription"))[:4000],
            "posted_at": _iso(j.get("pubDate")),
            "source": "Jobicy",
            "salary_raw": j.get("annualSalaryMin") and
                          f"{j.get('annualSalaryMin')} - {j.get('annualSalaryMax')} "
                          f"{j.get('salaryCurrency','')}" or "",
            "tags": j.get("jobIndustry", []) or [],
        })
    return out


def fetch_greenhouse(board: str) -> list[dict]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                params={"content": "true"}).json()
    out = []
    for j in data.get("jobs", []):
        out.append({
            "id": f"gh-{board}-{j['id']}",
            "title": j.get("title", ""),
            "company": board.replace("-", " ").title(),
            "location": (j.get("location") or {}).get("name", ""),
            "remote": "remote" in ((j.get("location") or {}).get("name", "")).lower(),
            "url": j.get("absolute_url", ""),
            "description": strip_html(j.get("content"))[:4000],
            "posted_at": _iso(j.get("updated_at")),
            "source": f"Greenhouse/{board}",
            "salary_raw": "",
            "tags": [],
        })
    return out


def fetch_lever(board: str) -> list[dict]:
    data = _get(f"https://api.lever.co/v0/postings/{board}",
                params={"mode": "json"}).json()
    out = []
    for j in data:
        cats = j.get("categories") or {}
        out.append({
            "id": f"lever-{board}-{j.get('id')}",
            "title": j.get("text", ""),
            "company": board.replace("-", " ").title(),
            "location": cats.get("location", ""),
            "remote": "remote" in (cats.get("location", "") or "").lower(),
            "url": j.get("hostedUrl", ""),
            "description": strip_html(j.get("descriptionPlain") or j.get("description"))[:4000],
            "posted_at": _iso((j.get("createdAt") or 0) / 1000 if j.get("createdAt") else None),
            "source": f"Lever/{board}",
            "salary_raw": "",
            "tags": [cats.get("team", ""), cats.get("commitment", "")],
        })
    return out


def fetch_adzuna(country: str, queries: list[str]) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.info("Adzuna skipped: no credentials")
        return []
    out = []
    for q in queries:
        data = _get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                    params={"app_id": app_id, "app_key": app_key,
                            "results_per_page": 50, "what": q,
                            "content-type": "application/json"}).json()
        for j in data.get("results", []):
            smin, smax = j.get("salary_min"), j.get("salary_max")
            out.append({
                "id": f"adzuna-{j.get('id')}",
                "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("display_name", ""),
                "location": (j.get("location") or {}).get("display_name", ""),
                "remote": False,
                "url": j.get("redirect_url", ""),
                "description": strip_html(j.get("description"))[:4000],
                "posted_at": _iso(j.get("created")),
                "source": f"Adzuna/{country.upper()}",
                "salary_raw": f"{int(smin):,} - {int(smax):,} EUR" if smin and smax else "",
                "tags": [],
            })
    return out


# --------------------------------------------------------------------------- #
def fetch_all(cfg: dict, queries: list[str]) -> list[dict]:
    src = cfg.get("sources", {})
    jobs: list[dict] = []

    if src.get("remotive"):
        jobs += _safe("Remotive")(fetch_remotive, queries)
    if src.get("remoteok"):
        jobs += _safe("RemoteOK")(fetch_remoteok)
    if src.get("arbeitnow"):
        jobs += _safe("Arbeitnow")(fetch_arbeitnow)
    if src.get("jobicy"):
        jobs += _safe("Jobicy")(fetch_jobicy)
    for board in src.get("greenhouse_boards", []) or []:
        jobs += _safe(f"Greenhouse/{board}")(fetch_greenhouse, board)
    for board in src.get("lever_boards", []) or []:
        jobs += _safe(f"Lever/{board}")(fetch_lever, board)
    if src.get("adzuna"):
        for c in src.get("adzuna_countries", []) or []:
            jobs += _safe(f"Adzuna/{c}")(fetch_adzuna, c, queries)

    # de-duplicate on id, then on (title, company)
    seen_id, seen_tc, unique = set(), set(), []
    for j in jobs:
        tc = (j["title"].lower().strip(), j["company"].lower().strip())
        if j["id"] in seen_id or tc in seen_tc:
            continue
        seen_id.add(j["id"])
        seen_tc.add(tc)
        unique.append(j)
    log.info("total unique: %d", len(unique))
    return unique
