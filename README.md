# enforcement-signals

Weekly tracker of public bank enforcement actions (Federal Reserve, OCC, FDIC, FinCEN), scored and mapped to the fraud, AML and sanctions solution areas each one signals a need for. Independent portfolio project.

**Dashboard:** https://chrissanchez111.github.io/enforcement-signals/
**Latest target list:** [`targets/`](targets/) (refreshed every Monday)

## Why

Enforcement actions are public, and they create buying windows. The useful insight is one step removed from the bank that got hit: when a sponsor bank is put under a consent order, it has to tighten oversight of every fintech on its rails, so those fintechs inherit the pressure to prove their transaction monitoring, KYC and KYB hold up.

So the tracker ranks targets by fit, not just by severity:

- **Best fit:** fintechs, payment companies and crypto firms that run on a bank under an order, plus the sponsor banks themselves.
- **Weaker fit:** community banks (often capital-constrained) and megabanks (build in-house or have entrenched vendors). They stay on the list as peer stories.

## How it works

1. **Collect.** Every Monday morning, a GitHub Action runs `src/collect.py`. It pulls the Federal Reserve's enforcement CSV, reads the OCC's monthly enforcement releases (the last 12 months), and merges in curated actions from `data/manual_actions.json` (FDIC, FinCEN, state regulators, and the fintech partners of sponsor banks). Curated entries win when the same action appears twice.
2. **Fan out.** Each curated sponsor bank lists its publicly documented fintech partners, with a source link for every one. Each partner becomes its own target row, carrying the bank's order as its trigger. Partners reported only in older or third-party sources are marked "confirm before outreach" and scored lower.
3. **Classify.** Each action is tagged with themes (BSA/AML, sanctions, third-party/fintech, fraud/consumer, safety and soundness). For Federal Reserve actions, the script opens the press release and the attached order PDF and tags it from the order text; results are cached in `data/fed_cache.json` so each order is read once.
4. **Score.** Theme, action severity, penalty, recency and segment fit combine into a 0–100 score. Actions from the last 180 days are "Just hit"; older ones are "Remediating."
5. **Map.** Each theme maps to the solution areas to lead with, plus a suggested opening question.
6. **Publish.** Actions first seen in the last week are flagged as new. Results are committed to `docs/data.json` (the dashboard) and `targets/YYYY-MM.md` (the monthly list).

## Adding an action

Add an entry to `data/manual_actions.json`. Set `active_order` for older orders that are still in force, so they stay on the list. Every partner needs a `source` link.

```json
{
  "institution": "Example Bank, N.A.",
  "regulator": "OCC",
  "action": "Consent order",
  "date": "2026-11-01",
  "summary": "One or two lines from the order.",
  "themes": ["BSA/AML"],
  "url": "https://link-to-the-order",
  "segment": "Sponsor bank",
  "active_order": true,
  "partners": [
    {"name": "Example Fintech", "segment": "Fintech / payments",
     "note": "Issuing bank for its debit card.", "source": "https://link-showing-the-relationship"}
  ]
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
- Automated FDIC and NYDFS collection
- Automated partner discovery (card issuer disclosures, fintech "banking services provided by" footers)
- Fintech-direct sources: NYDFS and state money-transmitter actions, FinCEN MSB penalties
- Hiring signals (BSA/AML analyst job postings)

## Disclaimer

Public records only. Not affiliated with any regulator or vendor. Nothing here is legal or compliance advice.
