from typing import Dict, List, Optional, Tuple

from schemas import (
    AnalysisAssumptions,
    IncentiveAnalysisRequest,
    IncentiveAnalysisResponse,
    IncentiveMatch,
    SourceCitation,
    UpgradeAnalysis,
)
from services.incentive_index import IncentiveIndex, get_default_index


DEFAULT_SQUARE_FOOTAGE = 1800
DEFAULT_HOME_TYPE = "single family"
DEFAULT_UTILITY = "Georgia Power"


def analyze_retrofit_incentives(
    request: IncentiveAnalysisRequest,
    index: Optional[IncentiveIndex] = None,
) -> IncentiveAnalysisResponse:
    incentive_index = index or get_default_index()
    costs = incentive_index.search_costs(request)
    incentives = incentive_index.search_incentives(request)
    square_footage = request.square_footage or DEFAULT_SQUARE_FOOTAGE

    citations_by_id: Dict[str, SourceCitation] = {}
    upgrade_rows: List[Tuple[float, UpgradeAnalysis]] = []

    for cost_document in costs:
        upgrade_key = cost_document["upgrade_key"]
        gross_cost = _scaled_cost(cost_document, square_footage)
        annual_savings = _scaled_savings(cost_document, square_footage)
        matched_incentives = _matched_incentives_for_upgrade(
            upgrade_key,
            gross_cost,
            incentives,
            citations_by_id,
        )
        selected_incentives = _select_stackable_incentives(matched_incentives)
        incentive_total = sum(incentive.amount for incentive in selected_incentives)
        net_cost = max(gross_cost - incentive_total, 0)
        payback_years = round(net_cost / annual_savings, 1) if annual_savings else None

        cost_citation_id = f"citation-{cost_document['id']}"
        citations_by_id[cost_citation_id] = SourceCitation(
            id=cost_citation_id,
            title=cost_document["name"],
            source=cost_document["source"],
            source_url=cost_document.get("source_url"),
            snippet=cost_document["citation_snippet"],
        )

        score = _rank_score(
            net_cost=net_cost,
            annual_savings=annual_savings,
            carbon_avoided=cost_document["carbon_avoided_tons"],
            confidence=cost_document["confidence"],
        )
        upgrade_rows.append(
            (
                score,
                UpgradeAnalysis(
                    upgrade_key=upgrade_key,
                    name=cost_document["name"],
                    description=cost_document["description"],
                    rank=0,
                    gross_cost=round(gross_cost, 2),
                    net_cost=round(net_cost, 2),
                    annual_savings=round(annual_savings, 2),
                    carbon_avoided_tons=cost_document["carbon_avoided_tons"],
                    payback_years=payback_years,
                    confidence=cost_document["confidence"],
                    matched_incentives=selected_incentives,
                    citations=[cost_citation_id]
                    + [incentive.citation_id for incentive in selected_incentives],
                ),
            )
        )

    ranked_upgrades = [
        _copy_model(upgrade, {"rank": rank})
        for rank, (_, upgrade) in enumerate(
            sorted(upgrade_rows, key=lambda row: row[0], reverse=True),
            start=1,
        )
    ]

    eligible_incentives = _dedupe_incentives(
        incentive
        for upgrade in ranked_upgrades
        for incentive in upgrade.matched_incentives
    )

    assumptions = AnalysisAssumptions(
        location=_location_label(request),
        square_footage=square_footage,
        home_type=request.home_type or DEFAULT_HOME_TYPE,
        utility=request.utility or DEFAULT_UTILITY,
        notes=[
            "MVP analysis uses curated seed data and deterministic calculations.",
            "Missing property details are filled with Atlanta defaults until the questionnaire and property data APIs exist.",
            "Income-qualified programs are flagged from user-provided income only when available.",
        ],
    )

    return IncentiveAnalysisResponse(
        address=request.address,
        summary=_summary_for(ranked_upgrades),
        ranked_upgrades=ranked_upgrades,
        eligible_incentives=eligible_incentives,
        assumptions=assumptions,
        citations=list(citations_by_id.values()),
    )


def _scaled_cost(cost_document: Dict, square_footage: int) -> float:
    midpoint = (cost_document["cost_low"] + cost_document["cost_high"]) / 2
    scale = square_footage / DEFAULT_SQUARE_FOOTAGE
    if cost_document["upgrade_key"] in {"attic_insulation", "air_sealing"}:
        return midpoint * min(max(scale, 0.75), 1.5)
    return midpoint * min(max(scale, 0.85), 1.25)


def _scaled_savings(cost_document: Dict, square_footage: int) -> float:
    scale = square_footage / DEFAULT_SQUARE_FOOTAGE
    return cost_document["annual_savings"] * min(max(scale, 0.8), 1.35)


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
        if document.get("eligibility_status") in {
            "income_likely_too_high",
            "renter_needs_owner_approval",
        }:
            continue

        citation_id = f"citation-{document['id']}"
        citations_by_id[citation_id] = SourceCitation(
            id=citation_id,
            title=document["name"],
            source=document["source"],
            source_url=document.get("source_url"),
            snippet=document["citation_snippet"],
        )
        matches.append(
            IncentiveMatch(
                id=document["id"],
                name=document["name"],
                source=document["source"],
                incentive_type=document["incentive_type"],
                amount=round(_calculate_incentive_amount(gross_cost, document), 2),
                amount_description=document["amount_description"],
                eligible_upgrades=document["eligible_upgrades"],
                eligibility_notes=_eligibility_notes(document),
                stackable=document["stackable"],
                citation_id=citation_id,
            )
        )
    return matches


def _calculate_incentive_amount(gross_cost: float, document: Dict) -> float:
    amount_rule = document.get("amount_rule", {})
    if amount_rule.get("type") == "percentage_cap":
        calculated_amount = gross_cost * amount_rule.get("percent", 0)
        cap = amount_rule.get("cap", 0)
        return min(calculated_amount, cap) if cap else calculated_amount
    if amount_rule.get("type") == "fixed":
        return amount_rule.get("amount", 0)
    return 0


def _select_stackable_incentives(incentives: List[IncentiveMatch]) -> List[IncentiveMatch]:
    stackable = [incentive for incentive in incentives if incentive.stackable]
    non_stackable = [incentive for incentive in incentives if not incentive.stackable]
    if not non_stackable:
        return stackable

    stackable_total = sum(incentive.amount for incentive in stackable)
    best_non_stackable = max(non_stackable, key=lambda incentive: incentive.amount)
    if best_non_stackable.amount > stackable_total:
        return [best_non_stackable]
    return stackable


def _eligibility_notes(document: Dict) -> str:
    status = document.get("eligibility_status")
    if status == "needs_income_verification":
        return f"{document['eligibility']} Income was not provided, so eligibility needs verification."
    if status == "renter_needs_owner_approval":
        return f"{document['eligibility']} Renter eligibility needs owner approval, so this incentive is not counted in net cost."
    return document["eligibility"]


def _rank_score(
    net_cost: float,
    annual_savings: float,
    carbon_avoided: float,
    confidence: str,
) -> float:
    payback_component = annual_savings / max(net_cost, 1)
    confidence_weight = {"high": 1.2, "medium": 1.0, "low": 0.8}.get(confidence, 1.0)
    return (payback_component * 1000 + annual_savings / 100 + carbon_avoided * 2) * confidence_weight


def _dedupe_incentives(incentives) -> List[IncentiveMatch]:
    deduped: Dict[str, IncentiveMatch] = {}
    for incentive in incentives:
        existing = deduped.get(incentive.id)
        if existing is None or incentive.amount > existing.amount:
            deduped[incentive.id] = incentive
    return list(deduped.values())


def _copy_model(model, update: Dict):
    if hasattr(model, "model_copy"):
        return model.model_copy(update=update)
    return model.copy(update=update)


def _location_label(request: IncentiveAnalysisRequest) -> str:
    if request.zip_code:
        return f"Atlanta area ZIP {request.zip_code}"
    return "Atlanta, Georgia"


def _summary_for(ranked_upgrades: List[UpgradeAnalysis]) -> str:
    if not ranked_upgrades:
        return "No matching upgrade recommendations were found in the local MVP index."

    best = ranked_upgrades[0]
    total_savings = sum(upgrade.annual_savings for upgrade in ranked_upgrades)
    return (
        f"The strongest first move is {best.name}, with an estimated "
        f"{best.payback_years} year payback after currently modeled incentives. "
        f"Across the matched upgrade set, estimated annual savings are ${total_savings:,.0f}."
    )
