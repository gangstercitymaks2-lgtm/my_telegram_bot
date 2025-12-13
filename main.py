import telegram
print("PTB VERSION:", telegram.__version__)

import logging
import os
from dotenv import load_dotenv

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest

from database import init_db
from handlers import conv_handler, mod_approve, mod_reject

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return

    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.error("❌ Нет WEBHOOK_URL")
        return

    port = int(os.getenv("PORT", 8080))

    # HTTPX с увеличенными таймаутами
    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=120,
        write_timeout=120,
    )

    # --- создаём приложение ---
    app: Application = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .build()
    )

    app.bot_data["MOD_CHAT_ID"] = os.getenv("MOD_CHAT_ID")

    # Основной диалог
    app.add_handler(conv_handler)

    # Модерация
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_ok:"))
    app.add_handler(CallbackQueryHandler(mod_reject, pattern=r"^mod_no:"))

    logger.info("🚀 Bot starting with webhook…")

    # --- ВАЖНО: webhook path ---
    WEBHOOK_PATH = "/webhook"

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=WEBHOOK_PATH,
        webhook_url=webhook_url + WEBHOOK_PATH,
    )


if __name__ == "__main__":
    main()
