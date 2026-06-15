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
        "primary_goal": "Lower bills",
        "roof_type": "Tile",
        "planning_roof_replacement": "Yes",
        "ev_owner_or_planning": "Planning within 3 years",
        "planned_electric_additions": "Yes",
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
        self.assertEqual(request.preferences.primary_goal, "lower_bills")
        self.assertEqual(request.preferences.roof_type, "tile")
        self.assertEqual(request.preferences.roof_replacement_status, "yes")
        self.assertEqual(request.preferences.ev_owner_or_planning, "planning_ev")
        self.assertEqual(request.preferences.planned_electric_additions, True)

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
        self.assertEqual(payload["mode"], "homeowner")
        self.assertEqual(payload["summary_source"], "test")
        self.assertIn("calculation", payload)
        self.assertIsNone(payload["building_analysis"])
        self.assertGreaterEqual(len(payload["calculation"]["ranked_options"]), 1)
        self.assertTrue(
            any(
                option["upgrade_key"] == "solar"
                for option in payload["calculation"]["ranked_options"]
            )
        )
        self.assertIn("totals", payload["calculation"])
        self.assertIn("llm_context", payload["calculation"])
        self.assertEqual(
            set(payload.keys()),
            {"mode", "calculation", "building_analysis", "llm_summary", "summary_source", "model"},
        )

    def test_generate_plan_routes_apartment_to_building_mode(self):
        apartment_answers = {
            **_answers(),
            "home_ownership_status": "Rent / Lease",
            "home_type": "Condo / Apartment",
            "_property_meta": {
                **_answers()["_property_meta"],
                "property_type": "Apartment",
                "square_footage": 24000,
                "bedrooms": 40,
            },
        }
        async_fetch = AsyncMock(
            return_value={
                **apartment_answers,
                "_solar_data": _solar_data(),
            }
        )

        with patch("main.get_property_and_solar_data", async_fetch), patch(
            "main.summarize_retrofit_calculation",
        ) as summarize:
            response = TestClient(app).post(
                "/generate-plan",
                json={
                    "address": "456 Apartment Ave NE, Atlanta, GA",
                    "answers": apartment_answers,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "building")
        self.assertIsNone(payload["calculation"])
        self.assertIsNotNone(payload["building_analysis"])
        self.assertEqual(payload["building_analysis"]["mode"], "building")
        self.assertIn(
            "12 months electric utility history",
            payload["building_analysis"]["missing_inputs"],
        )
        self.assertFalse(
            any(
                recommendation["package_key"] == "solar"
                for recommendation in payload["building_analysis"]["recommendations"]
            )
        )
        summarize.assert_not_called()

    def test_generate_plan_routes_single_family_renter_to_renter_safe_mode(self):
        renter_answers = {
            **_answers(),
            "home_ownership_status": "Rent / Lease",
            "home_type": "Single Family",
            "_property_meta": {
                **_answers()["_property_meta"],
                "property_type": "Single Family",
            },
        }
        async_fetch = AsyncMock(
            return_value={
                **renter_answers,
                "_solar_data": _solar_data(),
            }
        )

        with patch("main.get_property_and_solar_data", async_fetch):
            response = TestClient(app).post(
                "/generate-plan",
                json={
                    "address": "789 Rental Rd NE, Atlanta, GA",
                    "answers": renter_answers,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "renter_safe")
        self.assertIsNone(payload["calculation"])
        self.assertIsNotNone(payload["building_analysis"])

    def test_explicit_landlord_mode_returns_building_quick_estimate(self):
        building_answers = {
            **_answers(),
            "role": "Landlord",
            "scope": "Single building",
            "building_type": "Garden-style multifamily",
            "units": 24,
            "square_footage": 24000,
            "occupancy": 22,
            "utility_structure": "Common-area meter plus tenant meters",
            "electric_bill_responsibility": "Tenant pays in-unit, owner pays common areas",
            "gas_bill_responsibility": "No gas / all electric",
            "hvac_system_type": "Split systems",
            "domestic_hot_water_type": "Central electric",
            "roof_control": "Owner controls roof",
            "primary_goal": "Plan capital budget",
            "utility_history": [
                {
                    "fuel_type": "electric",
                    "months": 12,
                    "total_usage": 180000,
                    "total_cost": 27000,
                    "usage_unit": "kWh",
                    "meter_scope": "Common-area meter plus tenant meters",
                }
            ],
            "_property_meta": {
                **_answers()["_property_meta"],
                "property_type": "Single Family",
                "square_footage": 24000,
            },
        }
        async_fetch = AsyncMock(
            return_value={
                **building_answers,
                "_solar_data": _solar_data(),
            }
        )

        with patch("main.get_property_and_solar_data", async_fetch), patch(
            "main.summarize_retrofit_calculation",
        ) as summarize:
            response = TestClient(app).post(
                "/generate-plan",
                json={
                    "mode": "landlord",
                    "role": "landlord",
                    "scope": "single_building",
                    "address": "456 Apartment Ave NE, Atlanta, GA",
                    "answers": building_answers,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "building")
        self.assertIsNone(payload["calculation"])
        analysis = payload["building_analysis"]
        self.assertGreaterEqual(analysis["data_completeness_score"], 80)
        self.assertIsNotNone(analysis["benchmark"])
        self.assertEqual(analysis["benchmark"]["site_eui_kbtu_per_sq_ft"], 25.6)
        self.assertGreaterEqual(len(analysis["recommendations"]), 3)
        self.assertGreaterEqual(len(analysis["eligible_incentives"]), 1)
        self.assertTrue(any("split incentives" in warning.lower() for warning in analysis["warnings"]))
        summarize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
