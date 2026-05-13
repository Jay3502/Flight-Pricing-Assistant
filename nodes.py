from agents.normalization_agent import NormalizationAgent
from agents.explanation_agent import ExplanationAgent, FlightRecommendation
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)


async def search_node(state, executor):
    results = await executor.execute(state['tool_plan'])
    return {"raw_results": results}


def normalize_node(state):
    agent = NormalizationAgent()
    results = agent.run(state["raw_results"])
    return {"flights": results}


def optimize_node(state):
    flights = state.get("flights", [])
    query = state.get("user_query", "").lower()

    is_nonstop_req = "non-stop" in query or "direct" in query

    def ranking_key(f):
        stops = int(f.get('stops', 0))
        price = float(f.get('price', 0))
        if is_nonstop_req:
            return (stops, price)
        return (price, stops)

    ranked = sorted(flights, key=ranking_key)
    return {"ranked_flights": ranked}


def generate_google_flights_url(departure_id, arrival_id, date_str, return_date=None):
    base = "https://www.google.com/travel/flights"
    if return_date:
        q = f"Flights from {departure_id} to {arrival_id} on {date_str} returning {return_date}"
    else:
        q = f"Flights from {departure_id} to {arrival_id} on {date_str} one way"
    return f"{base}?q={quote(q)}"


def explain_node(state):
    flights_to_explain = state.get("ranked_flights", []) or state.get("flights", [])
    user_input = state.get("user_query", "")

    if not flights_to_explain:
        return {"explanation": "No flights found.", "explanation_data": None}

    best_flight = flights_to_explain[0]
    alternatives = flights_to_explain[1:5]

    dep = best_flight.get('from_airport', '')
    arr = best_flight.get('to_airport', '')

    raw_date = best_flight.get('departure_time', '')
    date_str = raw_date.split('T')[0] if 'T' in raw_date else raw_date.split(' ')[0]

    # ✅ FIX: read return_date from STATE, not from the flight object
    # The flight object only has outbound leg data — return_date was never stored there
    return_date = state.get("return_date")  # None for one-way, "YYYY-MM-DD" for round-trip

    booking_url = generate_google_flights_url(dep, arr, date_str, return_date)

    try:
        recommendation = ExplanationAgent().run(best_flight, alternatives, booking_url, user_input)
        recommendation.booking_url = booking_url  # override LLM-generated URL with the real one
    except Exception as e:
        logger.error("ExplanationAgent failed: %s", e)
        fallback_data = FlightRecommendation(
            summary="I found some great flights for you!",
            best_flight_reasoning="This flight was selected based on your search criteria.",
            top_choice_details=f"{best_flight.get('airline')} - ₹{best_flight.get('price')}",
            alternatives_table="Please refer to the search results for more options.",
            travel_tip="Always check airline baggage policies before booking.",
            booking_url=booking_url
        )
        return {
            "explanation": "I found flights, but I had a display error. See details below.",
            "explanation_data": fallback_data
        }

    return {
        "explanation": recommendation.summary,
        "explanation_data": recommendation
    }