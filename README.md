# Flight Pricing AI Assistant

An AI-powered flight search assistant using LangGraph, Groq, SerpAPI, and Streamlit.

## Setup

1. Clone the repo
```bash
   git clone https://github.com/YOUR_USERNAME/flight-pricing-assistant.git
   cd flight-pricing-assistant
```

2. Create a virtual environment
```bash
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # Mac/Linux
```

3. Install dependencies
```bash
   pip install -r requirements.txt
```

4. Add your API keys
```bash
   cp .env.example .env
   # Edit .env and add your real keys
```

5. Run the MCP server (Terminal 1)
```bash
   python run_mcp_server.py
```

6. Run the app (Terminal 2)
```bash
   streamlit run streamlit_app.py
```

## Keys needed
- `SERP_API_KEY` from [serpapi.com](https://serpapi.com)
- `GROQ_API_KEY` from [console.groq.com](https://console.groq.com)