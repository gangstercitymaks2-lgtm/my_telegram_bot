import logging
import os
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from database import init_db
from handlers import conv_handler, mod_approve, mod_reject

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_webhook(app):
    """Настройка вебхука при старте"""
    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", 8080))

    if not webhook_url:
        logger.error("❌ Не указан WEBHOOK_URL в Railway ENV")
        return

    # Удаляем старый вебхук
    await app.bot.delete_webhook(drop_pending_updates=True)

    # Ставим новый
    ok = await app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query"],
    )

    if ok:
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    else:
        logger.error("❌ Ошибка установки webhook")

    # Запуск веб-сервера
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="",   # бот принимает на / (корень)
        webhook_url=webhook_url,
    )

    logger.info(f"🌍 Webhook сервер запущен на порту {port}")


def main():
    init_db()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ Нет TELEGRAM_BOT_TOKEN в ENV")
        return

    request = HTTPXRequest(connect_timeout=30, read_timeout=120)

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .post_init(init_webhook)     # <── webhook запускается автоматически!
        .build()
    )

    app.bot_data["MOD_CHAT_ID"] = os.getenv("MOD_CHAT_ID")

    # основной диалог
    app.add_handler(conv_handler)

    # кнопки модератора
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_ok:"))
    app.add_handler(CallbackQueryHandler(mod_reject, pattern=r"^mod_no:"))

    logger.info("🚀 Bot starting with webhook…")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path="",
    )


if __name__ == "__main__":
    main()
