import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

UPGRADE_ALIASES = {
    "heat_pump": ["heat pump", "hvac", "heating", "cooling", "air source"],
    "attic_insulation": ["attic insulation", "insulation", "r-49", "envelope"],
    "air_sealing": ["air sealing", "draft", "leak", "weatherization", "envelope"],
    "heat_pump_water_heater": ["heat pump water heater", "water heater", "hot water"],
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
        self.incentives = _load_json(incentives_path or DATA_DIR / "incentives_seed.json")
        self.costs = _load_json(costs_path or DATA_DIR / "install_costs_seed.json")
        self.vector_store = None
        if use_vector:
            try:
                from services.vector_store import ChromaVectorStore

                vector_store = ChromaVectorStore()
                if vector_store.count() > 0:
                    self.vector_store = vector_store
            except RuntimeError:
                self.vector_store = None

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
        if self.vector_store:
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
        vector_matches = self.vector_store.query(
            query_text=query_text,
            limit=limit,
            measures=categories,
            jurisdiction=jurisdiction,
            utility=utility,
        )
        return [
            self._vector_match_to_incentive(match, query)
            for match in vector_matches
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
