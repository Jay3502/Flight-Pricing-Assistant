from langchain_groq import ChatGroq
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage

class FlightRecommendation(BaseModel):
    summary: str = Field(description="A brief, professional overview of the flight options.")
    best_flight_reasoning: str = Field(description="Why this specific flight was chosen as the top pick.")
    top_choice_details: str = Field(description="Key details: Airline, Price, Departure Time, and Stops.")
    alternatives_table: str = Field(description="A Markdown table comparing the other options.")
    travel_tip: Optional[str] = Field(description="A helpful tip (e.g., baggage, check-in, or layover advice).")
    booking_url: str = Field(description="The direct Google Flights URL for this search.")

    @validator('booking_url')
    def validate_url(cls, v):
        if not v.startswith("https://www.google.com/travel/flights"):
            raise ValueError("Must be a Google Flights URL")
        return v

    @validator('alternatives_table')
    def validate_markdown(cls, v):
        if "|" not in v:
            return "No alternative flights found that match your criteria."
        return v

class ExplanationAgent:
    def __init__(self):
        # Set temperature to 0.0 for maximum consistency with structured output
        self.llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.0) 
        self.structured_llm = self.llm.with_structured_output(FlightRecommendation)

    def run(self, best, alts, booking_url, user_query): 
        query_lc = user_query.lower()
        has_nonstop_intent = "non-stop" in query_lc or "direct" in query_lc
        winner_is_nonstop = int(best.get('stops', 1)) == 0

        # System message forces the JSON constraint
        system_message = SystemMessage(content=(
            "You are a Senior Travel Consultant. You must respond ONLY with a "
            "valid JSON object based on the provided schema. Do not include "
            "any introductory text or explanations outside the JSON."
        ))

        # Human message contains your original prompt logic and data
        human_content = f"""
            User Query: "{user_query}"

            ### DATA TO PROCESS:
            - WINNER: {best}
            - RUNNERS_UP: {alts}
            - SEARCH_LINK: {booking_url}

            ### STRICT LOGIC RULES:
            1. CONSTRAINT SATISFACTION:
               - IF "{has_nonstop_intent}" is TRUE AND "{winner_is_nonstop}" is TRUE: Celebrate the perfect non-stop match.
               - IF "{has_nonstop_intent}" is TRUE BUT "{winner_is_nonstop}" is FALSE: Apologize and explain no non-stops were available.
            
            2. THE "NO-DUPLICATE" RULE:
               - Flight {best.get('flight_number')} is the WINNER. Do NOT list it in the Alternatives Table.

            3. THE "CHEAPEST" RULE:
               - Highlight the price difference if the user asked for the cheapest option.

            ### OUTPUT STRUCTURE:
            - Summary: Address "{user_query}" and include the link.
            - Best Flight Reasoning: Explain why winner satisfies conditions.
            - Alternatives Table: Valid Markdown. Tag non-stops with '✅ Non-stop'.
            - Travel Tip: Contextual advice.
        """
        
        human_message = HumanMessage(content=human_content)
        
        # Invoke with the message list
        return self.structured_llm.invoke([system_message, human_message])