import os
import random
import base64
import logging
import sqlite3
import tempfile
from datetime import datetime
import subprocess
from gtts import gTTS
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = 766751955

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """Ти НейроТіп — саркастичний бот без фільтрів. Коментуєш коротко, влучно, смішно.

Техніки (чергуй кожного разу):
- Помітити деталь яку всі пропустили ("одна кросівка — бо на дві не вистачило")
- Зробити логічний але абсурдний висновок ("їж печінку — алкоголь не зрозуміє яку атакувати")
- Перевернути ситуацію проти автора ("Єва піде гуляти сама")
- Зробити математику/факт який вбиває ("їм буде 974 роки")
- Одне слово-вирок: "Єблан", "Жах", "Сочувствую", "Виходжу"

Формат відповіді:
- 1 повідомлення: одне коротке речення або одне слово
- 2-3 повідомлення через "|||": перше — факт/погодження, друге — добивання
- Ніколи не пиши більше 2-3 коротких речень

Правила:
- ТІЛЬКИ українська мова
- Розмовна, без пафосу
- Мат — тільки якщо реально смішно і влучно
- Ніяких "можливо", "мабуть", довгих пояснень
- Щоразу новий підхід"""

VOICE_PROMPT = """Подивись на це фото і дай ОДНУ коротку фразу (3-7 слів) українською для голосового повідомлення.
Фраза має бути смішна, груба або абсурдна — як реакція людини яка побачила щось дивне.
Приклади стилю: "шо за хуйня тут відбувається", "мамо рідна", "я такого не замовляв", "виходжу з чату", "господи боже мій".
Відповідай ТІЛЬКИ фразою, без лапок і пояснень."""


def init_db():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            message_count INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_messages INTEGER DEFAULT 0,
            total_photos INTEGER DEFAULT 0
        )
    """)
    c.execute("INSERT OR IGNORE INTO stats (id, total_messages, total_photos) VALUES (1, 0, 0)")
    conn.commit()
    conn.close()


def track_user(user_id: int, username: str, first_name: str) -> bool:
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    is_new = c.fetchone() is None
    c.execute("""
        INSERT INTO users (user_id, username, first_name, first_seen, last_seen, message_count)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET
            last_seen = ?,
            message_count = message_count + 1
    """, (user_id, username, first_name, now, now, now))
    conn.commit()
    conn.close()
    return is_new


def track_message(is_photo: bool = False):
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    if is_photo:
        c.execute("UPDATE stats SET total_messages = total_messages + 1, total_photos = total_photos + 1 WHERE id = 1")
    else:
        c.execute("UPDATE stats SET total_messages = total_messages + 1 WHERE id = 1")
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect("stats.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT total_messages, total_photos FROM stats WHERE id = 1")
    row = c.fetchone()
    total_messages = row[0] if row else 0
    total_photos = row[1] if row else 0
    c.execute("SELECT COUNT(*) FROM users WHERE last_seen >= date('now', '-1 day')")
    active_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE last_seen >= date('now', '-7 days')")
    active_week = c.fetchone()[0]
    conn.close()
    return total_users, total_messages, total_photos, active_today, active_week


async def generate_voice(phrase: str) -> bytes:
    tts = gTTS(text=phrase, lang="uk")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_file:
        tts.save(mp3_file.name)
        mp3_path = mp3_file.name
    ogg_path = mp3_path.replace(".mp3", ".ogg")
    subprocess.run(
        ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", ogg_path, "-y"],
        check=True, capture_output=True
    )
    os.unlink(mp3_path)
    with open(ogg_path, "rb") as f:
        data = f.read()
    os.unlink(ogg_path)
    return data


async def send_reply(message, text: str):
    parts = [p.strip() for p in text.split("|||") if p.strip()]
    for part in parts:
        await message.reply_text(part)


async def notify_new_user(context: ContextTypes.DEFAULT_TYPE, user):
    username = f"@{user.username}" if user.username else "без username"
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🐹 Новий користувач!\n👤 {user.first_name} ({username})\n🆔 {user.id}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = track_user(user.id, user.username or "", user.first_name or "")
    if is_new:
        await notify_new_user(context, user)
    await update.message.reply_text(
        "Привіт, я НейроТіп 🐹\nКидай фото або пиши що хочеш — прокоментую як вмію."
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total_users, total_messages, total_photos, active_today, active_week = get_stats()
    text = (
        f"📊 Статистика НейроТіпа\n\n"
        f"👥 Всього користувачів: {total_users}\n"
        f"💬 Всього повідомлень: {total_messages}\n"
        f"🖼 З них фото: {total_photos}\n"
        f"🔥 Активних сьогодні: {active_today}\n"
        f"📅 Активних за тиждень: {active_week}"
    )
    await update.message.reply_text(text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    is_new = track_user(user.id, user.username or "", user.first_name or "")
    if is_new:
        await notify_new_user(context, user)
    track_message(is_photo=True)
    caption = message.caption or ""

    photo = message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    b64_image = base64.b64encode(file_bytes).decode("utf-8")

    user_content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
    ]
    if caption:
        user_content.append({"type": "text", "text": caption})

    try:
        # Текстова відповідь
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=200,
        )
        reply = response.choices[0].message.content
        await send_reply(message, reply)

        # Голосове — 100% для тесту
        if True:
            try:
                voice_response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": VOICE_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=30,
                )
                phrase = voice_response.choices[0].message.content.strip()
                logger.info(f"Generating voice: {phrase}")
                voice_data = await generate_voice(phrase)
                await message.reply_voice(voice=voice_data)
            except Exception as ve:
                logger.error(f"Voice error: {ve}")

    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text("Хомяк тимчасово в нірці, спробуй пізніше 🐹")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = track_user(user.id, user.username or "", user.first_name or "")
    if is_new:
        await notify_new_user(context, user)
    track_message(is_photo=False)
    text = update.message.text

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=200,
        )
        reply = response.choices[0].message.content
        await send_reply(update.message, reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Хомяк тимчасово в нірці, спробуй пізніше 🐹")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("НейроТіп запущений 🐹")
    app.run_polling()


if __name__ == "__main__":
    main()
