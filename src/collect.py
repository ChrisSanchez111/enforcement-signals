"""Collect public bank enforcement actions and turn them into a weekly-refreshed target list.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import occ  # noqa: E402

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
    "Fraud / consumer": ["fraud", "fraudulent", "udap", "udaap", "consumer protection", "unfair or deceptive"],
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
MAX_PDF_PAGES = 40


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


# ---- Fit with the target buyer -------------------------------------------
# The buyer is fintechs, payment companies, crypto firms, marketplaces and the
# sponsor banks behind them. Community banks and megabanks are weak fits.
MEGABANKS = ["bank of america", "american express", "jpmorgan", "chase bank", "wells fargo", "citibank",
             "citigroup", "capital one", "u.s. bank", "pnc", "truist", "goldman sachs", "morgan stanley"]
SEGMENT_FIT = {"Fintech / payments": 15, "Crypto": 15, "Marketplace / ecommerce": 15, "Sponsor bank": 10,
               "Regional bank": 0, "Community bank": -20, "Megabank": -30}
UNVERIFIED_PENALTY = 15   # partner link reported in older or third-party sources; confirm before outreach

PARTNER_SOLUTIONS = ["Transaction Monitoring", "Global KYB", "Global KYC", "Agentic AML Ops"]
SPONSOR_SOLUTIONS = ["Sponsor Banking", "Transaction Monitoring", "Agentic AML Ops", "Global KYB"]
ICP_SEGMENTS = {"Fintech / payments", "Crypto", "Marketplace / ecommerce", "Sponsor bank"}


def segment_of(item: dict) -> str:
    if item.get("segment"):
        return item["segment"]
    name = item["institution"].lower()
    if any(m in name for m in MEGABANKS):
        return "Megabank"
    text = (item.get("summary", "") + " " + item.get("action", "")).lower()
    if "Third-party / fintech" in item.get("themes", []) or re.search(
            r"virtual currency|crypto|digital asset|fintech|program manager|banking-as-a-service|baas", text):
        return "Sponsor bank"
    return "Community bank"   # most Fed holding-company actions


def score(item: dict, today: date) -> int:
    s = max((THEME_WEIGHT.get(t, 0) for t in item["themes"]), default=0)
    action = item.get("action", "").lower()
    s += max((w for k, w in ACTION_WEIGHT if k in action), default=0)
    if item.get("penalty_usd"):
        s += 10
    age = (today - date.fromisoformat(item["date"])).days
    s += 25 if age <= 90 else 15 if age <= FRESH_DAYS else 5
    s += SEGMENT_FIT.get(item.get("segment", ""), 0)
    if item.get("verify"):
        s -= UNVERIFIED_PENALTY
    return max(0, min(s, 100))


def enrich(item: dict, today: date) -> dict:
    item["themes"] = classify(item)
    item["segment"] = segment_of(item)
    item["icp"] = item["segment"] in ICP_SEGMENTS
    lead = next((t for t in item["themes"] if t in PLAYBOOK), None)
    if item.get("via"):
        item["solutions"] = PARTNER_SOLUTIONS
    elif item["segment"] == "Sponsor bank":
        item["solutions"] = SPONSOR_SOLUTIONS
    else:
        item["solutions"] = list(dict.fromkeys(p for t in item["themes"] for p in PLAYBOOK.get(t, [])))
    if not item.get("opener"):
        item["opener"] = OPENERS.get(lead, "") if lead else ""
    age = (today - date.fromisoformat(item["date"])).days
    if not item.get("tier"):
        item["tier"] = "Just hit" if age <= FRESH_DAYS else "Remediating"
    item["score"] = score(item, today)
    return item


PARTNER_OPENER = ("{bank} is under a {regulator} {action_lc}. Sponsor banks under orders push their partners for "
                  "stronger monitoring and KYC evidence. Is {partner} getting more compliance questions from {bank} yet?")


def fan_out(actions: list[dict]) -> list[dict]:
    """Turn each sponsor bank's documented fintech partners into target rows of their own."""
    rows = []
    for a in actions:
        for p in a.get("partners", []):
            rows.append({
                "institution": p["name"],
                "regulator": a["regulator"],
                "action": f"Partner of {a['institution']} ({a['action']})",
                "date": a["date"],
                "summary": f"Runs on {a['institution']}, which is under this order. {p.get('note', '')}".strip(),
                "themes": list(dict.fromkeys(a.get("themes", []) + ["Third-party / fintech"])),
                "segment": p.get("segment", "Fintech / payments"),
                "tier": "Partner of a bank under order",
                "via": a["institution"],
                "url": p.get("source", a.get("url", "")),
                "opener": PARTNER_OPENER.format(bank=a["institution"].split(" (")[0], regulator=a["regulator"],
                                                action_lc=a["action"].lower().split(" (")[0],
                                                partner=p["name"]),
                "active_order": a.get("active_order", False),
                "verify": bool(re.search(r"confirm", p.get("note", ""), re.I)),
                "source": "Partner of curated action",
            })
    return rows


def norm_name(name: str) -> str:
    name = name.lower().split("(")[0]
    name = re.sub(r",.*$", "", name) if not name.startswith("bank of america") else "bank of america"
    name = re.sub(r"\b(n\.a\.|national association|the|inc\.?)\b", " ", name)
    return re.sub(r"[^a-z]", "", name)


def dedupe(items: list[dict]) -> list[dict]:
    """Drop repeats of the same institution and regulator within 120 days. Earlier items win,
    so curated entries (listed first) beat automated ones."""
    kept: list[dict] = []
    for it in items:
        d = date.fromisoformat(it["date"])
        dup = any(norm_name(k["institution"]) == norm_name(it["institution"]) and k["regulator"] == it["regulator"]
                  and abs((date.fromisoformat(k["date"]) - d).days) <= 120 for k in kept)
        if not dup:
            kept.append(it)
    return kept


def item_key(it: dict) -> str:
    return "|".join([re.sub(r"\W", "", it["institution"].lower()), it["regulator"], it["date"]])


def mark_new(items: list[dict], today: date) -> None:
    """Carry each action's first_seen date from the last run; flag ones first seen in the last 7 days."""
    prev = {}
    if DATA_OUT.exists():
        try:
            last = json.loads(DATA_OUT.read_text())
            # Older runs didn't record first_seen; treat their actions as seen on that run's date.
            prev = {item_key(a): a.get("first_seen") or last.get("generated") for a in last.get("actions", [])}
        except (ValueError, KeyError):
            prev = {}
    for it in items:
        it["first_seen"] = prev.get(item_key(it)) or today.isoformat()
        it["new"] = (today - date.fromisoformat(it["first_seen"])).days < 7 and bool(prev)


def write_markdown(items: list[dict], month: str, statuses: dict) -> Path:
    TARGETS_DIR.mkdir(exist_ok=True)
    fit = [i for i in items if i.get("icp")][:30]
    other = [i for i in items if not i.get("icp") and i["solutions"]][:15]
    fresh = [i for i in items if i.get("new")]
    lines = [
        f"# Target list: {month}",
        "",
        f"Updated {date.today().isoformat()} (runs every Monday) from public enforcement records. "
        "Independent research project; not affiliated with any vendor or regulator.",
        "",
        "## New this week",
        "",
    ]
    lines += [f"- **{i['institution']}** ({i['segment']}; {i['regulator']}: {i['action']}, {i['date']})"
              for i in fresh] or ["- Nothing new since last Monday."]
    def table(rows):
        out = ["| Score | Target | Segment | Why now | Date | Lead with |", "|---:|---|---|---|---|---|"]
        for i in rows:
            inst = f"[{i['institution']}]({i['url']})" if i.get("url") else i["institution"]
            out.append(f"| {i['score']} | {inst} | {i['segment']} | {i['regulator']}: {i['action']} | {i['date']} | "
                       f"{', '.join(i['solutions'][:3])} |")
        return out if rows else ["- None this period."]
    lines += ["", "## Best-fit targets (fintechs, crypto, sponsor banks)", ""] + table(fit)
    lines += ["", "## Other banks (weaker fit: community banks and megabanks)", ""] + table(other)
    lines += ["", "## Source status", ""] + [f"- {k}: {v}" for k, v in statuses.items()]
    lines += ["", "Unclassified Federal Reserve actions are on the dashboard; open the order to check the theme, "
              "then add it to `data/manual_actions.json` with `themes` set."]
    path = TARGETS_DIR / f"{month}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def main() -> int:
    today = date.today()
    fed, fed_status = load_fed()
    occ_items, occ_status = occ.load_occ(fetch)
    manual = load_manual()
    statuses = {"Federal Reserve CSV": f"{fed_status}, {len(fed)} open institution actions",
                "OCC monthly releases": occ_status,
                "Curated (OCC, FDIC, FinCEN, other)": f"{len(manual)} actions"}
    cutoff = today - timedelta(days=LOOKBACK_DAYS)
    fed = [i for i in fed if date.fromisoformat(i["date"]) >= cutoff]
    statuses["Fed order tagging"] = tag_fed(fed)
    live = lambda i: i.get("active_order") or date.fromisoformat(i["date"]) >= cutoff
    manual = [i for i in manual if live(i)]
    partners = fan_out(manual)
    statuses["Partners of banks under order"] = f"{len(partners)} fintech/crypto targets"
    items = [i for i in dedupe(manual + partners + occ_items + fed) if live(i)]
    items = sorted((enrich(i, today) for i in items), key=lambda i: (-i["score"], i["date"]))
    mark_new(items, today)
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
