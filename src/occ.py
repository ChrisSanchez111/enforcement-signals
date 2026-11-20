"""Collect bank enforcement actions from the OCC's monthly news releases.

The OCC publishes one release a month ("OCC Announces Enforcement Actions for
<Month> <Year>"). Each release has a bulleted list of actions against banks,
then separate lists for individuals (IAPs) and terminations. We read only the
bank list.

Each bank bullet reads roughly:
  "Cease and Desist Order against United Texas Bank, Dallas, Texas, for
   deficiencies in its BSA/AML compliance program ... (Docket No. AA-ENF-2026-29)"
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from urllib.parse import urljoin

INDEX_URLS = [
    "https://www.occ.gov/topics/laws-and-regulations/enforcement-actions/index-enforcement-actions.html",
    "https://www.occ.treas.gov/topics/laws-and-regulations/enforcement-actions/index-enforcement-actions.html",
]
RELEASE_LINK = re.compile(
    r'<a[^>]+href="([^"]*nr-occ-\d{4}-\d+\.html)"[^>]*>\s*([^<]*Enforcement Actions for[^<]*)</a>', re.I)
BANK_SECTION_START = re.compile(r"actions? (?:taken )?against banks? (?:are|is)\s*:|against banks? to require", re.I)
SECTION_END = re.compile(r"institution-affiliated part|against IAPs|termination actions|terminat(?:ed|ing) .* actions? are|"
                         r"To receive alerts|All OCC public enforcement", re.I)
BULLET = re.compile(r"^(?P<action>[A-Z][^.]*?)\s+(?:against|with)\s+(?P<bank>[^,]+?),\s*(?P<city>[^,]+?),\s*"
                    r"(?P<state>[A-Z][A-Za-z .]+?),\s*(?:for|related to|regarding|to)\s+(?P<why>.*)$", re.S)
DOCKET = re.compile(r"\(Docket No\.?\s*([A-Z0-9-]+)\)")
RELEASE_DATE = re.compile(r"News Release\s+\d{4}-\d+\W{0,12}([A-Z][a-z]+\.? \d{1,2}, \d{4})")
ANY_DATE = re.compile(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})")


def html_lines(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", html)
    html = re.sub(r"\s+", " ", html)   # source line breaks are not content breaks
    html = re.sub(r"(?i)</(li|p|h\d|div|tr)>|<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text).replace("\u00a0", " ")
    return [re.sub(r"\s+", " ", l).strip() for l in text.split("\n") if l.strip()]


def release_links(index_html: str, base: str, limit: int = 13) -> list[str]:
    links = [urljoin(base, href) for href, _ in RELEASE_LINK.findall(index_html)]
    return list(dict.fromkeys(links))[:limit]


def main_lines(html: str) -> list[str]:
    """The release body: from its title to the media-contact footer."""
    lines = html_lines(html)
    start = next((i for i, l in enumerate(lines) if TITLE.search(l)), 0)
    end = next((i for i, l in enumerate(lines) if i > start and re.search(r"(?i)^media contact|^related link", l)), len(lines))
    return lines[max(0, start - 3):end]


def parse_release(html: str, url: str) -> list[dict]:
    return parse_lines(main_lines(html), url)


def parse_lines(lines: list[str], url: str) -> list[dict]:
    # The page's menus come first; the date sits on the "News Release YYYY-N | Month D, YYYY" line.
    body_start = next((i for i, l in enumerate(lines) if re.match(r"News Release \d{4}-\d+", l)), 0)
    lines = [html_lib.unescape(l) for l in lines[body_start:]]
    head = " ".join(lines[:5])
    m = RELEASE_DATE.search(head) or ANY_DATE.search(head)
    released = ""
    if m:
        try:
            released = datetime.strptime(m.group(1).replace(".", ""), "%B %d, %Y").date().isoformat()
        except ValueError:
            released = ""
    actions, inside = [], False
    for line in lines:
        line = re.sub(r"\s+,", ",", line)
        line = re.sub(r",?\s+(National Association|N\.A\.)(?=,)", " N.A.", line)
        if not inside:
            if BANK_SECTION_START.search(line):
                inside = True
            continue
        if SECTION_END.search(line) and not BULLET.match(line):
            break
        if re.match(r"(?i)order terminating|termination of", line):
            continue
        b = BULLET.match(line)
        if not b:
            continue
        docket = DOCKET.search(line)
        why = DOCKET.sub("", b.group("why")).strip(" .")
        actions.append({
            "institution": f"{b.group('bank').strip()} ({b.group('city').strip()}, {b.group('state').strip()})",
            "regulator": "OCC",
            "action": b.group("action").strip(),
            "date": released,
            "summary": why[:600] + ("." if why else ""),
            "url": (f"https://www.occ.gov/static/enforcement-actions/ea{docket.group(1)}.pdf" if docket else url),
            "source": "OCC monthly release",
        })
    return [a for a in actions if a["date"]]


YEAR_PAGE = "https://occ.treas.gov/news-events/newsroom/news-issuances-by-year/news-releases/{year}-news-releases.html"
RELEASE_URL = "https://occ.treas.gov/news-issuances/news-releases/{year}/nr-occ-{year}-{n}.html"
ANY_RELEASE = re.compile(r"nr-occ-(\d{4})-(\d+)\.html")
TITLE = re.compile(r"Enforcement Actions for ([A-Z][a-z]+ \d{4})")
# Known monthly enforcement releases, so the first run has a floor even if discovery fails.
SEEDS = [(2025, 131), (2026, 3), (2026, 40), (2026, 48), (2026, 59), (2026, 93)]
MAX_NEW_FETCHES = 160


def candidate_releases(pages: list[str], today_year: int) -> list[tuple[int, int]]:
    """Every release number from 1 up to the highest one seen this year, plus links and seeds."""
    found = {(int(y), int(n)) for p in pages for y, n in ANY_RELEASE.findall(p)}
    top = max([n for y, n in found | set(SEEDS) if y == today_year] or [0])
    cands = found | set(SEEDS) | {(today_year, n) for n in range(1, top + 1)}
    return sorted(cands, reverse=True)


def load_occ(fetch, cache: dict, today_year: int, sleep=None) -> tuple[list[dict], str]:
    """cache maps release URL -> {"enforcement": bool, "actions": [...]}; it is updated in place."""
    pages = []
    for u in INDEX_URLS + [YEAR_PAGE.format(year=today_year), YEAR_PAGE.format(year=today_year - 1)]:
        try:
            pages.append(fetch(u))
        except Exception:
            continue
    fetched = failed = 0
    for y, n in candidate_releases(pages, today_year):
        url = RELEASE_URL.format(year=y, n=n)
        if url in cache and not (cache[url]["enforcement"] and not cache[url].get("lines")):
            continue
        if fetched >= MAX_NEW_FETCHES:
            break
        try:
            html = fetch(url)
            fetched += 1
            if sleep:
                sleep(0.4)
        except Exception as exc:
            failed += 1
            if "404" in str(exc):
                cache[url] = {"enforcement": False, "actions": []}
            continue
        is_enf = bool(TITLE.search(html))
        cache[url] = {"enforcement": is_enf, "lines": main_lines(html) if is_enf else []}
    # Re-parse from saved text every run, so parser fixes apply without re-downloading.
    enf = {u: v for u, v in cache.items() if v["enforcement"]}
    actions = []
    for u, v in enf.items():
        v.pop("actions", None)
        actions += parse_lines(v.get("lines", []), u)
    if not pages and not fetched:
        return actions, f"unavailable this run; using {len(enf)} cached monthly releases"
    return actions, (f"ok, {len(enf)} monthly enforcement releases known ({fetched} new pages checked, "
                     f"{failed} errors), {len(actions)} bank actions")
