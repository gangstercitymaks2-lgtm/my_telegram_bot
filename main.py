import logging
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CallbackQueryHandler
from telegram.request import HTTPXRequest
from database import init_db
from handlers import conv_handler, mod_approve, mod_reject

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def post_init(app):
    """Вызывается автоматически после запуска приложения"""
    webhook_url = os.getenv("WEBHOOK_URL")
    await app.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

def main():
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN")
        return

    request = HTTPXRequest(connect_timeout=30, read_timeout=120)

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Данные модерации
    app.bot_data["MOD_CHAT_ID"] = os.getenv("MOD_CHAT_ID")

    # Основной диалог
    app.add_handler(conv_handler)

    # Модерация
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_ok:"))
    app.add_handler(CallbackQueryHandler(mod_reject, pattern=r"^mod_no:"))

    logger.info("🚀 Bot starting with webhook…")

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path="",                        # URL path (пусть пустой)
        webhook_url=os.getenv("WEBHOOK_URL")
    )


if __name__ == "__main__":
    main()
