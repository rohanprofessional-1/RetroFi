import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from schemas import RetrofitCalculationRequest
from services.incentive_index import IncentiveIndex
from services.retrofit_calculator import calculate_retrofit_options


def _mock_payload():
    return json.loads((BACKEND_ROOT / "data" / "mock_retrofit_calculation_request.json").read_text())


class RetrofitCalculatorTests(unittest.TestCase):
    def test_same_dto_produces_same_output(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        index = IncentiveIndex(use_vector=False)

        first = calculate_retrofit_options(request, index=index)
        second = calculate_retrofit_options(request, index=index)

        self.assertEqual(_dump(first), _dump(second))

    def test_capped_percentage_incentive_math_affects_net_cost(self):
        payload = _mock_payload()
        payload["upgrade_interests"] = ["heat pump"]
        request = RetrofitCalculationRequest(**payload)

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        heat_pump = next(option for option in response.ranked_options if option.upgrade_key == "heat_pump")

        self.assertGreaterEqual(heat_pump.incentive_total, 2000)
        self.assertEqual(heat_pump.net_cost, heat_pump.gross_cost - heat_pump.incentive_total)
        self.assertIsNotNone(heat_pump.payback_years)

    def test_solar_option_uses_dto_production_and_cost(self):
        request = RetrofitCalculationRequest(**_mock_payload())

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        solar = next(option for option in response.ranked_options if option.upgrade_key == "solar")

        self.assertEqual(solar.gross_cost, 21600)
        self.assertGreater(solar.annual_savings, 1000)
        self.assertGreater(solar.carbon_avoided_tons, 0)
        self.assertIn("citation-google-solar-input", solar.citations)

    def test_duplicate_incentive_programs_are_collapsed(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        response = calculate_retrofit_options(request, index=_DuplicateSolarIncentiveIndex())
        solar = next(option for option in response.ranked_options if option.upgrade_key == "solar")

        duplicate_display_rows = [
            incentive
            for incentive in solar.matched_incentives
            if incentive.name == "Residential Clean Energy Credit" and incentive.amount == 6480
        ]

        self.assertEqual(len(duplicate_display_rows), 1)
        self.assertEqual(solar.incentive_total, 6480)

    def test_retcast_carbon_math_is_used_for_efficiency_options(self):
        payload = _mock_payload()
        payload["upgrade_interests"] = ["attic insulation"]
        request = RetrofitCalculationRequest(**payload)

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        insulation = next(option for option in response.ranked_options if option.upgrade_key == "attic_insulation")

        self.assertTrue(
            any("Retcast energy deltas" in note for note in insulation.calculation_notes)
        )
        self.assertGreater(insulation.carbon_avoided_tons, 0)

    def test_endpoint_returns_calculation_response_shape(self):
        client = TestClient(app)

        response = client.post("/calculate-retrofit/", json=_mock_payload())

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["address"], "123 Peachtree St NE, Atlanta, GA")
        self.assertGreaterEqual(len(payload["ranked_options"]), 1)
        self.assertIn("totals", payload)
        self.assertIn("llm_context", payload)
        self.assertGreaterEqual(len(payload["llm_context"]["ranked_option_facts"]), 1)


def _dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class _DuplicateSolarIncentiveIndex:
    def search_costs(self, _request):
        return []

    def search_incentives(self, _request, limit=12):
        return [
            _residential_clean_energy_document("irs-25d-solar-source-chunk-1"),
            _residential_clean_energy_document("irs-25d-solar-source-chunk-2"),
        ][:limit]


def _residential_clean_energy_document(document_id):
    return {
        "id": document_id,
        "name": "Residential Clean Energy Credit",
        "source": "Internal Revenue Service",
        "source_url": "https://www.irs.gov/credits-deductions/residential-clean-energy-credit",
        "incentive_type": "Tax Credit",
        "eligible_upgrades": ["solar"],
        "amount_rule": {
            "type": "percentage_cap",
            "percent": 0.3,
            "cap": 0,
        },
        "amount_description": "30% of eligible costs",
        "eligibility": "Existing homes may qualify for the residential clean energy credit.",
        "eligibility_status": "likely_eligible",
        "stackable": True,
        "citation_snippet": "The Residential Clean Energy Credit equals 30% of qualified solar costs.",
    }


if __name__ == "__main__":
    unittest.main()
