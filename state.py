from typing import TypedDict, List, Dict, Any, Optional


class FlightSearchState(TypedDict, total=False):
    user_query: str
    tool_plan: List[Dict[str, Any]]
    raw_results: List[Any]
    flights: List[Any]
    ranked_flights: List[Any]
    explanation: str
    explanation_data: Any
    return_date: Optional[str]