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
