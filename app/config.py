import os
from dataclasses import dataclass


@dataclass
class Config:
    telegram_bot_token: str
    anthropic_api_key: str
    bot_name: str
    system_prompt: str
    database_url: str
    model: str


def load_config() -> Config:
    return Config(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        bot_name=os.environ.get("BOT_NAME", "Assistant"),
        system_prompt=os.environ.get(
            "SYSTEM_PROMPT",
            "You are a helpful personal assistant. Be concise and friendly.",
        ),
        database_url=os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/bot.db"),
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
    )
