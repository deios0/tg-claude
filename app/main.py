import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.config import load_config
from app.database import get_session, init_db
from app.handlers import handle_callback_query, handle_message, handle_start
from app.models import Reminder

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def check_reminders(bot):
    """Check for due reminders and send them."""
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        result = await session.execute(
            select(Reminder).where(Reminder.sent == False, Reminder.due_at <= now)
        )
        reminders = result.scalars().all()
        for reminder in reminders:
            try:
                await bot.send_message(
                    chat_id=reminder.user_id,
                    text=f"Reminder: {reminder.text}",
                )
                reminder.sent = True
            except Exception as e:
                logger.error("Failed to send reminder %d: %s", reminder.id, e)
        await session.commit()


def main():
    config = load_config()

    app = ApplicationBuilder().token(config.telegram_bot_token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Post-init: DB + scheduler
    async def post_init(application):
        await init_db()
        logger.info("Database initialized")

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            check_reminders,
            IntervalTrigger(seconds=60),
            args=[application.bot],
        )
        scheduler.start()
        logger.info("Reminder scheduler started (every 60s)")

    app.post_init = post_init

    logger.info("Starting bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
