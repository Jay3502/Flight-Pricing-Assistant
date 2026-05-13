import streamlit as st
import pandas as pd
import pydeck as pdk
import asyncio
import nest_asyncio
import logging
import traceback
from app import MCPClient, get_compiled_app
from tool_loader import ToolLoader
from agents.planner_agent import PlannerAgent
from tool_executor import ToolExecutor
import airportsdata

# ── LOGGING SETUP ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

nest_asyncio.apply()

# ── AIRPORT DATA ──────────────────────────────────────────────────────────────
try:
    airports_db = airportsdata.load('IATA')
except Exception as e:
    logger.error("Failed to load airports database: %s", e)
    airports_db = {}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_coords(iata_code: str) -> tuple:
    """Return (lat, lon) for an IATA code. Falls back to centre of India."""
    if not iata_code:
        return 20.5937, 78.9629

    code = str(iata_code).strip().upper()
    airport = airports_db.get(code)
    if airport:
        return airport['lat'], airport['lon']

    # Hardcoded fallbacks for common Indian routes
    defaults = {
        "DEL": (28.5562, 77.1000),
        "BLR": (13.1986, 77.7066),
        "VGA": (16.5304, 80.7967),
        "BOM": (19.0896, 72.8656),
        "HYD": (17.2403, 78.4294),
        "MAA": (12.9941, 80.1709),
        "CCU": (22.6520, 88.4463),
        "AMD": (23.0771, 72.6347),
        "COK": (10.1520, 76.3919),
        "PNQ": (18.5821, 73.9197),
    }
    return defaults.get(code, (20.5937, 78.9629))


def fmt_time(raw: str) -> str:
    """Extract HH:MM from ISO datetime strings or plain time strings."""
    if not raw or raw == "N/A":
        return "N/A"
    try:
        if 'T' in raw:
            return raw.split('T')[-1][:5]
        if ' ' in raw:
            return raw.split(' ')[-1][:5]
        return raw[:5]
    except Exception:
        return "N/A"


def fmt_price(price) -> str:
    """Safely format a price value as ₹ string."""
    try:
        return f"₹{int(price):,}"
    except (TypeError, ValueError):
        return "N/A"


def render_map(src_id: str, dst_id: str, is_round_trip: bool):
    """Render a pydeck ArcLayer map. Two arcs for round-trip, one for one-way."""
    src_lat, src_lon = get_coords(src_id)
    dst_lat, dst_lon = get_coords(dst_id)

    arcs = [{"start": [src_lon, src_lat], "end": [dst_lon, dst_lat],
              "color_s": [255, 100, 0, 180], "color_e": [0, 255, 200, 180]}]

    if is_round_trip:
        arcs.append({"start": [dst_lon, dst_lat], "end": [src_lon, src_lat],
                     "color_s": [0, 200, 255, 180], "color_e": [255, 150, 0, 180]})

    title = f"🌐 Round-Trip: {src_id} ✈️ {dst_id} ✈️ {src_id}" if is_round_trip \
            else f"🌐 Flight Path: {src_id} ✈️ {dst_id}"
    st.subheader(title)

    try:
        st.pydeck_chart(pdk.Deck(
            map_provider='carto',
            map_style='dark',
            initial_view_state=pdk.ViewState(
                latitude=(src_lat + dst_lat) / 2,
                longitude=(src_lon + dst_lon) / 2,
                zoom=3.8,
                pitch=45,
            ),
            layers=[
                pdk.Layer(
                    "ArcLayer",
                    data=pd.DataFrame(arcs),
                    get_source_position="start",
                    get_target_position="end",
                    get_source_color="color_s",
                    get_target_color="color_e",
                    get_width=6,
                )
            ]
        ))
    except Exception as e:
        logger.error("Map render failed: %s", e)
        st.warning("⚠️ Map could not be rendered.")


def render_flight_metrics(flight: dict, label: str, show_price: bool = True):
    """Render a single flight leg as a 4-column metrics row."""
    st.markdown(f"#### {label}  •  {flight.get('airline', 'Unknown')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fare (Total)" if show_price else "Fare", fmt_price(flight.get('price')) if show_price else "Included")
    c2.metric("Departs", fmt_time(flight.get('departure_time')))
    stops = flight.get('stops', 0)
    c3.metric("Route Type", "Direct ✅" if stops == 0 else f"{stops} Stop{'s' if stops > 1 else ''}")
    c4.metric("Flight No.", flight.get('flight_number', 'N/A'))


# ── ASYNC AGENT SESSION ───────────────────────────────────────────────────────

async def run_flight_agent_session(user_query: str) -> dict:
    """Connect to MCP server, run the full agent graph, return state."""
    mcp = MCPClient("http://localhost:8000/mcp")
    try:
        await mcp.connect()
    except Exception as e:
        raise ConnectionError(
            f"Could not connect to the MCP server at localhost:8000. "
            f"Make sure `python run_mcp_server.py` is running. Details: {e}"
        )

    try:
        tools = await ToolLoader(mcp, ["flight"]).load()
        if not tools:
            raise RuntimeError("No flight tools were loaded from the MCP server.")

        planner  = PlannerAgent(tools)
        executor = ToolExecutor(mcp)
        app      = get_compiled_app(planner, executor)
        result   = await app.ainvoke({"user_query": user_query})
        return result

    except ConnectionError:
        raise  # re-raise as-is so the UI can show the right message

    except Exception as e:
        logger.error("Agent session failed:\n%s", traceback.format_exc())
        raise RuntimeError(f"The flight agent encountered an error: {e}") from e

    finally:
        try:
            await mcp.close()
        except Exception:
            pass  # best-effort close; don't mask the original error


# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Smart Flight Assistant", page_icon="✈️", layout="wide")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f5; color: #1E1E1E !important; }
    h1, h2, h3, h4, p, span, label { color: #1E1E1E !important; font-family: 'Inter', sans-serif; }

    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        border: 1px solid #ffffff;
        transition: transform 0.2s ease;
    }
    div[data-testid="stMetric"]:hover { transform: translateY(-5px); }
    [data-testid="stMetricLabel"]  { color: #64748b !important; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; }
    [data-testid="stMetricValue"]  { color: #0f172a !important; font-weight: 800; font-size: 28px; }

    .stAlert {
        background-color: #ffffff !important;
        border-left: 5px solid #3b82f6 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .stChatMessage {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 20px;
        margin-bottom: 15px;
        padding: 15px;
    }
    .stLinkButton > a {
        background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%) !important;
        color: #ffffff !important;
        border-radius: 10px !important;
        padding: 12px 24px !important;
        font-weight: 700 !important;
        border: none !important;
        box-shadow: 0 4px 14px 0 rgba(59, 130, 246, 0.39) !important;
    }
    section[data-testid="stSidebar"] { background-color: #ffffff !important; }
    </style>
""", unsafe_allow_html=True)

# ── SESSION STATE INIT ────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/airplane-take-off.png", width=80)
    st.title("Search Control")
    st.markdown("Your AI-powered concierge for real-time flight intelligence.")

    if st.button("🗑️ Reset Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("v2.1.0 • Connected to Live GDS")

# ── MAIN UI ───────────────────────────────────────────────────────────────────
st.title("✈️ Smart Flight Assistant")

# Replay chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── CHAT INPUT ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Where to? (e.g., 'Round trip BLR to HYD on 1st June, returning 5th June')"):

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        # ── RUN AGENT ─────────────────────────────────────────────────────────
        state_result = None
        agent_error  = None

        with st.status("🛸 Scouting the skies for best deals...", expanded=True) as status:
            try:
                loop         = asyncio.get_event_loop()
                state_result = loop.run_until_complete(run_flight_agent_session(prompt))
                status.update(label="✅ Flight Intelligence Gathered", state="complete", expanded=False)

            except ConnectionError as e:
                agent_error = str(e)
                status.update(label="❌ MCP Server Unreachable", state="error", expanded=False)

            except RuntimeError as e:
                agent_error = str(e)
                status.update(label="❌ Agent Error", state="error", expanded=False)

            except Exception as e:
                agent_error = f"Unexpected error: {e}"
                logger.error("Unhandled exception in agent:\n%s", traceback.format_exc())
                status.update(label="❌ Unexpected Error", state="error", expanded=False)

        # ── SHOW ERROR IF AGENT FAILED ────────────────────────────────────────
        if agent_error:
            st.error(f"❌ {agent_error}")
            st.info("💡 **Tip:** Make sure `python run_mcp_server.py` is running in a separate terminal and your `.env` file contains valid API keys.")
            st.session_state.messages.append({"role": "assistant", "content": f"Error: {agent_error}"})
            st.stop()

        # ── VALIDATE STATE ────────────────────────────────────────────────────
        if not state_result:
            st.warning("⚠️ The agent returned an empty response. Please try again.")
            st.stop()

        # ── HANDLE EARLY EXPLANATION (e.g. "date too far", "can't parse query") 
        if state_result.get("explanation") and not state_result.get("explanation_data"):
            msg = state_result["explanation"]
            st.warning(f"🤖 {msg}")
            st.session_state.messages.append({"role": "assistant", "content": msg})
            st.stop()

        # ── HANDLE NO RESULTS ─────────────────────────────────────────────────
        if not state_result.get("explanation_data"):
            st.warning("😔 No flights found matching your criteria. Try different dates or a nearby airport.")
            st.session_state.messages.append({"role": "assistant", "content": "No flights found for that search."})
            st.stop()

        # ── EXTRACT DATA ──────────────────────────────────────────────────────
        try:
            data        = state_result["explanation_data"]
            ranked      = state_result.get("ranked_flights", [])

            if not ranked:
                st.warning("😔 No ranked flights available.")
                st.stop()

            top_f       = ranked[0]
            return_leg  = top_f.get("return_leg")   # None → one-way
            is_round    = return_leg is not None

            src_id = top_f.get('from_airport', '')
            dst_id = top_f.get('to_airport', '')

            if not src_id or not dst_id:
                st.error("❌ Airport data is missing from the flight results. Please try your search again.")
                logger.error("Missing airport IDs: from=%s to=%s", src_id, dst_id)
                st.stop()

        except (KeyError, IndexError, TypeError) as e:
            st.error(f"❌ Failed to read flight data: {e}")
            logger.error("Data extraction error:\n%s", traceback.format_exc())
            st.stop()

        # ── OUTBOUND LEG ──────────────────────────────────────────────────────
        st.markdown("### 🏆 Top Choice")
        render_flight_metrics(
            top_f,
            label=f"✈️ Outbound  {src_id} → {dst_id}",
            show_price=True
        )

        # ── RETURN LEG (round-trip only) ──────────────────────────────────────
        if is_round:
            st.write("---")
            try:
                render_flight_metrics(
                    return_leg,
                    label=f"🔄 Return  {return_leg.get('from_airport', dst_id)} → {return_leg.get('to_airport', src_id)}",
                    show_price=False
                )
            except Exception as e:
                logger.error("Return leg render failed: %s", e)
                st.warning("⚠️ Return leg details could not be displayed.")

        # ── MAP ───────────────────────────────────────────────────────────────
        st.write("---")
        render_map(src_id, dst_id, is_round)

        # ── AGENT ANALYSIS ────────────────────────────────────────────────────
        st.write("---")
        try:
            st.info(f"**Agent Analysis:** {data.best_flight_reasoning}")
        except Exception as e:
            logger.warning("Could not render agent analysis: %s", e)

        # ── BOOKING BUTTON ────────────────────────────────────────────────────
        try:
            booking_url = data.booking_url
            if booking_url and booking_url.startswith("http"):
                st.link_button("🚀 Secure This Price via Google Flights", booking_url, use_container_width=True)
            else:
                st.warning("⚠️ Booking link is unavailable for this result.")
        except Exception as e:
            logger.error("Booking URL render failed: %s", e)
            st.warning("⚠️ Could not display booking link.")

        # ── ALTERNATIVES ──────────────────────────────────────────────────────
        st.write("---")
        with st.expander("📂 View Alternatives"):
            try:
                alts = data.alternatives_table
                if alts and "|" in alts:
                    st.markdown(alts)
                else:
                    st.info("No alternative flights to display.")
            except Exception as e:
                logger.warning("Alternatives render failed: %s", e)
                st.info("Alternatives could not be loaded.")

        # ── TRAVEL TIP ────────────────────────────────────────────────────────
        try:
            if data.travel_tip:
                st.success(f"💡 **Traveler Tip:** {data.travel_tip}")
        except Exception as e:
            logger.warning("Travel tip render failed: %s", e)

        # ── UPDATE CHAT HISTORY ───────────────────────────────────────────────
        try:
            summary = data.summary or "Here are your flight results."
            st.session_state.messages.append({"role": "assistant", "content": summary})
        except Exception as e:
            logger.warning("Could not update chat history: %s", e)
            st.session_state.messages.append({"role": "assistant", "content": "Flight search complete."})