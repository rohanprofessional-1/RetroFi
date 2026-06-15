import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SOLAR_API_BASE = "https://solar.googleapis.com/v1"
GEOCODE_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DC_TO_AC_EFFICIENCY = 0.85
DEFAULT_ELECTRICITY_RATE_USD_PER_KWH = 0.15
MAX_PRODUCTION_TO_USAGE_RATIO = 3.0


class SolarAPIError(Exception):
    """Raised when the Google Solar or Geocoding API returns an error."""


def parse_money(money: Optional[dict]) -> float:
    if not money:
        return 0.0
    units = int(money.get("units") or 0)
    nanos = int(money.get("nanos") or 0)
    return units + nanos / 1_000_000_000


async def geocode_address(address: str) -> tuple[float, float]:
    api_key = _require_api_key()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            GEOCODE_API_URL,
            params={"address": address, "key": api_key},
        )
        response.raise_for_status()
        data = response.json()

    if data.get("status") != "OK" or not data.get("results"):
        raise SolarAPIError(f"Geocoding failed for address: {data.get('status')}")

    location = data["results"][0]["geometry"]["location"]
    return float(location["lat"]), float(location["lng"])


async def fetch_solar_potential(lat: float, lng: float) -> dict:
    api_key = _require_api_key()
    base_params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "key": api_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{SOLAR_API_BASE}/buildingInsights:findClosest",
            params={**base_params, "requiredQuality": "HIGH"},
        )
        if response.status_code == 404:
            response = await client.get(
                f"{SOLAR_API_BASE}/buildingInsights:findClosest",
                params={
                    **base_params,
                    "requiredQuality": "BASE",
                    "experiments": "EXPANDED_COVERAGE",
                },
            )

    if response.status_code == 404:
        raise SolarAPIError(
            "No building found near this address. Try a more specific street address."
        )
    if not response.is_success:
        raise SolarAPIError(
            f"Solar API request failed ({response.status_code}): {response.text}"
        )
    return response.json()


def parse_solar_data(raw: dict, monthly_bill_usd: float) -> dict:
    solar_potential = raw.get("solarPotential") or {}
    financial_analysis = _find_closest_financial_analysis(
        solar_potential.get("financialAnalyses") or [],
        monthly_bill_usd,
    )
    financial_metrics = _extract_financial_metrics(financial_analysis)
    panel_config = _select_panel_config(
        solar_potential,
        financial_analysis,
        monthly_bill_usd,
    )

    panel_capacity_watts = float(solar_potential.get("panelCapacityWatts") or 400)
    panel_count = int(panel_config.get("panelsCount") or 0) if panel_config else 0
    yearly_energy_dc_kwh = (
        float(panel_config.get("yearlyEnergyDcKwh") or 0) if panel_config else 0.0
    )
    system_size_kw = round((panel_count * panel_capacity_watts) / 1000, 2)
    annual_production_kwh = float(
        (financial_metrics or {}).get("initialAcKwhPerYear")
        or yearly_energy_dc_kwh * DC_TO_AC_EFFICIENCY
    )
    carbon_factor = float(solar_potential.get("carbonOffsetFactorKgPerMwh") or 0)
    carbon_avoided_kg = (
        annual_production_kwh * carbon_factor / 1000 if carbon_factor else 0.0
    )
    roof_segments = _build_roof_segments(solar_potential.get("roofSegmentStats") or [])
    max_panels = int(solar_potential.get("maxArrayPanelsCount") or 0)

    return {
        "buildingId": raw.get("name"),
        "center": raw.get("center"),
        "imageryQuality": raw.get("imageryQuality"),
        "imageryDate": raw.get("imageryDate"),
        "regionCode": raw.get("regionCode"),
        "panelCount": panel_count,
        "maxPanels": max_panels,
        "systemSizeKw": system_size_kw,
        "panelCapacityWatts": panel_capacity_watts,
        "annualProductionKwh": round(annual_production_kwh),
        "yearlyEnergyDcKwh": round(yearly_energy_dc_kwh),
        "sunshineHoursPerYear": round(
            float(solar_potential.get("maxSunshineHoursPerYear") or 0), 1
        ),
        "carbonAvoidedKgPerYear": round(carbon_avoided_kg, 1),
        "carbonAvoidedTonsPerYear": round(carbon_avoided_kg / 907.185, 2),
        "upfrontCost": (
            round(financial_metrics["upfrontCost"]) if financial_metrics else None
        ),
        "netUpfrontCost": (
            round(financial_metrics["netUpfrontCost"]) if financial_metrics else None
        ),
        "annualSavings": (
            round(financial_metrics["annualSavings"]) if financial_metrics else None
        ),
        "savings20Year": (
            round(financial_metrics["savings20Year"]) if financial_metrics else None
        ),
        "paybackYears": (
            round(financial_metrics["paybackYears"], 1)
            if financial_metrics and financial_metrics.get("paybackYears")
            else None
        ),
        "matchedMonthlyBill": (
            round(financial_metrics["matchedMonthlyBill"], 2)
            if financial_metrics
            else None
        ),
        "solarPercentage": (
            financial_metrics.get("solarPercentage") if financial_metrics else None
        ),
        "netMeteringAllowed": (
            financial_metrics.get("netMeteringAllowed") if financial_metrics else None
        ),
        "percentageExportedToGrid": (
            financial_metrics.get("percentageExportedToGrid")
            if financial_metrics
            else None
        ),
        "roofSegments": roof_segments,
        "installationNotes": _build_installation_notes(
            roof_segments,
            panel_count,
            max_panels,
        ),
        "incentives": _solar_incentives(financial_metrics),
        "hasFinancialAnalysis": financial_metrics is not None,
        "raw": raw,
    }


async def fetch_solar_for_address(address: str, monthly_bill_usd: float) -> dict:
    lat, lng = await geocode_address(address)
    raw = await fetch_solar_potential(lat, lng)
    parsed = parse_solar_data(raw, monthly_bill_usd)
    parsed["coordinates"] = {"lat": lat, "lng": lng}
    return parsed


def _require_api_key() -> str:
    if not GOOGLE_API_KEY:
        raise SolarAPIError(
            "GOOGLE_API_KEY is not set. Add it to a .env file in the project root or backend directory."
        )
    return GOOGLE_API_KEY


def _find_closest_financial_analysis(
    analyses: list[dict],
    monthly_bill_usd: float,
) -> Optional[dict]:
    if not analyses:
        return None
    return min(
        analyses,
        key=lambda analysis: abs(
            parse_money(analysis.get("monthlyBill")) - monthly_bill_usd
        ),
    )


def _estimate_annual_kwh_from_bill(
    monthly_bill_usd: float,
    financial_details: Optional[dict] = None,
) -> float:
    if monthly_bill_usd <= 0:
        return 0.0
    average_kwh_per_month = (financial_details or {}).get("averageKwhPerMonth")
    if average_kwh_per_month:
        return float(average_kwh_per_month) * 12
    return (monthly_bill_usd * 12) / DEFAULT_ELECTRICITY_RATE_USD_PER_KWH


def _config_ac_production_kwh(config: dict) -> float:
    return float(config.get("yearlyEnergyDcKwh") or 0) * DC_TO_AC_EFFICIENCY


def _is_reasonable_sizing(
    config: dict,
    monthly_bill_usd: float,
    financial_details: Optional[dict],
) -> bool:
    if monthly_bill_usd <= 0:
        return True
    target_kwh = _estimate_annual_kwh_from_bill(monthly_bill_usd, financial_details)
    if target_kwh <= 0:
        return True
    return _config_ac_production_kwh(config) <= target_kwh * MAX_PRODUCTION_TO_USAGE_RATIO


def _select_panel_config_by_usage(configs: list[dict], target_annual_kwh: float) -> dict:
    if target_annual_kwh <= 0:
        return configs[0]
    for config in configs:
        if _config_ac_production_kwh(config) >= target_annual_kwh * 0.9:
            return config
    return configs[-1]


def _select_panel_config(
    solar_potential: dict,
    financial_analysis: Optional[dict],
    monthly_bill_usd: float,
) -> Optional[dict]:
    configs = solar_potential.get("solarPanelConfigs") or []
    if not configs:
        return None
    financial_details = (financial_analysis or {}).get("financialDetails") or {}
    index = (financial_analysis or {}).get("panelConfigIndex")
    if index is not None and 0 <= index < len(configs):
        config = configs[index]
        if _is_reasonable_sizing(config, monthly_bill_usd, financial_details):
            return config
    target_kwh = _estimate_annual_kwh_from_bill(monthly_bill_usd, financial_details)
    return _select_panel_config_by_usage(configs, target_kwh)


def _extract_financial_metrics(financial_analysis: Optional[dict]) -> Optional[dict]:
    if not financial_analysis:
        return None
    cash_purchase = financial_analysis.get("cashPurchaseSavings") or {}
    if not cash_purchase.get("outOfPocketCost") and not cash_purchase.get("savings"):
        return None

    cash_savings = cash_purchase.get("savings") or {}
    financial_details = financial_analysis.get("financialDetails") or {}
    upfront_cost = parse_money(cash_purchase.get("outOfPocketCost"))
    annual_savings = parse_money(cash_savings.get("savingsYear1"))
    payback_years = cash_savings.get("paybackYears")
    if upfront_cost <= 0 and annual_savings <= 0 and not payback_years:
        return None

    rebate_value = parse_money(cash_purchase.get("rebateValue"))
    return {
        "upfrontCost": upfront_cost,
        "netUpfrontCost": max(upfront_cost - rebate_value, 0),
        "annualSavings": annual_savings,
        "savings20Year": parse_money(cash_savings.get("savingsYear20")),
        "paybackYears": float(payback_years) if payback_years else None,
        "federalIncentive": parse_money(financial_details.get("federalIncentive")),
        "stateIncentive": parse_money(financial_details.get("stateIncentive")),
        "utilityIncentive": parse_money(financial_details.get("utilityIncentive")),
        "srecTotal": parse_money(financial_details.get("lifetimeSrecTotal")),
        "solarPercentage": financial_details.get("solarPercentage"),
        "netMeteringAllowed": financial_details.get("netMeteringAllowed"),
        "percentageExportedToGrid": financial_details.get("percentageExportedToGrid"),
        "initialAcKwhPerYear": financial_details.get("initialAcKwhPerYear"),
        "matchedMonthlyBill": parse_money(financial_analysis.get("monthlyBill")),
    }


def _build_roof_segments(roof_segment_stats: list[dict]) -> list[dict]:
    segments = []
    for index, segment in enumerate(roof_segment_stats):
        stats = segment.get("stats") or {}
        sunshine = stats.get("sunshineQuantiles") or []
        median_sunshine = sunshine[len(sunshine) // 2] if sunshine else None
        segments.append(
            {
                "segmentIndex": index,
                "pitchDegrees": round(segment.get("pitchDegrees", 0), 1),
                "azimuthDegrees": round(segment.get("azimuthDegrees", 0), 1),
                "areaMeters2": round(stats.get("areaMeters2", 0), 1),
                "medianSunshineHoursPerYear": (
                    round(median_sunshine, 1) if median_sunshine is not None else None
                ),
            }
        )
    return segments


def _build_installation_notes(
    roof_segments: list[dict],
    panel_count: int,
    max_panels: int,
) -> str:
    if not roof_segments:
        return (
            f"A solar array of up to {max_panels} panels may fit on this roof. "
            "A site survey is recommended to confirm mounting locations and electrical tie-in."
        )

    top_segments = sorted(
        roof_segments,
        key=lambda segment: segment.get("medianSunshineHoursPerYear") or 0,
        reverse=True,
    )[:3]
    segment_notes = [
        f"Segment {segment['segmentIndex']}: {segment['pitchDegrees']} deg pitch, "
        f"{segment['azimuthDegrees']} deg azimuth, {segment['areaMeters2']} m2"
        for segment in top_segments
    ]
    return (
        f"Recommended system size: {panel_count} panels (max roof capacity: {max_panels}). "
        "Prioritize placement on the sunniest roof segments: "
        + "; ".join(segment_notes)
        + "."
    )


def _solar_incentives(financial_metrics: Optional[dict]) -> list[dict]:
    if not financial_metrics:
        return []
    rows = [
        ("Federal Solar Investment Tax Credit (ITC)", "federalIncentive", "Tax Credit"),
        ("State Solar Incentive", "stateIncentive", "Incentive"),
        ("Utility Solar Incentive", "utilityIncentive", "Rebate"),
        ("Solar Renewable Energy Credits (SRECs)", "srecTotal", "Credit"),
    ]
    return [
        {
            "name": name,
            "amount": financial_metrics[key],
            "type": incentive_type,
            "source": "Google Solar API",
        }
        for name, key, incentive_type in rows
        if financial_metrics.get(key, 0) > 0
    ]
