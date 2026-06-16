import hashlib
import json
import time


_TTL_SECONDS = 86400  # 24 hours
_store: dict[str, tuple[float, object]] = {}


def _make_key(*parts) -> str:
    serialized = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def get(key: str) -> object | None:
    entry = _store.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _TTL_SECONDS:
        del _store[key]
        return None
    return value


def set(key: str, value: object) -> None:
    _store[key] = (time.monotonic(), value)


def make_action_steps_key(upgrade_key: str, address: str, property_profile: dict,
                           matched_incentives: list, gross_cost: float,
                           net_cost: float, annual_savings: float,
                           payback_years: float | None) -> str:
    return _make_key(upgrade_key, address.lower().strip(), property_profile,
                     matched_incentives, gross_cost, net_cost, annual_savings, payback_years)


def make_solar_steps_key(address: str, solar_data: dict, matched_incentives: list) -> str:
    return _make_key("solar", address.lower().strip(), solar_data, matched_incentives)
