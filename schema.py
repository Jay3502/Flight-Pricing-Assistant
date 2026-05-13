from pydantic import BaseModel
from typing import List


class Segment(BaseModel):
    from_airport: str
    to_airport: str
    departure: str
    arrival: str


class Flight(BaseModel):
    flight_id: str
    airline: str
    flight_number: str
    price_inr: int
    segments: List[Segment]
    duration_minutes: int
    stops: int
    baggage: str
    source: str
    confidence: float