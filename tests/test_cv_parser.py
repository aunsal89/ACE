"""Unit tests for CV text extraction, heuristic segmentation, and source saving."""

import sys
from pathlib import Path
import unittest
import tempfile

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.utils.cv_parser import (
    extract_contact_info_regex,
    parse_cv_heuristic,
    save_parsed_cv_to_tenant,
    extract_text_from_file,
)


class TestCVParser(unittest.TestCase):
    def test_extract_contact_info_regex(self):
        sample_text = """
        John Doe
        Email: john.doe@example.com | Phone: +1-555-234-5678
        LinkedIn: https://linkedin.com/in/johndoe
        GitHub: https://github.com/johndoe
        """
        contact = extract_contact_info_regex(sample_text)
        self.assertEqual(contact["email"], "john.doe@example.com")
        self.assertEqual(contact["linkedin"], "https://linkedin.com/in/johndoe")
        self.assertEqual(contact["github"], "https://github.com/johndoe")

    def test_parse_cv_heuristic(self):
        sample_cv = """
        Alex Mercer
        alex.mercer@example.com | +44 7700 900077 | London, UK
        
        # Professional Summary
        Senior Systems Architect with 12+ years experience building distributed platforms.
        
        # Experience
        ### Principal Architect | CloudScale Corp (2020 - Present)
        * Designed high-throughput microservices in Go and Python.
        * Directed engineering team of 15 developers.
        
        # Education
        **MSc Computer Science** | Imperial College London (2014 - 2016)
        **BSc Software Engineering** | University of Manchester (2010 - 2014)
        
        # Technical Skills
        * **Languages:** Python, Go, C++, SQL
        * **Infrastructure:** Kubernetes, Docker, AWS, Kafka
        """
        parsed = parse_cv_heuristic(sample_cv, candidate_name="Alex Mercer")
        self.assertEqual(parsed["metadata"]["name"], "Alex Mercer")
        self.assertEqual(parsed["metadata"]["email"], "alex.mercer@example.com")
        
        sections = parsed["sections"]
        self.assertIn("Experience.md", sections)
        self.assertIn("Education.md", sections)
        self.assertIn("Toolbox.md", sections)
        self.assertIn("Summary.md", sections)

        self.assertIn("CloudScale Corp", sections["Experience.md"])
        self.assertIn("Imperial College London", sections["Education.md"])
        self.assertIn("Kubernetes", sections["Toolbox.md"])

    def test_save_parsed_cv_to_tenant(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tenant_dir = Path(tmp_dir) / "test_tenant"
            parsed_data = {
                "sections": {
                    "Experience.md": "# Professional Experience\n\nBuilt distributed engines.",
                    "Education.md": "# Education\n\nBSc Computer Science",
                    "Toolbox.md": "# Skills\n\nPython, Docker",
                }
            }
            saved = save_parsed_cv_to_tenant(tenant_dir, parsed_data)
            self.assertTrue(saved["Experience.md"].exists())
            self.assertTrue(saved["Education.md"].exists())
            self.assertTrue(saved["Toolbox.md"].exists())

            content = saved["Experience.md"].read_text(encoding="utf-8")
            self.assertIn("Built distributed engines", content)


if __name__ == "__main__":
    unittest.main()
