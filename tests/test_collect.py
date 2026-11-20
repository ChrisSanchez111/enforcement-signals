import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import collect  # noqa: E402

FED_SAMPLE = """Effective Date,Termination Date,Banking Organization,Individual,Individual Affiliation,Action,URL
09/15/2026,,Example Bancorp,,,Written Agreement,https://example.gov/a
08/01/2026,,,Jane Doe,Example Bank,Prohibition from Banking,https://example.gov/b
01/10/2020,03/01/2022,Old Bank Corp,,,Cease and Desist Order,https://example.gov/c
"""


class CollectTests(unittest.TestCase):
    def test_fed_csv_keeps_open_institution_actions_only(self):
        rows = collect.parse_fed_csv(FED_SAMPLE)
        self.assertEqual([r["institution"] for r in rows], ["Example Bancorp"])
        self.assertEqual(rows[0]["date"], "2026-09-15")

    def test_classify_from_text(self):
        item = {"action": "Consent order", "summary": "Deficiencies in the BSA/AML program and OFAC screening"}
        self.assertEqual(collect.classify(item), ["BSA/AML", "Sanctions"])

    def test_curated_themes_win(self):
        self.assertEqual(collect.classify({"themes": ["Sanctions"], "summary": "bsa"}), ["Sanctions"])

    def test_enrich_scores_and_maps(self):
        item = collect.enrich({"institution": "X", "regulator": "OCC", "action": "Consent order", "segment": "Sponsor bank",
                               "date": "2026-11-01", "summary": "BSA/AML failures"}, date(2026, 11, 20))
        self.assertIn("Transaction Monitoring", item["solutions"])
        self.assertEqual(item["tier"], "Just hit")
        self.assertGreaterEqual(item["score"], 80)

    def test_read_fed_document_uses_order_text(self):
        html = '<p>The Board announced a written agreement.</p><a href="/files/order.pdf">Order</a>'
        order = "The Bank shall improve its BSA/AML compliance program and suspicious activity reporting. BSA officer staffing."
        seen = []
        out = collect.read_fed_document("https://example.gov/pr.htm", get=lambda u: html,
                                        get_pdf=lambda u: seen.append(u) or order)
        self.assertEqual(seen, ["https://example.gov/files/order.pdf"])
        self.assertEqual(out["themes"], ["BSA/AML"])

    def test_capital_only_order_is_safety_and_soundness(self):
        out = collect.read_fed_document("https://x.gov/a", get=lambda u: "capital plan and capital ratios and liquidity",
                                        get_pdf=lambda u: "")
        self.assertEqual(out["themes"], ["Safety & soundness"])

    def test_mark_new_carries_first_seen(self):
        import json, tempfile
        tmp = Path(tempfile.mkdtemp()) / "data.json"
        old = collect.DATA_OUT
        collect.DATA_OUT = tmp
        try:
            a = {"institution": "A Bank", "regulator": "OCC", "date": "2026-10-01"}
            b = {"institution": "B Bank", "regulator": "OCC", "date": "2026-11-01"}
            tmp.write_text(json.dumps({"actions": [dict(a, first_seen="2026-10-05")]}))
            items = [dict(a), dict(b)]
            collect.mark_new(items, date(2026, 11, 23))
            self.assertFalse(items[0]["new"])
            self.assertEqual(items[0]["first_seen"], "2026-10-05")
            self.assertTrue(items[1]["new"])
        finally:
            collect.DATA_OUT = old

    def test_fan_out_and_fit(self):
        bank = {"institution": "Example Sponsor Bank (City, ST)", "regulator": "OCC", "action": "Consent order",
                "date": "2026-11-01", "segment": "Sponsor bank", "themes": ["BSA/AML"],
                "partners": [{"name": "PayCo", "segment": "Fintech / payments", "source": "https://x"}]}
        rows = collect.fan_out([bank])
        self.assertEqual(rows[0]["institution"], "PayCo")
        self.assertIn("Third-party / fintech", rows[0]["themes"])
        self.assertIn("Example Sponsor Bank", rows[0]["opener"])
        fin = collect.enrich(rows[0], date(2026, 11, 20))
        comm = collect.enrich({"institution": "Small Bancshares", "regulator": "Federal Reserve",
                               "action": "Written Agreement", "date": "2026-11-01", "themes": ["BSA/AML"]},
                              date(2026, 11, 20))
        self.assertTrue(fin["icp"])
        self.assertFalse(comm["icp"])
        self.assertGreater(fin["score"], comm["score"])

    def test_megabank_detected(self):
        self.assertEqual(collect.segment_of({"institution": "Wells Fargo Bank, N.A.", "themes": []}), "Megabank")

    def test_occ_release_parsing(self):
        import occ
        html = """<div><p>News Release 2026-59 | July 16, 2026</p>
        <h1>OCC Announces Enforcement Actions for July 2026</h1>
        <p>The OCC uses enforcement actions against banks to require the board of directors and management
        to take timely actions. Actions taken against banks are:</p>
        <ul><li>Cease and Desist Order against United Texas Bank, Dallas, Texas, for deficiencies in its Bank Secrecy
        Act/anti-money laundering (BSA/AML) compliance program, which resulted in violations of law.
        (Docket No. AA-ENF-2026-29)</li>
        <li>Civil Money Penalty against Bank of America, National Association, Charlotte, North Carolina, for BSA
        compliance program deficiencies. (Docket No. AA-ENF-2026-41)</li></ul>
        <p>The OCC uses enforcement actions against institution-affiliated parties (IAPs) to deter violations.</p>
        <ul><li>Order of Prohibition against Jane Roe, former teller at Example Bank, N.A., Town, Ohio, for embezzling.</li></ul>
        <p>The termination actions are:</p>
        <ul><li>Order Terminating the Formal Agreement with Old Bank, City, Texas, dated 2024.</li></ul></div>"""
        acts = occ.parse_release(html, "https://x/nr.html")
        self.assertEqual([a["institution"] for a in acts],
                         ["United Texas Bank (Dallas, Texas)", "Bank of America N.A. (Charlotte, North Carolina)"])
        self.assertEqual(acts[0]["date"], "2026-07-16")
        self.assertEqual(acts[0]["url"], "https://www.occ.gov/static/enforcement-actions/eaAA-ENF-2026-29.pdf")
        self.assertEqual(collect.classify(acts[0]), ["BSA/AML"])

    def test_release_links(self):
        import occ
        idx = '<a href="/news-issuances/news-releases/2026/nr-occ-2026-93.html">OCC Announces Enforcement Actions for October 2026</a>' \
              '<a href="/x/nr-occ-2026-90.html">Unrelated release</a>'
        self.assertEqual(occ.release_links(idx, "https://www.occ.gov/topics/a.html"),
                         ["https://www.occ.gov/news-issuances/news-releases/2026/nr-occ-2026-93.html"])

    def test_dedupe_prefers_curated(self):
        cur = {"institution": "United Texas Bank, N.A. (Dallas, TX)", "regulator": "OCC", "date": "2026-06-12"}
        auto = {"institution": "United Texas Bank (Dallas, Texas)", "regulator": "OCC", "date": "2026-07-16"}
        self.assertEqual(collect.dedupe([cur, auto]), [cur])


if __name__ == "__main__":
    unittest.main()
