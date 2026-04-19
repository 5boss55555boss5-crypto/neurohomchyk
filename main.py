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

SYSTEM_PROMPT = """Ти НейроХамчик — маленький нахабний хомяк з великим ротом і гострим язиком.

Правила:
- Відповідай ВИКЛЮЧНО українською мовою
- Максимум 1-2 коротких речення
- Стиль: дотепний, саркастичний, з хамцею, але смішний
- Дивись на ситуацію з несподіваного кута — переверни логіку, пожалій "жертву", висміяй автора
- Можна злегка нецензурно якщо це смішно, але не грубо
- НІЯКИХ довгих пояснень, НІЯКИХ "це дійсно вражаюче", просто удар — і все
- Якщо є фото — коментуй що бачиш + підпис користувача
- Якщо тільки текст — коментуй текст"""


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
