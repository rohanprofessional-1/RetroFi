import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from services.incentive_schema_extractor import IncentiveIndexRecord, extract_records
from services.source_parsers import chunk_source, parse_html_source, parse_pdf_source
from services.vector_store import ChromaVectorStore


class SourceVectorIndexTests(unittest.TestCase):
    def test_html_parser_extracts_irs_metadata(self):
        source = parse_html_source(
            REPO_ROOT / "sources" / "Energy Efficient Home Improvement Credit _ Internal Revenue Service.html"
        )

        self.assertEqual(source.source_type, "irs_html")
        self.assertIn("Energy Efficient Home Improvement Credit", source.title)
        self.assertEqual(
            source.source_url,
            "https://www.irs.gov/credits-deductions/energy-efficient-home-improvement-credit",
        )
        self.assertIn("tax credit", source.text.lower())

    def test_schema_extractor_creates_irs_25c_records(self):
        source = parse_html_source(
            REPO_ROOT / "sources" / "Energy Efficient Home Improvement Credit _ Internal Revenue Service.html"
        )
        records = extract_records(chunk_source(source))
        measures = {record.measure for record in records if record.program_id == "irs-25c"}

        self.assertIn("heat_pump", measures)
        self.assertTrue(any(record.max_cap >= 2000 for record in records if record.measure == "heat_pump"))

    def test_hear_pdf_extracts_rebate_clues_when_pypdf_available(self):
        try:
            import pypdf  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("pypdf is not installed")

        source = parse_pdf_source(REPO_ROOT / "sources" / "HEAR DIY Webpage - HEAR-DIY-Pathway.pdf")

        self.assertIn("$840", source.text)
        self.assertIn("80% AMI", source.text)
        self.assertIn("ENERGY STAR", source.text)

    def test_chroma_vector_store_round_trip_when_available(self):
        try:
            import chromadb  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("chromadb is not installed")

        record = IncentiveIndexRecord(
            id="test-ga-hear-diy-electric-cooking",
            program_id="ga-hear-diy",
            program_name="Georgia Home Energy Rebates HEAR DIY Pathway",
            admin="Georgia Home Energy Rebates",
            source_url="https://energyrebates.georgia.gov",
            source_type="state_rebate_pdf",
            document_date="2024",
            jurisdiction="Georgia",
            utility_territory="",
            building_type="tenant",
            fuel_type="electric",
            measure="electric_cooking",
            equipment_requirements="ENERGY STAR certified electric cooking appliance.",
            rebate_amount=0,
            rebate_percent=1.0,
            max_cap=840,
            eligibility_rules="Eligible households can select one appliance.",
            income_rules="Available below 150% AMI.",
            contractor_rules="DIY pathway requires proof of installation.",
            application_deadline="Proof of installation within 90 days.",
            stacking_notes="Verify stacking with other rebates.",
            raw_text_chunk="Georgia HEAR DIY rebate for ENERGY STAR electric cooking appliances up to $840.",
            parse_confidence="high",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChromaVectorStore(persist_path=Path(tmpdir))
            store.reset()
            self.assertEqual(store.upsert_records([record]), 1)
            matches = store.query(
                "Georgia electric cooking appliance rebate",
                measures=["electric_cooking"],
                jurisdiction="Georgia",
            )

        self.assertEqual(matches[0]["program_id"], "ga-hear-diy")
        self.assertEqual(matches[0]["max_cap"], 840)


if __name__ == "__main__":
    unittest.main()
