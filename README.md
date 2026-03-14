# DroxClaw

Telegram bot with a LangGraph agent: webhook or polling, optional GitHub/email integrations, and custom skills.

## Setup

1. **Clone and enter the project** (paths are resolved from the project directory; avoid moving the repo without recreating the venv).

2. **Create a virtual environment at the current path** (required if you moved the repo or see path errors):

   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Do not edit `.venv` in place to fix old paths; recreate it so all paths point to the current project root.

3. **Configure environment:** Copy `.env.example` to `.env` and set at least `TELEGRAM_BOT_TOKEN` and `OLLAMA_API_KEY`. See `.env.example` for optional vars.

4. **Run:**

   ```bash
   python main.py
   ```

## Features

- FastAPI app (webhook endpoint at `/webhook`, optional `/health`)
- LangGraph agent with SQLite memory, Python REPL, file tools, DuckDuckGo (via skills), optional GitHub and email tools
- Heartbeat to admin chat when `ADMIN_CHAT_ID` is set
- Custom skills: add modules under `skills/` with a `get_tools()` function

## Recreating the virtual environment

If the project was cloned from another machine or moved (e.g. from `C:\Users\dustin\droxclaw` to `C:\Users\droxa\droxclaw`), the existing `.venv` may contain hardcoded paths. Recreate it:

1. Remove or rename the existing `.venv` folder.
2. From the project root, run: `python -m venv .venv`, activate it, then `pip install -r requirements.txt`.

This ensures scripts and activation use the current project path.
