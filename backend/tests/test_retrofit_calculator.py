import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from schemas import RetrofitCalculationRequest, RetrofitOptionCalculation
from services.incentive_index import IncentiveIndex
from services.retrofit_calculator import calculate_retrofit_options, compute_efficiency_lookup
from services.retrofit_request_builder import build_retrofit_calculation_request
from services.sequencing import sequence_options


def _mock_payload():
    return json.loads((BACKEND_ROOT / "data" / "mock_retrofit_calculation_request.json").read_text())


class RetrofitCalculatorTests(unittest.TestCase):
    def test_same_dto_produces_same_output(self):
        request = RetrofitCalculationRequest(**_mock_payload())
        index = IncentiveIndex(use_vector=False)

        first = calculate_retrofit_options(request, index=index)
        second = calculate_retrofit_options(request, index=index)

        self.assertEqual(_dump(first), _dump(second))

        first_sequences = [option.recommended_sequence for option in first.ranked_options]
        second_sequences = [option.recommended_sequence for option in second.ranked_options]
        self.assertEqual(first_sequences, second_sequences)

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

    def test_dependency_order_respected_across_focuses(self):
        for focus in ["cost", "carbon", "balanced"]:
            payload = _mock_payload()
            payload["focus"] = focus
            request = RetrofitCalculationRequest(**payload)

            response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
            by_key = {option.upgrade_key: option for option in response.ranked_options}

            self.assertLess(
                by_key["air_sealing"].recommended_sequence,
                by_key["attic_insulation"].recommended_sequence,
            )
            self.assertLess(
                by_key["attic_insulation"].recommended_sequence,
                by_key["heat_pump"].recommended_sequence,
            )
            self.assertLess(
                by_key["heat_pump"].recommended_sequence,
                by_key["solar"].recommended_sequence,
            )
            self.assertLess(
                by_key["heat_pump_water_heater"].recommended_sequence,
                by_key["solar"].recommended_sequence,
            )

    def test_focus_changes_tie_break_ordering(self):
        dependency_map = {
            "air_sealing": {"depends_on": []},
            "heat_pump_water_heater": {"depends_on": []},
        }
        options = [
            _stub_option("air_sealing", score=50),
            _stub_option("heat_pump_water_heater", score=60),
        ]
        efficiency_lookup = {
            "air_sealing": {"cost_efficiency": 90, "carbon_efficiency": 10},
            "heat_pump_water_heater": {"cost_efficiency": 10, "carbon_efficiency": 90},
        }

        cost_focused = sequence_options(
            options, focus="cost", dependency_map=dependency_map, efficiency_lookup=efficiency_lookup
        )
        carbon_focused = sequence_options(
            options, focus="carbon", dependency_map=dependency_map, efficiency_lookup=efficiency_lookup
        )

        cost_first = next(option for option in cost_focused if option.recommended_sequence == 1)
        carbon_first = next(option for option in carbon_focused if option.recommended_sequence == 1)

        self.assertEqual(cost_first.upgrade_key, "air_sealing")
        self.assertEqual(carbon_first.upgrade_key, "heat_pump_water_heater")
        self.assertNotEqual(cost_first.upgrade_key, carbon_first.upgrade_key)

    def test_balanced_score_is_not_payback_dominated(self):
        request = RetrofitCalculationRequest(**_mock_payload())

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        by_key = {option.upgrade_key: option for option in response.ranked_options}

        heat_pump_water_heater = by_key["heat_pump_water_heater"]
        attic_insulation = by_key["attic_insulation"]

        # Heat pump water heater has a longer payback than attic insulation...
        self.assertGreater(heat_pump_water_heater.payback_years, attic_insulation.payback_years)
        # ...but a meaningfully higher carbon avoided per dollar of net cost.
        self.assertGreater(
            heat_pump_water_heater.carbon_avoided_tons / heat_pump_water_heater.net_cost,
            attic_insulation.carbon_avoided_tons / attic_insulation.net_cost,
        )
        # Under the balanced score the higher-carbon-efficiency option outranks the
        # shorter-payback option, which the old payback-dominated score reversed.
        self.assertGreater(heat_pump_water_heater.score, attic_insulation.score)
        self.assertLess(heat_pump_water_heater.rank, attic_insulation.rank)

    def test_single_option_input_assigns_first_sequence(self):
        payload = _mock_payload()
        payload["upgrade_interests"] = ["solar"]
        request = RetrofitCalculationRequest(**payload)

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        self.assertEqual(len(response.ranked_options), 1)
        solar = response.ranked_options[0]
        self.assertEqual(solar.upgrade_key, "solar")
        self.assertEqual(solar.recommended_sequence, 1)
        self.assertTrue(solar.sequence_notes)

    def test_sequence_options_handles_missing_dependency_entry(self):
        request = RetrofitCalculationRequest(**_mock_payload())

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        sequenced = sequence_options(response.ranked_options, focus="balanced", dependency_map={})

        self.assertEqual(len(sequenced), len(response.ranked_options))
        sequence_numbers = sorted(option.recommended_sequence for option in sequenced)
        self.assertEqual(sequence_numbers, list(range(1, len(sequenced) + 1)))

    def test_endpoint_focus_carbon_returns_sequencing(self):
        client = TestClient(app)
        payload = _mock_payload()
        payload["focus"] = "carbon"

        response = client.post("/calculate-retrofit/", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["sequencing_focus"], "carbon")
        for option in body["ranked_options"]:
            self.assertGreaterEqual(option["recommended_sequence"], 1)

    def test_endpoint_default_focus_is_balanced(self):
        client = TestClient(app)

        response = client.post("/calculate-retrofit/", json=_mock_payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["sequencing_focus"], "balanced")

    def test_endpoint_sequence_retrofit_reorders_without_changing_financials(self):
        client = TestClient(app)

        calc_response = client.post("/calculate-retrofit/", json=_mock_payload())
        self.assertEqual(calc_response.status_code, 200)
        ranked_options = calc_response.json()["ranked_options"]

        responses = {}
        for focus in ["cost", "carbon"]:
            response = client.post(
                "/sequence-retrofit/",
                json={"ranked_options": ranked_options, "focus": focus},
            )
            self.assertEqual(response.status_code, 200)
            responses[focus] = response.json()
            self.assertEqual(responses[focus]["sequencing_focus"], focus)

            by_key = {option["upgrade_key"]: option for option in responses[focus]["ranked_options"]}
            self.assertLess(
                by_key["air_sealing"]["recommended_sequence"],
                by_key["attic_insulation"]["recommended_sequence"],
            )
            self.assertLess(
                by_key["heat_pump"]["recommended_sequence"],
                by_key["solar"]["recommended_sequence"],
            )
            self.assertLess(
                by_key["heat_pump_water_heater"]["recommended_sequence"],
                by_key["solar"]["recommended_sequence"],
            )

            original_by_key = {option["upgrade_key"]: option for option in ranked_options}
            for upgrade_key, sequenced_option in by_key.items():
                original_option = original_by_key[upgrade_key]
                self.assertEqual(sequenced_option["rank"], original_option["rank"])
                self.assertEqual(sequenced_option["score"], original_option["score"])
                self.assertEqual(sequenced_option["net_cost"], original_option["net_cost"])

        cost_first = next(
            option for option in responses["cost"]["ranked_options"] if option["recommended_sequence"] == 1
        )
        carbon_first = next(
            option for option in responses["carbon"]["ranked_options"] if option["recommended_sequence"] == 1
        )
        self.assertEqual(cost_first["upgrade_key"], carbon_first["upgrade_key"])

    def test_compute_efficiency_lookup_matches_scored_options(self):
        request = RetrofitCalculationRequest(**_mock_payload())

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))
        efficiency_lookup = compute_efficiency_lookup(response.ranked_options)

        for option in response.ranked_options:
            self.assertAlmostEqual(
                efficiency_lookup[option.upgrade_key]["score"], option.score, places=4
            )

    def test_builder_defaults_without_primary_goal(self):
        payload = _mock_payload()
        answers = {
            "monthly_electricity_bill": "$150",
            "monthly_gas_bill": "$40",
            "home_ownership_status": "Own",
            "home_type": "Single Family",
            "year_built": "1980 - 2000",
            "square_footage": "1,500 - 2,500 sq ft",
            "appliances_fuel": "Electric",
        }

        request = build_retrofit_calculation_request(
            address=payload["property"]["address"], answers=answers
        )

        self.assertEqual(request.upgrade_interests, [])
        self.assertEqual(request.focus, "balanced")


def _stub_option(upgrade_key, score):
    return RetrofitOptionCalculation(
        upgrade_key=upgrade_key,
        name=upgrade_key,
        description="",
        rank=0,
        gross_cost=0,
        incentive_total=0,
        net_cost=1,
        annual_savings=0,
        carbon_avoided_tons=0,
        payback_years=None,
        score=score,
        confidence="medium",
        matched_incentives=[],
        citations=[],
        calculation_notes=[],
    )


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
