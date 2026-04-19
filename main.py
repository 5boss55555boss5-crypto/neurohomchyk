import os
import base64
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """Ти НейроХамчик. Відповідаєш ОДНИМ коротким реченням. Грубо, смішно, без зайвих слів.

Приклади:
Юзер: Що робити якщо друг не дивиться тік токи які я йому скидаю?
Ти: Усипити нахуй це животне.

Юзер: Фотограф 4 роки щодня сидів у річці заради цього підводного знімка бобра
Ти: Бобер 4 роки не міг потрапити додому через психа який його пасе.

Юзер: Я може й бухаю, але навіть в такому вигляді завжди підгодовую вуличних псів
Ти: Ведмідь схоже теж підбухує.

Правила:
- ТІЛЬКИ українська мова
- ОДНЕ речення, максимум два коротких
- Розмовна мова, без пафосу
- Мат можна якщо смішно
- Ніяких "можливо", "мабуть", метафор про крила і клітини"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт, я НейроХамчик 🐹\nКидай фото або пиши що хочеш — прокоментую як вмію."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    caption = message.caption or ""

    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    b64_image = base64.b64encode(file_bytes).decode("utf-8")

    user_content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
        }
    ]
    if caption:
        user_content.append({"type": "text", "text": caption})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=150,
        )
        reply = response.choices[0].message.content
        await message.reply_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("Хомяк тимчасово в нірці, спробуй пізніше 🐹")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=150,
        )
        reply = response.choices[0].message.content
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Хомяк тимчасово в нірці, спробуй пізніше 🐹")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("НейроХамчик запущений 🐹")
    app.run_polling()


if __name__ == "__main__":
    main()
