import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from schemas import (
    HouseholdProfile,
    PropertyProfile,
    RetrofitCalculationRequest,
    RetrofitOptionCalculation,
)
from services.incentive_index import IncentiveIndex
from services.retrofit_calculator import calculate_retrofit_options
from services.timeline_optimizer import build_timeline


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _option(
    upgrade_key,
    gross_cost,
    net_cost,
    annual_savings=0.0,
    carbon_avoided_tons=0.0,
    name=None,
):
    return RetrofitOptionCalculation(
        upgrade_key=upgrade_key,
        name=name or upgrade_key,
        description="",
        rank=0,
        gross_cost=gross_cost,
        incentive_total=max(gross_cost - net_cost, 0),
        net_cost=net_cost,
        annual_savings=annual_savings,
        carbon_avoided_tons=carbon_avoided_tons,
        payback_years=None,
        score=0,
        confidence="medium",
        matched_incentives=[],
        citations=[],
        calculation_notes=[],
    )


def _request(
    *,
    focus="balanced",
    budget_per_year=None,
    planning_horizon_years=5,
    current_year=2026,
    tax_liability_estimate=None,
    utility=None,
    household_income=None,
    owner_occupied=True,
):
    return RetrofitCalculationRequest(
        property=PropertyProfile(address="123 Test St, Atlanta, GA"),
        household=HouseholdProfile(
            tax_liability_estimate=tax_liability_estimate,
            utility=utility,
            household_income=household_income,
            owner_occupied=owner_occupied,
        ),
        focus=focus,
        budget_per_year=budget_per_year,
        planning_horizon_years=planning_horizon_years,
        current_year=current_year,
    )


# Most temporal fields default to None to exercise None-robustness. Callers pass
# only the fields a given test cares about.
_DOC_FIELDS = [
    "cap_category", "annual_cap", "lifetime_cap", "resets_annually",
    "available_from_year", "expires_year", "step_down_schedule", "claim_timing",
    "claim_lag_days", "availability_type", "program_status", "data_confidence",
    "last_verified_year", "subsidy_basis_reduction", "income_rebate_taxable",
    "ownership_required", "primary_residence_required", "tax_liability_required",
    "equipment_certification_required", "contractor_required",
    "energy_audit_required", "min_project_cost", "income_max", "utility",
]


def _doc(doc_id, eligible_upgrades, amount_rule=None, **overrides):
    doc = {
        "id": doc_id,
        "name": overrides.pop("name", doc_id),
        "eligible_upgrades": eligible_upgrades,
        "amount_rule": amount_rule,
    }
    for field in _DOC_FIELDS:
        doc[field] = None
    doc.update(overrides)
    return doc


def _detail(timeline, upgrade_key):
    return next(d for d in timeline.upgrade_details if d.upgrade_key == upgrade_key)


# 25C heat-pump-equipment-style program: 30% of cost, shared $2,000 annual cap.
def _shared_cap_doc(doc_id, upgrade):
    return _doc(
        doc_id,
        [upgrade],
        amount_rule={"type": "percentage_cap", "percent": 0.3, "cap": 2000},
        cap_category="25c-heat-pump-equipment",
        annual_cap=2000,
        resets_annually=True,
        available_from_year=2020,
        claim_timing="tax_filing",
        claim_lag_days=120,
        data_confidence="high",
        tax_liability_required=False,
        program_status="active",
    )


class TimelineOptimizerTests(unittest.TestCase):
    def test_cap_sharing_creates_stagger_incentive(self):
        # Two upgrades whose 30% credits each want $2,000 but share one $2,000 cap.
        gross = 6667  # 0.3 * gross ~= 2000
        options = [
            _option("heat_pump", gross_cost=gross, net_cost=2000),
            _option("heat_pump_water_heater", gross_cost=gross, net_cost=2000),
        ]
        docs = [
            _shared_cap_doc("prog-hp", "heat_pump"),
            _shared_cap_doc("prog-hpwh", "heat_pump_water_heater"),
        ]

        # Budget allows both in one year, but staggering captures the full cap twice.
        request = _request(budget_per_year=5000, planning_horizon_years=5)
        timeline = build_timeline(request, options, docs)

        hp_year = _detail(timeline, "heat_pump").scheduled_year
        hpwh_year = _detail(timeline, "heat_pump_water_heater").scheduled_year
        self.assertIsNotNone(hp_year)
        self.assertIsNotNone(hpwh_year)
        self.assertNotEqual(hp_year, hpwh_year)

        # Force both into the same year (1-year horizon) and confirm the cap-sharing
        # note surfaces. A dummy over-budget upgrade anchors the normalization range
        # so both real upgrades remain worth scheduling even when cap-shared.
        forced_options = [
            _option("heat_pump", gross_cost=gross, net_cost=1500, annual_savings=5000),
            _option("heat_pump_water_heater", gross_cost=gross, net_cost=1500, annual_savings=5000),
            _option("panel_dummy", gross_cost=100000, net_cost=100000),
        ]
        forced_request = _request(budget_per_year=5000, planning_horizon_years=1)
        forced_timeline = build_timeline(forced_request, forced_options, docs)

        self.assertEqual(_detail(forced_timeline, "heat_pump").scheduled_year, 2026)
        self.assertEqual(_detail(forced_timeline, "heat_pump_water_heater").scheduled_year, 2026)
        notes = [note for year in forced_timeline.years for note in year.cap_sharing_notes]
        self.assertTrue(notes, "expected a cap-sharing note when both share the cap in one year")

    def test_step_down_schedule_prefers_earlier(self):
        options = [_option("solar", gross_cost=20000, net_cost=14000, annual_savings=1800, carbon_avoided_tons=3.0)]
        docs = [
            _doc(
                "solar-25d",
                ["solar"],
                amount_rule={"type": "percentage_cap", "percent": 0.30, "cap": 0},
                cap_category="25d-solar",
                step_down_schedule={"2026": 0.30, "2028": 0.22},
                available_from_year=2022,
                expires_year=2034,
                claim_timing="tax_filing",
                claim_lag_days=120,
                data_confidence="high",
                tax_liability_required=False,
            )
        ]
        request = _request(budget_per_year=50000, planning_horizon_years=3)
        timeline = build_timeline(request, options, docs)

        # 0.30 in year 1 beats 0.22 in year 3, so the optimizer installs in year 1.
        self.assertEqual(_detail(timeline, "solar").scheduled_year, 2026)

    def test_dag_dependencies_respected_across_years(self):
        # Real seed DAG: heat_pump depends on air_sealing + attic_insulation, which
        # are themselves chained. A tight budget forces one upgrade per year.
        options = [
            _option("air_sealing", gross_cost=3000, net_cost=3000, annual_savings=250, carbon_avoided_tons=0.6),
            _option("attic_insulation", gross_cost=3000, net_cost=3000, annual_savings=450, carbon_avoided_tons=1.1),
            _option("heat_pump", gross_cost=3000, net_cost=3000, annual_savings=800, carbon_avoided_tons=2.4),
        ]
        request = _request(budget_per_year=3000, planning_horizon_years=5)
        timeline = build_timeline(request, options, incentive_docs=[])

        air = _detail(timeline, "air_sealing").scheduled_year
        attic = _detail(timeline, "attic_insulation").scheduled_year
        heat_pump = _detail(timeline, "heat_pump").scheduled_year

        for year in (air, attic, heat_pump):
            self.assertIsNotNone(year)
        self.assertGreaterEqual(attic, air)
        self.assertGreaterEqual(heat_pump, air)
        self.assertGreaterEqual(heat_pump, attic)

    def test_none_fields_dont_crash(self):
        options = [_option("heat_pump", gross_cost=12000, net_cost=9000, annual_savings=800, carbon_avoided_tons=2.4)]
        # Every optional incentive field is None.
        docs = [_doc("all-none", ["heat_pump"], amount_rule=None)]
        request = _request(budget_per_year=20000, planning_horizon_years=5)

        timeline = build_timeline(request, options, docs)  # must not raise

        detail = _detail(timeline, "heat_pump")
        self.assertTrue(detail.data_gaps, "missing fields should be reported as data gaps")

    def test_tax_liability_cap_applied(self):
        options = [_option("heat_pump", gross_cost=12000, net_cost=8000)]
        docs = [
            _doc(
                "fixed-2000",
                ["heat_pump"],
                amount_rule={"type": "fixed", "amount": 2000},
                tax_liability_required=True,
                available_from_year=2020,
                claim_timing="tax_filing",
                data_confidence="high",
            )
        ]
        request = _request(budget_per_year=20000, planning_horizon_years=5, tax_liability_estimate=500)
        timeline = build_timeline(request, options, docs)

        # $2,000 nominal credit is clamped to the household's $500 tax liability.
        self.assertEqual(_detail(timeline, "heat_pump").incentive_value, 500)

    def test_focus_changes_assignment(self):
        # Two upgrades competing for a single budget slot (only one fits per the
        # 1-year horizon + budget). One is cost-dominant, the other carbon-dominant.
        cost_option = _option("cost_winner", gross_cost=4000, net_cost=4000, annual_savings=5000, carbon_avoided_tons=0.1)
        carbon_option = _option("carbon_winner", gross_cost=4000, net_cost=4000, annual_savings=100, carbon_avoided_tons=10.0)
        options = [cost_option, carbon_option]

        cost_timeline = build_timeline(
            _request(focus="cost", budget_per_year=4000, planning_horizon_years=1), options, incentive_docs=[]
        )
        carbon_timeline = build_timeline(
            _request(focus="carbon", budget_per_year=4000, planning_horizon_years=1), options, incentive_docs=[]
        )

        self.assertIsNotNone(_detail(cost_timeline, "cost_winner").scheduled_year)
        self.assertIsNone(_detail(cost_timeline, "carbon_winner").scheduled_year)

        self.assertIsNotNone(_detail(carbon_timeline, "carbon_winner").scheduled_year)
        self.assertIsNone(_detail(carbon_timeline, "cost_winner").scheduled_year)

    def test_no_budget_no_timeline(self):
        payload = json.loads((BACKEND_ROOT / "data" / "mock_retrofit_calculation_request.json").read_text())
        request = RetrofitCalculationRequest(**payload)  # no budget_per_year

        response = calculate_retrofit_options(request, index=IncentiveIndex(use_vector=False))

        self.assertIsNone(response.timeline)
        self.assertGreaterEqual(len(response.ranked_options), 1)

    def test_key_insight_surfaces_stagger_gain(self):
        gross = 6667
        options = [
            _option("heat_pump", gross_cost=gross, net_cost=2000),
            _option("heat_pump_water_heater", gross_cost=gross, net_cost=2000),
        ]
        docs = [
            _shared_cap_doc("prog-hp", "heat_pump"),
            _shared_cap_doc("prog-hpwh", "heat_pump_water_heater"),
        ]
        request = _request(budget_per_year=5000, planning_horizon_years=5)
        timeline = build_timeline(request, options, docs)

        self.assertIsNotNone(timeline.key_insight)
        self.assertIn("$", timeline.key_insight)


if __name__ == "__main__":
    unittest.main()
