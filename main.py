import logging
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CallbackQueryHandler
from telegram.request import HTTPXRequest      # <─ добавили
from database import init_db
from handlers import conv_handler, mod_approve, mod_reject

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    init_db()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Нет TELEGRAM_BOT_TOKEN")
        return

    # --- создаём объект HTTPXRequest с увеличенными таймаутами ---
    # connect_timeout – время установки соединения,
    # read_timeout    – общее ожидание ответа (увеличьте при больших медиагруппах)
    request = HTTPXRequest(connect_timeout=30, read_timeout=120)

    # --- инициализация приложения с кастомным request ---
    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)          # <─ важная строка
        .build()
    )

    app.bot_data["MOD_CHAT_ID"] = os.getenv("MOD_CHAT_ID")

    # --- основной диалог ---
    app.add_handler(conv_handler)

    # --- кнопки модератора ---
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_ok:"))
    app.add_handler(CallbackQueryHandler(mod_reject,  pattern=r"^mod_no:"))

    logger.info("Bot started…")
    app.run_polling()

if __name__ == "__main__":
    main()
