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

## How it scores, and why

Each target gets a 0–100 score by adding up five parts. The point is ranking: who to call first, and why now.

| Part | Points | Why |
|---|---|---|
| **What the order is about** (highest theme) | BSA/AML 40 · Sanctions 35 · Third-party/fintech 35 · Fraud/consumer 20 · Safety & soundness 5 | AML, sanctions and fintech-oversight failures map directly to products a fraud/AML platform sells. Capital and management problems mostly don't. |
| **How serious the action is** | Consent order or cease-and-desist +20 · Written/formal agreement or civil money penalty +15 · Prompt corrective action +10 | Formal orders come with deadlines and required program reviews, which is when tools get bought. |
| **Money penalty attached** | +10 | A fine puts the problem in front of the board. |
| **How recent** | Last 90 days +25 · last 180 days +15 · older +5 | Earlier outreach lands while the remediation plan is being written. Older orders still count: remediation runs 6–18 months. |
| **Fit with the buyer** (segment) | Fintech, crypto or marketplace +15 · Sponsor bank +10 · Regional bank 0 · Community bank −20 · Megabank −30 | Fintechs, crypto firms and sponsor banks buy fraud/AML platforms. Community banks are often capital-constrained; megabanks build in-house or have entrenched vendors. |

Two adjustments: partner links reported only in older or third-party sources lose 15 points ("confirm before outreach"), and existing Sardine customers are scored 0 and listed as references.

**Fintech partners** of a bank under an order inherit the bank's themes, plus "Third-party/fintech." They lead with transaction monitoring and KYB (what their bank will ask for) and with device-and-behavior and payment-fraud tools, because tighter controls usually mean more good customers declined. Each fintech gets two openers: one on compliance pressure, one on approval rates. **Sponsor banks** lead with sanctions screening, where AI automation has the clearest public proof.

## What it can't do yet

- **Fintech partners are researched by hand.** Every link has a source, but the tool doesn't discover new partners on its own. A new sponsor-bank order shows up automatically; its fintechs have to be added to `data/manual_actions.json`.
- **Only two regulators are automated.** The Federal Reserve (CSV feed) and the OCC (monthly releases). FDIC, FinCEN and state regulators like NYDFS are curated by hand.
- **The OCC is a trickle.** Many months have no bank actions at all, and most actions are capital or management problems at community banks.
- **Federal Reserve tagging is keyword-based.** It reads the order text and needs two keyword hits per theme, so it can mis-tag an order. Some Fed orders can't be read and stay "Unclassified."
- **Scores are judgment calls, not a trained model.** The weights encode one view of who buys and when. They're easy to change, and worth arguing about.
- **Hiring signals are checked by hand.** Recent compliance hires and open AML roles (a sign of alert backlog or a team being built) are looked up on careers pages and LinkedIn and noted in the summary. No names are stored. Automating this is next.
- **Name matching is simple.** Duplicate detection and the customer flag match on normalized names, so similarly named institutions can collide.

## Existing customers

`data/known_customers.json` lists companies publicly named as Sardine customers (from its customers page and job posting). Any target that matches is flagged as an existing customer, scored 0 and moved out of the best-fit list, so it's used as a reference rather than prospected.

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
