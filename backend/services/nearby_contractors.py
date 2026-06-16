import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
MIN_RATINGS_COUNT = 5


async def find_solar_installers(
    lat: float,
    lng: float,
    radius_m: int = 40000,
) -> list[dict]:
    """Return up to 3 nearby solar installers from Google Places, sorted by rating."""
    api_key = GOOGLE_API_KEY
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                PLACES_NEARBY_URL,
                params={
                    "location": f"{lat},{lng}",
                    "radius": radius_m,
                    "keyword": "solar panel installation",
                    "key": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    results = data.get("results") or []
    installers = []
    for place in results:
        rating = place.get("rating")
        ratings_count = place.get("user_ratings_total", 0)
        if rating and ratings_count >= MIN_RATINGS_COUNT:
            geometry = place.get("geometry") or {}
            location = geometry.get("location") or {}
            installers.append(
                {
                    "name": place.get("name", ""),
                    "rating": rating,
                    "ratings_count": ratings_count,
                    "vicinity": place.get("vicinity", ""),
                    "place_id": place.get("place_id", ""),
                    "lat": location.get("lat"),
                    "lng": location.get("lng"),
                }
            )

    installers.sort(key=lambda x: x["rating"], reverse=True)
    return installers[:3]
