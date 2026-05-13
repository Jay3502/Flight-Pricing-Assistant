import os
import requests
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from typing import Optional

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Real Flight Tools", json_response=True)

api_key = os.getenv("SERP_API_KEY")
if not api_key:
    logger.error("SERP_API_KEY not found in .env file!")
else:
    logger.info("SERP_API_KEY loaded successfully.")


def _serpapi_get(params: dict) -> dict:
    """Shared helper — GET SerpAPI and return parsed JSON."""
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.error("SerpAPI error: %s", data["error"])
            return {"error": data["error"]}
        return data
    except requests.Timeout:
        return {"error": "SerpAPI request timed out."}
    except requests.HTTPError as e:
        return {"error": f"HTTP error: {e}"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def search_flights(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    return_date: Optional[str] = None
):
    """
    Search for flights via SerpAPI Google Flights.

    For round-trips SerpAPI requires TWO calls:
      1. First call  → returns outbound itineraries, each with a departure_token
      2. Second call → uses departure_token of the best outbound to fetch return legs

    We do both calls here and stitch the return leg onto the best outbound itinerary
    before returning, so the rest of the pipeline stays simple.
    """
    if not (len(departure_id) == 3 and len(arrival_id) == 3):
        return {"flights": [], "error": "Invalid IATA airport code format."}

    is_round_trip = bool(return_date)
    trip_type     = "1" if is_round_trip else "2"

    logger.info(
        "Searching: %s → %s | outbound=%s | return=%s | type=%s",
        departure_id, arrival_id, outbound_date, return_date, trip_type
    )

    # ── CALL 1: outbound flights ───────────────────────────────────────────────
    params1 = {
        "engine":         "google_flights",
        "departure_id":   departure_id,
        "arrival_id":     arrival_id,
        "outbound_date":  outbound_date,
        "type":           trip_type,
        "currency":       "INR",
        "hl":             "en",
        "api_key":        api_key,
    }
    if return_date:
        params1["return_date"] = return_date

    data1 = _serpapi_get(params1)
    if "error" in data1:
        return {"flights": [], "error": data1["error"]}

    all_outbound = data1.get("best_flights", []) + data1.get("other_flights", [])
    logger.info("Call 1: found %d outbound itineraries", len(all_outbound))

    if not all_outbound:
        return {"flights": [], "is_round_trip": is_round_trip}

    # ── CALL 2: return flights (round-trip only) ───────────────────────────────
    # SerpAPI puts a departure_token on each outbound itinerary.
    # We use the token from the *best* (first) outbound itinerary to get its
    # matching return options, then attach the best return leg to every
    # outbound itinerary so normalization_agent can unpack it uniformly.
    if is_round_trip:
        best_token = all_outbound[0].get("departure_token")

        if best_token:
            params2 = {
                "engine":          "google_flights",
                "departure_id":    departure_id,
                "arrival_id":      arrival_id,
                "outbound_date":   outbound_date,
                "return_date":     return_date,
                "type":            "1",
                "currency":        "INR",
                "hl":              "en",
                "api_key":         api_key,
                "departure_token": best_token,   # ← key: unlocks return results
            }
            data2 = _serpapi_get(params2)

            if "error" not in data2:
                return_itineraries = (
                    data2.get("best_flights", []) +
                    data2.get("other_flights", [])
                )
                logger.info("Call 2: found %d return itineraries", len(return_itineraries))

                # Attach the best return itinerary's legs to every outbound
                # under the key "return_flights" so normalization_agent can read it.
                if return_itineraries:
                    best_return_legs = return_itineraries[0].get("flights", [])
                    for itinerary in all_outbound:
                        itinerary["return_flights"] = best_return_legs
            else:
                logger.warning("Call 2 failed: %s", data2["error"])
        else:
            logger.warning("No departure_token on best outbound — cannot fetch return leg")

    return {
        "flights":       all_outbound,
        "is_round_trip": is_round_trip,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")