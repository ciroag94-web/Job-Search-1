# Job Hunter

A self-hosted job search agent for a compliance / financial-crime professional who wants
the *next* role, not the same one again: early-stage startups, B2B SaaS, scale-ups,
founding and chief-of-staff style openings — ranked for **Munich**, **remote**, and
anywhere in the EU where the pay actually matches the cost of living.

**The search runs the moment you open the page.** The dashboard queries the job boards
itself, scores the results in the browser, and shows them — no button to press, no
waiting for a server. On top of that, a GitHub Action repeats the run every 24 hours,
adds the sources a browser can't reach, and keeps a dated history so "new today"
means something.

```
job-hunter/
├── requirements.txt
├── src/
│   ├── main.py                   # the nightly run (Python)
│   ├── fetchers.py               # job board APIs
│   └── scoring.py                # location, salary, company size, match score
├── docs/                         # published by GitHub Pages
│   ├── index.html                # the dashboard — one self-contained file
│   ├── config.json               # everything you'll want to tune — read by BOTH
│   └── jobs.json                 # nightly history, written by the Action
└── .github/workflows/job-hunt.yml
```

`index.html` is self-contained — the fetch-and-score engine is inside it, so double-clicking
the file works. It reads `docs/config.json` when one is served alongside it (that is what
Python reads too, so the two runs never disagree) and falls back to a copy of the same
config baked into the page when it can't.

**After editing `config.json`, paste the new contents over the `DEFAULT_CONFIG` object
near the top of `index.html`** so the offline fallback stays current. Served over
GitHub Pages, the file always wins and the fallback never runs.

## Deploy in five minutes

1. Create an empty repository on GitHub (public, so Pages is free).
2. Push this folder:

   ```bash
   cd job-hunter
   git init && git add -A
   git commit -m "Job hunter"
   git branch -M main
   git remote add origin https://github.com/<you>/job-hunter.git
   git push -u origin main
   ```

3. **Settings → Pages** → Source: *Deploy from a branch* → branch `main`, folder `/docs` → Save.
4. **Settings → Actions → General** → Workflow permissions → *Read and write permissions* → Save.
   (The bot commits `docs/jobs.json` back to the repo.)
5. **Actions → Job hunt → Run workflow** to fill the dashboard now instead of waiting for 06:00 UTC.

Your board lives at `https://<you>.github.io/job-hunter/`.

## Run it locally

Double-click `docs/index.html` and it searches. For the version closest to production —
config file read from disk, nightly history merged in — serve the folder instead:

```bash
python -m http.server -d docs 8000   # http://localhost:8000
```

To run the Python side by hand:

```bash
pip install -r requirements.txt
python src/main.py            # real fetch, updates docs/jobs.json
python src/main.py --demo     # sample data, no network
```

## What runs where

| | On page load, in your browser | Nightly, on GitHub Actions |
|---|---|---|
| Remotive, Arbeitnow, Jobicy, Greenhouse, Lever | yes | yes |
| RemoteOK, Adzuna | blocked by CORS | yes |
| History / `first_seen` dates | read from `jobs.json` | written to `jobs.json` |

Each source reports itself as it lands — you see `Remotive: 142`, `Arbeitnow: 87`, or
`unreachable` if a board is down. One dead API never stops the rest. **Search again**
re-runs everything without reloading.

## Sources

No API key needed: **Remotive**, **RemoteOK**, **Arbeitnow** (strong on Germany),
**Jobicy**, plus any **Greenhouse** or **Lever** board you list in `docs/config.json` —
that is how you track specific startups (`boards.greenhouse.io/<token>` → add `<token>`).
Those five run in the browser too, so adding a board shows up on the very next page load.

Optional: **Adzuna** for on-site German/Dutch/Austrian/Italian roles. Register a free
app, then add `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` under **Settings → Secrets and
variables → Actions**, and set `adzuna` to `true` in `docs/config.json`. Adzuna and RemoteOK only feed the
nightly run; their results reach the page through `jobs.json`.

LinkedIn, Indeed and Xing are deliberately absent — scraping them breaks their terms and
gets the runner blocked. Use the dashboard to triage, then apply on those platforms by hand.

## How a job is scored

| Signal | Effect |
|---|---|
| AML / KYC / compliance / fraud term in the title | +8 each |
| "Evolving" role in the title — founding, chief of staff, biz ops, product, GTM | +10 each |
| Startup / seed / Series A / B2B SaaS / equity mentions | +5 each |
| Munich | +30 |
| Remote | +22 |
| Berlin, Amsterdam, Dublin, Zurich, Copenhagen, Luxembourg… | +14 |
| Salary disclosed in the posting | +8 |
| Company looks 1–50 people | +10 |
| Weak pay-vs-cost city | −12 |
| Fluent German required | −8 |
| On-site outside the EU | −20 |
| Internship, working student, unpaid | dropped entirely |

Everything in that table comes from `docs/config.json`, applied identically by
`src/scoring.py` and the engine inside `index.html`.

## Salary

Shown as a range on every card. When the posting states a figure, it is parsed and
converted to EUR and labelled *from posting*. When it doesn't, the range is estimated
from the city benchmark table in `docs/config.json` and labelled *estimate* — so you always
know which number you're looking at. A city is flagged **weak pay/cost balance** when its
benchmark salary is below €48k or its purchasing power falls under the threshold; those
roles are hidden by default and the filter is one click away.

Benchmarks are a starting point, not gospel. Update them as you learn what the market
actually pays you.

## Dashboard filters

Country, city (the list narrows to the selected country), company size, source, minimum
salary, free-text search, remote-only, added-today, salary-disclosed-only, and
hide-weak-balance. Sort by match score, date, or salary.

## Changing what it looks for

Everything lives in `docs/config.json`: keywords, excluded words, priority cities, salary
benchmarks, sources, the minimum score. Change the schedule in
`.github/workflows/job-hunt.yml` — `cron: "0 6 * * *"` is 06:00 UTC daily; `"0 6,18 * * *"`
would make it twice a day.

## Company size

Inferred from the wording of the posting ("Series A", "founding team", "global leader",
"10,000+ employees"), because no free API exposes headcount. It reads `Unknown` when the
text gives nothing away — that is honest rather than guessed.
