from typing import Optional


HOMEOWNER_MODE = "homeowner"
BUILDING_MODE = "building"
RENTER_SAFE_MODE = "renter_safe"


BUILDING_REQUESTED_MODES = {
    "building",
    "landlord",
    "enterprise",
    "multifamily",
    "commercial",
    "portfolio",
}
RENTER_REQUESTED_MODES = {"renter", "renter_safe", "tenant"}


def classify_retrofit_mode(answers: dict, requested_mode: Optional[str] = None) -> str:
    requested = _normalize_requested_mode(requested_mode or answers.get("mode"))
    if requested in BUILDING_REQUESTED_MODES:
        return BUILDING_MODE
    if requested in RENTER_REQUESTED_MODES:
        return RENTER_SAFE_MODE
    if requested == HOMEOWNER_MODE:
        return _safe_homeowner_or_redirect(answers)

    meta = answers.get("_property_meta") or {}
    home_type = _normalize_property_type(
        answers.get("home_type") or meta.get("property_type")
    )
    owner_occupied = _owner_occupied(answers.get("home_ownership_status"))

    if home_type in {"apartment", "condo", "multifamily", "commercial", "mixed_use"}:
        return BUILDING_MODE

    if owner_occupied is False:
        return RENTER_SAFE_MODE

    return HOMEOWNER_MODE


def _safe_homeowner_or_redirect(answers: dict) -> str:
    meta = answers.get("_property_meta") or {}
    home_type = _normalize_property_type(
        answers.get("home_type") or meta.get("property_type")
    )
    owner_occupied = _owner_occupied(answers.get("home_ownership_status"))
    if home_type in {"apartment", "condo", "multifamily", "commercial", "mixed_use"}:
        return BUILDING_MODE
    if owner_occupied is False:
        return RENTER_SAFE_MODE
    return HOMEOWNER_MODE


def _normalize_requested_mode(value) -> Optional[str]:
    if not value:
        return None
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_property_type(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "single" in normalized:
        return "single_family"
    if "town" in normalized:
        return "townhouse"
    if "multi" in normalized or "duplex" in normalized or "triplex" in normalized:
        return "multifamily"
    if "apartment" in normalized:
        return "apartment"
    if "condo" in normalized:
        return "condo"
    if "commercial" in normalized or "office" in normalized or "retail" in normalized:
        return "commercial"
    if "mixed" in normalized:
        return "mixed_use"
    return normalized


def _owner_occupied(value) -> Optional[bool]:
    if value is None:
        return None
    normalized = str(value).lower()
    if "own" in normalized or "owner" in normalized:
        return True
    if "rent" in normalized or "lease" in normalized:
        return False
    return None
