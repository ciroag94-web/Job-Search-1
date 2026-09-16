"""Enrichment + scoring.

Turns a raw job dict into a scored, filterable record:
    country, city, salary_min, salary_max, salary_source, company_size,
    stage_signals, score, reasons, weak_balance
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Location parsing
# --------------------------------------------------------------------------- #
CITY_COUNTRY = {
    "munich": "Germany", "münchen": "Germany", "muenchen": "Germany",
    "berlin": "Germany", "hamburg": "Germany", "frankfurt": "Germany",
    "cologne": "Germany", "köln": "Germany", "stuttgart": "Germany",
    "düsseldorf": "Germany", "dusseldorf": "Germany", "leipzig": "Germany",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands",
    "dublin": "Ireland", "cork": "Ireland",
    "zurich": "Switzerland", "zürich": "Switzerland", "zug": "Switzerland",
    "geneva": "Switzerland", "basel": "Switzerland",
    "vienna": "Austria", "wien": "Austria",
    "paris": "France", "lyon": "France",
    "copenhagen": "Denmark", "stockholm": "Sweden", "oslo": "Norway",
    "helsinki": "Finland", "luxembourg": "Luxembourg",
    "milan": "Italy", "milano": "Italy", "rome": "Italy", "roma": "Italy",
    "turin": "Italy", "torino": "Italy", "bologna": "Italy", "naples": "Italy",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
    "lisbon": "Portugal", "lisboa": "Portugal", "porto": "Portugal",
    "warsaw": "Poland", "warszawa": "Poland", "krakow": "Poland", "kraków": "Poland",
    "prague": "Czechia", "praha": "Czechia", "brno": "Czechia",
    "budapest": "Hungary", "bucharest": "Romania", "sofia": "Bulgaria",
    "tallinn": "Estonia", "riga": "Latvia", "vilnius": "Lithuania",
    "valletta": "Malta", "sliema": "Malta", "athens": "Greece",
    "london": "United Kingdom", "manchester": "United Kingdom",
    "edinburgh": "United Kingdom", "belfast": "United Kingdom",
    "dubai": "UAE", "abu dhabi": "UAE",
    "new york": "USA", "san francisco": "USA", "austin": "USA",
    "singapore": "Singapore",
}

COUNTRY_WORDS = {
    "germany": "Germany", "deutschland": "Germany", "netherlands": "Netherlands",
    "ireland": "Ireland", "switzerland": "Switzerland", "austria": "Austria",
    "france": "France", "denmark": "Denmark", "sweden": "Sweden",
    "norway": "Norway", "finland": "Finland", "luxembourg": "Luxembourg",
    "italy": "Italy", "italia": "Italy", "spain": "Spain", "españa": "Spain",
    "portugal": "Portugal", "poland": "Poland", "polska": "Poland",
    "czech": "Czechia", "czechia": "Czechia", "hungary": "Hungary",
    "romania": "Romania", "bulgaria": "Bulgaria", "estonia": "Estonia",
    "latvia": "Latvia", "lithuania": "Lithuania", "malta": "Malta",
    "greece": "Greece", "cyprus": "Cyprus", "belgium": "Belgium",
    "united kingdom": "United Kingdom", "uk": "United Kingdom",
    "emirates": "UAE", "uae": "UAE",
    "united states": "USA", "usa": "USA", "canada": "Canada",
    "singapore": "Singapore", "europe": "Europe (any)", "emea": "Europe (any)",
    "worldwide": "Worldwide", "anywhere": "Worldwide", "global": "Worldwide",
}

REMOTE_RE = re.compile(r"\b(remote|anywhere|work from home|wfh|distributed)\b", re.I)


def parse_location(job: dict) -> tuple[str, str, bool]:
    """Return (country, city, is_remote)."""
    raw = (job.get("location") or "").strip()
    low = raw.lower()
    is_remote = bool(job.get("remote")) or bool(REMOTE_RE.search(low))

    city = ""
    for c, country in CITY_COUNTRY.items():
        if re.search(rf"\b{re.escape(c)}\b", low):
            city = c.title()
            return country, "Munich" if c in ("münchen", "muenchen") else city, is_remote

    country = ""
    for w, name in COUNTRY_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", low):
            country = name
            break

    if not country:
        country = "Remote / Unspecified" if is_remote else (raw or "Unspecified")
    return country, city, is_remote


# --------------------------------------------------------------------------- #
# Salary
# --------------------------------------------------------------------------- #
CUR = {"$": 0.92, "usd": 0.92, "€": 1.0, "eur": 1.0, "£": 1.17, "gbp": 1.17,
       "chf": 1.05, "sek": 0.087, "dkk": 0.134, "nok": 0.086, "pln": 0.23}

NUM_RE = re.compile(
    r"(?P<cur>[$€£]|usd|eur|gbp|chf|sek|dkk|nok|pln)?\s*"
    r"(?P<num>\d{2,3}(?:[.,]\d{3})+|\d{2,3}\s?[kK]|\d{4,7})",
    re.I)


def _to_eur(num_str: str, cur: str | None) -> float | None:
    s = num_str.strip().lower().replace(" ", "")
    try:
        if s.endswith("k"):
            val = float(s[:-1].replace(",", ".")) * 1000
        else:
            val = float(re.sub(r"[.,](?=\d{3}\b)", "", s).replace(",", "."))
    except ValueError:
        return None
    rate = CUR.get((cur or "eur").lower(), 1.0)
    return val * rate


def parse_salary(text: str) -> tuple[int | None, int | None]:
    """Pull a plausible annual EUR range out of free text."""
    if not text:
        return None, None
    window = text[:1500]
    vals = []
    for m in NUM_RE.finditer(window):
        v = _to_eur(m.group("num"), m.group("cur"))
        if v and 18_000 <= v <= 400_000:
            vals.append(int(v))
    if not vals:
        return None, None
    vals = sorted(set(vals))
    return vals[0], vals[-1] if len(vals) > 1 else vals[0]


def estimate_salary(city: str, country: str, benchmarks: dict) -> tuple[int, int, str]:
    key = city if city in benchmarks else None
    if not key:
        for k in benchmarks:
            if k.lower() == (city or "").lower():
                key = k
                break
    if not key:
        key = "Remote"
    base = benchmarks[key]["gross_eur"]
    return int(base * 0.85), int(base * 1.25), f"estimate ({key} benchmark)"


def purchasing_power(city: str, benchmarks: dict) -> float | None:
    b = benchmarks.get(city)
    if not b:
        return None
    return round(b["gross_eur"] / b["col_index"], 1)


def weak_balance(city: str, cfg: dict) -> bool:
    """True when the city pays too little in absolute terms, or buys too little."""
    b = cfg["salary_benchmarks"].get(city)
    if not b:
        return False
    pp = b["gross_eur"] / b["col_index"]
    return (pp < cfg.get("min_purchasing_power", 550)
            or b["gross_eur"] < cfg.get("min_gross_eur", 48000))


# --------------------------------------------------------------------------- #
# Company size / stage
# --------------------------------------------------------------------------- #
SIZE_RULES = [
    (re.compile(r"\b(pre-seed|preseed|seed stage|seed-stage|founding team|founding member|"
                r"first hire|series a)\b", re.I), "Startup (1-50)"),
    (re.compile(r"\b(series b|series c|scale-?up|fast-growing|high-growth|"
                r"we are \d{2,3} people)\b", re.I), "Scale-up (50-500)"),
    (re.compile(r"\b(\d{1,2},\d{3}\+? employees|global leader|fortune|"
                r"multinational|worldwide offices)\b", re.I), "Enterprise (1000+)"),
]


def guess_company_size(text: str) -> str:
    for rx, label in SIZE_RULES:
        if rx.search(text):
            return label
    return "Unknown"


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_job(job: dict, cfg: dict) -> dict:
    kw = cfg["keywords"]
    loc_cfg = cfg["locations"]
    bench = cfg["salary_benchmarks"]

    blob = f"{job['title']} {job['company']} {job['description']} {' '.join(map(str, job.get('tags', [])))}".lower()
    title = job["title"].lower()

    # hard exclusions
    for bad in kw["exclude"]:
        if bad in title:
            return {}

    score, reasons = 0, []

    core_hits = [k for k in kw["core"] if k in blob]
    adj_hits = [k for k in kw["adjacent"] if k in blob]
    sig_hits = [k for k in kw["company_signals"] if k in blob]

    if not core_hits and not adj_hits:
        return {}

    # domain relevance — stronger when it's in the title
    title_core = [k for k in kw["core"] if k in title]
    score += min(len(core_hits), 5) * 4
    score += len(title_core) * 8
    if title_core:
        reasons.append(f"core match in title: {', '.join(title_core[:3])}")

    # evolving / non-classic role
    title_adj = [k for k in kw["adjacent"] if k in title]
    score += min(len(adj_hits), 4) * 3 + len(title_adj) * 10
    if title_adj:
        reasons.append(f"role can evolve: {', '.join(title_adj[:3])}")

    # company type
    score += min(len(sig_hits), 5) * 5
    if sig_hits:
        reasons.append(f"startup / SaaS signals: {', '.join(sig_hits[:4])}")

    # location
    country, city, is_remote = parse_location(job)
    display_city = city or ("Remote" if is_remote else "—")
    if city.lower() in ("munich", "münchen"):
        score += 30
        reasons.append("Munich — top priority location")
    elif is_remote:
        score += 22
        reasons.append("remote")
    elif city in loc_cfg["good_eu"]:
        score += 14
        reasons.append(f"{city}: good salary/cost balance")
    elif city in loc_cfg["neutral_eu"]:
        score += 5
    elif country in ("USA", "Canada", "Singapore") and not is_remote:
        score -= 20
        reasons.append("outside EU, on-site")

    # salary
    smin, smax = parse_salary(job.get("salary_raw") or "")
    if not smin:
        smin, smax = parse_salary(job.get("description", ""))
    if smin:
        salary_source = "from posting"
        score += 8
        reasons.append("salary disclosed")
    else:
        smin, smax, salary_source = estimate_salary(city, country, bench)

    pp = purchasing_power(city, bench)
    weak = weak_balance(city, cfg)
    if weak:
        score -= 12
        reasons.append("weak salary / cost-of-living balance")
    if smax and smax >= 90_000:
        score += 6

    # German requirement is only a soft penalty (user has elementary German)
    if re.search(r"\b(fluent german|verhandlungssicher|muttersprache|native german|"
                 r"deutsch als muttersprache)\b", blob):
        score -= 8
        reasons.append("fluent German likely required")

    size = guess_company_size(blob)
    if size == "Startup (1-50)":
        score += 10
    elif size == "Scale-up (50-500)":
        score += 6

    return {
        **job,
        "country": country,
        "city": display_city,
        "is_remote": is_remote,
        "salary_min": smin,
        "salary_max": smax,
        "salary_source": salary_source,
        "purchasing_power": pp,
        "weak_balance": weak,
        "company_size": size,
        "score": max(0, min(100, score)),
        "reasons": reasons[:5],
    }
