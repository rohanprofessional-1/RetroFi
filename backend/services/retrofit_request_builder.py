import re
from typing import Optional

from schemas import (
    HouseholdProfile,
    PropertyProfile,
    RetcastInput,
    RetrofitCalculationRequest,
    RetrofitPreferences,
    SolarPotentialInput,
)
from services.retrofit_calculator import (
    DEFAULT_ELECTRIC_RATE,
    DEFAULT_GAS_RATE,
    DEFAULT_GAS_CARBON_KG_PER_THERM,
    DEFAULT_GRID_CARBON_KG_PER_KWH,
)


def build_retrofit_calculation_request(
    address: str,
    answers: dict,
    solar_data: Optional[dict] = None,
) -> RetrofitCalculationRequest:
    meta = answers.get("_property_meta") or {}
    monthly_electric_bill = _money_to_float(answers.get("monthly_electricity_bill"))
    monthly_gas_bill = _money_to_float(answers.get("monthly_gas_bill"))

    return RetrofitCalculationRequest(
        property=PropertyProfile(
            address=meta.get("formatted_address") or address,
            zip_code=meta.get("zip_code"),
            home_type=_home_type(answers.get("home_type") or meta.get("property_type")),
            year_built=_year_built(answers.get("year_built") or meta.get("year_built")),
            square_footage=_square_footage(answers.get("square_footage") or meta.get("square_footage")),
            bedrooms=_int_or_none(meta.get("bedrooms")),
            stories=_float_or_none(meta.get("floor_count")),
            heating_fuel=_fuel(answers.get("primary_heating_fuel")),
            cooling_type=answers.get("cooling_type") or meta.get("cooling_type"),
            water_heater_fuel=_appliance_fuel(answers.get("appliances_fuel")),
        ),
        household=HouseholdProfile(
            household_income=_money_to_float_or_none(answers.get("household_income")),
            household_size=_int_or_none(answers.get("num_occupants")),
            owner_occupied=_owner_occupied(answers.get("home_ownership_status")),
            utility=answers.get("utility") or "Georgia Power",
            electric_rate_per_kwh=DEFAULT_ELECTRIC_RATE,
            gas_rate_per_therm=DEFAULT_GAS_RATE,
        ),
        preferences=RetrofitPreferences(
            primary_goal=_primary_goal(answers.get("primary_goal")),
            roof_type=_roof_type(answers.get("roof_type") or meta.get("roof_type")),
            roof_replacement_status=_roof_replacement_status(answers.get("planning_roof_replacement")),
            ev_owner_or_planning=_ev_status(answers.get("ev_owner_or_planning")),
            planned_electric_additions=_yes_no(answers.get("planned_electric_additions")),
        ),
        solar=_solar_input(solar_data),
        retcast=_retcast_input(monthly_electric_bill, monthly_gas_bill),
        upgrade_interests=_upgrade_interests(answers),
    )


def _solar_input(solar_data: Optional[dict]) -> Optional[SolarPotentialInput]:
    if not solar_data:
        return None

    panel_count = _int_or_none(solar_data.get("panelCount"))
    max_panels = _int_or_none(solar_data.get("maxPanels"))
    system_kw = _float_or_none(solar_data.get("systemSizeKw"))
    yearly_dc_kwh = _float_or_none(solar_data.get("yearlyEnergyDcKwh"))
    annual_ac_kwh = _float_or_none(solar_data.get("annualProductionKwh"))
    if yearly_dc_kwh is None and annual_ac_kwh is not None:
        yearly_dc_kwh = round(annual_ac_kwh / 0.85, 2)

    return SolarPotentialInput(
        solar_viable=bool(panel_count or max_panels or annual_ac_kwh or yearly_dc_kwh),
        max_array_panels=max_panels,
        yearly_energy_dc_kwh=yearly_dc_kwh,
        installed_system_kw=system_kw,
        estimated_install_cost=_float_or_none(solar_data.get("upfrontCost")),
        annual_sunshine_hours=_float_or_none(solar_data.get("sunshineHoursPerYear")),
        roof_segment_count=len(solar_data.get("roofSegments") or []),
    )


def _retcast_input(monthly_electric_bill: float, monthly_gas_bill: float) -> RetcastInput:
    baseline_kwh = (
        monthly_electric_bill * 12 / DEFAULT_ELECTRIC_RATE
        if monthly_electric_bill > 0
        else None
    )
    baseline_therms = (
        monthly_gas_bill * 12 / DEFAULT_GAS_RATE if monthly_gas_bill > 0 else None
    )
    return RetcastInput(
        baseline_annual_kwh=round(baseline_kwh, 2) if baseline_kwh else None,
        baseline_annual_therms=round(baseline_therms, 2) if baseline_therms else None,
        projected_annual_kwh=round(baseline_kwh * 0.85, 2) if baseline_kwh else None,
        projected_annual_therms=round(baseline_therms * 0.8, 2) if baseline_therms else None,
        grid_carbon_kg_per_kwh=DEFAULT_GRID_CARBON_KG_PER_KWH,
        gas_carbon_kg_per_therm=DEFAULT_GAS_CARBON_KG_PER_THERM,
        confidence="low",
    )


def _upgrade_interests(answers: dict) -> list[str]:
    interests = []
    primary_goal = str(answers.get("primary_goal") or "").lower()
    if "backup" in primary_goal:
        interests.extend(["solar", "battery storage"])
    if "carbon" in primary_goal or "bill" in primary_goal or "value" in primary_goal:
        interests.extend(["solar", "heat pump", "insulation", "air sealing"])
    if answers.get("planning_roof_replacement") == "Yes":
        interests.append("solar")
    return list(dict.fromkeys(interests))


def _home_type(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "single" in normalized:
        return "single_family"
    if "town" in normalized:
        return "townhouse"
    if "condo" in normalized or "apartment" in normalized:
        return "condo"
    return str(value)


def _primary_goal(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "bill" in normalized:
        return "lower_bills"
    if "backup" in normalized:
        return "backup_power"
    if "carbon" in normalized:
        return "reduce_carbon"
    if "value" in normalized:
        return "increase_home_value"
    return "other"


def _roof_type(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "asphalt" in normalized or "shingle" in normalized:
        return "asphalt_shingle"
    if "metal" in normalized:
        return "metal"
    if "tile" in normalized:
        return "tile"
    if "flat" in normalized or "tpo" in normalized:
        return "flat"
    return "other"


def _roof_replacement_status(value) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).lower()
    if normalized.startswith("yes"):
        return "yes"
    if normalized.startswith("no"):
        return "no"
    if "sure" in normalized:
        return "unsure"
    return None


def _ev_status(value) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).lower()
    if "own" in normalized:
        return "owns_ev"
    if "planning" in normalized or "plan" in normalized:
        return "planning_ev"
    if normalized.startswith("no"):
        return "none"
    return None


def _yes_no(value) -> Optional[bool]:
    if value is None:
        return None
    normalized = str(value).lower()
    if normalized.startswith("yes"):
        return True
    if normalized.startswith("no"):
        return False
    return None


def _year_built(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    if "before" in text.lower():
        return 1979
    match = re.search(r"\d{4}", text)
    return int(match.group(0)) if match else None


def _square_footage(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "")
    if "under" in text.lower():
        return 900
    if "over" in text.lower():
        return 2600
    values = [int(match) for match in re.findall(r"\d+", text)]
    if len(values) >= 2:
        return round((values[0] + values[1]) / 2)
    return values[0] if values else None


def _fuel(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "heat pump" in normalized or "heat_pump" in normalized:
        return "heat_pump"
    if "gas" in normalized:
        return "natural_gas"
    if "electric" in normalized:
        return "electric"
    if "propane" in normalized:
        return "propane"
    if "oil" in normalized:
        return "oil"
    return str(value)


def _appliance_fuel(value) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).lower()
    if "mixed" in normalized:
        return "mixed"
    return _fuel(value)


def _owner_occupied(value) -> Optional[bool]:
    if value is None:
        return None
    normalized = str(value).lower()
    if "own" in normalized or "owner" in normalized:
        return True
    if "rent" in normalized or "lease" in normalized:
        return False
    return None


def _money_to_float(value) -> float:
    parsed = _money_to_float_or_none(value)
    return parsed or 0.0


def _money_to_float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.]", "", str(value))
    return float(cleaned) if cleaned else None


def _int_or_none(value) -> Optional[int]:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _float_or_none(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
