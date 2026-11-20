# enforcement-signals

Weekly tracker of public bank enforcement actions (Federal Reserve, OCC, FDIC, FinCEN), scored and mapped to the fraud, AML and sanctions solution areas each one signals a need for. Independent portfolio project.

**Dashboard:** https://chrissanchez111.github.io/enforcement-signals/
**Latest target list:** [`targets/`](targets/) (refreshed every Monday)

## Why

Enforcement actions are public, and they create a buying window. A consent order usually requires the bank to review its whole BSA/AML program and show progress on a deadline. The order also puts every peer bank on alert. This project turns those public records into a ranked prospect list, refreshed weekly with a reason to reach out.

## How it works

1. **Collect.** Every Monday morning, a GitHub Action runs `src/collect.py`. It pulls the Federal Reserve's enforcement CSV and merges in curated actions from `data/manual_actions.json` (OCC, FDIC and FinCEN don't publish a clean machine-readable feed).
2. **Classify.** Each action is tagged with themes (BSA/AML, sanctions, third-party/fintech, fraud/consumer, safety and soundness). For Federal Reserve actions, the script opens the press release and the attached order PDF and tags it from the order text; results are cached in `data/fed_cache.json` so each order is read once.
3. **Score.** Theme, action severity, penalty and recency combine into a 0–100 signal score. Actions from the last 180 days are "Just hit"; older ones are "Remediating."
4. **Map.** Each theme maps to the solution areas to lead with, plus a suggested opening question.
5. **Publish.** Actions first seen in the last week are flagged as new. Results are committed to `docs/data.json` (the dashboard) and `targets/YYYY-MM.md` (the monthly list).

## Adding an action

Add an entry to `data/manual_actions.json`:

```json
{
  "institution": "Example Bank, N.A.",
  "regulator": "OCC",
  "action": "Consent order",
  "date": "2026-11-01",
  "summary": "One or two lines from the order.",
  "themes": ["BSA/AML"],
  "url": "https://link-to-the-order"
}
```

## Run locally

```bash
python -m unittest discover -s tests
python src/collect.py
```

Standard library plus `pypdf` (for reading the Fed's attached orders): `pip install pypdf`.

## Roadmap

- Automated OCC and FDIC collection
- Peer-bank matching (similar size and fintech exposure to banks that were just hit)
- Hiring signals (BSA/AML analyst job postings)

## Disclaimer

Public records only. Not affiliated with any regulator or vendor. Nothing here is legal or compliance advice.
