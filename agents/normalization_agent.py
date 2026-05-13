from typing import List, Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NormalizationAgent:

    def run(self, raw_results: List[Dict[str, Any]]) -> List[Dict]:
        normalized_flights = []

        for result in raw_results:
            source_name = result.get("source", "unknown")
            flight_data = result.get("data", {})
            flights_list = flight_data.get("flights", [])
            is_round_trip = flight_data.get("is_round_trip", False)

            logger.info(
                "Normalizing %d itineraries from '%s' | round_trip=%s",
                len(flights_list), source_name, is_round_trip
            )

            for item in flights_list:
                try:
                    if "search_flights" in source_name.lower():
                        normalized = self._map_serpapi(item, is_round_trip)
                        if normalized:
                            normalized_flights.append(normalized)
                except Exception as e:
                    logger.error("Error normalizing flight from %s: %s", source_name, e)

        return normalized_flights

    def _map_serpapi(self, item: Dict, is_round_trip: bool = False) -> Optional[Dict]:
        # ── OUTBOUND LEG ──────────────────────────────────────────────────────
        legs = item.get("flights", [])
        if not legs:
            logger.warning("Skipping itinerary with no outbound legs")
            return None

        main_leg = legs[0]
        dest_leg = legs[-1]
        stops    = len(legs) - 1

        outbound = {
            "airline":        main_leg.get("airline", "Unknown"),
            "flight_number":  main_leg.get("flight_number", "N/A"),
            "price":          item.get("price", 999999),
            "from_airport":   main_leg.get("departure_airport", {}).get("id"),
            "to_airport":     dest_leg.get("arrival_airport",   {}).get("id"),
            "departure_time": main_leg.get("departure_airport", {}).get("time"),
            "arrival_time":   dest_leg.get("arrival_airport",   {}).get("time"),
            "stops":          stops,
            "is_layover":     stops > 0,
            "layover_cities": [
                leg.get("arrival_airport", {}).get("id")
                for leg in legs[:-1]
            ] if stops > 0 else [],
            "return_leg": None   # default — overwritten below for round-trips
        }

        if is_round_trip:
            return_legs = item.get("return_flights", [])

            if return_legs:
                r_main  = return_legs[0]
                r_dest  = return_legs[-1]
                r_stops = len(return_legs) - 1

                outbound["return_leg"] = {
                    "airline":        r_main.get("airline", "Unknown"),
                    "flight_number":  r_main.get("flight_number", "N/A"),
                    "from_airport":   r_main.get("departure_airport", {}).get("id"),
                    "to_airport":     r_dest.get("arrival_airport",   {}).get("id"),
                    "departure_time": r_main.get("departure_airport", {}).get("time"),
                    "arrival_time":   r_dest.get("arrival_airport",   {}).get("time"),
                    "stops":          r_stops,
                    "layover_cities": [
                        leg.get("arrival_airport", {}).get("id")
                        for leg in return_legs[:-1]
                    ] if r_stops > 0 else []
                }
            else:
                logger.warning(
                    "Round-trip itinerary %s → %s has no return_flights block",
                    outbound["from_airport"], outbound["to_airport"]
                )

        return outbound