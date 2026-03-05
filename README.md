# DhanHQ Trading Assistant

AI-powered conversational trading assistant for the Indian stock market (NSE) via DhanHQ broker. Powered by Google Gemini 3.1 Pro with function calling, thinking, and Google Search grounding.

## Features

- Natural language order placement: "buy 10 NIFTYBEES at market"
- Holdings, positions, and fund balance queries
- Stock search by name or symbol
- Order book and order cancellation
- Safety: all trade actions require explicit confirmation
- Google Search grounding for market news and analysis

## Setup

1. Install dependencies:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure `app/.env` with your DhanHQ credentials:
   ```
   client_id=your_client_id
   access_token=your_access_token
   ```

3. Place your Vertex AI service account JSON in `app/`.

4. Run:
   ```bash
   cd app && python cli.py
   ```

## Example Commands

- "Show my holdings"
- "What's my fund balance?"
- "Buy 5 shares of HDFCBANK at market"
- "Place a limit order for 10 NIFTYBEES at Rs 250"
- "Show pending orders"
- "Cancel order 123456"
- "Search for Infosys"
