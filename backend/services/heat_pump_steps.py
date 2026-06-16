import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from services.climate_zone import get_climate_zone


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ASHRAE 99.6% heating design temperatures by IECC zone
_DESIGN_TEMP_BY_ZONE = {
    1: ("above 40°F", False),
    2: ("20°F to 40°F", False),
    3: ("10°F to 25°F", False),
    4: ("-5°F to 15°F", True),
    5: ("-15°F to 0°F", True),
    6: ("-25°F to -10°F", True),
    7: ("-35°F to -20°F", True),
    8: ("below -35°F", True),
}

# kWh equivalent of 1 therm of heat delivered at COP 3.0 vs gas at 80% AFUE
_KWH_PER_THERM_EQUIV = 29.3 / 3.0   # ≈ 9.77 kWh at COP 3.0
_GAS_AFUE = 0.80


def _fuel_switching_economics(electricity_per_kwh: float | None, gas_per_therm: float | None) -> str:
    if not electricity_per_kwh or not gas_per_therm:
        return "local rate data unavailable — request quotes with actual rate comparison"
    hp_cost = electricity_per_kwh * _KWH_PER_THERM_EQUIV
    gas_cost = gas_per_therm / _GAS_AFUE
    savings_pct = round((gas_cost - hp_cost) / gas_cost * 100)
    direction = "cheaper" if hp_cost < gas_cost else "more expensive"
    return (
        f"At ${electricity_per_kwh:.3f}/kWh electric and ${gas_per_therm:.3f}/therm gas: "
        f"heat pump delivers heat at ${hp_cost:.3f}/therm-equivalent vs gas at ${gas_cost:.3f}/therm-equivalent — "
        f"heat pump is {abs(savings_pct)}% {direction} to operate"
    )


def _system_type_recommendation(home_type: str | None, sq_ft: int | None, cooling_type: str | None) -> str:
    sq_ft = sq_ft or 0
    home_type = (home_type or "").lower()
    has_ducts = cooling_type and "central" in (cooling_type or "").lower()
    if has_ducts:
        return "ducted whole-home heat pump (replaces both furnace and existing central AC on same duct system)"
    if "condo" in home_type or "apartment" in home_type or sq_ft < 1200:
        return "single-zone or multi-zone mini-split (no ductwork required)"
    if sq_ft > 2500:
        return "multi-zone mini-split or ducted heat pump with new duct work — get contractor assessment"
    return "mini-split or ductless system if no central ducts exist; otherwise ducted whole-home system"


def _format_incentives(matched_incentives: list[dict]) -> str:
    if not matched_incentives:
        return "none matched"
    parts = []
    for inc in matched_incentives[:4]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        notes = inc.get("eligibility_notes", "")
        parts.append(f"{name} ({desc}){': ' + notes if notes else ''}")
    return "\n  ".join(parts)


def _format_contractors(contractors: list[dict]) -> str:
    if not contractors:
        return "none found nearby via Google Places"
    return "; ".join(
        f"{c['name']} ({c['rating']}★, {c['ratings_count']} reviews, {c['vicinity']})"
        for c in contractors
    )


def _build_prompt(
    address: str,
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    climate_info: dict,
    rates: dict,
    contractors: list[dict],
) -> str:
    year_built = property_profile.get("year_built")
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage")
    heating_fuel = property_profile.get("heating_fuel") or "unknown"
    cooling_type = property_profile.get("cooling_type") or ""

    zone = climate_info["zone"]
    design_temp, needs_cold_climate = _DESIGN_TEMP_BY_ZONE.get(zone, ("unknown", False))
    cold_climate_note = (
        f"cold-climate-rated HP required (NEEP-listed, rated to operate at or below 5°F) — "
        f"design temp for this zone is {design_temp}"
        if needs_cold_climate
        else f"standard heat pump is suitable — design temp for this zone is {design_temp}"
    )

    system_rec = _system_type_recommendation(home_type, sq_ft, cooling_type)
    economics = _fuel_switching_economics(rates.get("electricity_per_kwh"), rates.get("gas_per_therm"))
    utility_name = rates.get("utility_name") or "local utility"

    fuel_context = {
        "natural_gas": "replacing natural gas heat — fuel-switching economics are central to the ROI case",
        "oil": "replacing oil heat — heat pumps are almost always cheaper to operate than oil",
        "propane": "replacing propane — one of the strongest financial cases for switching to a heat pump",
        "electric": "replacing electric resistance — heat pump uses 2–3× less electricity for same heat output",
    }.get(heating_fuel, f"current fuel: {heating_fuel}")

    return (
        "You are an HVAC contractor advising a specific homeowner on installing an air source heat pump.\n"
        "Return ONLY a JSON array of exactly 6 objects. Each object must have exactly three keys:\n"
        '  "title": action heading, max 5 words\n'
        '  "summary": one sentence (max 20 words) specific to this homeowner\n'
        '  "bullets": array of 2-4 action items or data points, max 15 words each\n\n'
        "Cover these topics in order: (1) cold-climate suitability check, (2) system type selection, "
        "(3) Manual J load calculation, (4) fuel-switching economics at actual local rates, "
        "(5) incentive stack and paperwork, (6) installation checklist (electrical panel, backup heat, permits).\n"
        "Every bullet must use real numbers, the actual rates, and local contractor names where available.\n\n"
        "Homeowner data:\n"
        f"- Address: {address}\n"
        f"- IECC climate zone: {zone} ({climate_info['description']}) — {cold_climate_note}\n"
        f"- Home: {sq_ft or 'N/A'} sq ft {home_type}, built {year_built or 'year unknown'}\n"
        f"- Current heating: {fuel_context}\n"
        f"- Existing cooling: {cooling_type or 'unknown'}\n"
        f"- Recommended system type: {system_rec}\n"
        f"- Fuel-switching economics: {economics}\n"
        f"- Utility: {utility_name}\n"
        f"- Gross install cost: ${gross_cost:,.0f}\n"
        f"- Net cost after incentives: ${net_cost:,.0f}\n"
        f"- Estimated annual savings: ${annual_savings:,.0f}/yr\n"
        f"- Payback: {payback_years if payback_years else 'N/A'} years\n"
        f"- Incentives:\n  {_format_incentives(matched_incentives)}\n"
        f"- Nearby HVAC contractors: {_format_contractors(contractors)}\n\n"
        "Return only the JSON array, no markdown fences."
    )


def _call_anthropic(prompt: str) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return []
    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 1600,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    text = "".join(
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    ).strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    try:
        steps = json.loads(text)
        if isinstance(steps, list) and all(
            isinstance(s, dict) and "title" in s and "summary" in s and "bullets" in s
            for s in steps
        ):
            return [{"title": s["title"], "summary": s["summary"], "bullets": s["bullets"]} for s in steps]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _fallback_steps(
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    climate_info: dict,
    rates: dict,
    contractors: list[dict],
) -> list[dict]:
    zone = climate_info["zone"]
    design_temp, needs_cold_climate = _DESIGN_TEMP_BY_ZONE.get(zone, ("unknown", False))
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage") or "N/A"
    heating_fuel = property_profile.get("heating_fuel") or "current fuel"
    cooling_type = property_profile.get("cooling_type") or ""
    system_rec = _system_type_recommendation(home_type, sq_ft if isinstance(sq_ft, int) else None, cooling_type)
    economics = _fuel_switching_economics(rates.get("electricity_per_kwh"), rates.get("gas_per_therm"))
    incentive_names = [inc.get("name", "") for inc in matched_incentives[:3] if inc.get("name")]
    contractor_names = [c["name"] for c in contractors]

    cold_climate_bullets = [
        f"Zone {zone} design temperature is {design_temp}",
        "Require cold-climate HP rated to operate at or below 5°F (NEEP-listed product)" if needs_cold_climate
        else "Standard heat pump is appropriate for this climate zone",
        "Confirm minimum operating temperature spec before purchasing any unit",
    ]

    system_bullets = [f"Recommended: {system_rec}"]
    if cooling_type and "central" in cooling_type.lower():
        system_bullets.append("Existing ductwork can be reused — have contractor assess duct condition and leakage")
    else:
        system_bullets.append("No central ducts: mini-splits avoid duct installation cost")
    system_bullets.append(f"Size for {sq_ft} sq ft — contractor must perform Manual J before ordering equipment")

    incentive_bullets = []
    for inc in matched_incentives[:3]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        if name:
            incentive_bullets.append(f"{name}: {desc}")
    if not incentive_bullets:
        incentive_bullets = [f"Net cost after incentives: ${net_cost:,.0f}"]
    incentive_bullets.append("Equipment must be on ENERGY STAR Certified Heat Pumps list for 25C credit")

    contractor_bullets = ["Request quotes from at least 3 licensed HVAC contractors"]
    if contractor_names:
        contractor_bullets.insert(0, f"Rated local options: {', '.join(contractor_names)}")
    contractor_bullets.append("Confirm contractor will perform Manual J — refuse quotes without it")

    return [
        {
            "title": "Confirm Cold-Climate Suitability",
            "summary": f"Zone {zone} design temperatures reach {design_temp} — {'a cold-climate-rated HP is required' if needs_cold_climate else 'a standard HP is sufficient'}.",
            "bullets": cold_climate_bullets,
        },
        {
            "title": "Choose Your System Type",
            "summary": f"Your {sq_ft} sq ft {home_type} with {cooling_type or 'unknown cooling'} points to a specific system type.",
            "bullets": system_bullets,
        },
        {
            "title": "Require a Manual J Calculation",
            "summary": "Proper load sizing is the single biggest factor in heat pump performance and comfort.",
            "bullets": [
                "Manual J calculates exact heating/cooling load for your home dimensions and insulation",
                "Oversized units short-cycle, fail to dehumidify, and wear out faster",
                "Walk away from any quote that doesn't include a Manual J",
                "Ask for the load report in writing before equipment is ordered",
            ],
        },
        {
            "title": "Compare Fuel-Switching Economics",
            "summary": f"Switching from {heating_fuel} to a heat pump changes your operating cost structure.",
            "bullets": [
                economics,
                f"Annual savings estimate: ${annual_savings:,.0f}/yr at current rates",
                "Request a 10-year operating cost comparison from each contractor",
            ],
        },
        {
            "title": "Stack Your Incentives",
            "summary": f"Incentives reduce your gross cost from ${gross_cost:,.0f} to ${net_cost:,.0f}.",
            "bullets": incentive_bullets,
        },
        {
            "title": "Pre-Installation Checklist",
            "summary": f"Electrical panel capacity and permits must be confirmed before installation day.",
            "bullets": [
                "Verify electrical panel has capacity for HP circuit (often needs 240V/30–60A)",
                "Confirm installer pulls all required permits before work begins",
                "Ask about backup/auxiliary heat strategy for extreme cold days" if needs_cold_climate else
                "Confirm thermostat compatibility with new heat pump system",
                f"Expected payback: {payback_years if payback_years else 'N/A'} years at ${annual_savings:,.0f}/yr savings",
            ],
        },
    ]


def generate_heat_pump_steps(
    address: str,
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    rates: dict,
    contractors: list[dict],
) -> list[dict]:
    climate_info = get_climate_zone(address, property_profile.get("zip_code"))
    prompt = _build_prompt(
        address, gross_cost, net_cost, annual_savings, payback_years,
        matched_incentives, property_profile, climate_info, rates, contractors,
    )
    steps = _call_anthropic(prompt)
    if not steps:
        steps = _fallback_steps(
            gross_cost, net_cost, annual_savings, payback_years,
            matched_incentives, property_profile, climate_info, rates, contractors,
        )
    return steps
