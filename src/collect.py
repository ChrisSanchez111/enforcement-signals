"""Collect public bank enforcement actions and turn them into a monthly target list.

Sources
- Federal Reserve enforcement actions CSV (automated).
- data/manual_actions.json: hand-curated actions from the OCC, FDIC, FinCEN and
  others, which don't publish a clean machine-readable feed.

Output
- docs/data.json            all actions, classified and scored (feeds the dashboard)
- targets/YYYY-MM.md        that month's target list

Standard library only, plus pypdf (optional) for reading the Fed's attached orders.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "data" / "manual_actions.json"
DATA_OUT = ROOT / "docs" / "data.json"
TARGETS_DIR = ROOT / "targets"

FED_CSV_URLS = [
    "https://www.federalreserve.gov/supervisionreg/files/enforcementactions.csv",
    "https://www.federalreserve.gov/supervisionreg/files/enforcementactions.CSV",
]
LOOKBACK_DAYS = 365          # how far back actions stay on the dashboard
FRESH_DAYS = 180             # "just hit" window
USER_AGENT = "enforcement-signals (independent research project; github.com/ChrisSanchez111/enforcement-signals)"

# Violation themes -> keywords that identify them in titles or summaries.
THEMES = {
    "BSA/AML": ["bsa", "aml", "anti-money", "money laundering", "bank secrecy", "suspicious activity", "sar"],
    "Sanctions": ["ofac", "sanction"],
    "Third-party / fintech": ["third-party", "third party", "fintech", "sponsor", "baas", "banking-as-a-service", "payment processing"],
    "Fraud / consumer": ["fraud", "udap", "udaap", "consumer", "unfair", "deceptive"],
    "Safety & soundness": ["safety and soundness", "capital", "liquidity", "credit risk", "management"],
}

# Theme -> solution areas a fraud/AML platform would lead with.
PLAYBOOK = {
    "BSA/AML": ["Transaction Monitoring", "Agentic AML Ops", "Customer Risk Rating", "Case Management"],
    "Sanctions": ["Sanctions Screening", "Agentic AML Ops"],
    "Third-party / fintech": ["Sponsor Banking", "Global KYB", "Transaction Monitoring"],
    "Fraud / consumer": ["Payment Fraud", "Account Takeovers", "Device & Behavior"],
    "Safety & soundness": [],
}

OPENERS = {
    "BSA/AML": "Orders like this usually come with an end-to-end program review on a deadline. How are you handling first-pass alert review while that's underway?",
    "Sanctions": "After a sanctions finding, examiners look hard at screening precision. How much of your queue today is name-match noise?",
    "Third-party / fintech": "Regulators keep saying controls must keep pace with fintech growth. When you add a program, does your alert queue grow faster than your team?",
    "Fraud / consumer": "Findings like this tend to put fraud losses and customer friction on the board agenda at the same time. Which one is getting more pressure right now?",
    "Safety & soundness": "",
}

# Points for scoring how strong a target signal is.
THEME_WEIGHT = {"BSA/AML": 40, "Sanctions": 35, "Third-party / fintech": 35, "Fraud / consumer": 20, "Safety & soundness": 5}
ACTION_WEIGHT = [("consent order", 20), ("cease and desist", 20), ("civil money penalty", 15),
                 ("written agreement", 15), ("formal agreement", 15), ("prompt corrective", 10)]


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z]", "", h.lower())


def parse_fed_csv(text: str) -> list[dict]:
    """Parse the Fed CSV. Keeps institution actions only (individual prohibitions dropped)."""
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        r = {norm_header(k or ""): (v or "").strip() for k, v in raw.items()}
        org = r.get("bankingorganization", "")
        if not org or r.get("individual"):
            continue
        effective = parse_date(r.get("effectivedate", ""))
        if not effective:
            continue
        if r.get("terminationdate"):  # terminated actions are no longer live signals
            continue
        rows.append({
            "institution": org,
            "regulator": "Federal Reserve",
            "action": r.get("action", ""),
            "date": effective.isoformat(),
            "summary": "",
            "url": r.get("url", ""),
            "source": "Federal Reserve CSV",
        })
    return rows


def load_fed() -> tuple[list[dict], str]:
    for url in FED_CSV_URLS:
        try:
            return parse_fed_csv(fetch(url)), f"ok ({url})"
        except Exception as exc:  # keep going; one bad source must not kill the run
            last = f"unavailable this run ({exc.__class__.__name__})"
    return [], last


def load_manual() -> list[dict]:
    if not MANUAL.exists():
        return []
    items = json.loads(MANUAL.read_text())
    for it in items:
        it.setdefault("source", "Curated")
    return items


def classify_text(text: str, min_hits: int = 1) -> list[str]:
    """Themes whose keywords appear at least min_hits times in text."""
    text = text.lower()
    found = []
    for theme, words in THEMES.items():
        hits = sum(len(re.findall(rf"\b{re.escape(w)}\b", text)) for w in words)
        if hits >= min_hits:
            found.append(theme)
    return found


def classify(item: dict) -> list[str]:
    if item.get("themes"):
        return item["themes"]
    found = classify_text(" ".join([item.get("action", ""), item.get("summary", "")]))
    return found or ["Unclassified"]


# ---- Reading the Fed's press release and attached order --------------------

CACHE = ROOT / "data" / "fed_cache.json"
MIN_HITS_ORDER = 2   # full orders are long; one stray mention shouldn't tag a theme
MAX_PDF_PAGES = 12


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def pdf_links(html: str, base: str) -> list[str]:
    from urllib.parse import urljoin
    links = re.findall(r'href="([^"]+\.pdf)"', html, flags=re.I)
    return list(dict.fromkeys(urljoin(base, l) for l in links))


def pdf_text(url: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        reader = PdfReader(io.BytesIO(resp.read()))
    return " ".join((p.extract_text() or "") for p in reader.pages[:MAX_PDF_PAGES])


def read_fed_document(url: str, get=fetch, get_pdf=pdf_text) -> dict:
    """Return {'themes': [...], 'summary': str} for one Fed enforcement link."""
    html = get(url)
    text = html_to_text(html)
    for link in pdf_links(html, url)[:2]:
        try:
            text += " " + get_pdf(link)
        except Exception:
            continue
    themes = [t for t in classify_text(text, MIN_HITS_ORDER) if t != "Safety & soundness"]
    if not themes and classify_text(text, MIN_HITS_ORDER):
        themes = ["Safety & soundness"]
    return {"themes": themes or ["Unclassified"], "summary": "Tagged automatically from the Federal Reserve order text."}


def tag_fed(items: list[dict]) -> str:
    """Read each Fed action's documents once; remember results in data/fed_cache.json."""
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    read = failed = 0
    for it in items:
        url = it.get("url")
        if not url:
            continue
        if url not in cache:
            try:
                cache[url] = read_fed_document(url)
                read += 1
            except Exception:
                failed += 1
                continue
        it["themes"] = cache[url]["themes"]
        it["summary"] = it.get("summary") or cache[url]["summary"]
    CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return f"read {read} new orders, {failed} unreadable, {len(cache)} cached"


def score(item: dict, today: date) -> int:
    s = max((THEME_WEIGHT.get(t, 0) for t in item["themes"]), default=0)
    action = item.get("action", "").lower()
    s += max((w for k, w in ACTION_WEIGHT if k in action), default=0)
    if item.get("penalty_usd"):
        s += 10
    age = (today - date.fromisoformat(item["date"])).days
    s += 25 if age <= 90 else 15 if age <= FRESH_DAYS else 5
    return min(s, 100)


def enrich(item: dict, today: date) -> dict:
    item["themes"] = classify(item)
    lead = next((t for t in item["themes"] if t in PLAYBOOK), None)
    item["solutions"] = list(dict.fromkeys(p for t in item["themes"] for p in PLAYBOOK.get(t, [])))
    item["opener"] = OPENERS.get(lead, "") if lead else ""
    age = (today - date.fromisoformat(item["date"])).days
    item["tier"] = "Just hit" if age <= FRESH_DAYS else "Remediating"
    item["score"] = score(item, today)
    return item


def dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = (re.sub(r"\W", "", it["institution"].lower()), it["regulator"], it["date"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def write_markdown(items: list[dict], month: str, statuses: dict) -> Path:
    TARGETS_DIR.mkdir(exist_ok=True)
    top = [i for i in items if i["solutions"]][:25]
    lines = [
        f"# Target list: {month}",
        "",
        f"Generated {date.today().isoformat()} from public enforcement records. "
        "Independent research project; not affiliated with any vendor or regulator.",
        "",
        "| Score | Institution | Regulator | Action | Date | Themes | Lead with |",
        "|---:|---|---|---|---|---|---|",
    ]
    for i in top:
        inst = f"[{i['institution']}]({i['url']})" if i.get("url") else i["institution"]
        lines.append(f"| {i['score']} | {inst} | {i['regulator']} | {i['action']} | {i['date']} | "
                     f"{', '.join(i['themes'])} | {', '.join(i['solutions'][:3])} |")
    if not top:
        lines.append("| – | No classified actions this period | | | | | |")
    lines += ["", "## Source status", ""] + [f"- {k}: {v}" for k, v in statuses.items()]
    lines += ["", "Unclassified Federal Reserve actions are on the dashboard; open the order to check the theme, "
              "then add it to `data/manual_actions.json` with `themes` set."]
    path = TARGETS_DIR / f"{month}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    today = date.today()
    fed, fed_status = load_fed()
    manual = load_manual()
    statuses = {"Federal Reserve CSV": f"{fed_status}, {len(fed)} open institution actions",
                "Curated (OCC, FDIC, FinCEN, other)": f"{len(manual)} actions"}
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    fed = [i for i in fed if date.fromisoformat(i["date"]) >= cutoff]
    statuses["Fed order tagging"] = tag_fed(fed)
    items = [i for i in dedupe(manual + fed) if date.fromisoformat(i["date"]) >= cutoff]
    items = sorted((enrich(i, today) for i in items), key=lambda i: (-i["score"], i["date"]))
    month = today.strftime("%Y-%m")
    DATA_OUT.parent.mkdir(exist_ok=True)
    DATA_OUT.write_text(json.dumps({"generated": today.isoformat(), "month": month,
                                    "sources": statuses, "actions": items}, indent=2) + "\n")
    path = write_markdown(items, month, statuses)
    print(f"{len(items)} actions -> {DATA_OUT.relative_to(ROOT)}, {path.relative_to(ROOT)}")
    for k, v in statuses.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
