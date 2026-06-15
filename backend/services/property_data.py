from services.rentcast_api import get_pre_filled_answers
from services.solar_api import SolarAPIError, fetch_solar_for_address


async def get_property_and_solar_data(address: str, monthly_electricity_bill: float) -> dict:
    pre_filled = get_pre_filled_answers(address)
    try:
        pre_filled["_solar_data"] = await fetch_solar_for_address(
            address,
            monthly_electricity_bill,
        )
    except SolarAPIError:
        pre_filled["_solar_data"] = None
    return pre_filled

