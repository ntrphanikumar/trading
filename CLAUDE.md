# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Conversational AI trading assistant for the DhanHQ broker. Uses Gemini 2.5 Flash (Vertex AI) with function calling to interpret natural language trading commands and execute them via the `dhanhq` Python SDK. Includes an LLM-driven daily SIP that uses Google Search grounding for market-aware ETF allocation.

## Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the trading assistant
cd app && python cli.py
```

## Architecture

```
User input → Gemini 2.5 Flash (function calling + thinking) → Trading functions (dhanhq SDK) → Dhan API
                                                             → web_search → separate Gemini call with Google Search grounding
```

### Core Modules (all in `app/`)
- **cli.py** — Main entry point. Gemini chat loop with function calling. Web search via separate grounded API call (Vertex AI doesn't allow combining function calling + Google Search in one request).
- **sip.py** — LLM-driven daily SIP. Uses Gemini 3.1 Flash with Google Search grounding to decide ETF allocation based on market conditions. Cron-scheduled at 3:26 PM on trading days.
- **client.py** — Singleton `dhanhq` client initialization from `.env` credentials.
- **stocks.py** — Stock name → security_id lookup from `stocks.json` (~115 stocks/ETFs).
- **orders.py** — Order placement (market/limit), order book, pending orders, cancellation.
- **portfolio.py** — Holdings, positions, fund limits.

### Key Design Decisions
- **Confirmation gate**: `place_market_order`, `place_limit_order`, `cancel_order` always require user y/n before execution. Read-only operations execute immediately.
- **Two-config routing**: Vertex AI doesn't support function calling + Google Search grounding in a single request. `cli.py` uses function calling only; when Gemini needs web data, it calls `web_search()` which makes a separate grounded API call.
- **SIP strategy**: "Buy the dip, rebalance smart" — LLM checks real-time market conditions and portfolio allocation to decide daily ETF purchases within Rs 2000 budget.

### Configuration
- `app/.env` — DhanHQ credentials (`client_id`, `access_token`), `daily_sip_budget`, Google/Vertex AI settings
- `app/stocks.json` — Stock name to security ID mapping

### Dependencies
- `dhanhq` — Official DhanHQ broker SDK
- `google-genai` — Google Gen AI SDK (Vertex AI / Gemini)
- `python-dotenv` — Environment variable loading
