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


if __name__ == "__main__":
    unittest.main()
