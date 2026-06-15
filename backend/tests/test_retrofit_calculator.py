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

    def test_heating_fuel_changes_heat_pump_savings_and_carbon(self):
        gas_payload = _mock_payload()
        gas_payload["upgrade_interests"] = ["heat pump"]
        electric_payload = _mock_payload()
        electric_payload["upgrade_interests"] = ["heat pump"]
        electric_payload["property"]["heating_fuel"] = "electric"

        gas_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**gas_payload),
            index=IncentiveIndex(use_vector=False),
        )
        electric_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**electric_payload),
            index=IncentiveIndex(use_vector=False),
        )
        gas_heat_pump = _option(gas_response, "heat_pump")
        electric_heat_pump = _option(electric_response, "heat_pump")

        self.assertGreater(gas_heat_pump.annual_savings, electric_heat_pump.annual_savings)
        self.assertGreater(gas_heat_pump.carbon_avoided_tons, electric_heat_pump.carbon_avoided_tons)
        self.assertTrue(
            any("current heating fuel" in note for note in gas_heat_pump.calculation_notes)
        )

    def test_year_built_changes_envelope_savings(self):
        old_payload = _mock_payload()
        old_payload["upgrade_interests"] = ["attic insulation"]
        new_payload = _mock_payload()
        new_payload["upgrade_interests"] = ["attic insulation"]
        new_payload["property"]["year_built"] = 2020

        old_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**old_payload),
            index=IncentiveIndex(use_vector=False),
        )
        new_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**new_payload),
            index=IncentiveIndex(use_vector=False),
        )

        old_insulation = _option(old_response, "attic_insulation")
        new_insulation = _option(new_response, "attic_insulation")
        self.assertGreater(old_insulation.annual_savings, new_insulation.annual_savings)
        self.assertTrue(
            any("home age" in note for note in old_insulation.calculation_notes)
        )

    def test_appliance_fuel_and_occupants_change_water_heater_savings(self):
        gas_payload = _mock_payload()
        gas_payload["upgrade_interests"] = ["heat pump water heater"]
        gas_payload["household"]["household_size"] = 5
        electric_payload = _mock_payload()
        electric_payload["upgrade_interests"] = ["heat pump water heater"]
        electric_payload["property"]["water_heater_fuel"] = "electric"
        electric_payload["household"]["household_size"] = 1

        gas_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**gas_payload),
            index=IncentiveIndex(use_vector=False),
        )
        electric_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**electric_payload),
            index=IncentiveIndex(use_vector=False),
        )

        gas_water_heater = _option(gas_response, "heat_pump_water_heater")
        electric_water_heater = _option(electric_response, "heat_pump_water_heater")
        self.assertGreater(gas_water_heater.annual_savings, electric_water_heater.annual_savings)
        self.assertTrue(
            any("household size" in note for note in gas_water_heater.calculation_notes)
        )

    def test_roof_and_future_load_answers_change_solar_math(self):
        baseline_payload = _mock_payload()
        adjusted_payload = _mock_payload()
        adjusted_payload["preferences"] = {
            "roof_type": "tile",
            "roof_replacement_status": "yes",
            "ev_owner_or_planning": "owns_ev",
            "planned_electric_additions": True,
        }

        baseline_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**baseline_payload),
            index=IncentiveIndex(use_vector=False),
        )
        adjusted_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**adjusted_payload),
            index=IncentiveIndex(use_vector=False),
        )

        baseline_solar = _option(baseline_response, "solar")
        adjusted_solar = _option(adjusted_response, "solar")
        self.assertGreater(adjusted_solar.gross_cost, baseline_solar.gross_cost)
        self.assertGreater(adjusted_solar.annual_savings, baseline_solar.annual_savings)
        self.assertTrue(
            any("roof type" in note for note in adjusted_solar.calculation_notes)
        )
        self.assertTrue(
            any("EV charging" in note for note in adjusted_solar.calculation_notes)
        )

    def test_condo_home_type_suppresses_rooftop_solar_option(self):
        payload = _mock_payload()
        payload["property"]["home_type"] = "condo"

        response = calculate_retrofit_options(
            RetrofitCalculationRequest(**payload),
            index=IncentiveIndex(use_vector=False),
        )

        self.assertFalse(any(option.upgrade_key == "solar" for option in response.ranked_options))

    def test_renter_ownership_excludes_owner_sensitive_incentives(self):
        owner_payload = _mock_payload()
        owner_payload["upgrade_interests"] = ["heat pump"]
        renter_payload = _mock_payload()
        renter_payload["upgrade_interests"] = ["heat pump"]
        renter_payload["household"]["owner_occupied"] = False

        owner_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**owner_payload),
            index=IncentiveIndex(use_vector=False),
        )
        renter_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**renter_payload),
            index=IncentiveIndex(use_vector=False),
        )

        owner_heat_pump = _option(owner_response, "heat_pump")
        renter_heat_pump = _option(renter_response, "heat_pump")
        self.assertGreater(owner_heat_pump.incentive_total, renter_heat_pump.incentive_total)
        self.assertEqual(renter_heat_pump.incentive_total, 750)

    def test_primary_goal_changes_option_score(self):
        backup_payload = _mock_payload()
        backup_payload["preferences"] = {"primary_goal": "backup_power"}
        other_payload = _mock_payload()
        other_payload["preferences"] = {"primary_goal": "other"}

        backup_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**backup_payload),
            index=IncentiveIndex(use_vector=False),
        )
        other_response = calculate_retrofit_options(
            RetrofitCalculationRequest(**other_payload),
            index=IncentiveIndex(use_vector=False),
        )

        self.assertGreater(_option(backup_response, "solar").score, _option(other_response, "solar").score)

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


def _option(response, upgrade_key):
    return next(option for option in response.ranked_options if option.upgrade_key == upgrade_key)


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
