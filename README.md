RR4 Telegram Bot (python-telegram-bot v22.4)
------------------------------------------
Files included:
- main.py          (entrypoint)
- handlers.py      (wizard + moderation ConversationHandler)
- database.py      (sqlite helper for drafts)
- keyboards.py     (keyboards used in wizard)
- .env.example
- requirements.txt

Setup:
1. Copy .env.example -> .env and fill values (BOT_TOKEN, CHANNEL_ID, MOD_CHAT_ID).
2. Create a virtualenv and install requirements:
   python -m venv venv
   venv\Scripts\activate   (Windows) or source venv/bin/activate
   pip install -r requirements.txt
3. Run the bot:
   python main.py

Notes:
- Make sure to give your bot permission to send messages and post in the channel.
- This project is a functional skeleton; you can extend validation, error handling and database as needed.
