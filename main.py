import telegram
print("PTB VERSION:", telegram.__version__)

import logging
import os
from dotenv import load_dotenv

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
)
from telegram.request import HTTPXRequest

from database import init_db
from handlers import conv_handler, mod_approve, mod_reject

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 🔥 ТЕСТ: если это не срабатывает — webhook не доходит
async def test_start(update, context):
    logger.info("🔥 /start received")
    await update.message.reply_text("Бот жив и принимает апдейты ✅")


def main():
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", 8080))

    if not token:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return

    if not webhook_url:
        logger.error("❌ Нет WEBHOOK_URL")
        return

    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=120,
    )

    app: Application = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .build()
    )

    # 🔥 ОБЯЗАТЕЛЬНЫЙ ТЕСТОВЫЙ ХЕНДЛЕР
    app.add_handler(CommandHandler("start", test_start), group=0)

    # Основной диалог
    app.add_handler(conv_handler)

    # Модерация
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_ok:"))
    app.add_handler(CallbackQueryHandler(mod_reject, pattern=r"^mod_no:"))

    logger.info("🚀 Bot starting with webhook…")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="webhook",        # ← путь ТОЛЬКО здесь
        webhook_url=webhook_url,   # ← БЕЗ /webhook
    )


if __name__ == "__main__":
    main()
