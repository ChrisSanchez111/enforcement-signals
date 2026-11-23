import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import jobs  # noqa: E402


class TestJobs(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(jobs.clean_name("Evolve Bank & Trust (West Memphis, AR)"), "Evolve Bank & Trust")
        self.assertEqual(jobs.clean_name("United Texas Bank, N.A. (Dallas, TX)"), "United Texas Bank")
        self.assertEqual(jobs.clean_name("Circle (USDC)"), "Circle")

    def test_slug_candidates(self):
        s = jobs.slug_candidates("Evolve Bank & Trust (West Memphis, AR)")
        self.assertIn("evolvebankandtrust", s)
        self.assertIn("evolve", s)
        self.assertEqual(jobs.slug_candidates("Crypto.com")[0], "cryptocom")

    def test_parse_greenhouse(self):
        payload = {"jobs": [{"title": "BSA/AML Officer", "absolute_url": "https://x/1",
                             "location": {"name": "Remote"}, "content": "&lt;p&gt;Lead consent order remediation&lt;/p&gt;"}]}
        j = jobs.parse_board("greenhouse", payload)
        self.assertEqual(j[0]["text"], "Lead consent order remediation")

    def test_parse_lever_and_ashby(self):
        lever = [{"text": "Fraud Analyst", "hostedUrl": "https://l/1", "categories": {"location": "NYC"},
                  "descriptionPlain": "Review alerts", "lists": [{"content": "<li>Support the lookback</li>"}]}]
        self.assertIn("lookback", jobs.parse_board("lever", lever)[0]["text"])
        ashby = {"jobs": [{"title": "KYC Lead", "jobUrl": "https://a/1", "location": "SF",
                           "descriptionPlain": "Partner bank oversight", "isListed": True},
                          {"title": "Hidden", "isListed": False}]}
        self.assertEqual(len(jobs.parse_board("ashby", ashby)), 1)

    def test_classify(self):
        self.assertIsNone(jobs.classify({"title": "Software Engineer", "url": "", "location": "", "text": "consent order"}))
        c = jobs.classify({"title": "AML Investigator", "url": "", "location": "",
                           "text": "Help close MRAs and support our sponsor bank exam"})
        self.assertIn("MRA", c["signals"])
        self.assertIn("sponsor/partner bank", c["signals"])
        self.assertEqual(jobs.classify({"title": "Fraud Ops Analyst", "url": "", "location": "", "text": "queues"})["signals"], [])

    def test_summarize_levels(self):
        base = {"url": "", "location": ""}
        rem = [dict(base, title="BSA Manager", text="remediation program")]
        self.assertEqual(jobs.summarize("X", "greenhouse", "x", rem)["level"], "remediation")
        build = [dict(base, title=f"Fraud Analyst {i}", text="") for i in range(3)]
        self.assertEqual(jobs.summarize("X", "lever", "x", build)["level"], "build-out")
        none = [dict(base, title="Designer", text="")]
        self.assertEqual(jobs.summarize("X", "ashby", "x", none)["level"], "none")


if __name__ == "__main__":
    unittest.main()
