import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from schemas import IncentiveAnalysisRequest
from services.incentive_index import IncentiveIndex
from services.retrofit_analyzer import analyze_retrofit_incentives


class IncentiveAnalysisTests(unittest.TestCase):
    def test_index_returns_relevant_atlanta_incentives(self):
        index = IncentiveIndex()
        request = IncentiveAnalysisRequest(
            address="123 Peachtree St NE, Atlanta, GA",
            utility="Georgia Power",
            upgrade_interests=["heat pump", "attic insulation"],
        )

        matches = index.search_incentives(request)
        matched_upgrades = {
            upgrade
            for match in matches
            for upgrade in match.get("eligible_upgrades", [])
        }
        match_names = {match["name"] for match in matches}

        self.assertIn("heat_pump", matched_upgrades)
        self.assertIn("attic_insulation", matched_upgrades)
        self.assertTrue(
            any("Energy Efficient Home Improvement Credit" in name for name in match_names)
        )

    def test_analyzer_returns_ranked_upgrades_with_citations(self):
        request = IncentiveAnalysisRequest(
            address="123 Peachtree St NE, Atlanta, GA",
            square_footage=1800,
            utility="Georgia Power",
            upgrade_interests=["heat pump", "attic insulation"],
        )

        response = analyze_retrofit_incentives(request, index=IncentiveIndex())

        self.assertGreaterEqual(len(response.ranked_upgrades), 2)
        self.assertGreater(len(response.eligible_incentives), 0)
        self.assertGreater(len(response.citations), 0)
        self.assertLessEqual(
            response.ranked_upgrades[0].net_cost,
            response.ranked_upgrades[0].gross_cost,
        )

    def test_index_filters_incentives_by_market_segment(self):
        index = IncentiveIndex(use_vector=False)
        index.incentives.append(
            {
                "id": "multifamily-envelope-test",
                "name": "Multifamily Envelope Rebate",
                "source": "Test Program",
                "source_url": None,
                "incentive_type": "Utility Rebate",
                "eligible_upgrades": ["attic_insulation"],
                "geographic_scope": ["georgia", "atlanta"],
                "market_segments": ["multifamily", "building"],
                "utility": "Georgia Power",
                "amount_rule": {"type": "fixed", "amount": 2500},
                "stackable": True,
                "eligibility": "Modeled for multifamily properties.",
                "citation_snippet": "Multifamily properties may qualify for envelope incentives.",
            }
        )

        homeowner_matches = index.search_incentives(
            IncentiveAnalysisRequest(
                address="123 Peachtree St NE, Atlanta, GA",
                utility="Georgia Power",
                market_segment="homeowner",
                upgrade_interests=["attic insulation"],
            )
        )
        multifamily_matches = index.search_incentives(
            IncentiveAnalysisRequest(
                address="456 Apartment Ave NE, Atlanta, GA",
                utility="Georgia Power",
                market_segment="multifamily",
                upgrade_interests=["attic insulation"],
            )
        )

        self.assertFalse(
            any(match["id"] == "multifamily-envelope-test" for match in homeowner_matches)
        )
        self.assertTrue(
            any(match["id"] == "multifamily-envelope-test" for match in multifamily_matches)
        )

    def test_seed_multifamily_incentives_do_not_leak_to_homeowner(self):
        index = IncentiveIndex(use_vector=False)

        homeowner_matches = index.search_incentives(
            IncentiveAnalysisRequest(
                address="123 Peachtree St NE, Atlanta, GA",
                utility="Georgia Power",
                market_segment="homeowner",
                upgrade_interests=["common area lighting", "benchmarking"],
            )
        )
        multifamily_matches = index.search_incentives(
            IncentiveAnalysisRequest(
                address="456 Apartment Ave NE, Atlanta, GA",
                utility="Georgia Power",
                market_segment="multifamily",
                building_type="multifamily",
                units=24,
                utility_structure="Common-area meter plus tenant meters",
                upgrade_interests=["common area lighting", "benchmarking"],
            )
        )

        self.assertFalse(
            any(match["id"] == "ga-power-multifamily-energy-assessment" for match in homeowner_matches)
        )
        self.assertTrue(
            any(match["id"] == "ga-power-multifamily-energy-assessment" for match in multifamily_matches)
        )

    def test_commercial_segment_returns_commercial_building_program(self):
        matches = IncentiveIndex(use_vector=False).search_incentives(
            IncentiveAnalysisRequest(
                address="100 Office Rd NE, Atlanta, GA",
                market_segment="commercial",
                building_type="office",
                square_footage=50000,
                upgrade_interests=["building envelope", "hvac controls"],
            )
        )

        self.assertTrue(
            any(match["id"] == "federal-commercial-179d-building-efficiency" for match in matches)
        )

    def test_renter_segment_excludes_owner_and_building_programs(self):
        matches = IncentiveIndex(use_vector=False).search_incentives(
            IncentiveAnalysisRequest(
                address="789 Rental Rd NE, Atlanta, GA",
                market_segment="renter",
                owner_occupied=False,
                upgrade_interests=["heat pump", "common area lighting"],
            )
        )

        self.assertEqual(matches, [])

    def test_endpoint_returns_backend_only_analysis(self):
        client = TestClient(app)

        response = client.post(
            "/analyze-incentives/",
            json={
                "address": "123 Peachtree St NE, Atlanta, GA",
                "square_footage": 1800,
                "utility": "Georgia Power",
                "upgrade_interests": ["heat pump"],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["address"], "123 Peachtree St NE, Atlanta, GA")
        self.assertGreaterEqual(len(payload["ranked_upgrades"]), 1)
        self.assertGreaterEqual(len(payload["citations"]), 1)


if __name__ == "__main__":
    unittest.main()
