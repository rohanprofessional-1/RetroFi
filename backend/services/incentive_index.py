import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.request import Request, urlopen

from services.incentive_program_schema import (
    CapPool,
    IncentiveProgram,
    build_cap_pools,
    load_all_programs,
    load_programs,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEBUG_LOG_PATH = Path("/Users/rohannair/Desktop/Shenanigans/retrofi-atl/.cursor/debug-7b06a5.log")
DEBUG_SESSION_ID = "7b06a5"
DEBUG_LOG_ENDPOINT = "http://127.0.0.1:7596/ingest/3f6d0d4e-1307-4f80-a381-cf3930c45abc"


# region agent log
def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload) + "\n")
    except OSError:
        try:
            request = Request(
                DEBUG_LOG_ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Debug-Session-Id": DEBUG_SESSION_ID,
                },
                method="POST",
            )
            urlopen(request, timeout=2).close()
        except OSError:
            pass
# endregion

UPGRADE_ALIASES = {
    "heat_pump": ["heat pump", "hvac", "heating", "cooling", "air source"],
    "attic_insulation": ["attic insulation", "insulation", "r-49", "envelope"],
    "air_sealing": ["air sealing", "draft", "leak", "weatherization", "envelope"],
    "heat_pump_water_heater": ["heat pump water heater", "water heater", "hot water"],
    "solar": ["solar", "solar pv", "photovoltaic", "clean energy"],
    "battery_storage": ["battery", "battery storage"],
    "electrical_panel": ["electric panel", "electrical panel", "panelboard"],
}

STATE_CODES = {"ca", "fl", "ga", "il", "nc", "ny", "oh", "pa", "tx"}

ZIP_CODE_STATES = {
    "30": "ga",
    "90": "ca",
    "91": "ca",
    "92": "ca",
    "93": "ca",
    "94": "ca",
    "95": "ca",
    "32": "fl",
    "33": "fl",
    "34": "fl",
}


def _load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _get_value(query: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(query, dict):
        return query.get(field_name, default)
    return getattr(query, field_name, default)


def _document_text(document: Dict[str, Any]) -> str:
    values: List[str] = []
    for key in (
        "name",
        "source",
        "incentive_type",
        "eligibility",
        "citation_snippet",
        "description",
        "upgrade_key",
    ):
        value = document.get(key)
        if value:
            values.append(str(value))
    values.extend(document.get("eligible_upgrades", []))
    values.extend(document.get("geographic_scope", []))
    return " ".join(values)


def amount_description(amount_rule: Dict[str, Any]) -> str:
    if amount_rule.get("type") == "percentage_cap":
        percent = int(amount_rule.get("percent", 0) * 100)
        cap = amount_rule.get("cap", 0)
        if not cap:
            return f"{percent}% of eligible costs"
        return f"{percent}% of eligible costs up to ${cap:,.0f}"
    if amount_rule.get("type") == "fixed":
        amount = amount_rule.get("amount", 0)
        return f"Fixed ${amount:,.0f} incentive"
    return "Amount depends on program rules"


class IncentiveIndex:
    def __init__(
        self,
        incentives_path: Optional[Path] = None,
        costs_path: Optional[Path] = None,
        use_vector: bool = True,
    ):
        # Legacy seed data (backward compatibility fallback)
        self.incentives = _load_json(incentives_path or DATA_DIR / "incentives_seed.json")
        self.costs = _load_json(costs_path or DATA_DIR / "install_costs_seed.json")

        # ---- NEW: Structured program data (calculation layer) ----
        self.federal_programs = load_programs(DATA_DIR / "incentive_programs_federal.json")
        self.state_programs: Dict[str, List[IncentiveProgram]] = {}
        for state_code in STATE_CODES:
            state_path = DATA_DIR / f"incentive_programs_{state_code}.json"
            if state_path.exists():
                self.state_programs[state_code] = load_programs(state_path)

        self.cap_pools: Dict[str, CapPool] = {}
        self._rebuild_cap_pools()

        # ---- Citation layer (ChromaDB vector stores) ----
        self.vector_store = None
        self.state_vector_stores = {}
        if use_vector:
            try:
                from services.vector_store import ChromaVectorStore

                vector_store = ChromaVectorStore()
                if vector_store.count() > 0:
                    self.vector_store = vector_store

                for state_code in STATE_CODES:
                    try:
                        state_store = ChromaVectorStore(collection_name=f"retrofi_incentive_sources_{state_code}")
                        if state_store.count() > 0:
                            self.state_vector_stores[state_code] = state_store
                    except Exception:
                        pass
            except Exception as exc:
                # region agent log
                _debug_log(
                    "post-fix",
                    "H6",
                    "backend/services/incentive_index.py:103",
                    "Vector store unavailable; falling back to seed incentives",
                    {"error_type": type(exc).__name__, "error": str(exc)[:500]},
                )
                # endregion
                self.vector_store = None
                self.state_vector_stores = {}

    def _rebuild_cap_pools(self):
        """Build cap pools from all loaded programs."""
        all_programs = list(self.federal_programs)
        for state_programs in self.state_programs.values():
            all_programs.extend(state_programs)
        self.cap_pools = build_cap_pools(all_programs)

    # ----------------------------------------------------------------
    # NEW: Structured program access (calculation layer)
    # ----------------------------------------------------------------

    def get_programs_for_location(self, state_code: Optional[str] = None) -> List[IncentiveProgram]:
        """Return federal + state programs for the user's location."""
        programs = list(self.federal_programs)
        if state_code and state_code in self.state_programs:
            programs.extend(self.state_programs[state_code])
        return programs

    def get_programs_for_upgrade(
        self,
        upgrade_key: str,
        query: Any,
        tax_year: int = 2026,
    ) -> List[IncentiveProgram]:
        """Return programs applicable to an upgrade, filtered by location and eligibility."""
        state_code = _state_code_for_query(query)
        all_programs = self.get_programs_for_location(state_code)
        utility = (_get_value(query, "utility", "") or "").lower()
        household_income = _get_value(query, "household_income")

        matched: List[IncentiveProgram] = []
        for program in all_programs:
            # Must cover this upgrade
            if upgrade_key not in program.eligible_upgrades:
                continue

            # Check expiration
            if program.expires_year is not None and tax_year > program.expires_year:
                continue

            # Check program status
            if program.program_status not in ("active", "pending"):
                continue

            # Utility territory filter
            if program.utility_territory:
                if utility and program.utility_territory.lower() != utility:
                    continue

            # Income check (basic — full AMI check would need geographic data)
            if program.income_max_absolute is not None and household_income is not None:
                if household_income > program.income_max_absolute:
                    continue

            matched.append(program)

        return matched

    def search_structured_incentives(
        self, query: Any, limit: int = 12,
    ) -> List[Dict[str, Any]]:
        """Search incentives using structured program data.

        Returns dicts in the same shape as the legacy search_incentives()
        for backward compatibility with retrofit_calculator.py.
        """
        categories = self.infer_upgrade_categories(query)
        state_code = _state_code_for_query(query)
        all_programs = self.get_programs_for_location(state_code)

        if not all_programs:
            return []

        utility = (_get_value(query, "utility", "") or "").lower()
        household_income = _get_value(query, "household_income")
        tax_liability = _get_value(query, "tax_liability_estimate")

        import datetime as _dt
        current_year = _get_value(query, "current_year", None) or _dt.datetime.now().year

        results: List[Dict[str, Any]] = []
        for program in all_programs:
            upgrade_matches = set(program.eligible_upgrades).intersection(categories)
            if not upgrade_matches:
                continue

            if program.program_status not in ("active", "pending"):
                continue

            # Hard expiration filter — never surface expired programs.
            if program.expires_year is not None and current_year > program.expires_year:
                continue

            # Hard availability filter — skip if not yet available.
            if program.available_from_year is not None and current_year < program.available_from_year:
                continue

            # Drop programs with no computable amount — they'd show as $0 and mislead.
            ar = program.amount_rule
            if ar.amount_flat is None and ar.amount_percent is None and ar.per_unit_rate is None:
                continue

            # Utility territory filter
            if program.utility_territory:
                if utility and program.utility_territory.lower() != utility:
                    continue
                elif not utility:
                    pass  # Include but flag as needs verification

            # Income eligibility
            eligibility_status = "likely_eligible"
            if program.income_max_absolute is not None:
                if household_income is None:
                    eligibility_status = "needs_income_verification"
                elif household_income > program.income_max_absolute:
                    continue  # Definitively ineligible on the flat threshold
                # If income passes the flat threshold but an AMI tier is also set,
                # we still can't confirm eligibility without location-specific AMI
                # data — surface a verification note so users don't assume they qualify.
                if program.income_tier and program.income_tier != "any":
                    eligibility_status = "needs_income_verification"
            elif program.income_tier and program.income_tier != "any":
                # No flat cap at all — can't verify without location-specific AMI.
                eligibility_status = "needs_income_verification"

            # Pending programs exist in the data but aren't claimable today.
            if program.program_status == "pending":
                eligibility_status = "program_pending"

            # Equipment certification caveat — we can't verify at quote time.
            elif program.equipment_certification:
                eligibility_status = "needs_equipment_verification"

            # Tax liability warning
            tax_liability_note = None
            if program.tax_liability_required and tax_liability is not None:
                cap = program.amount_rule.annual_cap
                if cap and tax_liability < cap:
                    tax_liability_note = (
                        f"Your estimated tax liability of ${tax_liability:,.0f} may limit "
                        f"this ${cap:,.0f} credit"
                    )

            # Cap pool note
            cap_pool_note = None
            if program.cap_category and program.cap_category in self.cap_pools:
                pool = self.cap_pools[program.cap_category]
                if len(pool.program_ids) > 1:
                    other_names = [
                        p.name for p in all_programs
                        if p.program_id in pool.program_ids and p.program_id != program.program_id
                    ]
                    if other_names and pool.annual_cap:
                        cap_pool_note = (
                            f"Shares ${pool.annual_cap:,.0f} {'annual' if pool.resets_annually else 'lifetime'} "
                            f"cap with {', '.join(other_names)}"
                        )

            # Build legacy-compatible dict
            amount_rule_dict = _program_to_amount_rule(program)

            results.append({
                "id": program.program_id,
                "name": program.name,
                "source": program.source_program_id or program.geographic_scope,
                "source_url": program.source_url,
                "incentive_type": _program_incentive_type(program),
                "eligible_upgrades": program.eligible_upgrades,
                "geographic_scope": _program_geographic_scope(program),
                "utility": program.utility_territory,
                "amount_rule": amount_rule_dict,
                "stackable": program.stackable,
                "eligibility": _program_eligibility_text(program),
                "citation_snippet": f"{program.name} — {_program_incentive_type(program)}",
                "score": 10 * len(upgrade_matches),
                "matched_upgrade_keys": sorted(upgrade_matches),
                "eligibility_status": eligibility_status,
                "amount_description": amount_description(amount_rule_dict),
                # New structured fields
                "cap_category": program.cap_category,
                "resets_annually": program.resets_annually,
                "tax_liability_required": program.tax_liability_required,
                "amount_type": program.amount_rule.amount_type,
                "subsidy_basis_reduction": program.subsidy_basis_reduction,
                "cap_pool_note": cap_pool_note,
                "tax_liability_note": tax_liability_note,
                "exclusive_with": program.exclusive_with,
                "data_confidence": program.data_confidence,
                "_program": program,  # Attach full program for calculator access
            })

        results.sort(key=lambda d: d["score"], reverse=True)
        return results[:limit]

    def infer_upgrade_categories(self, query: Any) -> List[str]:
        interests = _get_value(query, "upgrade_interests", []) or []
        if not interests:
            return [cost["upgrade_key"] for cost in self.costs]

        categories: List[str] = []
        for interest in interests:
            normalized_interest = interest.lower()
            exact_matches = [
                category
                for category, aliases in UPGRADE_ALIASES.items()
                if category == normalized_interest or normalized_interest in aliases
            ]
            if exact_matches:
                categories.extend(exact_matches)
                continue
            for category, aliases in UPGRADE_ALIASES.items():
                if any(alias in normalized_interest for alias in aliases):
                    categories.append(category)

        return list(dict.fromkeys(categories)) or [cost["upgrade_key"] for cost in self.costs]

    def search_incentives(self, query: Any, limit: int = 12) -> List[Dict[str, Any]]:
        # Prefer structured program data when available
        structured = self.search_structured_incentives(query, limit)
        if structured:
            return structured

        # Fall back to vector search, then legacy seed data
        if self.vector_store or self.state_vector_stores:
            matches = self._search_vector_incentives(query, limit)
            if matches:
                return matches

        categories = self.infer_upgrade_categories(query)
        scored = [
            self._with_incentive_score(document, query, categories)
            for document in self.incentives
        ]
        matches = [document for document in scored if document["score"] > 0]
        return sorted(matches, key=lambda document: document["score"], reverse=True)[:limit]

    def search_costs(self, query: Any) -> List[Dict[str, Any]]:
        categories = self.infer_upgrade_categories(query)
        return [
            {**document, "score": self._cost_score(document, query, categories)}
            for document in self.costs
            if document["upgrade_key"] in categories
        ]

    def _with_incentive_score(
        self,
        document: Dict[str, Any],
        query: Any,
        categories: Iterable[str],
    ) -> Dict[str, Any]:
        score = 0
        eligible_upgrades = set(document.get("eligible_upgrades", []))
        category_matches = eligible_upgrades.intersection(categories)
        score += 10 * len(category_matches)

        address = (_get_value(query, "address", "") or "").lower()
        zip_code = (_get_value(query, "zip_code", "") or "").lower()
        utility = (_get_value(query, "utility", "") or "").lower()
        household_income = _get_value(query, "household_income")
        scopes = set(document.get("geographic_scope", []))

        if "federal" in scopes:
            score += 2
        if "georgia" in scopes and ("ga" in address or "georgia" in address or zip_code.startswith("30")):
            score += 3
        if "atlanta" in scopes and ("atlanta" in address or zip_code.startswith("303")):
            score += 3

        document_utility = (document.get("utility") or "").lower()
        if document_utility and utility and document_utility == utility:
            score += 4
        elif document_utility:
            score -= 1

        income_max = document.get("income_max")
        eligibility_status = "likely_eligible"
        if income_max is not None:
            if household_income is None:
                eligibility_status = "needs_income_verification"
                score += 1
            elif household_income <= income_max:
                score += 3
            else:
                eligibility_status = "income_likely_too_high"
                score -= 100

        query_tokens = _tokenize(
            " ".join(
                str(value or "")
                for value in (
                    _get_value(query, "address", ""),
                    _get_value(query, "home_type", ""),
                    _get_value(query, "utility", ""),
                    " ".join(_get_value(query, "upgrade_interests", []) or []),
                )
            )
        )
        score += len(query_tokens.intersection(_tokenize(_document_text(document))))

        return {
            **document,
            "score": score,
            "matched_upgrade_keys": sorted(category_matches),
            "eligibility_status": eligibility_status,
            "amount_description": amount_description(document.get("amount_rule", {})),
        }

    def _cost_score(
        self,
        document: Dict[str, Any],
        query: Any,
        categories: Iterable[str],
    ) -> int:
        score = 10 if document["upgrade_key"] in categories else 0
        query_tokens = _tokenize(" ".join(_get_value(query, "upgrade_interests", []) or []))
        score += len(query_tokens.intersection(_tokenize(_document_text(document))))
        return score

    def _search_vector_incentives(self, query: Any, limit: int) -> List[Dict[str, Any]]:
        categories = self.infer_upgrade_categories(query)
        query_text = " ".join(
            str(value or "")
            for value in (
                _get_value(query, "address", ""),
                _get_value(query, "home_type", ""),
                _get_value(query, "utility", ""),
                " ".join(_get_value(query, "upgrade_interests", []) or categories),
            )
        )
        jurisdiction = _jurisdiction_for_query(query)
        utility = _get_value(query, "utility")

        vector_matches: List[Dict[str, Any]] = []

        if self.vector_store:
            vector_matches.extend(
                self.vector_store.query(
                    query_text=query_text,
                    limit=limit,
                    measures=categories,
                    jurisdiction=jurisdiction,
                    utility=utility,
                )
            )

        state_code = _state_code_for_query(query)
        if state_code and state_code in self.state_vector_stores:
            state_matches = self.state_vector_stores[state_code].query(
                query_text=query_text,
                limit=limit,
                measures=categories,
                jurisdiction=None,
                utility=utility,
            )
            vector_matches.extend(state_matches)

        seen_ids = set()
        unique_matches = []
        for match in vector_matches:
            match_id = match.get("id")
            if match_id not in seen_ids:
                seen_ids.add(match_id)
                unique_matches.append(match)

        return [
            self._vector_match_to_incentive(match, query)
            for match in unique_matches[:limit]
        ]

    def _vector_match_to_incentive(self, match: Dict[str, Any], query: Any) -> Dict[str, Any]:
        amount_rule = _amount_rule_from_vector_match(match)
        measure = match.get("measure", "")
        eligibility_status = "likely_eligible"
        if match.get("income_rules") and _get_value(query, "household_income") is None:
            eligibility_status = "needs_income_verification"

        return {
            "id": match["id"],
            "name": match.get("program_name") or match["id"],
            "source": match.get("admin") or match.get("source_type", "Source document"),
            "source_url": match.get("source_url"),
            "incentive_type": _incentive_type(match),
            "eligible_upgrades": [measure] if measure else [],
            "geographic_scope": _geographic_scope(match.get("jurisdiction", "")),
            "utility": match.get("utility_territory") or None,
            "amount_rule": amount_rule,
            "stackable": _is_stackable(match),
            "eligibility": _join_notes(
                match.get("equipment_requirements", ""),
                match.get("eligibility_rules", ""),
                match.get("income_rules", ""),
                match.get("contractor_rules", ""),
                match.get("application_deadline", ""),
                match.get("stacking_notes", ""),
            ),
            "citation_snippet": _snippet(match.get("raw_text_chunk", "")),
            "score": match.get("score", 0),
            "matched_upgrade_keys": [measure] if measure else [],
            "eligibility_status": eligibility_status,
            "amount_description": amount_description(amount_rule),
            "equipment_requirements": match.get("equipment_requirements", ""),
            "stacking_notes": match.get("stacking_notes", ""),
            "application_deadline": match.get("application_deadline", ""),
            "parse_confidence": match.get("parse_confidence", ""),
        }


@lru_cache(maxsize=1)
def get_default_index() -> IncentiveIndex:
    return IncentiveIndex()


def _amount_rule_from_vector_match(match: Dict[str, Any]) -> Dict[str, Any]:
    rebate_amount = float(match.get("rebate_amount") or 0)
    rebate_percent = float(match.get("rebate_percent") or 0)
    max_cap = float(match.get("max_cap") or 0)
    if rebate_amount > 0:
        return {"type": "fixed", "amount": rebate_amount}
    if rebate_percent > 0:
        return {"type": "percentage_cap", "percent": rebate_percent, "cap": max_cap}
    return {"type": "source_defined", "amount": 0}


def _state_code_for_query(query: Any) -> Optional[str]:
    address = (_get_value(query, "address", "") or "").lower()
    zip_code = (_get_value(query, "zip_code", "") or "").lower()

    if zip_code:
        prefix = zip_code[:2]
        if prefix in ZIP_CODE_STATES:
            return ZIP_CODE_STATES[prefix]

    for state_code in STATE_CODES:
        if f" {state_code}" in address or f"{state_code}," in address:
            return state_code

    return None


def _jurisdiction_for_query(query: Any) -> str:
    address = (_get_value(query, "address", "") or "").lower()
    zip_code = (_get_value(query, "zip_code", "") or "").lower()
    if "atlanta" in address or "georgia" in address or " ga" in address or zip_code.startswith("30"):
        return "Georgia"
    return "US"


def _geographic_scope(jurisdiction: str) -> List[str]:
    lower = jurisdiction.lower()
    scopes = ["federal"] if lower in {"us", "federal"} else []
    if "georgia" in lower:
        scopes.extend(["georgia", "atlanta"])
    return scopes or [jurisdiction]


def _incentive_type(match: Dict[str, Any]) -> str:
    source_type = match.get("source_type", "")
    if source_type.startswith("irs"):
        return "Tax Credit"
    if "utility" in source_type:
        return "Utility Rebate"
    if "state" in source_type:
        return "State Rebate"
    return "Incentive"


def _is_stackable(match: Dict[str, Any]) -> bool:
    notes = (match.get("stacking_notes") or "").lower()
    return "not stack" not in notes and "cannot be combined" not in notes


def _join_notes(*values: str) -> str:
    return " ".join(value for value in values if value).strip() or "Eligibility rules are described in the cited source chunk."


def _snippet(raw_text: str, length: int = 360) -> str:
    text = re.sub(r"\s+", " ", raw_text).strip()
    return text[:length]


# ---------------------------------------------------------------------------
# IncentiveProgram → legacy dict converters
# ---------------------------------------------------------------------------

def _program_to_amount_rule(program: IncentiveProgram) -> Dict[str, Any]:
    """Convert an IncentiveProgram's AmountRule to the legacy amount_rule dict."""
    rule = program.amount_rule
    if rule.amount_flat is not None:
        return {"type": "fixed", "amount": rule.amount_flat}
    if rule.amount_percent is not None:
        return {
            "type": "percentage_cap",
            "percent": rule.amount_percent,
            "cap": rule.annual_cap or 0,
        }
    return {"type": "source_defined", "amount": 0}


def _program_incentive_type(program: IncentiveProgram) -> str:
    """Map amount_type to user-facing incentive type label."""
    mapping = {
        "tax_credit": "Tax Credit",
        "rebate": "Rebate",
        "grant": "Grant",
        "loan": "Loan",
        "rate_discount": "Rate Discount",
    }
    return mapping.get(program.amount_rule.amount_type, "Incentive")


def _program_geographic_scope(program: IncentiveProgram) -> List[str]:
    """Build legacy geographic_scope list from program fields."""
    scopes = []
    if program.geographic_scope == "federal":
        scopes.append("federal")
    if program.state:
        scopes.append(program.state)
    if program.geographic_scope in ("state", "utility", "local"):
        scopes.append(program.geographic_scope)
    return scopes or ["federal"]


def _program_eligibility_text(program: IncentiveProgram) -> str:
    """Generate eligibility text from structured program fields."""
    parts = []
    if program.ownership_required:
        parts.append("Owner-occupied homes only")
    if program.primary_residence_required:
        parts.append("Primary residence required")
    if program.income_tier and program.income_tier != "any":
        tier_label = program.income_tier.replace("_", " ")
        if program.income_max_absolute:
            parts.append(f"Income-qualified ({tier_label}, up to ${program.income_max_absolute:,.0f} — exact limit depends on location and household size)")
        else:
            parts.append(f"Income-qualified ({tier_label} — exact threshold depends on location and household size, verification required)")
    if program.tax_liability_required:
        parts.append("Requires sufficient federal tax liability to claim")
    if program.equipment_certification:
        parts.append(f"Equipment must meet certification requirements: {program.equipment_certification}")
    if program.contractor_required is True:
        parts.append("Must use a program-approved or licensed contractor")
    elif program.contractor_required is False:
        parts.append("DIY-eligible")
    if program.energy_audit_required:
        parts.append("Energy audit required before work begins")
    return " ".join(parts + []) if not parts else ". ".join(parts) + "."
