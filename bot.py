import os
import json
import time
import sqlite3
import mimetypes
import requests
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KIE_API_KEY = os.getenv("KIE_API_KEY")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден!")
if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден!")
if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден!")
if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден!")

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

DB_PATH = "/var/data/users.db"
MAIN_MENU_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/xena-2-bot/51586486d72bc1529924833288dadc53daa8e09c/main_menu.jpg"
MAIN_CHANNEL_URL = "https://t.me/Xena18H"
SUPPORT_URL = "https://t.me/Vlad101ss"
BOT_RETURN_URL = "https://t.me/Xena18Bot"

ADMIN_IDS = {6164104276}

VIDEO_PRICES = {
    "5": 98,
    "10": 147,
    "15": 196,
}

TOPUP_AMOUNTS = [250, 500, 1000, 5000]

user_states = {}


# =========================
# КЛАВИАТУРЫ
# =========================

def navigation_keyboard(buttons, back_callback="main_menu"):
    keyboard = list(buttons)
    keyboard.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)])
    keyboard.append([InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def back_to_menu_keyboard(back_callback="main_menu"):
    return navigation_keyboard([], back_callback=back_callback)


def main_inline_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Создать ВИДЕО", callback_data="create_video")],
        [InlineKeyboardButton("🖼 Создать ИЗОБРАЖЕНИЕ", callback_data="create_image")],
        [InlineKeyboardButton("🎵 Создать АУДИО", callback_data="create_audio")],
        [InlineKeyboardButton("💳 ПОПОЛНИТЬ БАЛАНС", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("🤝 Партнерка", callback_data="partner")],
        [InlineKeyboardButton("💼 Кабинет партнера", callback_data="partner_profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Поддержка", url=SUPPORT_URL)],
    ])


def topup_inline_menu():
    return navigation_keyboard(
        [[InlineKeyboardButton(f"{amount} ₽", callback_data=f"topup_{amount}")]
         for amount in TOPUP_AMOUNTS],
        back_callback="main_menu"
    )


def video_models_menu():
    return navigation_keyboard([
        [InlineKeyboardButton("🎬 Seedance 2.0", callback_data="model_seedance_2")],
        [InlineKeyboardButton("🧠 Grok Imagine Video 1.5", callback_data="model_grok_imagine_15")],
        [InlineKeyboardButton("⚡ Kling 3.0 Turbo", callback_data="model_kling_30_turbo")],
        [InlineKeyboardButton("🐎 HappyHorse-1.1", callback_data="model_happyhorse_11")],
        [InlineKeyboardButton("🎞 Wan 2.7 Video", callback_data="model_wan_27_video")],
        [InlineKeyboardButton("💎 Gemini Omni", callback_data="model_gemini_omni")],
        [InlineKeyboardButton("🌊 Hailuo 2.3", callback_data="model_hailuo_23")],
        [InlineKeyboardButton("🎥 Veo 3.1", callback_data="model_veo_31")],
    ], back_callback="main_menu")


def seedance_modes_menu():
    return navigation_keyboard([
        [InlineKeyboardButton("🎥 Текст → Видео", callback_data="seedance_text_video")],
        [InlineKeyboardButton("🖼 Картинка → Видео", callback_data="seedance_image_video")],
        [InlineKeyboardButton("🖼🎬 Картинка + Видео → Видео", callback_data="seedance_image_video_to_video")],
    ], back_callback="create_video")


def audio_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("🔊 Сгенерировать AI-звук", callback_data="seedance_audio_ai")],
        [InlineKeyboardButton("🎵 Добавить своё аудио", callback_data="seedance_audio_custom")],
        [InlineKeyboardButton("🔇 Без звука", callback_data="seedance_audio_off")],
    ], back_callback=back_callback)


def resolution_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("480p", callback_data="seedance_resolution_480p")],
        [InlineKeyboardButton("720p", callback_data="seedance_resolution_720p")],
        [InlineKeyboardButton("1080p", callback_data="seedance_resolution_1080p")],
        [InlineKeyboardButton("4K", callback_data="seedance_resolution_4K")],
    ], back_callback=back_callback)


def aspect_ratio_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("16:9", callback_data="seedance_aspect_16_9")],
        [InlineKeyboardButton("4:3", callback_data="seedance_aspect_4_3")],
        [InlineKeyboardButton("1:1", callback_data="seedance_aspect_1_1")],
        [InlineKeyboardButton("3:4", callback_data="seedance_aspect_3_4")],
        [InlineKeyboardButton("9:16", callback_data="seedance_aspect_9_16")],
        [InlineKeyboardButton("21:9", callback_data="seedance_aspect_21_9")],
    ], back_callback=back_callback)


def duration_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("5 секунд", callback_data="seedance_duration_5")],
        [InlineKeyboardButton("10 секунд", callback_data="seedance_duration_10")],
        [InlineKeyboardButton("15 секунд", callback_data="seedance_duration_15")],
    ], back_callback=back_callback)


def generate_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="seedance_generate")]
    ], back_callback=back_callback)


# =========================
# БАЗА ДАННЫХ
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            free_used INTEGER DEFAULT 0,
            paid_credits INTEGER DEFAULT 0
        )
    """)

    for sql in [
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ref_mode TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN partner_balance INTEGER DEFAULT 0",
    ]:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT free_used, paid_credits FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, free_used, paid_credits) VALUES (?, 0, 0)",
            (user_id,)
        )
        conn.commit()
        free_used, paid_credits = 0, 0
    else:
        free_used, paid_credits = row

    conn.close()
    return free_used, paid_credits


def save_username(user_id: int, username):
    if not username:
        return

    username = username.lower()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, free_used, paid_credits, username) VALUES (?, 0, 0, ?)",
        (user_id, username)
    )
    cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))

    conn.commit()
    conn.close()


def get_user_id_by_username(username: str):
    username = username.replace("@", "").lower()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()

    return row[0] if row else None


def give_balance(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, free_used, paid_credits) VALUES (?, 0, 0)",
        (user_id,)
    )
    cur.execute(
        "UPDATE users SET paid_credits = paid_credits + ? WHERE user_id = ?",
        (amount, user_id)
    )

    conn.commit()
    conn.close()


def decrement_paid_credit(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET paid_credits = paid_credits - ? WHERE user_id = ? AND paid_credits >= ?",
        (amount, user_id, amount)
    )

    conn.commit()
    conn.close()


def set_referrer(user_id: int, referrer_id: int, ref_mode: str):
    if user_id == referrer_id:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row and row[0]:
        conn.close()
        return

    cur.execute(
        "UPDATE users SET referrer_id = ?, ref_mode = ? WHERE user_id = ?",
        (referrer_id, ref_mode, user_id)
    )

    conn.commit()
    conn.close()


def get_referrer(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT referrer_id, ref_mode FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return 0, ""

    return row[0] or 0, row[1] or ""


def add_partner_money(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET partner_balance = partner_balance + ? WHERE user_id = ?",
        (amount, user_id)
    )

    conn.commit()
    conn.close()


def get_partner_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT partner_balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    return row[0] if row else 0


def apply_deposit_bonus(user_id: int, amount: int):
    referrer_id, _ = get_referrer(user_id)
    if referrer_id:
        add_partner_money(referrer_id, int(amount * 0.7))


def get_all_partners():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id, username, partner_balance
        FROM users
        WHERE partner_balance > 0
        ORDER BY partner_balance DESC
    """)
    rows = cur.fetchall()
    conn.close()

    return rows


def reset_partner_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET partner_balance = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# =========================
# KIE / SEEDANCE
# =========================

def kie_headers(json_content=False):
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def upload_file_to_kie(file_path: str, upload_path: str = "xena-bot") -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"
    path = Path(file_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    with open(file_path, "rb") as f:
        files = {"file": (path.name, f, mime_type)}
        data = {
            "uploadPath": upload_path,
            "fileName": path.name,
        }
        response = requests.post(
            url,
            headers=kie_headers(),
            files=files,
            data=data,
            timeout=3600
        )

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки файла в Kie: {result}")

    return result["data"]["downloadUrl"]


def create_seedance_video_task(settings: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    input_data = {
        "prompt": settings.get("prompt", ""),
        "generate_audio": bool(settings.get("generate_audio", False)),
        "resolution": settings.get("resolution", "480p"),
        "aspect_ratio": settings.get("aspect_ratio", "9:16"),
        "duration": int(settings.get("duration", "5")),
    }

    if settings.get("first_frame_url"):
        input_data["first_frame_url"] = settings["first_frame_url"]

    if settings.get("last_frame_url"):
        input_data["last_frame_url"] = settings["last_frame_url"]

    if settings.get("reference_image_urls"):
        input_data["reference_image_urls"] = settings["reference_image_urls"]

    if settings.get("reference_video_urls"):
        input_data["reference_video_urls"] = settings["reference_video_urls"]

    if settings.get("reference_audio_urls"):
        input_data["reference_audio_urls"] = settings["reference_audio_urls"]

    payload = {
        "model": "bytedance/seedance-2",
        "input": input_data
    }

    response = requests.post(
        url,
        headers=kie_headers(json_content=True),
        json=payload,
        timeout=3600
    )
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания задачи Seedance: {result}")

    return result["data"]["taskId"]


def wait_kie_video_result(task_id: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"

    for _ in range(360):
        response = requests.get(
            url,
            headers=kie_headers(),
            params={"taskId": task_id},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        data = result.get("data", {})
        state = data.get("state")

        if state == "success":
            result_json_raw = data.get("resultJson")
            result_json = json.loads(result_json_raw) if isinstance(result_json_raw, str) else (result_json_raw or {})

            video_urls = (
                result_json.get("resultUrls")
                or result_json.get("videoUrls")
                or result_json.get("videos")
                or result_json.get("urls")
                or []
            )

            if not video_urls:
                raise RuntimeError(f"Видео готово, но ссылка не найдена: {result_json}")

            return video_urls[0]

        if state == "fail":
            raise RuntimeError(f"Kie не смог сгенерировать видео: {data.get('failMsg')}")

        time.sleep(10)

    raise RuntimeError("Видео генерировалось слишком долго. Попробуйте позже.")


def download_video(video_url: str, user_id: int) -> str:
    video_path = MEDIA_DIR / f"{user_id}_seedance_result.mp4"

    response = requests.get(video_url, timeout=3600)
    response.raise_for_status()

    with open(video_path, "wb") as f:
        f.write(response.content)

    return str(video_path)


def generate_seedance_video(settings: dict, user_id: int) -> str:
    task_id = create_seedance_video_task(settings)
    video_url = wait_kie_video_result(task_id)
    return download_video(video_url, user_id)


# =========================
# YOOKASSA
# =========================

def create_yookassa_payment(user_id: int, amount: int):
    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": f"topup_{user_id}_{amount}_{int(time.time())}",
        "Content-Type": "application/json"
    }

    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": BOT_RETURN_URL
        },
        "description": f"Пополнение баланса Telegram-бота на {amount} рублей",
        "metadata": {
            "user_id": str(user_id),
            "amount": str(amount)
        }
    }

    response = requests.post(
        url,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        headers=headers,
        json=payload,
        timeout=60
    )

    response.raise_for_status()
    result = response.json()

    return result["confirmation"]["confirmation_url"], result["id"]


def check_yookassa_payment(payment_id: str) -> bool:
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"

    response = requests.get(
        url,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=60
    )

    response.raise_for_status()
    result = response.json()

    return result.get("status") == "succeeded"


# =========================
# ОБЩИЕ СООБЩЕНИЯ
# =========================

async def send_main_menu(target):
    caption = (
        f"Наш канал (ГАЛЕРЕЯ + ПРОМПТЫ):\n{MAIN_CHANNEL_URL}\n\n"
        f"Подпишись, чтобы нас не потерять!"
    )

    if hasattr(target, "reply_photo"):
        await target.reply_photo(
            photo=MAIN_MENU_PHOTO,
            caption=caption,
            reply_markup=main_inline_menu()
        )
    else:
        await target.send_photo(
            photo=MAIN_MENU_PHOTO,
            caption=caption,
            reply_markup=main_inline_menu()
        )


async def send_not_ready(chat, title="Этот раздел"):
    await chat.send_message(
        f"{title} пока в разработке.\n\n"
        "Сейчас подключаем Seedance 2.0.",
        reply_markup=back_to_menu_keyboard(back_callback="create_video")
    )


async def start_seedance_prompt(chat, user_id: int, mode: str):
    user_states[user_id] = {
        "model": "seedance_2",
        "mode": mode,
        "step": "waiting_prompt",
    }

    await chat.send_message(
        "✍️ Добавьте описание видео.\n\n"
        "Напишите, что должно происходить в ролике.",
        reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
    )


async def ask_seedance_image(chat, user_id: int, mode: str):
    user_states[user_id] = {
        "model": "seedance_2",
        "mode": mode,
        "step": "waiting_image",
    }

    await chat.send_message(
        "🖼 Отправьте изображение.\n\n"
        "Можно отправить JPG, PNG, WEBP или обычное фото из Telegram.",
        reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
    )


async def ask_seedance_video(chat, user_id: int):
    user_states[user_id]["step"] = "waiting_video"

    await chat.send_message(
        "🎬 Отправьте исходное видео.\n\n"
        "Поддерживаются короткие видео до 15 секунд.",
        reply_markup=back_to_menu_keyboard(back_callback="seedance_image_video_to_video")
    )


async def ask_seedance_prompt_after_files(chat, user_id: int):
    user_states[user_id]["step"] = "waiting_prompt"

    await chat.send_message(
        "✍️ Добавьте описание видео.\n\n"
        "Напишите, что должно происходить в ролике.",
        reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
    )


async def ask_seedance_audio(chat, user_id: int):
    user_states[user_id]["step"] = "choose_audio"

    mode = user_states[user_id].get("mode")
    if mode == "text_to_video":
        back_callback = "seedance_text_video"
    elif mode == "image_to_video":
        back_callback = "seedance_image_video"
    else:
        back_callback = "seedance_image_video_to_video"

    await chat.send_message(
        "🎵 Выберите звук:",
        reply_markup=audio_menu(back_callback=back_callback)
    )


async def ask_seedance_custom_audio(chat, user_id: int):
    user_states[user_id]["step"] = "waiting_audio"

    await chat.send_message(
        "🎵 Отправьте своё аудио.\n\n"
        "Можно отправить аудиофайл, голосовое сообщение или видео со звуком.",
        reply_markup=back_to_menu_keyboard(back_callback="seedance_audio_ai")
    )


async def ask_seedance_resolution(chat, user_id: int):
    user_states[user_id]["step"] = "choose_resolution"

    await chat.send_message(
        "📺 Выберите разрешение:",
        reply_markup=resolution_menu(back_callback="seedance_audio_ai")
    )


async def ask_seedance_aspect(chat, user_id: int):
    user_states[user_id]["step"] = "choose_aspect_ratio"

    await chat.send_message(
        "📐 Выберите формат видео:",
        reply_markup=aspect_ratio_menu(back_callback="seedance_resolution_720p")
    )


async def ask_seedance_duration(chat, user_id: int):
    user_states[user_id]["step"] = "choose_duration"

    await chat.send_message(
        "⏱ Выберите длительность:",
        reply_markup=duration_menu(back_callback="seedance_aspect_9_16")
    )


async def ask_seedance_generate(chat, user_id: int):
    user_states[user_id]["step"] = "ready_to_generate"
    settings = user_states[user_id]

    audio_text = {
        "ai": "AI-звук",
        "custom": "своё аудио",
        "off": "без звука",
    }.get(settings.get("audio_mode"), "без звука")

    await chat.send_message(
        "✅ Всё готово.\n\n"
        f"Нейросеть: Seedance 2.0\n"
        f"Звук: {audio_text}\n"
        f"Разрешение: {settings.get('resolution')}\n"
        f"Формат: {settings.get('aspect_ratio')}\n"
        f"Длительность: {settings.get('duration')} сек\n\n"
        "Нажмите кнопку ниже, чтобы создать видео.",
        reply_markup=generate_menu(back_callback="seedance_duration_5")
    )


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_username(user_id, update.message.from_user.username)
    get_user(user_id)

    if context.args:
        ref_code = context.args[0]
        if ref_code.startswith("partner_"):
            referrer_id = int(ref_code.replace("partner_", ""))
            set_referrer(user_id, referrer_id, "bonus")

    await send_main_menu(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_username(user_id, update.message.from_user.username)

    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Используй:\n/give USER_ID СУММА\n\nПример:\n/give 123456789 98"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Ошибка формата.")
        return

    give_balance(target_id, amount)
    await update.message.reply_text(f"✅ Пользователю {target_id} выдано {amount} ₽")


async def giveuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Используй:\n/giveuser @username СУММА\n\nПример:\n/giveuser @username 98"
        )
        return

    username = context.args[0]

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Ошибка суммы.")
        return

    target_id = get_user_id_by_username(username)

    if target_id is None:
        await update.message.reply_text(
            "❌ Пользователь не найден.\n"
            "Он должен сначала написать боту /start."
        )
        return

    give_balance(target_id, amount)
    await update.message.reply_text(f"✅ @{username.replace('@', '')} выдано {amount} ₽")


async def partners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    rows = get_all_partners()

    if not rows:
        await update.message.reply_text("Партнёров с балансом нет.")
        return

    text = "💼 Партнёрские выплаты:\n\n"

    for user_id, username, balance in rows:
        name = username or "без username"
        text += f"ID: {user_id}\n@{name}\nК выплате: {balance} ₽\n\n"

    await update.message.reply_text(text)


async def paypartner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Используй:\n/paypartner USER_ID")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ошибка ID.")
        return

    reset_partner_balance(target_id)
    await update.message.reply_text(f"✅ Партнёрский баланс {target_id} обнулён.")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Выберите сумму пополнения:",
        reply_markup=topup_inline_menu()
    )


# =========================
# INLINE-КНОПКИ
# =========================

async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data
    chat = query.message.chat

    try:
        await query.message.delete()
    except Exception:
        pass

    if action == "main_menu":
        user_states.pop(user_id, None)
        await send_main_menu(chat)
        return

    if action == "create_video":
        await chat.send_message(
            "Выберите нейросеть для генерации видео:",
            reply_markup=video_models_menu()
        )
        return

    if action == "model_seedance_2":
        await chat.send_message(
            "🎬 Seedance 2.0\n\nВыберите режим генерации:",
            reply_markup=seedance_modes_menu()
        )
        return

    if action in [
        "model_grok_imagine_15",
        "model_kling_30_turbo",
        "model_happyhorse_11",
        "model_wan_27_video",
        "model_gemini_omni",
        "model_hailuo_23",
        "model_veo_31",
    ]:
        await send_not_ready(chat)
        return

    if action == "seedance_text_video":
        await start_seedance_prompt(chat, user_id, mode="text_to_video")
        return

    if action == "seedance_image_video":
        await ask_seedance_image(chat, user_id, mode="image_to_video")
        return

    if action == "seedance_image_video_to_video":
        await ask_seedance_image(chat, user_id, mode="image_video_to_video")
        return

    if action in ["seedance_audio_ai", "seedance_audio_custom", "seedance_audio_off"]:
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        if action == "seedance_audio_ai":
            user_states[user_id]["audio_mode"] = "ai"
            user_states[user_id]["generate_audio"] = True
            await ask_seedance_resolution(chat, user_id)
            return

        if action == "seedance_audio_custom":
            user_states[user_id]["audio_mode"] = "custom"
            user_states[user_id]["generate_audio"] = False
            await ask_seedance_custom_audio(chat, user_id)
            return

        user_states[user_id]["audio_mode"] = "off"
        user_states[user_id]["generate_audio"] = False
        await ask_seedance_resolution(chat, user_id)
        return

    if action.startswith("seedance_resolution_"):
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        resolution = action.replace("seedance_resolution_", "")
        user_states[user_id]["resolution"] = resolution
        await ask_seedance_aspect(chat, user_id)
        return

    if action.startswith("seedance_aspect_"):
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        aspect = action.replace("seedance_aspect_", "").replace("_", ":")
        user_states[user_id]["aspect_ratio"] = aspect
        await ask_seedance_duration(chat, user_id)
        return

    if action.startswith("seedance_duration_"):
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        duration = action.replace("seedance_duration_", "")
        user_states[user_id]["duration"] = duration
        await ask_seedance_generate(chat, user_id)
        return

    if action == "seedance_generate":
        await handle_seedance_generate(chat, user_id)
        return

    if action.startswith("checkpay_"):
        parts = action.split("_")
        payment_id = parts[1]
        amount = int(parts[2])

        try:
            paid = check_yookassa_payment(payment_id)
        except Exception as e:
            await chat.send_message(
                f"❌ Не удалось проверить оплату:\n\n{e}",
                reply_markup=back_to_menu_keyboard(back_callback="buy")
            )
            return

        if not paid:
            await chat.send_message(
                "⏳ Оплата пока не найдена.\n\n"
                "Если ты уже оплатил — подожди 10–20 секунд и нажми кнопку ещё раз.",
                reply_markup=navigation_keyboard([
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
                ], back_callback="buy")
            )
            return

        give_balance(user_id, amount)
        apply_deposit_bonus(user_id, amount)
        _, paid_credits = get_user(user_id)

        await chat.send_message(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽.",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action.startswith("topup_"):
        amount = int(action.replace("topup_", ""))
        payment_url, payment_id = create_yookassa_payment(user_id, amount)

        await chat.send_message(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            f"1. Нажмите «Оплатить»\n"
            f"2. После оплаты вернитесь сюда\n"
            f"3. Нажмите «✅ Проверить оплату»",
            reply_markup=navigation_keyboard([
                [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
                [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
            ], back_callback="buy")
        )
        return

    if action == "buy":
        await chat.send_message(
            "💳 Выберите сумму пополнения:",
            reply_markup=topup_inline_menu()
        )
        return

    if action == "profile":
        _, paid_credits = get_user(user_id)

        await chat.send_message(
            f"👤 Твой баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Стоимость видео:\n"
            f"5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"10 секунд — {VIDEO_PRICES['10']} ₽\n"
            f"15 секунд — {VIDEO_PRICES['15']} ₽",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action == "partner":
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        await chat.send_message(
            "🤝 Партнерка\n\n"
            "За каждого приведенного активного пользователя вы получаете 70% от каждого его депозита "
            "на свой бонусный счёт.\n\n"
            "Ваша реферальная ссылка:\n"
            f"https://t.me/{bot_username}?start=partner_{user_id}",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action == "partner_profile":
        partner_balance = get_partner_balance(user_id)

        await chat.send_message(
            f"💼 Кабинет партнера\n\n"
            f"Бонусный счет: {partner_balance} бонусов\n\n"
            f"1 бонус = 1 ₽.",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action == "help":
        await chat.send_message(
            "📘 Инструкция\n\n"
            "1. Выберите, что хотите создать.\n"
            "2. Выберите нейросеть.\n"
            "3. Следуйте шагам бота: загрузите файлы, добавьте описание и выберите настройки.\n"
            "4. Нажмите «Создать видео» и дождитесь результата.",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action == "create_image":
        await chat.send_message(
            "🖼 Создание изображений пока в разработке.",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return

    if action == "create_audio":
        await chat.send_message(
            "🎵 Создание аудио пока в разработке.",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )
        return


async def handle_seedance_generate(chat, user_id: int):
    if user_id not in user_states:
        await chat.send_message(
            "Сначала настройте генерацию.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    settings = user_states[user_id]
    duration = settings.get("duration", "5")

    if duration not in VIDEO_PRICES:
        await chat.send_message(
            "⏱ Для выбранной длительности цена пока не настроена.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    video_cost = VIDEO_PRICES[duration]
    _, paid_credits = get_user(user_id)

    if paid_credits < video_cost:
        await chat.send_message(
            f"💳 Недостаточно средств.\n\n"
            f"Стоимость: {video_cost} ₽\n"
            f"Ваш баланс: {paid_credits} ₽",
            reply_markup=navigation_keyboard([
                [InlineKeyboardButton("💳 ПОПОЛНИТЬ БАЛАНС", callback_data="buy")]
            ], back_callback="model_seedance_2")
        )
        return

    await chat.send_message(
        "🎬 Запускаю Seedance 2.0.\n\n"
        "Генерация может занять несколько минут."
    )

    try:
        video_path = generate_seedance_video(settings, user_id)
        decrement_paid_credit(user_id, video_cost)

        with open(video_path, "rb") as video_file:
            await chat.send_video(
                video=video_file,
                caption="✅ Готово! Вот твоё видео.",
                read_timeout=3600,
                write_timeout=3600,
                connect_timeout=60,
                pool_timeout=3600
            )

        _, paid_credits_after = get_user(user_id)

        await chat.send_message(
            f"Баланс: {paid_credits_after} ₽",
            reply_markup=back_to_menu_keyboard(back_callback="main_menu")
        )

    except Exception as e:
        import traceback
        print("SEEDANCE_GENERATION_ERROR:", repr(e))
        traceback.print_exc()

        await chat.send_message(
            "❌ Ошибка генерации Seedance 2.0.\n\n"
            "Если ошибка повторяется — напишите в поддержку:\n"
            f"{SUPPORT_URL}",
            disable_web_page_preview=True,
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )

    user_states.pop(user_id, None)


# =========================
# ВХОДЯЩИЕ ФАЙЛЫ И ТЕКСТ
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_states:
        await update.message.reply_text(
            "Сначала выберите режим генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    state = user_states[user_id]
    step = state.get("step")

    if step != "waiting_image":
        await update.message.reply_text("Сейчас бот не ждёт изображение.")
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    image_url = upload_file_to_kie(str(image_path), upload_path="xena-bot/images")

    state["first_frame_url"] = image_url
    state.setdefault("reference_image_urls", []).append(image_url)

    if state.get("mode") == "image_video_to_video":
        await ask_seedance_video(update.message.chat, user_id)
    else:
        await ask_seedance_prompt_after_files(update.message.chat, user_id)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_states:
        await update.message.reply_text(
            "Сначала выберите режим генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    state = user_states[user_id]
    step = state.get("step")
    document = update.message.document

    file = await context.bot.get_file(document.file_id)
    safe_name = document.file_name or f"{user_id}_file"
    file_path = MEDIA_DIR / f"{user_id}_{int(time.time())}_{safe_name}"
    await file.download_to_drive(str(file_path))

    url = upload_file_to_kie(str(file_path), upload_path="xena-bot/files")
    mime = document.mime_type or mimetypes.guess_type(safe_name)[0] or ""

    if step == "waiting_image" and mime.startswith("image/"):
        state["first_frame_url"] = url
        state.setdefault("reference_image_urls", []).append(url)

        if state.get("mode") == "image_video_to_video":
            await ask_seedance_video(update.message.chat, user_id)
        else:
            await ask_seedance_prompt_after_files(update.message.chat, user_id)
        return

    if step == "waiting_video" and (mime.startswith("video/") or "quicktime" in mime or "matroska" in mime):
        state["reference_video_urls"] = [url]
        await ask_seedance_prompt_after_files(update.message.chat, user_id)
        return

    if step == "waiting_audio" and (mime.startswith("audio/") or mime.startswith("video/")):
        state["reference_audio_urls"] = [url]
        await ask_seedance_resolution(update.message.chat, user_id)
        return

    await update.message.reply_text(
        "Файл получен, но сейчас бот ждёт другой тип файла.",
        reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_states:
        await update.message.reply_text(
            "Сначала выберите режим генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    state = user_states[user_id]
    step = state.get("step")
    video = update.message.video

    file = await context.bot.get_file(video.file_id)
    video_path = MEDIA_DIR / f"{user_id}_{video.file_unique_id}.mp4"
    await file.download_to_drive(str(video_path))

    video_url = upload_file_to_kie(str(video_path), upload_path="xena-bot/videos")

    if step == "waiting_video":
        state["reference_video_urls"] = [video_url]
        await ask_seedance_prompt_after_files(update.message.chat, user_id)
        return

    if step == "waiting_audio":
        state["reference_audio_urls"] = [video_url]
        await ask_seedance_resolution(update.message.chat, user_id)
        return

    await update.message.reply_text("Сейчас бот не ждёт видео.")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_states:
        await update.message.reply_text(
            "Сначала выберите режим генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    state = user_states[user_id]
    step = state.get("step")

    if step != "waiting_audio":
        await update.message.reply_text("Сейчас бот не ждёт аудио.")
        return

    audio = update.message.audio or update.message.voice
    file = await context.bot.get_file(audio.file_id)

    ext = "ogg" if update.message.voice else "mp3"
    audio_path = MEDIA_DIR / f"{user_id}_{audio.file_unique_id}.{ext}"
    await file.download_to_drive(str(audio_path))

    audio_url = upload_file_to_kie(str(audio_path), upload_path="xena-bot/audio")
    state["reference_audio_urls"] = [audio_url]

    await ask_seedance_resolution(update.message.chat, user_id)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if text == "🚀 Запустить бота":
        await send_main_menu(update.message)
        return

    if user_id in user_states and user_states[user_id].get("step") == "waiting_prompt":
        user_states[user_id]["prompt"] = text
        await ask_seedance_audio(update.message.chat, user_id)
        return

    await update.message.reply_text(
        "Выберите действие в меню.",
        reply_markup=back_to_menu_keyboard(back_callback="main_menu")
    )


# =========================
# ЗАПУСК
# =========================

def main():
    init_db()

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(60)
        .read_timeout(3600)
        .write_timeout(3600)
        .pool_timeout(3600)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(CommandHandler("giveuser", giveuser))
    app.add_handler(CommandHandler("partners", partners))
    app.add_handler(CommandHandler("paypartner", paypartner))

    app.add_handler(CallbackQueryHandler(menu_button))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
