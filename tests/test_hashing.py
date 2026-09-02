import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

"""Unit tests for deduplication hashing and text normalization."""

import unittest
from src.utils.hashing import (
    clean_job_url,
    generate_deduplication_hash,
    generate_semantic_cluster_key,
    normalize_company,
    normalize_title,
)


class TestHashing(unittest.TestCase):
    def test_normalize_company(self):
        self.assertEqual(normalize_company("Baykar Teknoloji A.Ş."), "baykar teknoloji")
        self.assertEqual(normalize_company("ASELSAN Elektronik San. ve Tic. A.Ş."), "aselsan elektronik")
        self.assertEqual(normalize_company("Siemens AG"), "siemens")
        self.assertEqual(normalize_company("Citadel LLC"), "citadel")

    def test_normalize_title(self):
        self.assertEqual(normalize_title("Embedded Software Lead (m/w/d)"), "embedded software lead")
        self.assertEqual(normalize_title("Quantitative Developer [Remote]"), "quantitative developer")
        self.assertEqual(normalize_title("Lead Embedded Systems Architect - Automotive (f/m/d)"), "lead embedded systems architect automotive")

    def test_clean_job_url(self):
        url = "https://kariyer.baykartech.com/job/101?utm_source=linkedin&utm_medium=cpc&ref=aggregator"
        cleaned = clean_job_url(url)
        self.assertEqual(cleaned, "https://kariyer.baykartech.com/job/101")

        # Test Google Jobs URL fragment preservation
        google_jobs_url = "https://www.google.com/search?q=embedded+jobs&ibp=htl;jobs#fpstate=tldetail&htidocid=ABC123XYZ"
        cleaned_gj = clean_job_url(google_jobs_url)
        self.assertIn("#fpstate=tldetail&htidocid=ABC123XYZ", cleaned_gj)
        self.assertIn("ibp=htl%3Bjobs", cleaned_gj)

        # Test missing scheme auto-prefix
        no_scheme = "kariyer.baykartech.com/tr/"
        cleaned_scheme = clean_job_url(no_scheme)
        self.assertEqual(cleaned_scheme, "https://kariyer.baykartech.com/tr/")

    def test_deterministic_dedup_hash(self):
        h1 = generate_deduplication_hash(
            company="Baykar Teknoloji A.Ş.",
            title="Gömülü Yazılım Lideri (m/w/d)",
            location="Istanbul",
            url="https://kariyer.baykartech.com/job/101?utm_source=linkedin"
        )
        h2 = generate_deduplication_hash(
            company="Baykar Teknoloji",
            title="Gömülü Yazılım Lideri",
            location="Istanbul",
            url="https://kariyer.baykartech.com/job/101"
        )
        self.assertEqual(h1, h2)

    def test_semantic_cluster_key(self):
        k1 = generate_semantic_cluster_key("ASELSAN A.Ş.", "Lead Embedded Architect (m/w/d)")
        k2 = generate_semantic_cluster_key("Aselsan", "Lead Embedded Architect")
        self.assertEqual(k1, k2)


if __name__ == "__main__":
    unittest.main()
