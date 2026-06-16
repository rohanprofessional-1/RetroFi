import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from schemas import RetrofitSummaryResponse
from services.retrofit_request_builder import build_retrofit_calculation_request


def _answers():
    return {
        "monthly_electricity_bill": "$140",
        "monthly_gas_bill": "$70",
        "home_ownership_status": "Own",
        "appliances_fuel": "Gas",
        "home_type": "Single Family",
        "year_built": 1935,
        "square_footage": 1800,
        "num_occupants": "3",
        "primary_heating_fuel": "Gas",
        "_property_meta": {
            "formatted_address": "123 Peachtree St NE, Atlanta, GA",
            "zip_code": "30308",
            "property_type": "Single Family",
            "year_built": 1935,
            "square_footage": 1800,
            "bedrooms": 3,
            "floor_count": 2,
            "cooling_type": "central_ac",
        },
    }


def _solar_data():
    return {
        "panelCount": 22,
        "maxPanels": 28,
        "systemSizeKw": 8.8,
        "annualProductionKwh": 11000,
        "yearlyEnergyDcKwh": 12941,
        "upfrontCost": 26400,
        "sunshineHoursPerYear": 1850,
        "roofSegments": [{"segmentIndex": 0}, {"segmentIndex": 1}],
    }


class GeneratePlanIntegrationTests(unittest.TestCase):
    def test_builder_maps_answers_and_solar_data_to_calculator_request(self):
        request = build_retrofit_calculation_request(
            address="123 Peachtree St NE, Atlanta, GA",
            answers=_answers(),
            solar_data=_solar_data(),
        )

        self.assertEqual(request.property.address, "123 Peachtree St NE, Atlanta, GA")
        self.assertEqual(request.property.zip_code, "30308")
        self.assertEqual(request.household.owner_occupied, True)
        self.assertEqual(request.household.household_size, 3)
        self.assertTrue(request.solar.solar_viable)
        self.assertEqual(request.solar.max_array_panels, 28)
        self.assertEqual(request.solar.installed_system_kw, 8.8)
        self.assertEqual(request.solar.estimated_install_cost, 26400)
        self.assertGreater(request.retcast.baseline_annual_kwh, 0)
        self.assertGreater(request.retcast.baseline_annual_therms, 0)

    def test_generate_plan_endpoint_returns_calculator_summary_shape(self):
        async_fetch = AsyncMock(
            return_value={
                **_answers(),
                "_solar_data": _solar_data(),
            }
        )

        def summarize(calculation):
            return RetrofitSummaryResponse(
                calculation=calculation,
                llm_summary="Calculator-backed summary",
                summary_source="test",
                model=None,
            )

        with patch("main.get_property_and_solar_data", async_fetch), patch(
            "main.summarize_retrofit_calculation",
            side_effect=summarize,
        ):
            response = TestClient(app).post(
                "/generate-plan",
                json={
                    "address": "123 Peachtree St NE, Atlanta, GA",
                    "answers": _answers(),
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary_source"], "test")
        self.assertIn("calculation", payload)
        self.assertGreaterEqual(len(payload["calculation"]["ranked_options"]), 1)
        self.assertTrue(
            any(
                option["upgrade_key"] == "solar"
                for option in payload["calculation"]["ranked_options"]
            )
        )


if __name__ == "__main__":
    unittest.main()
