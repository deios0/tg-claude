import json
import logging
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select

from app.config import load_config
from app.database import get_session
from app.models import Conversation, Fact, Reminder
from app.tools import TOOLS

logger = logging.getLogger(__name__)


async def _load_context(user_id: int) -> str:
    """Load facts and pending reminders for the user."""
    async with get_session() as session:
        result = await session.execute(
            select(Fact).where(Fact.user_id == user_id).order_by(Fact.created_at.desc())
        )
        facts = result.scalars().all()

        result = await session.execute(
            select(Reminder)
            .where(Reminder.user_id == user_id, Reminder.sent == False)
            .order_by(Reminder.due_at)
        )
        reminders = result.scalars().all()

    parts = []
    if facts:
        facts_text = "\n".join(f"- [{f.category}] {f.fact}" for f in facts)
        parts.append(f"Known facts about the user:\n{facts_text}")
    if reminders:
        reminders_text = "\n".join(
            f"- {r.text} (due: {r.due_at.isoformat()})" for r in reminders
        )
        parts.append(f"Pending reminders:\n{reminders_text}")

    return "\n\n".join(parts)


async def _load_history(user_id: int, limit: int = 10) -> list[dict]:
    """Load last N messages from conversation history."""
    async with get_session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))

    return [{"role": r.role, "content": r.content} for r in rows]


async def _save_message(user_id: int, role: str, content: str):
    """Save a message to conversation history."""
    async with get_session() as session:
        session.add(Conversation(user_id=user_id, role=role, content=content))
        await session.commit()


async def _execute_tool(name: str, params: dict, user_id: int) -> str:
    """Execute a tool and return the result as a JSON string."""
    async with get_session() as session:
        if name == "save_fact":
            fact = Fact(
                user_id=user_id,
                category=params.get("category", "general"),
                fact=params["fact"],
            )
            session.add(fact)
            await session.commit()
            return json.dumps({"status": "saved", "id": fact.id})

        elif name == "create_reminder":
            reminder = Reminder(
                user_id=user_id,
                text=params["text"],
                due_at=datetime.fromisoformat(params["due_at"]),
            )
            session.add(reminder)
            await session.commit()
            return json.dumps(
                {"status": "created", "id": reminder.id, "due_at": params["due_at"]}
            )

        elif name == "get_reminders":
            result = await session.execute(
                select(Reminder)
                .where(Reminder.user_id == user_id, Reminder.sent == False)
                .order_by(Reminder.due_at)
            )
            reminders = result.scalars().all()
            items = [
                {"id": r.id, "text": r.text, "due_at": r.due_at.isoformat()}
                for r in reminders
            ]
            return json.dumps({"reminders": items, "count": len(items)})

    return json.dumps({"error": f"Unknown tool: {name}"})


async def chat_response(user_message: str, user_id: int) -> tuple[str, list[dict]]:
    """
    Send a message to Claude with tools enabled.

    Returns (response_text, tool_calls) where tool_calls is a list of
    {"name": str, "result": dict} for tracking undo-able actions.
    """
    config = load_config()
    client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    # 1. Load context
    context = await _load_context(user_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 2. Build system prompt
    system_parts = [config.system_prompt, f"\nCurrent time: {now}"]
    if context:
        system_parts.append(f"\n{context}")
    system_parts.append(
        "\nYou have tools available. Use them when appropriate — don't ask "
        "for confirmation, just act.\n"
        "When the user shares personal information, save it as a fact.\n"
        "When the user asks to be reminded of something, create a reminder."
    )
    system = "\n".join(system_parts)

    # 3. Load history + append new message
    history = await _load_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]

    # 4. Save user message to DB
    await _save_message(user_id, "user", user_message)

    # 5. Call Claude
    response = await client.messages.create(
        model=config.model,
        system=system,
        messages=messages,
        tools=TOOLS,
        max_tokens=4000,
    )

    # 6. Tool use loop
    tool_calls = []
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, block.input)
                result = await _execute_tool(block.name, block.input, user_id)
                tool_calls.append({"name": block.name, "result": json.loads(result)})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = await client.messages.create(
            model=config.model,
            system=system,
            messages=messages,
            tools=TOOLS,
            max_tokens=4000,
        )

    # 7. Extract final text
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # 8. Save assistant response
    if text:
        await _save_message(user_id, "assistant", text)

    return text, tool_calls
