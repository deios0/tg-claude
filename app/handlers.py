import logging

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.chat import chat_response
from app.database import get_session
from app.models import Reminder, User

logger = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — create user and send welcome message."""
    user = update.effective_user
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        if not result.scalar_one_or_none():
            session.add(User(telegram_id=user.id, name=user.full_name))
            await session.commit()

    await update.message.reply_text(
        f"Hi {user.first_name}! I'm your AI assistant powered by Claude.\n\n"
        "I can:\n"
        "- Remember things about you\n"
        "- Set reminders\n"
        "- Have natural conversations\n\n"
        "Just message me!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    user = update.effective_user
    text = update.message.text

    # Ensure user exists
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user.id)
        )
        if not result.scalar_one_or_none():
            session.add(User(telegram_id=user.id, name=user.full_name))
            await session.commit()

    # Typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response_text, tool_calls = await chat_response(text, user.id)
    except Exception:
        logger.exception("Error in chat_response")
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        return

    if not response_text:
        response_text = "(No response)"

    # Build undo buttons for create_reminder calls
    keyboard_buttons = []
    for call in tool_calls:
        if call["name"] == "create_reminder" and "id" in call["result"]:
            rid = call["result"]["id"]
            keyboard_buttons.append(
                [InlineKeyboardButton("Cancel reminder", callback_data=f"undo_reminder_{rid}")]
            )

    reply_markup = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    msg = await update.message.reply_text(response_text, reply_markup=reply_markup)

    # Auto-remove buttons after 60 seconds
    if reply_markup and context.job_queue:
        context.job_queue.run_once(
            _remove_keyboard,
            60,
            data={"chat_id": msg.chat_id, "message_id": msg.message_id},
        )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses (undo actions)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("undo_reminder_"):
        reminder_id = int(data.replace("undo_reminder_", ""))
        async with get_session() as session:
            result = await session.execute(
                select(Reminder).where(Reminder.id == reminder_id)
            )
            reminder = result.scalar_one_or_none()
            if reminder:
                await session.delete(reminder)
                await session.commit()
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("Reminder cancelled.")
            else:
                await query.edit_message_reply_markup(reply_markup=None)


async def _remove_keyboard(context: ContextTypes.DEFAULT_TYPE):
    """Remove inline keyboard from a message after timeout."""
    data = context.job.data
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=data["chat_id"],
            message_id=data["message_id"],
            reply_markup=None,
        )
    except Exception:
        pass  # Message may already have been edited
