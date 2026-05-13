import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)

class PlannerAgent:
    def __init__(self, tools):
        if not tools:
            logger.warning("No tools were loaded by ToolLoader!")
            self.llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
        else:
            self.llm = ChatGroq(
                model="openai/gpt-oss-120b",
                temperature=0,
            ).bind_tools(
                tools,
                tool_choice="required"
            )

    def run(self, query):
        # FIX 1: Dynamic date — was hardcoded to "January 26, 2026" which is now stale
        today = datetime.date.today()
        today_str = today.strftime("%A, %B %d, %Y")   # e.g. "Monday, May 11, 2026"
        today_iso = today.isoformat()                  # e.g. "2026-05-11"

        system_prompt = (
            f"You are a global Flight Systems Integrator. Today's date is {today_str}."

            "\n\n### PROTOCOL 1: IATA TRANSLATION"
            "\n- The target API strictly rejects full city names. Resolve every location to its 3-letter IATA code."
            "\n- Use the most high-traffic hub for ambiguous cities (e.g., 'London' -> 'LHR', 'New York' -> 'JFK', 'Delhi' -> 'DEL', 'Bangalore' -> 'BLR')."

            "\n\n### PROTOCOL 2: TEMPORAL ANCHORING"
            f"\n- Reference Date: {today_iso}."
            "\n- Use this to resolve relative dates ('next Tuesday', 'this weekend', 'day after tomorrow')."
            "\n- All dates must be formatted as 'YYYY-MM-DD'."

            "\n\n### PROTOCOL 3: ARGUMENT INTEGRITY"
            "\n- departure_id:  Must be 3 uppercase IATA letters."
            "\n- arrival_id:    Must be 3 uppercase IATA letters."
            "\n- outbound_date: Required. ISO 8601 date string (YYYY-MM-DD)."

            # FIX 2: return_date added — without this the LLM never passes it even
            # when the user clearly asks for a round trip / to-fro / return flight
            "\n- return_date:   Optional. Include ONLY when the user explicitly asks for a "
            "round-trip, return flight, to-fro, or two-way journey. "
            "Format: YYYY-MM-DD. Omit entirely for one-way searches."

            "\n\n### PROTOCOL 4: TRIP TYPE DETECTION"
            # FIX 3: Explicit round-trip vs one-way logic — previously missing entirely
            "\n- ONE-WAY:    User says 'one way', 'single', or gives only one date. "
            "Call search_flights with outbound_date only."
            "\n- ROUND-TRIP: User says 'round trip', 'return', 'to and fro', 'to-fro', "
            "'both ways', or gives two dates. "
            "Call search_flights with BOTH outbound_date AND return_date."
            "\n- AMBIGUOUS:  If trip type is unclear but two dates are mentioned, treat as round-trip."

            "\n\n### MISSION"
            f"\n- Analyze the user query: '{query}'"
            "\n- Identify: Origin, Destination, Outbound Date, and (if applicable) Return Date."
            "\n- Output ONLY the tool call for 'search_flights'. No conversational filler."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        response = self.llm.invoke(messages)

        tool_calls = response.tool_calls or []
        
        validated = []
        for call in tool_calls:
            args = call.get("args", {})
            dep = args.get("departure_id", "")
            arr = args.get("arrival_id", "")
            outbound = args.get("outbound_date", "")

            if len(dep) != 3 or len(arr) != 3:
                logger.error(
                    "PlannerAgent produced invalid IATA codes: dep=%s arr=%s — skipping call",
                    dep, arr
                )
                continue

            try:
                datetime.date.fromisoformat(outbound)
            except ValueError:
                logger.error(
                    "PlannerAgent produced invalid outbound_date: %s — skipping call", outbound
                )
                continue

            # return_date is optional — only validate format if it was provided
            return_date = args.get("return_date")
            if return_date:
                try:
                    datetime.date.fromisoformat(return_date)
                except ValueError:
                    logger.warning(
                        "PlannerAgent produced invalid return_date: %s — removing it", return_date
                    )
                    # Remove bad return_date rather than dropping the whole call
                    call["args"].pop("return_date")

            validated.append(call)

        return validated