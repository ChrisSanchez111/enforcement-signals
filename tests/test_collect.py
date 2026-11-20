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
        item = collect.enrich({"institution": "X", "regulator": "OCC", "action": "Consent order",
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


if __name__ == "__main__":
    unittest.main()
