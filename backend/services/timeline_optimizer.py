"""Multi-year retrofit timeline optimizer.

This module is a new, optional pass that runs *after* the deterministic
``calculate_retrofit_options`` pipeline. It takes the already-ranked options plus
the already-fetched incentive documents and searches over a small, DAG- and
budget-constrained space of multi-year schedules, picking the assignment that
maximizes a focus-weighted (cost / carbon / balanced) score.

The defining trait of the temporal layer is None-robustness: incentive documents
are real-world-messy and frequently have missing fields. Every field read goes
through :func:`coalesce` with an appropriate *neutral element* so that an unknown
value never raises and never silently disqualifies an otherwise-eligible program —
instead it is surfaced as a ``data_gap`` and discounts the program's confidence.
"""

import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from schemas import (
    RetrofitCalculationRequest,
    RetrofitOptionCalculation,
    RetrofitTimeline,
    TimelineUpgradeDetail,
    TimelineYear,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEQUENCING_SEED_PATH = DATA_DIR / "sequencing_dependencies_seed.json"

# claim_timing → typical lag in days (used when claim_lag_days is absent)
_TIMING_LAG = {"tax_filing": 120, "within_90_days": 90, "point_of_sale": 0}


# --------------------------------------------------------------------------- #
# Constants and defaults
# --------------------------------------------------------------------------- #
GRID_DECARBONIZATION_RATE = 0.015   # 1.5%/yr grid carbon intensity decline
ENERGY_AUDIT_ADDON_COST = 300.0
PERMIT_ADDON_COST = 150.0
DEFAULT_CONFIDENCE_FLOOR = 0.6
CONFIDENCE_BASE = {"high": 1.0, "medium": 0.85, "low": 0.7}
TEMPORAL_FIELDS = [
    "annual_cap", "resets_annually", "expires_year", "step_down_schedule",
    "claim_timing", "claim_lag_days", "availability_type", "program_status",
    "data_confidence", "subsidy_basis_reduction",
]
FOCUS_WEIGHTS = {
    "cost":     (1.0, 0.0),
    "carbon":   (0.0, 1.0),
    "balanced": (0.5, 0.5),
}


# --------------------------------------------------------------------------- #
# None-robustness primitives
# --------------------------------------------------------------------------- #
def coalesce(value, neutral):
    """Return ``value`` unless it is missing, in which case return ``neutral``.

    The neutral element is chosen by the caller per usage so that an unknown value
    behaves like the identity for that operation:

    * multiplicative eligibility gate -> ``1`` (unknown does not disqualify)
    * upper-bound cap                 -> ``math.inf`` (unknown does not cap)
    * lower-bound floor               -> ``0`` (unknown floor passes everything)
    * amount / percent / step-down    -> ``0`` (missing program contributes nothing)
    * year upper bound (expires)      -> ``9999``; lower bound (available_from) -> ``0``
    * claim lag                       -> ``0`` (treat as immediate)
    """
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return neutral
    return value


def weighted_mean_over_present(terms: List[Tuple[float, float, bool]]) -> float:
    """Weighted mean that normalizes the denominator over present terms only.

    ``terms`` is a list of ``(value, weight, has_data)``. Terms whose ``has_data``
    is False are dropped from both the numerator and the denominator, so a missing
    dimension does not drag the mean toward zero.
    """
    total_weight = sum(w for _, w, present in terms if present)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w, present in terms if present) / total_weight


# --------------------------------------------------------------------------- #
# DAG loading
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_dependency_map() -> Dict[str, Dict]:
    with SEQUENCING_SEED_PATH.open("r", encoding="utf-8") as file:
        entries = json.load(file)
    return {entry["upgrade_key"]: entry for entry in entries}


def find_doc(prog_id: str, incentive_docs: List[Dict]) -> Optional[Dict]:
    for doc in incentive_docs:
        if doc.get("id") == prog_id:
            return doc
    return None


def _hydrate_doc(doc: Dict) -> Dict:
    """Back-fill temporal and structural fields from the attached IncentiveProgram object.

    The structured ``incentive_index`` path (smol/lin-opt) returns docs with
    ``_program`` attached but without the flat temporal fields that this module
    reads (``annual_cap``, ``claim_lag_days``, ``expires_year``, etc.).
    Hydrating once here lets every downstream ``coalesce()`` call find real
    values instead of ``None``.

    The seed/legacy path already has these fields at the top level, so the
    ``if doc.get(field) is None`` guards make this a no-op on that path.
    """
    program = doc.get("_program")
    if program is None:
        return doc

    hydrated = dict(doc)

    # Annual and lifetime caps (on the AmountRule sub-object)
    if hydrated.get("annual_cap") is None:
        hydrated["annual_cap"] = program.amount_rule.annual_cap
    if hydrated.get("lifetime_cap") is None:
        hydrated["lifetime_cap"] = program.amount_rule.lifetime_cap

    # Temporal availability window
    if hydrated.get("expires_year") is None:
        hydrated["expires_year"] = program.expires_year
    if hydrated.get("available_from_year") is None:
        hydrated["available_from_year"] = program.available_from_year

    # Step-down schedule: IncentiveProgram stores List[StepDownEntry]; convert to
    # the {str(year): rate} dict that _raw_amount() expects.
    if hydrated.get("step_down_schedule") is None and program.step_down_schedule:
        hydrated["step_down_schedule"] = {str(e.year): e.rate for e in program.step_down_schedule}

    # Claim timing and derived lag
    if hydrated.get("claim_timing") is None:
        hydrated["claim_timing"] = program.claim_timing
    if hydrated.get("claim_lag_days") is None:
        timing = program.claim_timing or ""
        hydrated["claim_lag_days"] = _TIMING_LAG.get(timing, 0)

    # Program status
    if hydrated.get("program_status") is None:
        hydrated["program_status"] = program.program_status

    # resets_annually, subsidy_basis_reduction, tax_liability_required, cap_category
    # and data_confidence are already included in the structured dict by
    # search_structured_incentives(), so no backfill needed for those.

    return hydrated


# --------------------------------------------------------------------------- #
# Cost and incentive math (per-program, None-robust)
# --------------------------------------------------------------------------- #
def compute_adjusted_cost(option: RetrofitOptionCalculation, incentive_docs: List[Dict]) -> float:
    """Full project cost: gross cost plus any compliance add-ons implied by the programs.

    This is the PV-of-cost term in the NPV. Incentives are added back separately as a
    positive PV term, so this must be the *gross* cost — using ``net_cost`` here (which
    already nets out incentives) would double-count them. Some programs require an
    energy audit or a permit, which add real out-of-pocket cost.
    """
    eligible = [d for d in incentive_docs if option.upgrade_key in d.get("eligible_upgrades", [])]
    addon = 0.0
    if any(coalesce(d.get("energy_audit_required"), False) for d in eligible):
        addon += ENERGY_AUDIT_ADDON_COST
    if any(coalesce(d.get("permit_required"), False) for d in eligible):
        addon += PERMIT_ADDON_COST
    return option.gross_cost + addon


def _upfront_outlay(
    option: RetrofitOptionCalculation,
    incentive_docs: List[Dict],
    calendar_year: int,
    current_year: int,
    tax_liability,
    request: Optional[RetrofitCalculationRequest],
) -> float:
    """Cash the homeowner needs *at install* — full cost minus point-of-sale rebates only.

    Tax credits and tax-filing rebates arrive months later (next April), so they do NOT
    reduce the upfront budget requirement. This is what the per-year budget constraint
    must see, not ``net_cost`` (which optimistically subtracts those deferred incentives).
    """
    entries, _, _ = _program_incentives(
        option.upgrade_key, option.gross_cost, incentive_docs,
        calendar_year, current_year, tax_liability, request,
    )
    pos = sum(e["raw"] for e in entries if e["doc"].get("claim_timing") == "point_of_sale")
    return max(compute_adjusted_cost(option, incentive_docs) - pos, 0.0)


def _gross_raw(doc: Dict, gross_cost: float, calendar_year: int) -> float:
    """Raw program amount on a gross basis, before basis reduction and caps."""
    amount_rule = doc.get("amount_rule") or {}
    step = doc.get("step_down_schedule")
    if step:
        applicable_pct = max(
            (pct for yr_str, pct in step.items() if int(yr_str) <= calendar_year),
            default=coalesce(amount_rule.get("percent"), 0),
        )
    else:
        applicable_pct = coalesce(amount_rule.get("percent"), 0)
    if applicable_pct > 0:
        return applicable_pct * gross_cost
    if amount_rule.get("type") == "fixed":
        return coalesce(amount_rule.get("amount"), 0)
    return 0.0


def _raw_amount(doc: Dict, gross_cost: float, calendar_year: int, incentive_docs: List[Dict], upgrade: str = "") -> float:
    """Pre-cap-sharing raw amount for one program, including basis reduction."""
    amount_rule = doc.get("amount_rule") or {}

    # Step-down percentage: highest scheduled year key <= calendar_year.
    step = doc.get("step_down_schedule")
    if step:
        applicable_pct = max(
            (pct for yr_str, pct in step.items() if int(yr_str) <= calendar_year),
            default=coalesce(amount_rule.get("percent"), 0),
        )
    else:
        applicable_pct = coalesce(amount_rule.get("percent"), 0)
    flat = coalesce(amount_rule.get("amount"), 0) if amount_rule.get("type") == "fixed" else 0

    # Basis reduction: only POS rebates that *also cover this upgrade* may reduce the
    # eligible basis for a percentage credit (e.g. the GA HEAR heat-pump rebate reduces
    # the cost basis for the 25C heat-pump credit, but a HPWH rebate must not).
    basis = gross_cost
    for other_raw in incentive_docs:
        other = _hydrate_doc(other_raw)
        if other is doc or other.get("id") == doc.get("id"):
            continue
        if upgrade and upgrade not in other.get("eligible_upgrades", []):
            continue
        if coalesce(other.get("subsidy_basis_reduction"), False) and other.get("claim_timing") == "point_of_sale":
            basis -= _gross_raw(other, gross_cost, calendar_year)
    basis = max(basis, 0)

    if applicable_pct > 0:
        return applicable_pct * basis
    if flat > 0:
        return flat
    return 0.0


def _apply_individual_caps(doc: Dict, raw: float, tax_liability) -> float:
    """Apply the per-program tax-liability, annual, and lifetime caps."""
    tax_cap = coalesce(tax_liability, math.inf) if doc.get("tax_liability_required") else math.inf

    # annual_cap: prefer the top-level field (set by _hydrate_doc or seed data);
    # fall back to amount_rule["cap"] which the legacy-compatible dict always sets.
    # Guard against amount_rule being explicitly None (None-crash safety).
    top_annual = doc.get("annual_cap")
    rule_cap = (doc.get("amount_rule") or {}).get("cap") or None
    annual_cap = coalesce(top_annual if top_annual is not None else rule_cap, math.inf)

    lifetime_cap = coalesce(doc.get("lifetime_cap"), math.inf)
    # A program that resets annually has, effectively, no binding lifetime cap.
    if coalesce(doc.get("resets_annually"), True):
        lifetime_cap = math.inf
    return min(raw, annual_cap, lifetime_cap, tax_cap)


def _program_confidence(doc: Dict) -> float:
    populated = sum(1 for f in TEMPORAL_FIELDS if doc.get(f) is not None)
    field_completeness = populated / len(TEMPORAL_FIELDS)
    confidence_base = CONFIDENCE_BASE.get(coalesce(doc.get("data_confidence"), "medium"), 0.85)
    availability_discount = 0.8 if coalesce(doc.get("availability_type"), "always_available") == "pool_limited" else 1.0
    return confidence_base * (DEFAULT_CONFIDENCE_FLOOR + (1 - DEFAULT_CONFIDENCE_FLOOR) * field_completeness) * availability_discount


def _field_gaps(doc: Dict) -> List[str]:
    """Names of temporal fields that were None, for UI transparency."""
    name = doc.get("name", doc.get("id", "incentive"))
    return [f"{name}: {field} not specified" for field in TEMPORAL_FIELDS if doc.get(field) is None]


def _eligibility_gate(doc: Dict, gross_cost: float, request: Optional[RetrofitCalculationRequest]) -> Tuple[bool, List[str]]:
    """Eligibility gate that never raises on missing data.

    Returns ``(eligible, gaps)``. A condition we *know* fails disqualifies the
    program; a condition we *cannot evaluate* (because user data is missing) does
    not disqualify it — it is recorded as a data gap instead.
    """
    gaps: List[str] = []
    name = doc.get("name", doc.get("id", "incentive"))
    household = getattr(request, "household", None) if request else None

    # Ownership: only a hard gate when we know the user is not an owner.
    if coalesce(doc.get("ownership_required"), False):
        owner = getattr(household, "owner_occupied", None) if household else None
        if owner is None:
            gaps.append(f"{name}: ownership status unknown")
        elif owner is False:
            return False, gaps

    # Income: gate only when both the program cap and the household income are known.
    income_max = doc.get("income_max")
    if income_max is not None:
        income = getattr(household, "household_income", None) if household else None
        if income is None:
            gaps.append(f"{name}: household income unknown (income-qualified program)")
        elif income > income_max:
            return False, gaps

    # Utility: gate only when both the program utility and the user utility are known.
    doc_utility = doc.get("utility")
    if doc_utility:
        user_utility = getattr(household, "utility", None) if household else None
        if not user_utility:
            gaps.append(f"{name}: utility unknown")
        elif str(user_utility).lower() != str(doc_utility).lower():
            return False, gaps

    # Minimum project cost is a real floor; unknown -> 0 -> always passes.
    if gross_cost < coalesce(doc.get("min_project_cost"), 0):
        return False, gaps

    # Program status: unknown -> "active".
    if coalesce(doc.get("program_status"), "active") != "active":
        return False, gaps

    return True, gaps


def _aggregate_confidence(confidences: List[float], weights: List[float]) -> float:
    if not confidences:
        return 1.0  # no eligible incentive -> nothing to caveat
    terms = [(c, w, True) for c, w in zip(confidences, weights)]
    if sum(w for _, w, _ in terms) == 0:
        return sum(confidences) / len(confidences)
    return weighted_mean_over_present(terms)


def _program_incentives(
    upgrade: str,
    gross_cost: float,
    incentive_docs: List[Dict],
    calendar_year: int,
    current_year: int,
    tax_liability,
    request: Optional[RetrofitCalculationRequest],
) -> Tuple[List[Dict], float, List[str]]:
    """Per-program pre-sharing incentive amounts for one upgrade in one year.

    Returns ``(entries, confidence, data_gaps)`` where each entry is
    ``{"prog_id", "raw", "doc"}``. Cap-category sharing across upgrades in the same
    year is resolved later by :func:`apply_cap_sharing`.
    """
    entries: List[Dict] = []
    data_gaps: List[str] = []
    confidences: List[float] = []
    weights: List[float] = []

    for raw_doc in incentive_docs:
        doc = _hydrate_doc(raw_doc)
        if upgrade not in doc.get("eligible_upgrades", []):
            continue
        data_gaps.extend(_field_gaps(doc))

        eligible, gaps = _eligibility_gate(doc, gross_cost, request)
        data_gaps.extend(gaps)
        if not eligible:
            continue

        # Temporal availability window.
        if not (calendar_year >= coalesce(doc.get("available_from_year"), 0)
                and calendar_year <= coalesce(doc.get("expires_year"), 9999)):
            continue

        raw = _raw_amount(doc, gross_cost, calendar_year, incentive_docs, upgrade)
        raw = _apply_individual_caps(doc, raw, tax_liability)
        prog_id = doc.get("id", doc.get("name", "unknown"))
        entries.append({"prog_id": prog_id, "raw": raw, "doc": doc})
        confidences.append(_program_confidence(doc))
        weights.append(raw)

    confidence = _aggregate_confidence(confidences, weights)
    data_gaps = list(dict.fromkeys(data_gaps))  # de-dupe, preserve order
    return entries, confidence, data_gaps


def compute_incentive_value(
    upgrade: str,
    gross_cost: float,
    incentive_docs: List[Dict],
    year: int,
    current_year: int,
    tax_liability,
    cohort_keys: Optional[List[str]] = None,
    request: Optional[RetrofitCalculationRequest] = None,
) -> Tuple[float, float, List[str]]:
    """Pre-sharing total incentive value for one upgrade scheduled in ``year``.

    ``year`` is the 1-based planning index; the calendar year is
    ``current_year + year - 1``. Cap-category sharing is intentionally *not* applied
    here — it is resolved at the cohort level in :func:`apply_cap_sharing`.
    """
    calendar_year = current_year + year - 1
    entries, confidence, data_gaps = _program_incentives(
        upgrade, gross_cost, incentive_docs, calendar_year, current_year, tax_liability, request
    )
    return sum(e["raw"] for e in entries), confidence, data_gaps


def apply_cap_sharing(year_entries: Dict[str, List[Dict]]) -> Tuple[Dict[str, List[Dict]], List[str]]:
    """Resolve shared annual caps across all upgrades scheduled in the same year.

    ``year_entries`` maps ``upgrade_key -> [program entry, ...]``. Programs that
    share a ``cap_category`` (e.g. the 25C heat-pump-equipment $2,000 cap shared by
    a heat pump and a heat pump water heater) are pooled; if the pool exceeds the
    cap, the cap is allocated proportionally and a staggering note is emitted.

    Returns ``(adjusted, notes)`` where ``adjusted`` maps
    ``upgrade_key -> [{"prog_id", "amount", "doc"}, ...]``.
    """
    by_category: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
    for upgrade_key, entries in year_entries.items():
        for entry in entries:
            cat = entry["doc"].get("cap_category")
            if cat:
                by_category[cat].append((upgrade_key, entry))

    adjusted: Dict[str, List[Dict]] = {uk: [] for uk in year_entries}
    handled = set()  # id() of entries already placed
    notes: List[str] = []

    for cat, items in by_category.items():
        total_raw = sum(entry["raw"] for _, entry in items)
        first_doc = items[0][1]["doc"]
        top_cap = first_doc.get("annual_cap")
        rule_cap = (first_doc.get("amount_rule") or {}).get("cap") or None
        cap = coalesce(top_cap if top_cap is not None else rule_cap, math.inf)
        if total_raw > cap and total_raw > 0:
            scale = cap / total_raw
            for upgrade_key, entry in items:
                adjusted[upgrade_key].append(
                    {"prog_id": entry["prog_id"], "amount": entry["raw"] * scale, "doc": entry["doc"]}
                )
                handled.add(id(entry))
            loss = total_raw - cap
            upgrades_str = ", ".join(sorted(set(uk for uk, _ in items)))
            notes.append(
                f"{upgrades_str} share the ${cap:,.0f} {cat} annual cap; "
                f"${loss:,.0f} in potential credits lost — consider staggering across years"
            )
        else:
            for upgrade_key, entry in items:
                adjusted[upgrade_key].append(
                    {"prog_id": entry["prog_id"], "amount": entry["raw"], "doc": entry["doc"]}
                )
                handled.add(id(entry))

    # Non-categorized programs flow through unchanged.
    for upgrade_key, entries in year_entries.items():
        for entry in entries:
            if id(entry) not in handled:
                adjusted[upgrade_key].append(
                    {"prog_id": entry["prog_id"], "amount": entry["raw"], "doc": entry["doc"]}
                )

    return adjusted, notes


# --------------------------------------------------------------------------- #
# NPV / carbon / scoring
# --------------------------------------------------------------------------- #
def _discount(rate: float, periods: float) -> float:
    return (1 / (1 + rate)) ** periods


def _raw_npv_carbon(
    option: RetrofitOptionCalculation,
    t: int,
    incentive_docs: List[Dict],
    request: RetrofitCalculationRequest,
) -> Tuple[float, float]:
    """NPV and cumulative carbon for one (upgrade, year) pair, ignoring cohort sharing.

    Used only to derive the min-max normalization bounds across the candidate space.
    """
    r = request.discount_rate
    H = request.planning_horizon_years
    Y0 = request.current_year
    tax_liability = getattr(getattr(request, "household", None), "tax_liability_estimate", None)
    calendar_year = Y0 + t - 1

    entries, _, _ = _program_incentives(
        option.upgrade_key, option.gross_cost, incentive_docs, calendar_year, Y0, tax_liability, request
    )
    disc_t = _discount(r, t - 1)
    incentive_pv = sum(
        disc_t * _discount(r, coalesce(e["doc"].get("claim_lag_days"), 0) / 365.0) * e["raw"]
        for e in entries
    )
    savings_pv = option.annual_savings * sum(_discount(r, j) for j in range(t - 1, H))
    cost_pv = disc_t * compute_adjusted_cost(option, incentive_docs)
    npv = savings_pv + incentive_pv - cost_pv

    # Grid decarbonizes ~1.5%/yr, so carbon avoided per operating year declines and
    # installing electric upgrades earlier captures more cumulative avoided carbon.
    carbon = sum(
        option.carbon_avoided_tons * (1 - GRID_DECARBONIZATION_RATE) ** (j - 1)
        for j in range(t - 1, H)
    )
    return npv, carbon


def _evaluate_assignment(
    assignment: Dict[str, Optional[int]],
    options_by_key: Dict[str, RetrofitOptionCalculation],
    incentive_docs: List[Dict],
    request: RetrofitCalculationRequest,
    norm_npv=None,
    norm_carbon=None,
) -> Tuple[float, Dict[str, Dict], Dict[int, List[str]]]:
    """Evaluate a full assignment, applying per-year cap-sharing.

    Returns ``(total_score, per_upgrade_results, cohort_notes_by_year_index)``. This
    is the single source of truth used both by the search (for the scalar score) and
    by :func:`build_timeline` (for the rich per-upgrade / per-year output).
    """
    r = request.discount_rate
    H = request.planning_horizon_years
    Y0 = request.current_year
    tax_liability = getattr(getattr(request, "household", None), "tax_liability_estimate", None)
    w_cost, w_carbon = FOCUS_WEIGHTS.get(request.focus, FOCUS_WEIGHTS["balanced"])

    # Group selected upgrades into per-year cohorts and price each program.
    cohorts: Dict[int, Dict[str, List[Dict]]] = defaultdict(dict)
    meta: Dict[str, Dict] = {}
    for upgrade_key, t in assignment.items():
        if t is None:
            continue
        option = options_by_key[upgrade_key]
        calendar_year = Y0 + t - 1
        entries, confidence, gaps = _program_incentives(
            upgrade_key, option.gross_cost, incentive_docs, calendar_year, Y0, tax_liability, request
        )
        cohorts[t][upgrade_key] = entries
        meta[upgrade_key] = {"confidence": confidence, "data_gaps": gaps}

    results: Dict[str, Dict] = {}
    cohort_notes: Dict[int, List[str]] = defaultdict(list)
    total_score = 0.0

    # Cross-year lifetime-cap ledger: a non-resetting lifetime cap (e.g. WAP's $8,009)
    # must deplete across the whole plan, not reset each year. Process years in order
    # so earlier claims consume the budget before later ones see it.
    lifetime_consumed: Dict[str, float] = defaultdict(float)

    for t in sorted(cohorts):
        year_entries = cohorts[t]
        adjusted, notes = apply_cap_sharing(year_entries)
        cohort_notes[t].extend(notes)

        for upgrade_key in sorted(adjusted):
            ledgered: List[Dict] = []
            for p in adjusted[upgrade_key]:
                doc = p["doc"]
                amount = p["amount"]
                if not coalesce(doc.get("resets_annually"), True):
                    lifetime_cap = coalesce(doc.get("lifetime_cap"), math.inf)
                    if lifetime_cap < math.inf:
                        remaining = max(lifetime_cap - lifetime_consumed[p["prog_id"]], 0.0)
                        amount = min(amount, remaining)
                        lifetime_consumed[p["prog_id"]] += amount
                ledgered.append({**p, "amount": amount})
            adjusted[upgrade_key] = ledgered

        disc_t = _discount(r, t - 1)
        for upgrade_key, progs in adjusted.items():
            option = options_by_key[upgrade_key]
            incentive_total = sum(p["amount"] for p in progs)
            incentive_pv = sum(
                disc_t * _discount(r, coalesce(p["doc"].get("claim_lag_days"), 0) / 365.0) * p["amount"]
                for p in progs
            )
            savings_pv = option.annual_savings * sum(_discount(r, j) for j in range(t - 1, H))
            cost_pv = disc_t * compute_adjusted_cost(option, incentive_docs)
            npv = savings_pv + incentive_pv - cost_pv
            carbon_value = sum(
                option.carbon_avoided_tons * (1 - GRID_DECARBONIZATION_RATE) ** (j - 1)
                for j in range(t - 1, H)
            )

            npv_has_data = option.annual_savings > 0 or incentive_total > 0
            carbon_has_data = option.carbon_avoided_tons > 0
            scored_npv = norm_npv(npv) if norm_npv else npv
            scored_carbon = norm_carbon(carbon_value) if norm_carbon else carbon_value
            score = meta[upgrade_key]["confidence"] * weighted_mean_over_present([
                (scored_npv, w_cost, npv_has_data),
                (scored_carbon, w_carbon, carbon_has_data),
            ])
            total_score += score

            results[upgrade_key] = {
                "t": t,
                "incentive_total": incentive_total,
                "incentive_pv": incentive_pv,
                "confidence": meta[upgrade_key]["confidence"],
                "data_gaps": meta[upgrade_key]["data_gaps"],
                "npv": npv,
                "carbon_value": carbon_value,
                "savings_pv": savings_pv,
                "score": score,
                "progs": progs,
            }

    return total_score, results, cohort_notes


def score_assignment(
    assignment: Dict[str, Optional[int]],
    options,
    incentive_docs: List[Dict],
    request: RetrofitCalculationRequest,
    norm_npv=None,
    norm_carbon=None,
) -> float:
    """Total focus-weighted score for a complete assignment."""
    options_by_key = options if isinstance(options, dict) else {o.upgrade_key: o for o in options}
    total, _, _ = _evaluate_assignment(assignment, options_by_key, incentive_docs, request, norm_npv, norm_carbon)
    return total


# --------------------------------------------------------------------------- #
# Feasible assignment enumeration (DAG + budget pruning)
# --------------------------------------------------------------------------- #
def _topo_order(keys, dependency_map: Dict[str, Dict]) -> List[str]:
    """Order keys so that every dependency precedes its dependents."""
    keyset = set(keys)
    ordered: List[str] = []
    visited = set()

    def visit(key: str):
        if key in visited:
            return
        visited.add(key)
        for dep in dependency_map.get(key, {}).get("depends_on", []):
            if dep in keyset:
                visit(dep)
        ordered.append(key)

    for key in sorted(keys):
        visit(key)
    return ordered


def feasible_assignments(
    upgrade_keys,
    T: int,
    dependency_map: Dict[str, Dict],
    budget_per_year: float,
    options_by_key: Dict[str, RetrofitOptionCalculation],
    upfront_by_key: Dict[str, float],
):
    """Yield only assignments respecting the DAG and per-year budget.

    ``upgrade_keys`` must be in topological order (dependencies first). An upgrade
    may be scheduled no earlier than the latest year of its (in-scope) dependencies,
    and never in the same year if that would push the year's cohort *upfront* cost
    (gross minus point-of-sale rebates) over budget. A dependency that is itself
    skipped makes the dependent unschedulable. Every upgrade may also be skipped.
    """
    def deps_of(upgrade: str) -> List[str]:
        return [d for d in dependency_map.get(upgrade, {}).get("depends_on", []) if d in options_by_key]

    def generate(remaining: List[str], current: Dict[str, Optional[int]]):
        if not remaining:
            yield dict(current)
            return
        upgrade = remaining[0]
        rest = remaining[1:]

        deps = deps_of(upgrade)
        dep_years = [current.get(dep) for dep in deps]
        if any(year is None for year in dep_years):
            # A dependency was skipped: this upgrade cannot be scheduled.
            schedulable_years: range = range(T + 1, T + 1)
        else:
            earliest = max(dep_years) if dep_years else 1
            schedulable_years = range(max(earliest, 1), T + 1)

        for t in schedulable_years:
            cohort_cost = sum(
                upfront_by_key[uk] for uk, yr in current.items() if yr == t
            )
            if cohort_cost + upfront_by_key[upgrade] <= budget_per_year:
                current[upgrade] = t
                yield from generate(rest, current)
                del current[upgrade]

        current[upgrade] = None
        yield from generate(rest, current)
        del current[upgrade]

    yield from generate(list(upgrade_keys), {})


# --------------------------------------------------------------------------- #
# The main entry point
# --------------------------------------------------------------------------- #
def build_timeline(
    request: RetrofitCalculationRequest,
    options: List[RetrofitOptionCalculation],
    incentive_docs: List[Dict],
) -> RetrofitTimeline:
    T = request.planning_horizon_years
    Y0 = request.current_year
    budget = request.budget_per_year if request.budget_per_year is not None else math.inf
    dependency_map = _load_dependency_map()
    options_by_key = {option.upgrade_key: option for option in options}
    upgrade_keys = _topo_order(options_by_key.keys(), dependency_map)
    tax_liability = getattr(getattr(request, "household", None), "tax_liability_estimate", None)

    # Upfront cash needed per upgrade = gross − point-of-sale rebates (tax credits land
    # later, so they don't relax the budget). This is what the budget constraint sees.
    upfront_by_key = {
        uk: _upfront_outlay(options_by_key[uk], incentive_docs, Y0, Y0, tax_liability, request)
        for uk in upgrade_keys
    }

    # Precompute min-max normalization bounds across the entire candidate space.
    all_npvs: List[float] = []
    all_carbons: List[float] = []
    for option in options:
        for t in range(1, T + 1):
            npv, carbon = _raw_npv_carbon(option, t, incentive_docs, request)
            all_npvs.append(npv)
            all_carbons.append(carbon)
    npv_min, npv_max = (min(all_npvs), max(all_npvs)) if all_npvs else (0.0, 1.0)
    carbon_min, carbon_max = (min(all_carbons), max(all_carbons)) if all_carbons else (0.0, 1.0)
    norm_npv = lambda x: (x - npv_min) / (npv_max - npv_min + 1e-9)
    norm_carbon = lambda x: (x - carbon_min) / (carbon_max - carbon_min + 1e-9)

    # Brute-force search over the feasible (DAG- and budget-constrained) space.
    best_score = -math.inf
    best_assignment: Dict[str, Optional[int]] = {uk: None for uk in upgrade_keys}
    for assignment in feasible_assignments(upgrade_keys, T, dependency_map, budget, options_by_key, upfront_by_key):
        total = score_assignment(assignment, options_by_key, incentive_docs, request, norm_npv, norm_carbon)
        if total > best_score:
            best_score = total
            best_assignment = dict(assignment)

    _, results, cohort_notes = _evaluate_assignment(
        best_assignment, options_by_key, incentive_docs, request, norm_npv, norm_carbon
    )
    selected = [uk for uk, t in best_assignment.items() if t is not None]

    # Detect the staggering insight: compare the best schedule's captured incentives
    # against a baseline that crams every selected upgrade into year 1.
    key_insight = _staggering_insight(
        best_assignment, results, options_by_key, incentive_docs, request, selected, norm_npv, norm_carbon
    )

    years = _build_years(best_assignment, results, cohort_notes, options_by_key, selected, Y0, T)
    upgrade_details = _build_details(
        best_assignment, results, options_by_key, incentive_docs, dependency_map, request, budget, Y0, tax_liability, upfront_by_key
    )

    total_npv = round(sum(results[uk]["npv"] for uk in selected), 2)
    total_carbon = round(sum(results[uk]["carbon_value"] for uk in selected), 3)

    return RetrofitTimeline(
        years=years,
        upgrade_details=upgrade_details,
        total_npv=total_npv,
        total_carbon_avoided_tons=total_carbon,
        focus=request.focus,
        planning_horizon_years=T,
        budget_per_year=request.budget_per_year,
        key_insight=key_insight,
    )


def _staggering_insight(
    best_assignment, results, options_by_key, incentive_docs, request, selected, norm_npv, norm_carbon
) -> Optional[str]:
    if not selected:
        return None
    best_incentive = sum(results[uk]["incentive_total"] for uk in selected)

    baseline = {uk: (1 if best_assignment[uk] is not None else None) for uk in best_assignment}
    _, baseline_results, _ = _evaluate_assignment(
        baseline, options_by_key, incentive_docs, request, norm_npv, norm_carbon
    )
    baseline_incentive = sum(baseline_results[uk]["incentive_total"] for uk in selected)

    gain = best_incentive - baseline_incentive
    if gain <= 200:
        return None

    staggered = [uk for uk in selected if best_assignment[uk] != 1]
    highlighted = staggered or selected
    names = ", ".join(options_by_key[uk].name for uk in highlighted)
    return (
        f"Staggering {names} across separate years captures an extra ${gain:,.0f} in incentives "
        f"compared with doing everything in year {request.current_year}."
    )


def _build_years(best_assignment, results, cohort_notes, options_by_key, selected, Y0, T) -> List[TimelineYear]:
    last_year = Y0 + T - 1

    # Incentives are received with a timing lag: tax-filing credits land the year
    # after the work; point-of-sale rebates land the same year.
    captured_by_year: Dict[int, float] = defaultdict(float)
    for uk in selected:
        scheduled_calendar = Y0 + best_assignment[uk] - 1
        for prog in results[uk]["progs"]:
            timing = prog["doc"].get("claim_timing")
            capture_year = scheduled_calendar + (1 if timing == "tax_filing" else 0)
            captured_by_year[min(capture_year, last_year)] += prog["amount"]

    def pos_rebate(uk: str) -> float:
        return sum(p["amount"] for p in results[uk]["progs"] if p["doc"].get("claim_timing") == "point_of_sale")

    years: List[TimelineYear] = []
    for calendar_year in range(Y0, Y0 + T):
        t = calendar_year - Y0 + 1
        cohort = [uk for uk in selected if best_assignment[uk] == t]
        outlay = sum(options_by_key[uk].gross_cost - pos_rebate(uk) for uk in cohort)
        years.append(
            TimelineYear(
                year=calendar_year,
                upgrades=cohort,
                outlay=round(outlay, 2),
                incentives_captured=round(captured_by_year.get(calendar_year, 0.0), 2),
                annual_savings_added=round(sum(options_by_key[uk].annual_savings for uk in cohort), 2),
                cumulative_savings_pv=round(sum(results[uk]["savings_pv"] for uk in cohort), 2),
                cap_sharing_notes=cohort_notes.get(t, []),
            )
        )
    return years


def _build_details(
    best_assignment, results, options_by_key, incentive_docs, dependency_map, request, budget, Y0, tax_liability, upfront_by_key
) -> List[TimelineUpgradeDetail]:
    details: List[TimelineUpgradeDetail] = []
    for uk, option in options_by_key.items():
        t = best_assignment.get(uk)
        if t is not None:
            res = results[uk]
            pos = sum(p["amount"] for p in res["progs"] if p["doc"].get("claim_timing") == "point_of_sale")
            details.append(
                TimelineUpgradeDetail(
                    upgrade_key=uk,
                    scheduled_year=Y0 + t - 1,
                    skipped_reason=None,
                    incentive_value=round(res["incentive_total"], 2),
                    incentive_confidence=round(res["confidence"], 3),
                    upfront_outlay=round(max(option.gross_cost - pos, 0.0), 2),
                    npv=round(res["npv"], 2),
                    carbon_value=round(res["carbon_value"], 3),
                    score=round(res["score"], 4),
                    data_gaps=res["data_gaps"],
                )
            )
        else:
            # Surface data gaps even for skipped upgrades (priced at year 1).
            _, confidence, gaps = _program_incentives(
                uk, option.gross_cost, incentive_docs, Y0, Y0, tax_liability, request
            )
            details.append(
                TimelineUpgradeDetail(
                    upgrade_key=uk,
                    scheduled_year=None,
                    skipped_reason=_skip_reason(uk, best_assignment, options_by_key, dependency_map, budget, upfront_by_key),
                    incentive_value=0.0,
                    incentive_confidence=round(confidence, 3),
                    upfront_outlay=round(upfront_by_key.get(uk, option.gross_cost), 2),
                    npv=0.0,
                    carbon_value=0.0,
                    score=0.0,
                    data_gaps=gaps,
                )
            )
    return details


def _skip_reason(uk, best_assignment, options_by_key, dependency_map, budget, upfront_by_key) -> str:
    deps = [d for d in dependency_map.get(uk, {}).get("depends_on", []) if d in options_by_key]
    if any(best_assignment.get(dep) is None for dep in deps):
        return "dependency_unmet"
    if upfront_by_key.get(uk, options_by_key[uk].gross_cost) > budget:
        return "over_budget"
    return "dominated"
