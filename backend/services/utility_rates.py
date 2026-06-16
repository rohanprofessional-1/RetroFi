import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

NREL_RATES_URL = "https://developer.nrel.gov/api/utility_rates/v3.json"
# 1 MCF (thousand cubic feet of natural gas) ≈ 10.37 therms
MCF_TO_THERMS = 10.37


async def get_utility_rates(address: str) -> dict:
    """
    Return residential electricity ($/kWh) and natural gas ($/therm) rates
    for the given address via the NREL Utility Rates API.
    Returns an empty dict if the API key is missing or the call fails.
    """
    api_key = os.getenv("NREL_API_KEY", "").strip()
    if not api_key:
        return {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                NREL_RATES_URL,
                params={"api_key": api_key, "address": address, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return {}

    outputs = (data.get("outputs") or {})
    residential = outputs.get("residential") or {}
    utility_name = outputs.get("utility_name") or ""

    electricity = residential.get("electricity")   # $/kWh
    gas_mcf = residential.get("natural_gas")        # $/MCF
    gas_therm = round(gas_mcf / MCF_TO_THERMS, 4) if gas_mcf else None

    return {
        "electricity_per_kwh": electricity,
        "gas_per_therm": gas_therm,
        "utility_name": utility_name,
    }
