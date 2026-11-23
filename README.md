# enforcement-signals

A weekly prospecting engine for fraud and AML software. It watches four public signals, figures out which banks, fintechs and crypto firms just got a reason to buy, and delivers one short Monday brief. Independent portfolio project.

**Dashboard:** https://chrissanchez111.github.io/enforcement-signals/
**Latest target list:** [`targets/`](targets/) (refreshed every Monday)

## At a glance

| Signal | The question it answers | Where it runs | Output |
|---|---|---|---|
| **1. Enforcement actions** | Who did a regulator just order to fix their BSA/AML, sanctions or fraud controls? | GitHub Action (`src/collect.py`) | `docs/data.json`, dashboard, `targets/` |
| **2. Sponsor-bank fan-out** | Which fintechs run on a bank that's under an order, and so inherit the pressure? | Same, from `data/manual_actions.json` | Partner rows in `docs/data.json` |
| **3. Champion moves** | Which risk and compliance leaders left a Sardine customer for a company that isn't one? | Claude scheduled task + Clay | Weekly email only (names stay private) |
| **4. Remediation hiring** | Who's posting jobs that say "consent order," "lookback" or "remediation"? | GitHub Action (`src/jobs.py`) | `docs/jobs.json` |

On top of the four signals, the weekly email adds a **news watch** (the 5 articles from the past week that matter most) and a **study pick** (the one Sardine product page that matches the week's top signal).

The strongest leads are where signals overlap: for example, a fintech whose sponsor bank is under a BSA/AML order and which just hired a compliance leader from a Sardine customer.

## The Monday run

| Time (ET) | What happens | Where |
|---|---|---|
| ~6:17 AM | Pull Fed and OCC enforcement actions, merge curated FDIC/FinCEN/state actions and sponsor-bank partners, classify and score them. Then scan job boards for remediation hiring. Commit the results. | GitHub Action (`.github/workflows/weekly.yml`) |
| 7:52 AM | Read the fresh data, search Clay for champion moves, check each new employer for enforcement, scan the week's news, pick a product to study, and send **one** email. | Claude scheduled task |

### What the weekly email contains, in order

1. **Top matches:** companies where two signals meet (a champion move, an open enforcement action on the company or its sponsor bank, or remediation hiring).
2. **Champion moves:** new moves in full (name, new role and employer, the Sardine customer they came from, confirmed or unverified, any enforcement flag, LinkedIn). Everyone already reported collapses into one "Still tracking" line.
3. **5 articles to watch:** ranked by how directly each one opens a buying window, each with one line on why it matters.
4. **Study this** (a matching Sardine product page, with what to learn from it) or **Monday Catch** (the week's must-know story when no product fits).
5. **Hiring signals:** up to 5 companies flagged "remediation" or "build-out."
6. **Everything else:** counts plus links to the dashboard and full lists.

**Repeats:** before searching, the task reads earlier "Weekly signals" emails in Gmail and collects everyone already reported. A person gets full detail again only if they change jobs again or a new enforcement flag appears. Nothing new has to be stored for this.

**Send-once guard:** right before sending, the task checks for a "Weekly signals" email sent in the last 6 hours and won't send a second. If one part fails (Clay, news, jobs), the email still goes out with a line saying what broke.

## What's public and what's private

- **Public (this repo):** enforcement records, sponsor-bank partner links with sources, scoring, company names on job boards, the list of publicly named Sardine customers, and the champion-search settings (`data/champion_watch.json`).
- **Private (the weekly email only):** the names of people in champion moves. **No individual's name is stored in this repo.**
- **No outreach.** The tool finds and ranks accounts. It doesn't write or send messages to prospects.

## Signals 1–2: enforcement actions and sponsor-bank fan-out

**Why:** enforcement actions are public, and they create buying windows. The useful insight is one step removed from the bank that got hit: when a sponsor bank is put under a consent order, it has to tighten oversight of every fintech on its rails, so those fintechs inherit the pressure to prove their transaction monitoring, KYC and KYB hold up. That's why the tracker ranks by fit, not just severity. Fintechs, payment companies, crypto firms and sponsor banks are the best fit; community banks and megabanks stay on the list as peer stories.

**How it works:**

1. **Collect.** Every Monday morning, a GitHub Action runs `src/collect.py`. It pulls the Federal Reserve's enforcement CSV, reads the OCC's monthly enforcement releases (the last 12 months), and merges in curated actions from `data/manual_actions.json` (FDIC, FinCEN, state regulators, and the fintech partners of sponsor banks). Curated entries win when the same action appears twice.
2. **Fan out.** Each curated sponsor bank lists its publicly documented fintech partners, with a source link for every one. Each partner becomes its own target row, carrying the bank's order as its trigger. Partners reported only in older or third-party sources are marked "confirm before outreach" and scored lower.
3. **Classify.** Each action is tagged with themes (BSA/AML, sanctions, third-party/fintech, fraud/consumer, safety and soundness). For Federal Reserve actions, the script opens the press release and the attached order PDF and tags it from the order text; results are cached in `data/fed_cache.json` so each order is read once.
4. **Score.** Theme, action severity, penalty, recency and segment fit combine into a 0–100 score. Actions from the last 180 days are "Just hit"; older ones are "Remediating."
5. **Map.** Each theme maps to the solution areas to lead with, plus a suggested opening question.
6. **Publish.** Actions first seen in the last week are flagged as new. Results are committed to `docs/data.json` (the dashboard) and `targets/YYYY-MM.md` (the monthly list).

### How it scores, and why

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

## Signal 3: champion moves

Risk, fraud and compliance leaders who leave a publicly named Sardine customer for a new role. In their first months, new leaders often revisit vendors and bring in tools they already trust.

- **Where the customer list comes from:** `data/known_customers.json` (67 names from Sardine's customers page, its job posting and ICBA's partner listing). `data/champion_watch.json` maps 65 of them to verified web domains, searched in batches of 10. The two left out (Heritage Bank, Portage Bank) share their names with several other banks, so the right one can't be confirmed.
- **Who counts:** people who held a title like Chief Risk Officer, BSA Officer, Chief Compliance Officer, Head of Fraud or Head of Financial Crimes at the customer, and started a similar role somewhere else in the last 6 months.
- **Confirmed vs unverified:** Clay's work history must show a role at the customer they were matched on. Otherwise the person is marked "unverified."
- **Every move stays on the list.** Enforcement is a bonus, not a filter. The only drop is a new employer that's already a Sardine customer.
- **Enforcement check on each new employer:**
  1. Is it, or a bank it runs on, in this tracker?
  2. If it's a fintech, which bank holds its accounts ("banking services provided by…"), and is that bank under an order?
  3. A targeted search of the regulators the tracker doesn't automate (FDIC, FinCEN, CFPB, NYDFS and other states, plus the CFTC and SEC for non-banks), covering 3 years and noting open vs terminated.
  4. Any open action on the company or its sponsor bank makes it a top match.
- **Limit:** Clay shows that someone *worked at* a Sardine customer, not that they *used* Sardine. Treat them as people who know the category, not confirmed champions.

## Signal 4: remediation hiring

Companies hiring to fix a compliance problem. `src/jobs.py` reads the public Greenhouse, Lever and Ashby job-board APIs (no login needed) for every best-fit target in the tracker, plus the companies in `data/job_watch.json`. Existing customers are skipped. A role counts if its title is a financial-crime role (BSA/AML, KYC/KYB, fraud, sanctions, transaction monitoring, compliance). Each company is then labeled:

- **Remediation:** a posting mentions a consent order, remediation, a lookback, MRAs, regulatory or exam findings, an enforcement action, or sponsor/partner bank oversight.
- **Build-out:** three or more financial-crime roles open at once.
- **Hiring / none:** fewer roles and no remediation language.

Results go to `docs/jobs.json`. The board each company uses is found by trying name-based slugs (e.g. `evolvebankandtrust`, `evolve`) and cached in `data/job_boards_cache.json`, rechecked monthly when nothing is found.

## News watch and study pick (email only)

- **News:** web searches each week for regulator press releases (OCC, FDIC, Fed, FinCEN, CFPB, NYDFS), "consent order" and new-BSA-officer news, Banking Dive and American Banker, news on the top targets and new champion employers, and Sardine and its competitors (Socure, Alloy, SEON, Sift, Feedzai, Unit21, BioCatch). Only items from the last 7 days with a real link make the cut.
- **Study pick:** the one sardine.ai product page that best fits the week's #1 signal (e.g. a BSA/AML order maps to AML Transaction Monitoring, a sanctions story to Sanctions Screening). The page is loaded before it's linked. If nothing fits, the email runs a "Monday Catch" story instead.

## Existing customers

`data/known_customers.json` lists companies publicly named as Sardine customers. Any enforcement target that matches is flagged, scored 0 and moved out of the best-fit list, so it's used as a reference rather than prospected. Champion moves to a customer and job scans of customers are skipped the same way.

## Repo map

| Path | What it is |
|---|---|
| `src/collect.py` | Signals 1–2: pulls the Fed CSV and OCC releases, merges curated actions, fans out partners, classifies, scores, writes the dashboard data and monthly list |
| `src/occ.py` | Reads the OCC's numbered monthly enforcement releases |
| `src/jobs.py` | Signal 4: job-board scanner |
| `data/manual_actions.json` | Hand-curated FDIC, FinCEN and state actions, plus each sponsor bank's fintech partners (every link sourced) |
| `data/known_customers.json` | Publicly named Sardine customers (used to avoid prospecting them) |
| `data/champion_watch.json` | Signal 3 settings: customer domains, titles, lookback, scoring rules |
| `data/job_watch.json` | Extra companies for the job scan, with optional board hints |
| `data/fed_cache.json`, `data/occ_cache.json`, `data/job_boards_cache.json` | Caches so each order or board is checked once |
| `docs/index.html`, `docs/data.json`, `docs/jobs.json` | The public dashboard and its data |
| `targets/YYYY-MM.md` | That month's ranked target list |
| `tests/` | Unit tests for the collector and the job scanner (run on every Action) |
| `.github/workflows/weekly.yml` | The Monday Action |

## What it can't do yet

- **Fintech partners are researched by hand.** Every link has a source, but new partners aren't discovered automatically. A new sponsor-bank order shows up on its own; its fintechs have to be added to `data/manual_actions.json`.
- **Only two regulators are automated.** The Federal Reserve (CSV feed) and the OCC (monthly releases). FDIC, FinCEN and state actions are curated by hand, and checked by search for champion employers.
- **The OCC is a trickle.** Many months have no bank actions, and most are capital or management problems at community banks.
- **Federal Reserve tagging is keyword-based.** It needs two keyword hits per theme, so it can mis-tag an order, and some orders can't be read.
- **Scores are judgment calls, not a trained model.** The weights encode one view of who buys and when.
- **Job scanning covers three job-board systems.** Banks on Workday, iCIMS or their own career sites aren't covered and are listed under `no_board_found`. Boards are matched by name, so a wrong match is possible.
- **Champion moves depend on Clay's data.** Small teams leave few profiles, and Clay can't show whether someone actually used Sardine.
- **Name matching is simple.** Similarly named institutions can collide.

## In one minute

Fraud and AML tools get bought when something forces the issue. This project watches four public triggers: regulator orders, the fintechs riding on a bank under an order, compliance leaders who just left a Sardine customer, and job posts that say "remediation." Every Monday it ranks the accounts where those triggers overlap and sends one brief, with the week's must-read news and the product page worth studying.

Under the hood, a GitHub Action pulls Federal Reserve and OCC data and scans Greenhouse, Lever and Ashby job boards. A Claude scheduled task then runs Clay searches across 65 Sardine customers, checks each new employer and its sponsor bank for enforcement, and writes the email. Scoring is a transparent 0–100 rubric, weighted toward the buyers a fraud and AML platform actually sells to.

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

## Glossary

**Compliance and financial crime**
- **AML (anti-money laundering):** the controls a financial company uses to detect and report money laundering.
- **BSA (Bank Secrecy Act):** the main US anti-money-laundering law. "BSA/AML" refers to a bank's whole program for complying with it.
- **BSA Officer:** the person a bank names as accountable for its BSA/AML program. Regulators deal with them directly.
- **CCO (Chief Compliance Officer):** the executive over all regulatory compliance.
- **CRO (Chief Risk Officer):** the executive over risk overall: credit, fraud, operational and compliance risk.
- **MLRO (Money Laundering Reporting Officer):** the UK and EU equivalent of a BSA Officer.
- **CAMS / CFE / CRCM:** common certifications for AML specialists, fraud examiners and compliance managers.
- **KYC (Know Your Customer):** verifying a person's identity at account opening.
- **KYB (Know Your Business):** the same for a business, including who owns and controls it (beneficial owners).
- **CIP / CDD / EDD:** Customer Identification Program, Customer Due Diligence and Enhanced Due Diligence. The required steps for knowing a customer, with EDD reserved for higher-risk customers.
- **Transaction monitoring:** reviewing payments after they happen to spot suspicious patterns.
- **Typology:** a known money-laundering or fraud pattern, such as structuring, funnel accounts or layering.
- **SAR (Suspicious Activity Report):** the report a bank files with FinCEN when it suspects a crime.
- **Sanctions screening:** checking customers and payments against government blocklists before money moves.
- **OFAC / SDN list:** the Treasury office that runs US sanctions, and its main list of blocked people and entities.
- **PEP (politically exposed person):** a public official or their relative, who gets extra scrutiny.
- **Adverse media:** negative news about a customer that may signal risk.
- **False positive:** an alert on activity that turns out to be legitimate. Cutting these is a main way AI saves analyst time.
- **TPRM (third-party risk management):** how a bank oversees its vendors and partners, including fintechs on its charter.

**Fraud**
- **ATO (account takeover):** a criminal getting into a real customer's account.
- **APP fraud / scams:** authorized push payment fraud, where the victim is tricked into sending money themselves.
- **Money mule:** an account used to move stolen or laundered money, sometimes without the owner knowing.
- **Chargeback:** a card payment reversed after a dispute. Too many costs a merchant money and can cost it card acceptance.
- **Device intelligence / behavioral biometrics:** signals about the phone or computer and how a person types, taps and moves, used to tell real users from fraudsters and bots.
- **Consortium:** shared fraud data across many companies, so a fraudster seen at one is flagged at others.

**Banking structure**
- **Sponsor bank:** a licensed bank that lets fintechs offer accounts and cards under its charter. Regulators hold it responsible for everything on its rails.
- **BaaS (banking-as-a-service):** the business model of a sponsor bank, often delivered through a middleware platform.
- **Fintech partner / program:** a fintech running on a sponsor bank. It's where "banking services provided by…" shows up in an app.
- **Community / regional / megabank:** rough size tiers, from small local banks to the largest national banks.
- **ACH / RTP / FedNow:** US payment rails: batch bank transfers, and two instant-payment networks.
- **MSB (money services business):** a non-bank that moves or exchanges money, such as a remittance company.

**Regulators**
- **OCC (Office of the Comptroller of the Currency):** supervises national banks.
- **FDIC (Federal Deposit Insurance Corporation):** insures deposits and supervises state banks that aren't Fed members.
- **Fed (Federal Reserve):** supervises state member banks and bank holding companies.
- **FinCEN (Financial Crimes Enforcement Network):** the Treasury bureau that writes and enforces BSA rules and receives SARs.
- **CFPB (Consumer Financial Protection Bureau):** enforces consumer-protection law.
- **NYDFS (New York Department of Financial Services):** New York's regulator, influential for crypto and money transmitters.
- **CFTC / SEC:** federal regulators for derivatives (including prediction markets) and for securities.
- **FCA:** the UK's financial regulator.

**Enforcement terms**
- **Consent order:** a formal order the institution agrees to, with required fixes and deadlines. The strongest common signal.
- **Cease-and-desist (C&D):** an order to stop a practice and fix it, similar in weight to a consent order.
- **Written / formal agreement:** a public agreement to fix problems, a step below an order.
- **CMP (civil money penalty):** a fine.
- **PCA (prompt corrective action):** action triggered by low capital. Usually not a buying signal for fraud and AML tools.
- **MRA / MRIA (Matters Requiring Attention / Immediate Attention):** exam findings a bank must fix. They're private, but job posts sometimes mention them.
- **Lookback:** a required re-review of past transactions, usually months of them, to find suspicious activity that was missed.
- **Remediation:** the work of fixing what an order or exam found. It typically runs 6–18 months.
- **Safety and soundness:** a bank's general financial health. Orders on this theme are usually about capital or management, not financial crime.
- **Terminated:** an order the regulator has lifted because the fixes were made.

**Sales and tooling**
- **ICP (ideal customer profile):** the kind of company most likely to buy. Here, "best fit" targets.
- **Champion:** someone inside an account who knows and supports your product.
- **BDR / AE:** business development rep (opens conversations and books meetings) and account executive (runs and closes the deal).
- **ATS (applicant tracking system):** the software companies post jobs through. Greenhouse, Lever and Ashby offer free public job feeds.
- **Clay:** a data platform for finding people and companies and enriching them (here, job changes and work history).
- **GitHub Action:** a script GitHub runs on a schedule. Here, the Monday collector and job scan.
- **Claude scheduled task:** a recurring Claude run. Here, it does the research and sends the Monday email.

## Run locally

```bash
python -m unittest discover -s tests
python src/collect.py
python src/jobs.py
```

Standard library plus `pypdf` (for reading the Fed's attached orders): `pip install pypdf`.

## Roadmap

- Automated FDIC, FinCEN and NYDFS collection
- Automated partner discovery (card-issuer disclosures, "banking services provided by" footers)
- Fintech-direct sources: state money-transmitter actions, FinCEN MSB penalties
- Job boards beyond Greenhouse, Lever and Ashby (Workday, iCIMS)

## Disclaimer

Public records only. Not affiliated with any regulator or vendor. Nothing here is legal or compliance advice.
