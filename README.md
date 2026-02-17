# Telegram + Claude Starter

Minimal but complete Telegram bot with Claude tool use. Clone, configure, launch.

3 demo tools included: **save_fact**, **create_reminder**, **get_reminders** — demonstrating write, time-based, and read patterns.

## Quick Start

### 1. Get API Keys

**Telegram Bot Token:**
1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow prompts (pick a name and username)
3. Copy the token (looks like `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`)

**Anthropic API Key:**
1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an account or sign in
3. Go to **API Keys** → **Create Key**
4. Copy the key (starts with `sk-ant-`)

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in:
```
TELEGRAM_BOT_TOKEN=your-token-from-botfather
ANTHROPIC_API_KEY=sk-ant-your-key
```

### 3. Run

**Option A — Local (Python 3.10+):**
```bash
pip install -r requirements.txt
python -m app.main
```

**Option B — Docker:**
```bash
docker compose up --build
```

### 4. Test

1. Open your bot in Telegram
2. Send `/start`
3. Say "remember that I like coffee" → bot saves a fact
4. Say "remind me in 5 minutes to take a break" → bot sets a reminder
5. Say "show my reminders" → bot lists pending reminders
6. Wait 5 min → bot sends the reminder proactively

## Architecture

```
┌─────────────┐         ┌───────────────────┐         ┌─────────┐
│  Telegram    │ polling │  app/             │         │ Claude  │
│  (user)      ├────────►│  handlers.py      │         │ API     │
│              │◄────────┤  chat.py          ├────────►│ (tools) │
└─────────────┘  reply   │  tools.py         │◄────────┤         │
                         └─────────┬─────────┘         └─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  SQLite (aiosqlite)│
                         │  users, facts,     │
                         │  reminders,        │
                         │  conversations     │
                         └───────────────────┘
```

### Data Flow

```
User: "remember that I like hiking"
  → handlers.py receives message
  → chat.py builds context (facts + reminders + last 10 messages)
  → Claude API call with tools
  → Claude decides: tool_use → save_fact(category="hobby", fact="likes hiking")
  → chat.py executes tool → INSERT INTO facts
  → Claude receives result → generates text response
  → handlers.py sends reply to Telegram
```

### Files

| File | Purpose |
|------|---------|
| `app/main.py` | Entry point — starts bot + reminder scheduler |
| `app/config.py` | Settings from environment variables |
| `app/database.py` | Async SQLAlchemy + SQLite setup |
| `app/models.py` | DB models: User, Fact, Reminder, Conversation |
| `app/chat.py` | Claude API call with tool use loop |
| `app/tools.py` | Tool definitions (JSON Schema) |
| `app/handlers.py` | Telegram handlers: /start, messages, callbacks |

### Key Design Choices

- **SQLite** via aiosqlite — zero config. Swap to PostgreSQL by changing `DATABASE_URL`
- **Polling** not webhook — works locally without a domain
- **Conversation history** stored in DB, last 10 messages loaded per Claude call
- **Reminder scheduler** checks every 60 seconds, sends due reminders proactively
- **System prompt** configurable via `.env`

## How to Add a Custom Tool

### Step 1: Define the Tool Schema

Add to `app/tools.py`:

```python
TOOLS = [
    # ... existing tools ...
    {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name",
                },
            },
            "required": ["city"],
        },
    },
]
```

### Step 2: Add the Handler

Add to `app/chat.py` inside `_execute_tool()`:

```python
elif name == "get_weather":
    city = params["city"]
    # Call a weather API, query DB, or compute anything
    weather = await fetch_weather(city)
    return json.dumps({"city": city, "temp": weather.temp, "condition": weather.condition})
```

### Step 3: Done

Claude reads the tool's `description` and `input_schema` and decides when to call it. No routing logic needed — Claude figures out intent from the conversation.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | From @BotFather |
| `ANTHROPIC_API_KEY` | Yes | — | From console.anthropic.com |
| `BOT_NAME` | No | `Assistant` | Bot display name |
| `SYSTEM_PROMPT` | No | Generic assistant | Claude's system prompt |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-5-20250929` | Claude model ID |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///data/bot.db` | SQLAlchemy async URL |

## Switching to PostgreSQL

```bash
pip install asyncpg
```

In `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/botdb
```

No code changes needed — SQLAlchemy handles the rest.

## Stack

| Layer | Technology |
|-------|-----------|
| AI | Claude API (Anthropic Python SDK) |
| Bot | python-telegram-bot v20+ |
| DB | SQLAlchemy 2.x async + SQLite |
| Scheduler | APScheduler |
| Deploy | Docker Compose |
