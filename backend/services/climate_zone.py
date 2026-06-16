import re

# Predominant IECC 2021 climate zone by US state abbreviation
_STATE_TO_ZONE: dict[str, int] = {
    "AK": 7, "AL": 3, "AR": 3, "AZ": 2, "CA": 3, "CO": 5, "CT": 5,
    "DC": 4, "DE": 4, "FL": 2, "GA": 3, "HI": 1, "IA": 5, "ID": 5,
    "IL": 5, "IN": 5, "KS": 4, "KY": 4, "LA": 2, "MA": 5, "MD": 4,
    "ME": 6, "MI": 5, "MN": 6, "MO": 4, "MS": 3, "MT": 6, "NC": 3,
    "ND": 6, "NE": 5, "NH": 6, "NJ": 4, "NM": 4, "NV": 3, "NY": 5,
    "OH": 5, "OK": 3, "OR": 4, "PA": 5, "RI": 5, "SC": 3, "SD": 6,
    "TN": 4, "TX": 2, "UT": 5, "VA": 4, "VT": 6, "WA": 4, "WI": 6,
    "WV": 5, "WY": 6,
}

_ZONE_INFO: dict[int, dict] = {
    1: {
        "description": "Very Hot–Humid",
        "air_sealing_priority": "moderate",
        "target_r_attic": "R-30 to R-49",
        "heating_dominated": False,
    },
    2: {
        "description": "Hot",
        "air_sealing_priority": "moderate",
        "target_r_attic": "R-38 to R-49",
        "heating_dominated": False,
    },
    3: {
        "description": "Warm",
        "air_sealing_priority": "moderate-high",
        "target_r_attic": "R-38 to R-49",
        "heating_dominated": False,
    },
    4: {
        "description": "Mixed",
        "air_sealing_priority": "high",
        "target_r_attic": "R-38 to R-60",
        "heating_dominated": True,
    },
    5: {
        "description": "Cool",
        "air_sealing_priority": "high",
        "target_r_attic": "R-49 to R-60",
        "heating_dominated": True,
    },
    6: {
        "description": "Cold",
        "air_sealing_priority": "very high",
        "target_r_attic": "R-49 to R-60",
        "heating_dominated": True,
    },
    7: {
        "description": "Very Cold",
        "air_sealing_priority": "critical",
        "target_r_attic": "R-60+",
        "heating_dominated": True,
    },
    8: {
        "description": "Subarctic",
        "air_sealing_priority": "critical",
        "target_r_attic": "R-60+",
        "heating_dominated": True,
    },
}

# Pre-1980 balloon-framed / pre-code homes have far more infiltration paths
_CONSTRUCTION_ERA: list[tuple[int, str]] = [
    (1940, "pre-1940 — balloon framing with open wall cavities connecting directly to attic space; expect very high infiltration"),
    (1980, "1940–1979 — platform framing but pre-energy-code; attic bypasses, unsealed plumbing chases, and rim joists are typical leakage paths"),
    (2000, "1980–1999 — energy codes introduced but inconsistently enforced; recessed lighting, HVAC penetrations, and attic hatches are common weak points"),
    (2012, "2000–2012 — improved code compliance; primary leakage paths are HVAC penetrations, recessed lights, and attic-access hatches"),
    (9999, "post-2012 — modern energy codes with good baseline air tightness; focus on HVAC penetrations and any recent additions or renovations"),
]


def _extract_state(address: str) -> str | None:
    # Match "City, ST 12345" or "City, ST" patterns
    match = re.search(r",\s*([A-Z]{2})\b", address.upper())
    return match.group(1) if match else None


def _construction_era_note(year_built: int | None) -> str:
    if not year_built:
        return "construction era unknown"
    for cutoff, note in _CONSTRUCTION_ERA:
        if year_built < cutoff:
            return f"{year_built} ({note})"
    return f"{year_built} (post-2012 — modern energy codes)"


def get_climate_zone(address: str, zip_code: str | None = None) -> dict:
    state = _extract_state(address)
    zone = _STATE_TO_ZONE.get(state, 4) if state else 4  # default to zone 4 (Mixed) if unknown
    info = _ZONE_INFO[zone]
    return {
        "zone": zone,
        "state": state or "unknown",
        **info,
    }


def get_construction_era_note(year_built: int | None) -> str:
    return _construction_era_note(year_built)
