import os
import httpx
from typing import Optional

RENTCAST_API_KEY = os.getenv("RENTCAST_API_KEY", "")
RENTCAST_BASE_URL = "https://api.rentcast.io/v1"


def fetch_property_data(address: str) -> dict:
    """
    Fetches property record data from the RentCast API for a given address.

    Returns a normalized dict of fields that are directly useful for the
    RetroFit recommendation engine and for pre-filling the LLM questionnaire
    so we don't ask the user for data we already have.

    Fields mapped back to questionnaire priorities:
      Priority 1 (Essential):
        - owner_occupied  → proxy for home ownership status
      Priority 2 (High-Value):
        - property_type   → home type (single family, condo, townhouse…)
        - year_built      → insulation / air-sealing needs for pre-1980 homes
        - heating_type    → primary heating fuel / system
      Priority 3 (Nice to Have):
        - square_footage  → heat pump sizing
        - bedrooms        → occupancy estimate
        - bathrooms       → occupancy / hot water heater sizing

    Additional fields useful for Solar API / general recommendations:
        - latitude / longitude  → passed directly to Google Solar API
        - roof_type             → affects solar panel suitability
        - cooling_type          → existing cooling system
        - floor_count           → affects heat pump load calc
        - lot_size              → ground-source heat pump feasibility
    """
    if not RENTCAST_API_KEY:
        raise ValueError(
            "RENTCAST_API_KEY environment variable is not set. "
            "Set it before calling fetch_property_data()."
        )

    url = f"{RENTCAST_BASE_URL}/properties"
    headers = {
        "Accept": "application/json",
        "X-Api-Key": RENTCAST_API_KEY,
    }
    params = {"address": address}

    response = httpx.get(url, headers=headers, params=params, timeout=10.0)
    response.raise_for_status()

    records = response.json()

    # The endpoint returns a list; take the first (most relevant) match.
    if not records:
        raise ValueError(f"No property record found for address: {address!r}")

    record = records[0] if isinstance(records, list) else records
    features: dict = record.get("features") or {}

    return _normalize(record, features)


def _normalize(record: dict, features: dict) -> dict:
    """Extracts and renames only the fields needed by the RetroFit system."""
    return {
        # ── Identity ──────────────────────────────────────────────────────────
        "rentcast_id": record.get("id"),
        "formatted_address": record.get("formattedAddress"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "county": record.get("county"),
        "zip_code": record.get("zipCode"),
        "state": record.get("state"),

        # ── Priority 1 — Essential ────────────────────────────────────────────
        # ownerOccupied is a boolean on the top-level record.
        # True  → individual owner lives here (eligible for most incentives)
        # False → investor/rental property (different incentive set)
        "owner_occupied": record.get("ownerOccupied"),
        # Existing cooling determines whether a heat-pump upgrade is a net-new
        # install or a replacement — directly affects cost and savings calc.
        "has_cooling": features.get("cooling"),
        "cooling_type": features.get("coolingType"),

        # ── Priority 2 — High-Value ───────────────────────────────────────────
        # e.g. "Single Family", "Condo", "Townhouse", "Multi Family"
        "property_type": record.get("propertyType"),
        # Pre-1980 homes almost always need insulation/air-sealing first.
        "year_built": record.get("yearBuilt"),
        # e.g. "Forced Air", "Baseboard", "Heat Pump", "Radiant", "None"
        # Used to infer primary heating fuel and identify upgrade paths.
        "heating_type": features.get("heatingType"),
        "has_heating": features.get("heating"),

        # ── Priority 3 — Nice to Have ─────────────────────────────────────────
        "square_footage": record.get("squareFootage"),
        "bedrooms": record.get("bedrooms"),
        "bathrooms": record.get("bathrooms"),

        # ── Solar / General Recommendations ──────────────────────────────────
        # roof_type affects panel mounting and suitability estimates.
        "roof_type": features.get("roofType"),
        # Floor count and lot size feed into load calculations for heat pumps
        # and ground-source feasibility respectively.
        "floor_count": features.get("floorCount"),
        "lot_size": record.get("lotSize"),
    }


def get_pre_filled_answers(address: str) -> dict:
    """
    Convenience wrapper used by the LLM questionnaire loop.

    Returns a dict whose keys match the questionnaire field names so the agent
    can skip questions for data we already have from RentCast, and only ask
    the user for fields that are None.
    """
    data = fetch_property_data(address)

    return {
        # Questionnaire field name → RentCast value (None if unavailable)

        # ── Priority 1 — Essential ────────────────────────────────────────────
        # RentCast cannot source utility bills — always ask.
        "monthly_electricity_bill": None,
        "monthly_gas_bill": None,
        # RentCast ownerOccupied covers this question fully.
        "home_ownership_status": (
            "owner" if data.get("owner_occupied") is True
            else "renter" if data.get("owner_occupied") is False
            else None
        ),
        # Heating fuel is inferred from heatingType, but water heating and
        # cooking fuel cannot be determined from RentCast — always ask.
        "appliances_fuel": None,
        # RentCast roofType covers this fully — skip the question if present.
        "roof_type": data.get("roof_type"),
        # Cooling presence and type are Essential — directly determines whether a
        # heat-pump upgrade is net-new or a replacement, affecting cost and savings.
        "has_cooling": data.get("has_cooling"),
        "cooling_type": data.get("cooling_type"),

        # ── Priority 2 — High-Value ───────────────────────────────────────────
        "home_type": data.get("property_type"),
        "year_built": data.get("year_built"),
        # Heating-only fuel inference from RentCast; supplements appliances_fuel.
        "primary_heating_fuel": _infer_heating_fuel(data.get("heating_type")),
        # EV ownership/intent affects panel sizing significantly — always ask.
        "ev_owner_or_planning": None,
        # Roof replacement timing affects whether solar is recommended now or
        # deferred — always ask. (roof_type from RentCast is available as context
        # in _property_meta but doesn't answer this forward-looking question.)
        "planning_roof_replacement": None,
        # User's primary goal shapes which upgrades are surfaced first — always ask.
        "primary_goal": None,

        # ── Priority 3 — Nice to Have ─────────────────────────────────────────
        "square_footage": data.get("square_footage"),
        "num_occupants": _estimate_occupants(
            data.get("bedrooms"), data.get("bathrooms")
        ),
        # Planned major electric additions (pool, hot tub, ADU, workshop,
        # battery backup) affect panel and system sizing — always ask.
        "planned_electric_additions": None,

        # Pass-through for downstream services
        "_property_meta": data,
    }


def _infer_heating_fuel(heating_type: Optional[str]) -> Optional[str]:
    """
    Maps RentCast heatingType strings to the fuel categories used in the
    questionnaire (gas, electric, oil, propane, heat_pump).
    """
    if not heating_type:
        return None
    ht = heating_type.lower()
    if "heat pump" in ht:
        return "heat_pump"
    if any(k in ht for k in ("gas", "forced air", "radiant")):
        return "gas"
    if any(k in ht for k in ("electric", "baseboard")):
        return "electric"
    if "oil" in ht:
        return "oil"
    if "propane" in ht:
        return "propane"
    return None


def _estimate_occupants(bedrooms: Optional[int], bathrooms: Optional[float]) -> Optional[int]:
    """
    Rough occupancy heuristic: 1.5 people per bedroom, rounded.
    Only used as a default if the user hasn't provided a number.
    """
    if bedrooms is None:
        return None
    return max(1, round(bedrooms * 1.5))
