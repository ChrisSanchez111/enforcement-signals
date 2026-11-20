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
RELEASE_DATE = re.compile(r"News Release\s+\d{4}-\d+\s*\|\s*([A-Z][a-z]+ \d{1,2}, \d{4})")


def html_lines(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", html)
    html = re.sub(r"\s+", " ", html)   # source line breaks are not content breaks
    html = re.sub(r"(?i)</(li|p|h\d|div|tr)>|<br\s*/?>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'")
            .replace("&rsquo;", "'").replace("&ldquo;", '"').replace("&rdquo;", '"'))
    return [re.sub(r"\s+", " ", l).strip() for l in text.split("\n") if l.strip()]


def release_links(index_html: str, base: str, limit: int = 13) -> list[str]:
    links = [urljoin(base, href) for href, _ in RELEASE_LINK.findall(index_html)]
    return list(dict.fromkeys(links))[:limit]


def parse_release(html: str, url: str) -> list[dict]:
    lines = html_lines(html)
    m = RELEASE_DATE.search(" ".join(lines[:60]))
    released = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat() if m else ""
    actions, inside = [], False
    for line in lines:
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


def load_occ(fetch) -> tuple[list[dict], str]:
    index_html, base = "", ""
    for u in INDEX_URLS:
        try:
            index_html, base = fetch(u), u
            break
        except Exception as exc:
            last = exc
    if not index_html:
        return [], f"unavailable this run ({last.__class__.__name__})"
    links = release_links(index_html, base)
    if not links:
        return [], "index page read, but no monthly release links found (page layout may have changed)"
    out, failed = [], 0
    for link in links:
        try:
            out += parse_release(fetch(link), link)
        except Exception:
            failed += 1
    return out, f"ok, {len(links)} monthly releases read ({failed} failed), {len(out)} bank actions"
