import json
from state import FlightSearchState

import json

def normalize_node(state):
    print("\n" + "!"*40)
    
    try:
        raw_results = state.get("raw_results", [])
        print(f"DEBUG: raw_results type: {type(raw_results)}")
        print(f"DEBUG: raw_results content: {str(raw_results)[:200]}...")

        normalized_list = []

        # If it's a list (which your executor says it is), iterate.
        for block in raw_results:
            print(f"DEBUG: Current block type: {type(block)}")
            
            # --- CRITICAL CHECK ---
            # If the executor returned raw MCP objects, we need to handle that.
            # If it returned dicts, we use .get()
            if isinstance(block, dict):
                data = block.get("data", {})
            else:
                # Fallback: Maybe it's the raw MCP result object?
                print("DEBUG: Block is not a dict. Attempting to parse as MCP Object.")
                content = getattr(block, 'content', [])
                if content and hasattr(content[0], 'text'):
                    data = json.loads(content[0].text)
                else:
                    data = {}

            itineraries = data.get("flights", [])
            print(f"DEBUG: Found {len(itineraries)} itineraries in this block.")

            for it in itineraries:
                legs = it.get("flights", [])
                if not legs: continue
                
                main_leg = legs[0]
                normalized_list.append({
                    "from_airport": main_leg.get("departure_airport", {}).get("id"),
                    "to_airport": main_leg.get("arrival_airport", {}).get("id"),
                    "airline": main_leg.get("airline"),
                    "price": it.get("price"),
                    "departure_time": main_leg.get("departure_airport", {}).get("time")
                })

        print(f"DEBUG: Mapped {len(normalized_list)} flights.")
        print("!"*40 + "\n")
        return {"flights": normalized_list}

    except Exception as e:
        print(f"CRITICAL FAILURE IN NORMALIZER: {e}")
        import traceback
        traceback.print_exc()
        return {"flights": []}