import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

RENTCAST_API_KEY = os.getenv("RENTCAST_API_KEY", "")
RENTCAST_BASE_URL = "https://api.rentcast.io/v1"


def fetch_property_data(address: str) -> dict:
    if not RENTCAST_API_KEY:
        raise ValueError(
            "RENTCAST_API_KEY environment variable is not set. "
            "Set it before calling fetch_property_data()."
        )

    response = httpx.get(
        f"{RENTCAST_BASE_URL}/properties",
        headers={"Accept": "application/json", "X-Api-Key": RENTCAST_API_KEY},
        params={"address": address},
        timeout=10.0,
    )
    response.raise_for_status()

    records = response.json()
    if not records:
        raise ValueError(f"No property record found for address: {address!r}")

    record = records[0] if isinstance(records, list) else records
    features = record.get("features") or {}
    return _normalize(record, features)


def get_pre_filled_answers(address: str) -> dict:
    data = fetch_property_data(address)
    return {
        "monthly_electricity_bill": None,
        "monthly_gas_bill": None,
        "home_ownership_status": (
            "owner"
            if data.get("owner_occupied") is True
            else "renter"
            if data.get("owner_occupied") is False
            else None
        ),
        "appliances_fuel": None,
        "roof_type": data.get("roof_type"),
        "has_cooling": data.get("has_cooling"),
        "cooling_type": data.get("cooling_type"),
        "home_type": data.get("property_type"),
        "year_built": data.get("year_built"),
        "primary_heating_fuel": _infer_heating_fuel(data.get("heating_type")),
        "ev_owner_or_planning": None,
        "planning_roof_replacement": None,
        "primary_goal": None,
        "square_footage": data.get("square_footage"),
        "num_occupants": _estimate_occupants(data.get("bedrooms")),
        "planned_electric_additions": None,
        "_property_meta": data,
    }


def _normalize(record: dict, features: dict) -> dict:
    return {
        "rentcast_id": record.get("id"),
        "formatted_address": record.get("formattedAddress"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "county": record.get("county"),
        "zip_code": record.get("zipCode"),
        "state": record.get("state"),
        "owner_occupied": record.get("ownerOccupied"),
        "has_cooling": features.get("cooling"),
        "cooling_type": features.get("coolingType"),
        "property_type": record.get("propertyType"),
        "year_built": record.get("yearBuilt"),
        "heating_type": features.get("heatingType"),
        "has_heating": features.get("heating"),
        "square_footage": record.get("squareFootage"),
        "bedrooms": record.get("bedrooms"),
        "bathrooms": record.get("bathrooms"),
        "roof_type": features.get("roofType"),
        "floor_count": features.get("floorCount"),
        "lot_size": record.get("lotSize"),
    }


def _infer_heating_fuel(heating_type: Optional[str]) -> Optional[str]:
    if not heating_type:
        return None
    normalized = heating_type.lower()
    if "heat pump" in normalized:
        return "heat_pump"
    if any(value in normalized for value in ("gas", "forced air", "radiant")):
        return "gas"
    if any(value in normalized for value in ("electric", "baseboard")):
        return "electric"
    if "oil" in normalized:
        return "oil"
    if "propane" in normalized:
        return "propane"
    return None


def _estimate_occupants(bedrooms: Optional[int]) -> Optional[int]:
    if bedrooms is None:
        return None
    return max(1, round(bedrooms * 1.5))
