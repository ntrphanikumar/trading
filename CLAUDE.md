# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Conversational AI trading assistant for the DhanHQ broker. Uses Gemini 2.5 Flash (Vertex AI) with function calling to interpret natural language trading commands and execute them via the `dhanhq` Python SDK. Three interfaces: CLI, Telegram bot (with voice support), and web UI. Includes an LLM-driven daily SIP, real-time market data via TradingView, price alerts with Telegram notifications, and automatic Dhan token renewal via TOTP.

## Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the CLI trading assistant
cd app && python cli.py

# Run the Telegram bot
cd app && python telegram_bot.py

# Run the web UI
cd app && python web.py

# Run the daily SIP (cron-scheduled)
cd app && python sip.py

# Run alert checker standalone
cd app && python alerts.py          # continuous checker
cd app && python alerts.py check    # one-shot check
cd app && python alerts.py update   # send market update to Telegram
```

## Architecture

```
User input (text/voice) → Gemini 2.5 Flash (function calling + thinking) → Trading functions (dhanhq SDK) → Dhan API
                                                                          → web_search → separate Gemini call with Google Search grounding
                                                                          → get_quote / get_market_overview → TradingView (real-time prices + technicals)
                                                                          → alerts → alerts.json + Telegram notifications
```

### Core Modules (all in `app/`)

**Shared infrastructure:**
- **gemini.py** — Shared Gemini (Vertex AI) client singleton, MODEL constant, `extract_text()` helper.
- **tools.py** — Shared tool declarations, function registry (`FUNCTIONS` dict), `CONFIRM_REQUIRED` set, `SYSTEM_INSTRUCTION`, `make_gemini_config()`, `execute_function()`. All 18 tool definitions for Gemini function calling live here.
- **client.py** — Singleton `dhanhq` client with automatic TOTP-based token renewal. Decodes JWT to check expiry, generates fresh token via `pyotp` + Dhan auth API when needed, persists to `.env`.
- **notify.py** — `send_telegram()` helper for sending messages via Telegram Bot API.

**Chat interfaces (all use shared gemini.py + tools.py):**
- **cli.py** — Terminal chat interface. Input loop with confirmation prompts for trade actions.
- **telegram_bot.py** — Telegram bot with long polling. Supports text and voice messages (sends OGG audio directly to Gemini as multimodal input). Runs alert checker as background daemon thread.
- **web.py** — Flask web UI with chat and SIP history tabs. Session-based conversations with confirmation flow via JSON API.

**Trading functions:**
- **stocks.py** — Stock name → security_id lookup from `stocks.json` (~115 stocks/ETFs).
- **orders.py** — Order placement (market/limit), order book, pending orders, cancellation.
- **portfolio.py** — Holdings, positions, fund limits.
- **market_data.py** — Real-time quotes and technical indicators (RSI, MACD, EMAs, Bollinger Bands, ADX, ATR) via TradingView. Also provides market overview for major Indian indices.
- **alerts.py** — Price alerts persisted to `alerts.json`. Background checker (5-min interval) sends Telegram notifications when triggered. Also provides on-demand market + portfolio updates.

**SIP:**
- **sip.py** — LLM-driven daily SIP. Uses Gemini 3.1 Flash Preview with Google Search grounding to decide ETF allocation based on market conditions. Cron-scheduled at 3:26 PM on trading days. Budget carry-forward on holidays.

### Key Design Decisions
- **Confirmation gate**: `place_market_order`, `place_limit_order`, `cancel_order` always require user confirmation before execution. Read-only operations execute immediately.
- **Two-config routing**: Vertex AI doesn't support function calling + Google Search grounding in a single request. Chat interfaces use function calling only; when Gemini needs web data, it calls `web_search()` which makes a separate grounded API call.
- **TOTP token auto-renewal**: Dhan tokens expire every 24 hours. `client.py` checks JWT expiry and auto-generates a new token using TOTP secret + trading PIN via Dhan's auth API.
- **Voice support**: Telegram bot sends OGG audio bytes directly to Gemini as `Part.from_bytes()` — no separate transcription step. Gemini handles speech understanding + function calling in one pass.
- **SIP strategy**: "Buy the dip, rebalance smart" — LLM checks real-time market conditions and portfolio allocation to decide daily ETF purchases within configurable budget.

### Configuration
- `app/.env` — DhanHQ credentials (`client_id`, `access_token`, `dhan_client_id`, `dhan_totp_secret`, `dhan_trading_pin`), `daily_sip_budget`, Google/Vertex AI settings (`google_service_account`, `google_project_id`, `google_location`), Telegram settings (`telegram_bot_token`, `telegram_chat_id`)
- `app/stocks.json` — Stock name to security ID mapping
- `app/alerts.json` — Active price alerts (auto-managed)
- `app/sip_history.json` — SIP trade history
- `app/sip_budget.json` — Holiday carry-forward budget

### Dependencies
- `dhanhq` — Official DhanHQ broker SDK
- `google-genai` — Google Gen AI SDK (Vertex AI / Gemini)
- `python-dotenv` — Environment variable loading
- `flask` — Web UI
- `pyotp` — TOTP generation for Dhan token renewal
- `PyJWT` — JWT decoding for token expiry checks
- `tradingview-ta` — Real-time market data and technical indicators
