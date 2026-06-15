from typing import List, Optional

from schemas import (
    AnalysisAssumptions,
    BuildingBenchmark,
    BuildingRecommendation,
    BuildingRetrofitRequest,
    BuildingRetrofitResponse,
    IncentiveAnalysisRequest,
    IncentiveMatch,
)
from services.incentive_index import get_default_index
from services.retrofit_request_builder import (
    _int_or_none,
    _owner_occupied,
    _square_footage,
    _year_built,
)


REQUIRED_BENCHMARKING_INPUTS = [
    "12 months electric utility history",
    "12 months gas or delivered-fuel history",
    "gross floor area",
    "number of units",
    "occupancy or operating schedule",
    "building type",
    "existing HVAC and domestic hot water systems",
]


def build_building_retrofit_request(address: str, answers: dict, mode: str) -> BuildingRetrofitRequest:
    meta = answers.get("_property_meta") or {}
    utility_history = answers.get("utility_history") or []
    existing_systems = _list_value(answers.get("existing_systems"))
    hvac_system_type = answers.get("hvac_system_type")
    domestic_hot_water_type = answers.get("domestic_hot_water_type")
    if hvac_system_type:
        existing_systems.append(f"HVAC: {hvac_system_type}")
    if domestic_hot_water_type:
        existing_systems.append(f"DHW: {domestic_hot_water_type}")

    return BuildingRetrofitRequest(
        address=meta.get("formatted_address") or address,
        mode=mode,
        role=answers.get("role"),
        scope=answers.get("scope"),
        building_type=_building_type(
            answers.get("building_type") or answers.get("home_type") or meta.get("property_type")
        ),
        gross_floor_area=_square_footage(answers.get("square_footage") or meta.get("square_footage")),
        units=_unit_count(answers, meta),
        occupancy=_int_or_none(answers.get("occupancy") or answers.get("num_occupants")),
        year_built=_year_built(answers.get("year_built") or meta.get("year_built")),
        owner_occupied=_owner_occupied(answers.get("home_ownership_status")),
        utility=answers.get("utility") or answers.get("electric_utility") or "Georgia Power",
        electric_utility=answers.get("electric_utility") or answers.get("utility") or "Georgia Power",
        gas_utility=answers.get("gas_utility"),
        utility_structure=answers.get("utility_structure"),
        electric_metering=answers.get("electric_metering"),
        gas_metering=answers.get("gas_metering"),
        electric_bill_responsibility=answers.get("electric_bill_responsibility"),
        gas_bill_responsibility=answers.get("gas_bill_responsibility"),
        portfolio_manager_property_id=answers.get("portfolio_manager_property_id"),
        utility_history=utility_history,
        existing_systems=existing_systems,
        hvac_system_type=hvac_system_type,
        domestic_hot_water_type=domestic_hot_water_type,
        roof_control=answers.get("roof_control"),
        primary_goal=answers.get("primary_goal"),
        planning_horizon=answers.get("planning_horizon"),
        capex_budget_range=answers.get("capex_budget_range"),
    )


def analyze_building_retrofit(request: BuildingRetrofitRequest) -> BuildingRetrofitResponse:
    missing_inputs = _missing_building_inputs(request)
    benchmarking_ready = not missing_inputs
    data_completeness_score = _data_completeness_score(request)
    benchmark = _benchmark(request)
    recommendations = _building_recommendations(request, benchmarking_ready, benchmark)
    eligible_incentives = _eligible_incentives(request)
    warnings = _warnings(request)
    next_steps = _next_steps(missing_inputs, request)

    assumptions = AnalysisAssumptions(
        location=request.address,
        square_footage=request.gross_floor_area or 0,
        home_type=request.building_type or "building",
        utility=request.utility or "unknown",
        notes=[
            "Building mode is a benchmarking-first workflow for apartments, multifamily, commercial, and renter-limited cases.",
            "Building quick estimates use data completeness, utility history, and building operations inputs before package-level economics.",
            "Solar is treated as feasibility until roof control, meter structure, and tenant allocation are confirmed.",
        ],
    )

    return BuildingRetrofitResponse(
        mode=request.mode,
        address=request.address,
        building_type=request.building_type,
        gross_floor_area=request.gross_floor_area,
        units=request.units,
        missing_inputs=missing_inputs,
        benchmarking_ready=benchmarking_ready,
        data_completeness_score=data_completeness_score,
        benchmark=benchmark,
        recommendations=recommendations,
        eligible_incentives=eligible_incentives,
        next_steps=next_steps,
        warnings=warnings,
        assumptions=assumptions,
    )


def building_summary(response: BuildingRetrofitResponse) -> str:
    if response.benchmarking_ready:
        return (
            f"RetroFi identified {response.address} as a larger-building retrofit case. "
            f"The intake is complete enough for benchmarking with a {response.data_completeness_score}% "
            "data completeness score, so the next step is to validate utility history and model phased packages."
        )

    missing = "; ".join(response.missing_inputs)
    return (
        f"RetroFi identified {response.address} as a larger-building or renter-limited case. "
        f"The current data completeness score is {response.data_completeness_score}%. Instead of "
        "recommending homeowner rooftop solar or single-home upgrades, collect benchmarking inputs first: "
        f"{missing}."
    )


def _missing_building_inputs(request: BuildingRetrofitRequest) -> List[str]:
    missing: List[str] = []
    if not _has_utility_history(request, "electric"):
        missing.append("12 months electric utility history")
    if not _has_utility_history(request, "gas") and not _is_no_gas_building(request):
        missing.append("12 months gas or delivered-fuel history")
    if not request.gross_floor_area:
        missing.append("gross floor area")
    if not request.units:
        missing.append("number of units")
    if not request.occupancy:
        missing.append("occupancy or operating schedule")
    if not request.building_type:
        missing.append("building type")
    if not request.existing_systems:
        missing.append("existing HVAC and domestic hot water systems")
    if not request.utility_structure:
        missing.append("utility and meter structure")
    return missing


def _building_recommendations(
    request: BuildingRetrofitRequest,
    benchmarking_ready: bool,
    benchmark: Optional[BuildingBenchmark],
) -> List[BuildingRecommendation]:
    data_required = [] if benchmarking_ready else REQUIRED_BENCHMARKING_INPUTS
    owner_tenant_note = _owner_tenant_split_note(request)
    recommendations = [
        BuildingRecommendation(
            package_key="benchmarking_audit",
            name="Benchmarking and Audit Package",
            description="Collect whole-building utility history, benchmark EUI, and scope an ASHRAE-style assessment before selecting measures.",
            priority=1,
            data_required=data_required,
            confidence="high" if benchmark and benchmark.site_eui_kbtu_per_sq_ft else "medium",
            estimated_cost_range="$2,500-$12,000",
            estimated_annual_savings_range="TBD after utility baseline",
            owner_tenant_split_note=owner_tenant_note,
        ),
        BuildingRecommendation(
            package_key="common_area_efficiency",
            name="Common-Area Efficiency Package",
            description="Evaluate lighting, controls, ventilation schedules, and shared equipment loads once baseline data is available.",
            priority=2,
            data_required=data_required,
            confidence="medium" if request.utility_structure else "low",
            estimated_cost_range="$0.50-$3.00/sq ft",
            estimated_annual_savings_range="5-15% of common-area electric spend",
            owner_tenant_split_note=owner_tenant_note,
        ),
        BuildingRecommendation(
            package_key="solar_feasibility",
            name="Solar Feasibility Study",
            description="Assess roof rights, structural constraints, tenant allocation, and interconnection before any larger-building solar recommendation.",
            priority=3,
            data_required=data_required,
            confidence="medium" if request.roof_control else "low",
            estimated_cost_range="Feasibility study before capex estimate",
            estimated_annual_savings_range="Depends on roof control, tariff, and allocation model",
            owner_tenant_split_note=owner_tenant_note,
        ),
    ]
    if request.hvac_system_type or request.domestic_hot_water_type:
        recommendations.insert(
            2,
            BuildingRecommendation(
                package_key="hvac_dhw_assessment",
                name="HVAC and Domestic Hot Water Assessment",
                description="Screen central and in-unit HVAC/DHW systems for electrification, controls, and replacement timing before capex planning.",
                priority=3,
                data_required=data_required,
                confidence="medium",
                estimated_cost_range="$1.00-$8.00/sq ft for targeted measures; major replacements require contractor scope",
                estimated_annual_savings_range="10-25% of affected heating, cooling, or hot water spend",
                owner_tenant_split_note=owner_tenant_note,
            ),
        )
        for index, recommendation in enumerate(recommendations, start=1):
            recommendation.priority = index
    return recommendations


def _data_completeness_score(request: BuildingRetrofitRequest) -> int:
    checks = [
        bool(request.building_type),
        bool(request.gross_floor_area),
        bool(request.units),
        bool(request.occupancy),
        bool(request.utility_structure),
        bool(request.existing_systems),
        _has_utility_history(request, "electric"),
        _has_utility_history(request, "gas") or _is_no_gas_building(request),
        bool(request.electric_bill_responsibility),
        bool(request.primary_goal),
    ]
    return round(sum(1 for check in checks if check) / len(checks) * 100)


def _benchmark(request: BuildingRetrofitRequest) -> BuildingBenchmark:
    electric = _utility_entry(request, "electric")
    gas = _utility_entry(request, "gas")
    annual_kwh = electric.total_usage if electric else None
    annual_therms = gas.total_usage if gas else None
    annual_cost = sum(
        entry.total_cost or 0
        for entry in request.utility_history
        if entry.months >= 12
    ) or None

    notes: List[str] = []
    site_eui = None
    if request.gross_floor_area and (annual_kwh or annual_therms):
        electric_kbtu = (annual_kwh or 0) * 3.412
        gas_kbtu = (annual_therms or 0) * 100
        site_eui = round((electric_kbtu + gas_kbtu) / request.gross_floor_area, 1)
        notes.append("Site EUI uses provided annual electric and fuel usage divided by gross floor area.")
    else:
        notes.append("Provide annual usage and gross floor area to calculate preliminary site EUI.")

    cost_per_sq_ft = None
    if annual_cost and request.gross_floor_area:
        cost_per_sq_ft = round(annual_cost / request.gross_floor_area, 2)
        notes.append("Utility cost intensity uses 12-month cost totals from the provided utility history.")

    confidence = "medium" if site_eui else "low"
    if site_eui and _has_utility_history(request, "electric") and (
        _has_utility_history(request, "gas") or _is_no_gas_building(request)
    ):
        confidence = "high"

    return BuildingBenchmark(
        annual_electric_kwh=annual_kwh,
        annual_gas_therms=annual_therms,
        annual_utility_cost=annual_cost,
        site_eui_kbtu_per_sq_ft=site_eui,
        utility_cost_per_sq_ft=cost_per_sq_ft,
        confidence=confidence,
        notes=notes,
    )


def _eligible_incentives(request: BuildingRetrofitRequest) -> List[IncentiveMatch]:
    index = get_default_index()
    incentive_request = IncentiveAnalysisRequest(
        address=request.address,
        home_type=request.building_type,
        year_built=request.year_built,
        square_footage=request.gross_floor_area,
        owner_occupied=request.owner_occupied,
        utility=request.electric_utility or request.utility,
        market_segment=_market_segment(request),
        role=request.role,
        building_type=request.building_type,
        units=request.units,
        utility_structure=request.utility_structure,
        upgrade_interests=[
            "benchmarking",
            "common area lighting",
            "hvac controls",
            "building envelope",
            "solar",
            "ev charging",
        ],
    )
    matches = index.search_incentives(incentive_request, limit=6)
    return [
        IncentiveMatch(
            id=document["id"],
            name=document["name"],
            source=document["source"],
            incentive_type=document["incentive_type"],
            amount=_incentive_amount(document),
            amount_description=document.get("amount_description", "Amount depends on program rules"),
            eligible_upgrades=document.get("eligible_upgrades", []),
            eligibility_notes=document.get("eligibility", ""),
            stackable=document.get("stackable", True),
            citation_id=f"citation-{document['id']}",
        )
        for document in matches
    ]


def _next_steps(missing_inputs: List[str], request: BuildingRetrofitRequest) -> List[str]:
    if missing_inputs:
        return [
            f"Collect or confirm: {missing_inputs[0]}.",
            "Separate owner-paid common-area usage from tenant-paid in-unit usage before modeling savings.",
            "Confirm decision authority, roof control, and current HVAC/DHW systems before contractor scoping.",
        ]
    return [
        "Validate utility history against bills or Portfolio Manager exports.",
        "Prioritize packages by owner-paid savings, tenant impact, incentives, and capex timing.",
        "Request contractor or audit scopes for the top-ranked building packages.",
    ]


def _warnings(request: BuildingRetrofitRequest) -> List[str]:
    warnings: List[str] = []
    if request.mode == "renter_safe":
        warnings.append("Tenant or renter-limited users should not receive owner-level capital recommendations without owner approval.")
    if _responsibility_mentions_tenant(request.electric_bill_responsibility) or _responsibility_mentions_tenant(request.gas_bill_responsibility):
        warnings.append("Tenant-paid utilities can create split incentives; owner and tenant savings should be modeled separately.")
    if not request.roof_control:
        warnings.append("Solar should remain a feasibility item until roof control and allocation rules are confirmed.")
    return warnings


def _has_utility_history(request: BuildingRetrofitRequest, fuel_type: str) -> bool:
    return any(
        fuel_type in entry.fuel_type.lower() and entry.months >= 12
        for entry in request.utility_history
    )


def _utility_entry(request: BuildingRetrofitRequest, fuel_type: str):
    for entry in request.utility_history:
        if fuel_type in entry.fuel_type.lower() and entry.months >= 12:
            return entry
    return None


def _building_type(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "apartment" in normalized:
        return "apartment"
    if "condo" in normalized:
        return "condo"
    if "multi" in normalized:
        return "multifamily"
    if "commercial" in normalized or "office" in normalized or "retail" in normalized:
        return "commercial"
    if "mixed" in normalized:
        return "mixed_use"
    return str(value)


def _unit_count(answers: dict, meta: dict) -> Optional[int]:
    for key in ("unit_count", "units", "number_of_units"):
        parsed = _int_or_none(answers.get(key) or meta.get(key))
        if parsed:
            return parsed
    bedrooms = _int_or_none(meta.get("bedrooms"))
    if bedrooms and _building_type(answers.get("home_type") or meta.get("property_type")) in {
        "apartment",
        "multifamily",
        "condo",
    }:
        return max(1, round(bedrooms / 2))
    return None


def _list_value(value) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _market_segment(request: BuildingRetrofitRequest) -> str:
    building_type = (request.building_type or "").lower()
    if any(value in building_type for value in ("commercial", "office", "retail", "mixed")):
        return "commercial"
    if "renter" in (request.mode or ""):
        return "renter"
    return "multifamily"


def _incentive_amount(document: dict) -> float:
    amount_rule = document.get("amount_rule", {})
    if amount_rule.get("type") == "fixed":
        return float(amount_rule.get("amount", 0))
    return 0.0


def _owner_tenant_split_note(request: BuildingRetrofitRequest) -> str:
    if _responsibility_mentions_tenant(request.electric_bill_responsibility) or _responsibility_mentions_tenant(request.gas_bill_responsibility):
        return "Model owner-paid and tenant-paid savings separately before counting NOI impact."
    if request.electric_bill_responsibility or request.gas_bill_responsibility:
        return "Savings appear owner-aligned based on current utility responsibility answers, but should be verified against leases."
    return "Utility responsibility is unknown; split-incentive risk should be resolved before payback modeling."


def _responsibility_mentions_tenant(value) -> bool:
    return "tenant" in str(value or "").lower()


def _is_no_gas_building(request: BuildingRetrofitRequest) -> bool:
    values = [
        request.gas_bill_responsibility,
        request.gas_metering,
        request.domestic_hot_water_type,
        " ".join(request.existing_systems),
    ]
    return any("no gas" in str(value).lower() or "all electric" in str(value).lower() for value in values)
