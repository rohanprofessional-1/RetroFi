from typing import Dict, List, Optional, Tuple

from schemas import (
    AnalysisAssumptions,
    IncentiveAnalysisRequest,
    IncentiveMatch,
    LlmContext,
    RetrofitCalculationRequest,
    RetrofitCalculationResponse,
    RetrofitCalculationTotals,
    RetrofitOptionCalculation,
    SourceCitation,
)
from services.incentive_index import IncentiveIndex, get_default_index
from services.sequencing import sequence_options


DEFAULT_SQUARE_FOOTAGE = 1800
DEFAULT_HOME_TYPE = "single_family"
DEFAULT_UTILITY = "Georgia Power"
DEFAULT_ELECTRIC_RATE = 0.14
DEFAULT_GAS_RATE = 1.35
DEFAULT_GRID_CARBON_KG_PER_KWH = 0.39
DEFAULT_GAS_CARBON_KG_PER_THERM = 5.3
DEFAULT_SOLAR_DOLLARS_PER_WATT = 3.0
SOLAR_AC_DERATE = 0.85


def calculate_retrofit_options(
    request: RetrofitCalculationRequest,
    index: Optional[IncentiveIndex] = None,
) -> RetrofitCalculationResponse:
    incentive_index = index or get_default_index()
    analysis_request = _to_incentive_request(request)
    costs = incentive_index.search_costs(analysis_request)
    incentives = incentive_index.search_incentives(analysis_request)

    citations_by_id: Dict[str, SourceCitation] = {}
    options: List[RetrofitOptionCalculation] = []
    missing_inputs = _missing_inputs(request)

    for cost_document in costs:
        option = _calculate_efficiency_option(
            request=request,
            cost_document=cost_document,
            incentive_documents=incentives,
            citations_by_id=citations_by_id,
        )
        options.append(option)

    solar_incentives: List[Dict] = []
    if request.solar and request.solar.solar_viable:
        solar_incentives = incentive_index.search_incentives(
            _to_incentive_request(request, upgrade_interests=["solar"]),
            limit=8,
        )
        option = _calculate_solar_option(
            request=request,
            incentive_documents=solar_incentives,
            citations_by_id=citations_by_id,
        )
        options.append(option)

    scored_options, efficiency_lookup = _apply_balanced_scores(options)

    ranked_options = [
        _copy_model(option, {"rank": rank})
        for rank, option in enumerate(
            sorted(scored_options, key=lambda option: option.score, reverse=True),
            start=1,
        )
    ]

    ranked_options = sequence_options(
        ranked_options,
        focus=request.focus,
        efficiency_lookup=efficiency_lookup,
    )

    totals = RetrofitCalculationTotals(
        gross_cost=round(sum(option.gross_cost for option in ranked_options), 2),
        incentive_total=round(sum(option.incentive_total for option in ranked_options), 2),
        net_cost=round(sum(option.net_cost for option in ranked_options), 2),
        annual_savings=round(sum(option.annual_savings for option in ranked_options), 2),
        carbon_avoided_tons=round(sum(option.carbon_avoided_tons for option in ranked_options), 2),
    )
    assumptions = _assumptions(request, missing_inputs)
    citations = list(citations_by_id.values())

    timeline = None
    if request.budget_per_year is not None:
        from services.timeline_optimizer import build_timeline

        all_incentive_docs = _dedup_docs(incentives + solar_incentives)
        timeline = build_timeline(
            request=request,
            options=ranked_options,
            incentive_docs=all_incentive_docs,
        )

    return RetrofitCalculationResponse(
        address=request.property.address,
        ranked_options=ranked_options,
        totals=totals,
        assumptions=assumptions,
        citations=citations,
        llm_context=_llm_context(
            request=request,
            ranked_options=ranked_options,
            totals=totals,
            assumptions=assumptions,
            missing_inputs=missing_inputs,
            citations=citations,
        ),
        sequencing_focus=request.focus,
        timeline=timeline,
    )


def _calculate_efficiency_option(
    request: RetrofitCalculationRequest,
    cost_document: Dict,
    incentive_documents: List[Dict],
    citations_by_id: Dict[str, SourceCitation],
) -> RetrofitOptionCalculation:
    square_footage = request.property.square_footage or DEFAULT_SQUARE_FOOTAGE
    upgrade_key = cost_document["upgrade_key"]
    gross_cost = _scaled_cost(cost_document, square_footage)
    matched_incentives = _matched_incentives_for_upgrade(
        upgrade_key=upgrade_key,
        gross_cost=gross_cost,
        incentive_documents=incentive_documents,
        citations_by_id=citations_by_id,
    )
    matched_incentives = _dedupe_incentives(matched_incentives)
    selected_incentives = _select_stackable_incentives(matched_incentives)
    incentive_total = sum(incentive.amount for incentive in selected_incentives)
    net_cost = max(gross_cost - incentive_total, 0)
    annual_savings, savings_notes = _annual_savings(request, cost_document)
    carbon_avoided, carbon_notes = _carbon_avoided(request, cost_document)
    payback_years = round(net_cost / annual_savings, 1) if annual_savings > 0 else None

    cost_citation_id = f"citation-{cost_document['id']}"
    citations_by_id[cost_citation_id] = SourceCitation(
        id=cost_citation_id,
        title=cost_document["name"],
        source=cost_document["source"],
        source_url=cost_document.get("source_url"),
        snippet=cost_document["citation_snippet"],
    )
    return RetrofitOptionCalculation(
        upgrade_key=upgrade_key,
        name=cost_document["name"],
        description=cost_document["description"],
        rank=0,
        gross_cost=round(gross_cost, 2),
        incentive_total=round(incentive_total, 2),
        net_cost=round(net_cost, 2),
        annual_savings=round(annual_savings, 2),
        carbon_avoided_tons=round(carbon_avoided, 2),
        payback_years=payback_years,
        score=0,
        confidence=cost_document["confidence"],
        matched_incentives=selected_incentives,
        citations=[cost_citation_id] + [incentive.citation_id for incentive in selected_incentives],
        calculation_notes=[
            f"Gross cost uses the midpoint of ${cost_document['cost_low']:,.0f}-${cost_document['cost_high']:,.0f}, scaled for {square_footage:,} sq ft.",
            *savings_notes,
            *carbon_notes,
        ],
    )


def _calculate_solar_option(
    request: RetrofitCalculationRequest,
    incentive_documents: List[Dict],
    citations_by_id: Dict[str, SourceCitation],
) -> RetrofitOptionCalculation:
    solar = request.solar
    gross_cost = solar.estimated_install_cost or (
        (solar.installed_system_kw or 0) * 1000 * DEFAULT_SOLAR_DOLLARS_PER_WATT
    )
    annual_kwh = solar.yearly_energy_dc_kwh or (solar.installed_system_kw or 0) * 1300
    annual_savings = annual_kwh * SOLAR_AC_DERATE * _electric_rate(request)
    carbon_avoided = annual_kwh * SOLAR_AC_DERATE * _grid_carbon(request) / 1000
    matched_incentives = _matched_incentives_for_upgrade(
        upgrade_key="solar",
        gross_cost=gross_cost,
        incentive_documents=incentive_documents,
        citations_by_id=citations_by_id,
    )
    matched_incentives = _dedupe_incentives(matched_incentives)
    selected_incentives = _select_stackable_incentives(matched_incentives)
    incentive_total = sum(incentive.amount for incentive in selected_incentives)
    net_cost = max(gross_cost - incentive_total, 0)
    payback_years = round(net_cost / annual_savings, 1) if annual_savings > 0 else None

    solar_citation_id = "citation-google-solar-input"
    citations_by_id[solar_citation_id] = SourceCitation(
        id=solar_citation_id,
        title="Google Solar API Input",
        source="Request DTO",
        source_url=None,
        snippet="Solar option uses caller-provided solar potential fields rather than a live API call.",
    )

    return RetrofitOptionCalculation(
        upgrade_key="solar",
        name="Rooftop Solar PV",
        description="Install rooftop solar panels based on the provided Google Solar API-like potential.",
        rank=0,
        gross_cost=round(gross_cost, 2),
        incentive_total=round(incentive_total, 2),
        net_cost=round(net_cost, 2),
        annual_savings=round(annual_savings, 2),
        carbon_avoided_tons=round(carbon_avoided, 2),
        payback_years=payback_years,
        score=0,
        confidence="medium",
        matched_incentives=selected_incentives,
        citations=[solar_citation_id] + [incentive.citation_id for incentive in selected_incentives],
        calculation_notes=[
            "Solar production uses DTO-provided yearly DC kWh with a conservative AC derate.",
            f"Electric bill savings use ${_electric_rate(request):.3f}/kWh.",
            f"Carbon avoided uses {_grid_carbon(request):.3f} kg CO2/kWh.",
        ],
    )


def _to_incentive_request(
    request: RetrofitCalculationRequest,
    upgrade_interests: Optional[List[str]] = None,
) -> IncentiveAnalysisRequest:
    return IncentiveAnalysisRequest(
        address=request.property.address,
        zip_code=request.property.zip_code,
        home_type=request.property.home_type,
        year_built=request.property.year_built,
        square_footage=request.property.square_footage,
        household_income=request.household.household_income,
        utility=request.household.utility,
        upgrade_interests=upgrade_interests if upgrade_interests is not None else request.upgrade_interests,
    )


def _scaled_cost(cost_document: Dict, square_footage: int) -> float:
    midpoint = (cost_document["cost_low"] + cost_document["cost_high"]) / 2
    scale = square_footage / DEFAULT_SQUARE_FOOTAGE
    if cost_document["upgrade_key"] in {"attic_insulation", "air_sealing"}:
        return midpoint * min(max(scale, 0.75), 1.5)
    return midpoint * min(max(scale, 0.85), 1.25)


def _annual_savings(request: RetrofitCalculationRequest, cost_document: Dict) -> Tuple[float, List[str]]:
    seed_savings = _scaled_seed_savings(
        cost_document["annual_savings"],
        request.property.square_footage or DEFAULT_SQUARE_FOOTAGE,
    )
    retcast_delta = _retcast_energy_savings(request)
    if retcast_delta <= 0:
        return seed_savings, ["Annual savings use install-cost seed assumptions because Retcast projected savings were not available."]

    upgrade_key = cost_document["upgrade_key"]
    if upgrade_key in {"heat_pump", "heat_pump_water_heater"}:
        retcast_savings = retcast_delta * 0.45
    elif upgrade_key in {"attic_insulation", "air_sealing"}:
        retcast_savings = retcast_delta * 0.25
    else:
        retcast_savings = seed_savings

    blended_savings = max(seed_savings * 0.75, min(retcast_savings, seed_savings * 1.5))
    return blended_savings, ["Annual savings blend seed assumptions with Retcast-provided projected energy savings."]


def _carbon_avoided(request: RetrofitCalculationRequest, cost_document: Dict) -> Tuple[float, List[str]]:
    retcast = request.retcast
    if not retcast:
        return cost_document["carbon_avoided_tons"], ["Carbon avoided uses seed assumptions because Retcast data was not provided."]

    kwh_delta = max((retcast.baseline_annual_kwh or 0) - (retcast.projected_annual_kwh or 0), 0)
    therm_delta = max((retcast.baseline_annual_therms or 0) - (retcast.projected_annual_therms or 0), 0)
    total_tons = (
        kwh_delta * _grid_carbon(request)
        + therm_delta * (retcast.gas_carbon_kg_per_therm or DEFAULT_GAS_CARBON_KG_PER_THERM)
    ) / 1000
    if total_tons <= 0:
        return cost_document["carbon_avoided_tons"], ["Carbon avoided falls back to seed assumptions because Retcast deltas were not positive."]

    share = 0.45 if cost_document["upgrade_key"] in {"heat_pump", "heat_pump_water_heater"} else 0.25
    return total_tons * share, ["Carbon avoided uses Retcast energy deltas and emissions factors."]


def _scaled_seed_savings(seed_savings: float, square_footage: int) -> float:
    scale = square_footage / DEFAULT_SQUARE_FOOTAGE
    return seed_savings * min(max(scale, 0.8), 1.35)


def _retcast_energy_savings(request: RetrofitCalculationRequest) -> float:
    retcast = request.retcast
    if not retcast:
        return 0
    electric_savings = max((retcast.baseline_annual_kwh or 0) - (retcast.projected_annual_kwh or 0), 0) * _electric_rate(request)
    gas_savings = max((retcast.baseline_annual_therms or 0) - (retcast.projected_annual_therms or 0), 0) * _gas_rate(request)
    return electric_savings + gas_savings


def _matched_incentives_for_upgrade(
    upgrade_key: str,
    gross_cost: float,
    incentive_documents: List[Dict],
    citations_by_id: Dict[str, SourceCitation],
) -> List[IncentiveMatch]:
    matches: List[IncentiveMatch] = []
    for document in incentive_documents:
        if upgrade_key not in document.get("eligible_upgrades", []):
            continue
        if document.get("eligibility_status") == "income_likely_too_high":
            continue
        citation_id = f"citation-{document['id']}"
        citations_by_id[citation_id] = SourceCitation(
            id=citation_id,
            title=document["name"],
            source=document["source"],
            source_url=document.get("source_url"),
            snippet=document["citation_snippet"],
        )

        # Use structured program object if available for better calculation
        program = document.get("_program")
        if program:
            amount = round(program.calculate_amount(gross_cost), 2)
        else:
            amount = round(_calculate_incentive_amount(gross_cost, document), 2)

        matches.append(
            IncentiveMatch(
                id=document["id"],
                name=document["name"],
                source=document["source"],
                incentive_type=document["incentive_type"],
                amount=amount,
                amount_description=document["amount_description"],
                eligible_upgrades=document["eligible_upgrades"],
                eligibility_notes=_eligibility_notes(document),
                stackable=document["stackable"],
                citation_id=citation_id,
                # New structured fields
                cap_category=document.get("cap_category"),
                resets_annually=document.get("resets_annually"),
                tax_liability_required=document.get("tax_liability_required"),
                amount_type=document.get("amount_type"),
                subsidy_basis_reduction=document.get("subsidy_basis_reduction"),
                cap_pool_note=document.get("cap_pool_note"),
                tax_liability_note=document.get("tax_liability_note"),
                exclusive_with=document.get("exclusive_with", []),
            )
        )
    return matches


def _calculate_incentive_amount(gross_cost: float, document: Dict) -> float:
    amount_rule = document.get("amount_rule", {})
    if amount_rule.get("type") == "percentage_cap":
        amount = gross_cost * amount_rule.get("percent", 0)
        cap = amount_rule.get("cap", 0)
        return min(amount, cap) if cap else amount
    if amount_rule.get("type") == "fixed":
        return amount_rule.get("amount", 0)
    return 0


def _select_stackable_incentives(incentives: List[IncentiveMatch]) -> List[IncentiveMatch]:
    # Filter out exclusive conflicts
    selected = list(incentives)
    exclusion_ids = set()
    for incentive in selected:
        exclusion_ids.update(incentive.exclusive_with)

    if exclusion_ids:
        selected = [i for i in selected if i.id not in exclusion_ids]

    stackable = [incentive for incentive in selected if incentive.stackable]
    non_stackable = [incentive for incentive in selected if not incentive.stackable]
    if not non_stackable:
        return stackable
    stackable_total = sum(incentive.amount for incentive in stackable)
    best_non_stackable = max(non_stackable, key=lambda incentive: incentive.amount)
    if best_non_stackable.amount > stackable_total:
        return [best_non_stackable]
    return stackable


def _dedupe_incentives(incentives: List[IncentiveMatch]) -> List[IncentiveMatch]:
    deduped: Dict[Tuple[str, str, str, float, Tuple[str, ...]], IncentiveMatch] = {}
    for incentive in incentives:
        key = (
            incentive.name,
            incentive.source,
            incentive.incentive_type,
            incentive.amount,
            tuple(sorted(incentive.eligible_upgrades)),
        )
        deduped.setdefault(key, incentive)
    return list(deduped.values())


def _eligibility_notes(document: Dict) -> str:
    status = document.get("eligibility_status", "")
    eligibility = document.get("eligibility", "")
    if status == "program_pending":
        return f"{eligibility} This program has not launched yet — amounts shown are estimates based on proposed rules."
    if status == "needs_income_verification":
        return f"{eligibility} Income eligibility cannot be confirmed without location-specific AMI data — verify before claiming."
    if status == "needs_equipment_verification":
        return f"{eligibility} Equipment must be verified to meet the required certification standards before this incentive can be claimed."
    return eligibility


CONFIDENCE_WEIGHTS = {"high": 1.2, "medium": 1.0, "low": 0.8}


def compute_efficiency_lookup(
    options: List[RetrofitOptionCalculation],
) -> Dict[str, Dict[str, float]]:
    cost_efficiencies = [option.annual_savings / max(option.net_cost, 1) for option in options]
    carbon_efficiencies = [option.carbon_avoided_tons / max(option.net_cost, 1) for option in options]

    normalized_cost = _min_max_normalize(cost_efficiencies)
    normalized_carbon = _min_max_normalize(carbon_efficiencies)

    efficiency_lookup: Dict[str, Dict[str, float]] = {}
    for option, norm_cost, norm_carbon in zip(options, normalized_cost, normalized_carbon):
        confidence_weight = CONFIDENCE_WEIGHTS.get(option.confidence, 1.0)
        score = (norm_cost + norm_carbon) / 2 * confidence_weight
        if option.upgrade_key == "solar":
            score += 2
        efficiency_lookup[option.upgrade_key] = {
            "cost_efficiency": norm_cost,
            "carbon_efficiency": norm_carbon,
            "score": score,
        }

    return efficiency_lookup


def _apply_balanced_scores(
    options: List[RetrofitOptionCalculation],
) -> Tuple[List[RetrofitOptionCalculation], Dict[str, Dict[str, float]]]:
    efficiency_lookup = compute_efficiency_lookup(options)
    scored_options = [
        _copy_model(option, {"score": round(efficiency_lookup[option.upgrade_key]["score"], 4)})
        for option in options
    ]
    return scored_options, efficiency_lookup


def _min_max_normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [50.0 for _ in values]
    return [(value - low) / (high - low) * 100 for value in values]


def _assumptions(request: RetrofitCalculationRequest, missing_inputs: List[str]) -> AnalysisAssumptions:
    notes = [
        "Deterministic engine performs all cost, incentive, savings, carbon, payback, and ranking math.",
        "Solar and Retcast data are consumed from the request DTO; no live external API calls are made in this endpoint.",
        "Claude/LLM usage should summarize the returned facts, not recalculate them.",
    ]
    if missing_inputs:
        notes.append(f"Defaults were used for: {', '.join(missing_inputs)}.")
    return AnalysisAssumptions(
        location=request.property.zip_code or "Atlanta, Georgia",
        square_footage=request.property.square_footage or DEFAULT_SQUARE_FOOTAGE,
        home_type=request.property.home_type or DEFAULT_HOME_TYPE,
        utility=request.household.utility or DEFAULT_UTILITY,
        notes=notes,
    )


def _missing_inputs(request: RetrofitCalculationRequest) -> List[str]:
    missing = []
    if request.property.square_footage is None:
        missing.append("square_footage")
    if not request.household.utility:
        missing.append("utility")
    if request.household.electric_rate_per_kwh is None:
        missing.append("electric_rate_per_kwh")
    if request.retcast is None:
        missing.append("retcast")
    if request.solar is None:
        missing.append("solar")
    return missing


def _llm_context(
    request: RetrofitCalculationRequest,
    ranked_options: List[RetrofitOptionCalculation],
    totals: RetrofitCalculationTotals,
    assumptions: AnalysisAssumptions,
    missing_inputs: List[str],
    citations: List[SourceCitation],
) -> LlmContext:
    top_option = ranked_options[0] if ranked_options else None
    homeowner_summary_facts = [
        f"Address: {request.property.address}",
        f"Home type: {assumptions.home_type}; size: {assumptions.square_footage} sq ft; utility: {assumptions.utility}",
        f"Total modeled net cost across options: ${totals.net_cost:,.0f}",
        f"Total modeled annual savings across options: ${totals.annual_savings:,.0f}",
        f"Total modeled carbon avoided: {totals.carbon_avoided_tons:.1f} tons CO2/year",
    ]
    if top_option:
        homeowner_summary_facts.append(
            f"Top ranked option: {top_option.name} with {top_option.payback_years} year payback."
        )

    starting_option = next(
        (option for option in ranked_options if option.recommended_sequence == 1),
        None,
    )
    if starting_option:
        homeowner_summary_facts.append(
            f"Recommended starting point: {starting_option.name} (step 1 of the install sequence)."
        )

    ranked_option_facts = [
        (
            f"#{option.rank} {option.name}: gross ${option.gross_cost:,.0f}, "
            f"incentives ${option.incentive_total:,.0f}, net ${option.net_cost:,.0f}, "
            f"saves ${option.annual_savings:,.0f}/yr, avoids {option.carbon_avoided_tons:.1f} tons CO2/yr. "
            f"Recommended install order: step {option.recommended_sequence}."
        )
        for option in ranked_options
    ]

    return LlmContext(
        homeowner_summary_facts=homeowner_summary_facts,
        ranked_option_facts=ranked_option_facts,
        assumptions=assumptions.notes,
        missing_inputs=missing_inputs,
        citation_snippets=[citation.snippet for citation in citations[:8]],
    )


def _electric_rate(request: RetrofitCalculationRequest) -> float:
    return request.household.electric_rate_per_kwh or DEFAULT_ELECTRIC_RATE


def _gas_rate(request: RetrofitCalculationRequest) -> float:
    return request.household.gas_rate_per_therm or DEFAULT_GAS_RATE


def _grid_carbon(request: RetrofitCalculationRequest) -> float:
    if request.retcast and request.retcast.grid_carbon_kg_per_kwh:
        return request.retcast.grid_carbon_kg_per_kwh
    return DEFAULT_GRID_CARBON_KG_PER_KWH


def _copy_model(model, update: Dict):
    if hasattr(model, "model_copy"):
        return model.model_copy(update=update)
    return model.copy(update=update)


def _dedup_docs(docs: List[Dict]) -> List[Dict]:
    """Return docs with duplicate IDs removed (first occurrence wins)."""
    seen: Dict[str, bool] = {}
    result: List[Dict] = []
    for doc in docs:
        doc_id = doc.get("id")
        if doc_id not in seen:
            seen[doc_id] = True
            result.append(doc)
    return result
