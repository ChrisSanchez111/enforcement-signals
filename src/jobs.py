"""Scan public job boards for remediation and financial-crime hiring at tracker targets.

Why: a bank or fintech that has been told to fix its compliance program usually hires
for it, and the job posts say so ("consent order", "remediation", "lookback", "MRA").
A burst of fraud, AML or KYC roles is a weaker version of the same signal.

Sources (all public, no login): Greenhouse, Lever and Ashby job-board APIs.
Targets: best-fit (icp) entries in docs/data.json, plus data/job_watch.json.
Existing Sardine customers are skipped.

Output
- docs/jobs.json               per-company hiring signals (feeds the weekly email)
- data/job_boards_cache.json   which ATS board each company uses (found once, rechecked monthly)

Standard library only.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_IN = ROOT / "docs" / "data.json"
WATCH = ROOT / "data" / "job_watch.json"
CUSTOMERS = ROOT / "data" / "known_customers.json"
CACHE = ROOT / "data" / "job_boards_cache.json"
OUT = ROOT / "docs" / "jobs.json"

USER_AGENT = "enforcement-signals (independent research project; github.com/ChrisSanchez111/enforcement-signals)"
RECHECK_DAYS = 30  # retry companies with no board found after this many days

BOARDS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}

# A role counts only if its title is a financial-crime role.
ROLE_TERMS = [
    r"\bbsa\b", r"\baml\b", r"anti[- ]money", r"money laundering", r"\bkyc\b", r"\bkyb\b",
    r"\bfraud\b", r"financial crimes?", r"fin ?crime", r"\bsanctions?\b", r"\bofac\b",
    r"transaction monitoring", r"\bcompliance\b", r"\bfiu\b", r"due diligence", r"\bedd\b",
    r"third[- ]party risk", r"\bchargebacks?\b", r"\bdisputes?\b", r"trust (and|&) safety",
]
# Phrases in the title or description that point to remediation, not routine hiring.
REMEDIATION_TERMS = {
    "consent order": r"consent order",
    "remediation": r"remediat",
    "lookback": r"look[- ]?back",
    "MRA": r"\bmrias?\b|\bmras?\b|matters requiring (immediate )?attention",
    "regulatory findings": r"(regulatory|exam(ination)?|audit) (findings|issues)",
    "enforcement action": r"enforcement action|cease[- ]and[- ]desist|written agreement",
    "sponsor/partner bank": r"(sponsor|partner) bank",
    "regulator-facing": r"regulator[- ]facing|regulatory exams?|examiner",
}
ROLE_RE = re.compile("|".join(ROLE_TERMS), re.I)
REMEDIATION_RE = {k: re.compile(v, re.I) for k, v in REMEDIATION_TERMS.items()}
BUILDOUT_MIN = 3  # this many open financial-crime roles at once = team build-out


def clean_name(name: str) -> str:
    """'Evolve Bank & Trust (West Memphis, AR)' -> 'Evolve Bank & Trust'; 'Circle (USDC)' -> 'Circle'."""
    name = re.sub(r"\s*\(.*?\)", "", name)
    name = re.sub(r",?\s+(N\.A\.|Inc\.?|LLC|Ltd\.?)$", "", name, flags=re.I)
    return name.strip()


def slug_candidates(name: str) -> list[str]:
    base = clean_name(name).lower().replace("&", "and")
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out = ["".join(words), "-".join(words), words[0]]
    trimmed = [w for w in words if w not in {"bank", "and", "trust", "the", "financial", "foundation", "development"}]
    if trimmed:
        out += ["".join(trimmed), "-".join(trimmed)]
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_board(ats: str, payload) -> list[dict]:
    """Normalize each ATS's response to [{title, url, location, text}]."""
    jobs = []
    if ats == "greenhouse" and isinstance(payload, dict):
        for j in payload.get("jobs", []):
            jobs.append({
                "title": j.get("title", ""),
                "url": j.get("absolute_url", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "text": strip_html(j.get("content", "")),
            })
    elif ats == "lever" and isinstance(payload, list):
        for j in payload:
            parts = [j.get("descriptionPlain") or strip_html(j.get("description", ""))]
            for block in j.get("lists", []) or []:
                parts.append(strip_html(block.get("content", "")))
            parts.append(j.get("additionalPlain") or "")
            jobs.append({
                "title": j.get("text", ""),
                "url": j.get("hostedUrl", ""),
                "location": (j.get("categories") or {}).get("location", ""),
                "text": " ".join(p for p in parts if p),
            })
    elif ats == "ashby" and isinstance(payload, dict):
        for j in payload.get("jobs", []):
            if j.get("isListed") is False:
                continue
            jobs.append({
                "title": j.get("title", ""),
                "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
                "location": j.get("location", ""),
                "text": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")),
            })
    return jobs


def classify(job: dict) -> dict | None:
    """Return the job with its signals if it's a financial-crime role, else None."""
    if not ROLE_RE.search(job["title"]):
        return None
    hay = f"{job['title']} {job['text']}"
    signals = [label for label, rx in REMEDIATION_RE.items() if rx.search(hay)]
    return {"title": job["title"], "url": job["url"], "location": job["location"], "signals": signals}


def find_board(name: str, hint: dict | None = None):
    """Try the hint first, then slug guesses on each ATS. Returns (ats, slug, jobs) or None."""
    tries = []
    if hint and hint.get("ats") and hint.get("slug"):
        tries.append((hint["ats"], hint["slug"]))
    for slug in slug_candidates(name):
        for ats in BOARDS:
            tries.append((ats, slug))
    for ats, slug in tries:
        payload = fetch_json(BOARDS[ats].format(slug=slug))
        jobs = parse_board(ats, payload)
        if jobs:
            return ats, slug, jobs
    return None


def summarize(name: str, ats: str, slug: str, jobs: list[dict]) -> dict:
    hits = [c for c in (classify(j) for j in jobs) if c]
    remediation = [h for h in hits if h["signals"]]
    if remediation:
        level = "remediation"
    elif len(hits) >= BUILDOUT_MIN:
        level = "build-out"
    elif hits:
        level = "hiring"
    else:
        level = "none"
    hits.sort(key=lambda h: (-len(h["signals"]), h["title"]))
    return {
        "company": name,
        "ats": ats,
        "board": BOARDS[ats].format(slug=slug).split("?")[0],
        "open_roles": len(jobs),
        "fincrime_roles": len(hits),
        "remediation_roles": len(remediation),
        "level": level,
        "jobs": hits[:10],
    }


def load_targets() -> list[dict]:
    customers = set()
    if CUSTOMERS.exists():
        customers = {c.lower() for c in json.loads(CUSTOMERS.read_text())["customers"]}
    targets, seen = [], set()
    if DATA_IN.exists():
        for a in json.loads(DATA_IN.read_text()).get("actions", []):
            if not a.get("icp") or a.get("customer"):
                continue
            name = clean_name(a["institution"])
            if name.lower() in seen or name.lower() in customers:
                continue
            seen.add(name.lower())
            targets.append({"name": name, "source": "tracker", "via": a.get("via")})
    if WATCH.exists():
        for w in json.loads(WATCH.read_text()).get("companies", []):
            name = w["name"]
            if name.lower() in seen or name.lower() in customers:
                continue
            seen.add(name.lower())
            targets.append({"name": name, "source": "watch", "hint": w.get("board")})
    return targets


def run(today: date | None = None) -> dict:
    today = today or date.today()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    results, missing = [], []
    for t in load_targets():
        key = t["name"].lower()
        entry = cache.get(key)
        hint = t.get("hint") or (entry if entry and entry.get("ats") else None)
        if entry and not entry.get("ats"):
            checked = date.fromisoformat(entry.get("checked", "2000-01-01"))
            if (today - checked).days < RECHECK_DAYS and not t.get("hint"):
                missing.append(t["name"])
                continue
        found = find_board(t["name"], hint)
        if not found:
            cache[key] = {"ats": None, "slug": None, "checked": today.isoformat()}
            missing.append(t["name"])
            continue
        ats, slug, jobs = found
        cache[key] = {"ats": ats, "slug": slug, "checked": today.isoformat()}
        s = summarize(t["name"], ats, slug, jobs)
        s["source"] = t["source"]
        if t.get("via"):
            s["via"] = t["via"]
        results.append(s)
    order = {"remediation": 0, "build-out": 1, "hiring": 2, "none": 3}
    results.sort(key=lambda r: (order[r["level"]], -r["remediation_roles"], -r["fincrime_roles"]))
    out = {
        "generated": today.isoformat(),
        "note": "Public job-board APIs (Greenhouse, Lever, Ashby). Boards are matched by name, so check the company before acting. Companies on other systems (Workday, iCIMS, own sites) aren't covered.",
        "companies": results,
        "no_board_found": sorted(missing),
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    CACHE.write_text(json.dumps(dict(sorted(cache.items())), indent=2) + "\n")
    return out


if __name__ == "__main__":
    o = run()
    flagged = [c for c in o["companies"] if c["level"] in ("remediation", "build-out")]
    print(f"{len(o['companies'])} boards scanned, {len(flagged)} flagged, {len(o['no_board_found'])} with no public board")
    sys.exit(0)
