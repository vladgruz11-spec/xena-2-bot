import os
import json
import time
import sqlite3
import mimetypes
import requests
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# ENV
# =========================

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


# =========================
# CONSTANTS
# =========================

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

DB_PATH = "/var/data/users.db"

MAIN_MENU_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/xena-2-bot/51586486d72bc1529924833288dadc53daa8e09c/main_menu.jpg"
MAIN_CHANNEL_URL = "https://t.me/Xena18H"
SUPPORT_URL = "https://t.me/Vlad101ss"

ADMIN_IDS = {6164104276}

# ВАЖНО:
# Это временные цены Seedance. Когда определишься со стоимостью разных режимов,
# меняй суммы здесь.
SEEDANCE_PRICES = {
    "text_to_video": {
        "5": 98,
        "10": 147,
        "15": 196,
    },
    "image_to_video": {
        "5": 98,
        "10": 147,
        "15": 196,
    },
    "image_video_to_video": {
        "5": 98,
        "10": 147,
        "15": 196,
    },
}

# Старые цены оставлены для совместимости с балансом/профилем
VIDEO_PRICES = {
    "5": 98,
    "10": 147,
    "15": 196,
}

# Состояния пользователей во время пошаговой генерации
user_states = {}


# =========================
# KEYBOARDS
# =========================

def navigation_keyboard(buttons, back_callback="main_menu"):
    buttons.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)])
    buttons.append([InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def back_to_menu_keyboard(back_callback="main_menu"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)],
        [InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ])


def main_inline_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Создать ВИДЕО", callback_data="create_video")],
        [InlineKeyboardButton("🖼 Создать ИЗОБРАЖЕНИЕ", callback_data="create_image")],
        [InlineKeyboardButton("🎵 Создать АУДИО", callback_data="create_audio")],
        [InlineKeyboardButton("💳 ПОПОЛНИТЬ БАЛАНС", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("🤝 Партнерка", callback_data="partner")],
        [InlineKeyboardButton("💼 Кабинет партнера", callback_data="partner_profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Поддержка", url=SUPPORT_URL)]
    ]
    return InlineKeyboardMarkup(keyboard)


def topup_inline_menu():
    keyboard = [
        [InlineKeyboardButton("250 ₽", callback_data="topup_250")],
        [InlineKeyboardButton("500 ₽", callback_data="topup_500")],
        [InlineKeyboardButton("1000 ₽", callback_data="topup_1000")],
        [InlineKeyboardButton("5000 ₽", callback_data="topup_5000")]
    ]
    return navigation_keyboard(keyboard, back_callback="main_menu")


def video_models_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Seedance 2.0", callback_data="model_seedance_2")],
        [InlineKeyboardButton("🧠 Grok Imagine Video 1.5", callback_data="model_grok_imagine_15")],
        [InlineKeyboardButton("⚡ Kling 3.0 Turbo", callback_data="model_kling_30_turbo")],
        [InlineKeyboardButton("🐎 HappyHorse-1.1", callback_data="model_happyhorse_11")],
        [InlineKeyboardButton("🎞 Wan 2.7 Video", callback_data="model_wan_27_video")],
        [InlineKeyboardButton("💎 Gemini Omni", callback_data="model_gemini_omni")],
        [InlineKeyboardButton("🌊 Hailuo 2.3", callback_data="model_hailuo_23")],
        [InlineKeyboardButton("🎥 Veo 3.1", callback_data="model_veo_31")]
    ]
    return navigation_keyboard(keyboard, back_callback="main_menu")


def seedance_modes_menu():
    keyboard = [
        [InlineKeyboardButton("🎥 Текст → Видео", callback_data="seedance_text_video")],
        [InlineKeyboardButton("🖼 Картинка → Видео", callback_data="seedance_image_video")],
        [InlineKeyboardButton("🖼🎬 Картинка + Видео → Видео", callback_data="seedance_image_video_to_video")]
    ]
    return navigation_keyboard(keyboard, back_callback="create_video")


def seedance_audio_menu(back_callback="model_seedance_2"):
    keyboard = [
        [InlineKeyboardButton("🔊 Сгенерировать AI-звук", callback_data="seedance_audio_ai")],
        [InlineKeyboardButton("🎵 Добавить своё аудио", callback_data="seedance_audio_custom")],
        [InlineKeyboardButton("🔇 Без звука", callback_data="seedance_audio_off")]
    ]
    return navigation_keyboard(keyboard, back_callback=back_callback)


def seedance_resolution_menu():
    keyboard = [
        [InlineKeyboardButton("480p", callback_data="seedance_resolution_480p")],
        [InlineKeyboardButton("720p", callback_data="seedance_resolution_720p")],
        [InlineKeyboardButton("1080p", callback_data="seedance_resolution_1080p")],
        [InlineKeyboardButton("4K", callback_data="seedance_resolution_4k")]
    ]
    return navigation_keyboard(keyboard, back_callback="seedance_back_audio")


def seedance_aspect_menu():
    keyboard = [
        [InlineKeyboardButton("16:9", callback_data="seedance_aspect_16_9")],
        [InlineKeyboardButton("4:3", callback_data="seedance_aspect_4_3")],
        [InlineKeyboardButton("1:1", callback_data="seedance_aspect_1_1")],
        [InlineKeyboardButton("3:4", callback_data="seedance_aspect_3_4")],
        [InlineKeyboardButton("9:16", callback_data="seedance_aspect_9_16")],
        [InlineKeyboardButton("21:9", callback_data="seedance_aspect_21_9")]
    ]
    return navigation_keyboard(keyboard, back_callback="seedance_back_resolution")


def seedance_duration_menu():
    keyboard = [
        [InlineKeyboardButton("5 секунд", callback_data="seedance_duration_5")],
        [InlineKeyboardButton("10 секунд", callback_data="seedance_duration_10")],
        [InlineKeyboardButton("15 секунд", callback_data="seedance_duration_15")]
    ]
    return navigation_keyboard(keyboard, back_callback="seedance_back_aspect")


def seedance_generate_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="seedance_generate")]
    ]
    return navigation_keyboard(keyboard, back_callback="seedance_back_duration")


def simple_stub_menu(back_callback="create_video"):
    return navigation_keyboard([], back_callback=back_callback)


# =========================
# DB
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
        free_used = 0
        paid_credits = 0
    else:
        free_used, paid_credits = row

    conn.close()
    return free_used, paid_credits


def save_username(user_id: int, username):
    if not username:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, free_used, paid_credits, username) VALUES (?, 0, 0, ?)",
        (user_id, username.lower())
    )

    cur.execute(
        "UPDATE users SET username = ? WHERE user_id = ?",
        (username.lower(), user_id)
    )

    conn.commit()
    conn.close()


def get_user_id_by_username(username: str):
    username = username.replace("@", "").lower()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    conn.close()

    if row is None:
        return None

    return row[0]


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


def add_paid_credit(user_id: int, amount: int):
    give_balance(user_id, amount)


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

    if row is None:
        return 0

    return row[0] or 0


def apply_deposit_bonus(user_id: int, amount: int):
    referrer_id, ref_mode = get_referrer(user_id)

    if not referrer_id:
        return

    bonus = int(amount * 0.7)

    if bonus > 0:
        add_partner_money(referrer_id, bonus)


def apply_referral_bonus(user_id: int, duration: str):
    referrer_id, ref_mode = get_referrer(user_id)

    if not referrer_id:
        return

    if ref_mode == "free":
        bonus = VIDEO_PRICES.get(duration, 0)
        if bonus > 0:
            give_balance(referrer_id, bonus)

    if ref_mode == "money":
        if duration == "5":
            bonus = 50
        elif duration == "10":
            bonus = 100
        elif duration == "15":
            bonus = 150
        else:
            bonus = 0

        if bonus > 0:
            add_partner_money(referrer_id, bonus)


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
# KIE
# =========================

def guess_mime_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)

    if mime_type:
        return mime_type

    suffix = Path(file_path).suffix.lower()

    if suffix in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix in [".mov", ".qt"]:
        return "video/quicktime"
    if suffix in [".mp3", ".mpeg"]:
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".aac":
        return "audio/aac"

    return "application/octet-stream"


def upload_file_to_kie(file_path: str, upload_folder: str = "xena-seedance") -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}"
    }

    path = Path(file_path)
    mime_type = guess_mime_type(file_path)

    with open(file_path, "rb") as f:
        files = {
            "file": (path.name, f, mime_type)
        }
        data = {
            "uploadPath": upload_folder,
            "fileName": path.name
        }

        response = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=3600
        )

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки файла в Kie: {result}")

    return result["data"]["downloadUrl"]


def build_seedance_input(settings: dict) -> dict:
    mode = settings.get("mode")

    payload_input = {
        "prompt": settings["prompt"],
        "generate_audio": settings.get("generate_audio", False),
        "resolution": settings.get("resolution", "480p"),
        "aspect_ratio": settings.get("aspect_ratio", "9:16"),
        "duration": int(settings.get("duration", "5")),
    }

    # Пользователь загрузил своё аудио
    if settings.get("audio_mode") == "custom" and settings.get("reference_audio_urls"):
        payload_input["reference_audio_urls"] = settings["reference_audio_urls"]
        payload_input["generate_audio"] = False

    # Текст → Видео
    if mode == "text_to_video":
        return payload_input

    # Картинка → Видео
    # Важно: здесь используем first_frame_url, а НЕ reference_image_urls.
    if mode == "image_to_video":
        if not settings.get("first_frame_url"):
            raise RuntimeError("Не загружена картинка для режима Картинка → Видео.")
        payload_input["first_frame_url"] = settings["first_frame_url"]
        return payload_input

    # Картинка + Видео → Видео
    # Важно: здесь НЕ используем first_frame_url, чтобы не получить ошибку 422.
    # Используем reference_image_urls + reference_video_urls.
    if mode == "image_video_to_video":
        if not settings.get("reference_image_urls"):
            raise RuntimeError("Не загружена картинка для режима Картинка + Видео → Видео.")
        if not settings.get("reference_video_urls"):
            raise RuntimeError("Не загружено исходное видео для режима Картинка + Видео → Видео.")

        payload_input["reference_image_urls"] = settings["reference_image_urls"]
        payload_input["reference_video_urls"] = settings["reference_video_urls"]
        return payload_input

    raise RuntimeError(f"Неизвестный режим Seedance: {mode}")


def create_seedance_video_task(settings: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "bytedance/seedance-2",
        "input": build_seedance_input(settings)
    }

    print("SEEDANCE_PAYLOAD:", json.dumps(payload, ensure_ascii=False))

    response = requests.post(url, headers=headers, json=payload, timeout=3600)
    response.raise_for_status()

    result = response.json()
    print("SEEDANCE_CREATE_RESULT:", result)

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания задачи Seedance: {result}")

    task_id = (
        result.get("data", {}).get("taskId")
        or result.get("data", {}).get("task_id")
        or result.get("data", {}).get("id")
    )

    if not task_id:
        raise RuntimeError(f"Seedance не вернул taskId: {result}")

    return task_id


def wait_kie_video_result(task_id: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}"
    }

    for _ in range(3600):
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"taskId": task_id},
                timeout=3600
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            time.sleep(10)
            continue

        data = result.get("data", {})
        state = data.get("state")

        if state == "success":
            result_json_raw = data.get("resultJson")

            if isinstance(result_json_raw, str):
                result_json = json.loads(result_json_raw)
            else:
                result_json = result_json_raw or {}

            video_urls = (
                result_json.get("resultUrls")
                or result_json.get("videoUrls")
                or result_json.get("videos")
                or result_json.get("urls")
                or []
            )

            if isinstance(video_urls, str):
                video_urls = [video_urls]

            if not video_urls:
                raise RuntimeError(f"Видео готово, но ссылка не найдена: {result_json}")

            return video_urls[0]

        if state in ["fail", "failed", "error"]:
            raise RuntimeError(f"Kie не смог сгенерировать видео: {data.get('failMsg') or data}")

        time.sleep(10)

    raise RuntimeError("Видео генерировалось слишком долго. Попробуй позже.")


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
            "return_url": "https://t.me/Xena18Bot"
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
# FLOW HELPERS
# =========================

async def send_main_menu(target):
    caption = (
        f"Наш канал (ГАЛЕРЕЯ+ПРОМПТЫ):\n{MAIN_CHANNEL_URL}\n"
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


async def ask_seedance_prompt(chat, back_callback="model_seedance_2"):
    await chat.send_message(
        "✍️ Добавьте описание видео.\n\n"
        "Напишите, что должно происходить в ролике.",
        reply_markup=back_to_menu_keyboard(back_callback=back_callback)
    )


async def ask_seedance_audio(chat, back_callback="model_seedance_2"):
    await chat.send_message(
        "🎵 Выберите звук:",
        reply_markup=seedance_audio_menu(back_callback=back_callback)
    )


async def ask_seedance_resolution(chat):
    await chat.send_message(
        "📺 Выберите разрешение:",
        reply_markup=seedance_resolution_menu()
    )


async def ask_seedance_aspect(chat):
    await chat.send_message(
        "📐 Выберите формат видео:",
        reply_markup=seedance_aspect_menu()
    )


async def ask_seedance_duration(chat):
    await chat.send_message(
        "⏱ Выберите длительность:",
        reply_markup=seedance_duration_menu()
    )


async def ask_seedance_final(chat, user_id: int):
    settings = user_states.get(user_id, {})
    mode = settings.get("mode", "")
    duration = settings.get("duration", "5")
    cost = get_seedance_price(mode, duration)

    await chat.send_message(
        "✅ Всё готово.\n\n"
        f"Стоимость генерации: {cost} ₽\n\n"
        "Нажмите кнопку ниже, чтобы создать видео.",
        reply_markup=seedance_generate_menu()
    )


def get_seedance_price(mode: str, duration: str) -> int:
    return SEEDANCE_PRICES.get(mode, {}).get(duration, VIDEO_PRICES.get(duration, 0))


def make_temp_path(user_id: int, file_unique_id: str, suffix: str) -> Path:
    safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return MEDIA_DIR / f"{user_id}_{file_unique_id}{safe_suffix}"


# =========================
# COMMAND HANDLERS
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

    await update.message.reply_text(
        f"Твой Telegram ID:\n{user_id}"
    )


async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Используй:\n"
            "/give USER_ID СУММА\n\n"
            "Пример:\n"
            "/give 123456789 98"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Ошибка формата.")
        return

    give_balance(target_id, amount)

    await update.message.reply_text(
        f"✅ Пользователю {target_id} выдано {amount} ₽"
    )


async def giveuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Используй:\n"
            "/giveuser @username СУММА\n\n"
            "Пример:\n"
            "/giveuser @username 98"
        )
        return

    username = context.args[0]

    try:
        amount = int(context.args[1])
    except Exception:
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

    await update.message.reply_text(
        f"✅ @{username.replace('@', '')} выдано {amount} ₽"
    )


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
        text += (
            f"ID: {user_id}\n"
            f"@{name}\n"
            f"К выплате: {balance} ₽\n\n"
        )

    await update.message.reply_text(text)


async def paypartner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Используй:\n"
            "/paypartner USER_ID"
        )
        return

    try:
        target_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("Ошибка ID.")
        return

    reset_partner_balance(target_id)

    await update.message.reply_text(
        f"✅ Партнёрский баланс {target_id} обнулён."
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса:\n\n"
        "Выберите сумму пополнения:",
        reply_markup=topup_inline_menu()
    )


# =========================
# CALLBACK HANDLER
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

    # ---- Payments ----

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
                "Если вы уже оплатили — подождите 10–20 секунд и нажмите кнопку ещё раз.",
                reply_markup=navigation_keyboard([
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
                ], back_callback="buy")
            )
            return

        add_paid_credit(user_id, amount)
        apply_deposit_bonus(user_id, amount)
        _, paid_credits = get_user(user_id)

        await chat.send_message(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action.startswith("topup_"):
        amount = int(action.replace("topup_", ""))

        payment_url, payment_id = create_yookassa_payment(user_id, amount)

        keyboard = navigation_keyboard([
            [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
        ], back_callback="buy")

        await chat.send_message(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            f"1. Нажмите «Оплатить»\n"
            f"2. После оплаты вернитесь сюда\n"
            f"3. Нажмите «✅ Проверить оплату»",
            reply_markup=keyboard
        )
        return

    # ---- Main sections ----

    if action == "buy":
        await chat.send_message(
            "💳 Выберите сумму пополнения:",
            reply_markup=topup_inline_menu()
        )
        return

    if action == "profile":
        free_used, paid_credits = get_user(user_id)

        await chat.send_message(
            f"👤 Ваш баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Текущая стоимость Seedance:\n"
            f"5 секунд — от {VIDEO_PRICES['5']} ₽\n"
            f"10 секунд — от {VIDEO_PRICES['10']} ₽\n"
            f"15 секунд — от {VIDEO_PRICES['15']} ₽",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "partner":
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        await chat.send_message(
            "🤝 Партнерка\n\n"
            "За каждого приведенного активного пользователя вы будете получать бонусы "
            "на свой бонусный счет.\n\n"
            "Информация о бонусах отображается в разделе «Кабинет партнера».\n\n"
            f"Ваша реферальная ссылка:\n"
            f"https://t.me/{bot_username}?start=partner_{user_id}",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "partner_profile":
        partner_balance = get_partner_balance(user_id)

        await chat.send_message(
            f"💼 Кабинет партнера\n\n"
            f"Бонусный счет: {partner_balance} бонусов\n\n"
            f"1 бонус = 1 ₽.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "help":
        await chat.send_message(
            "📘 Инструкция\n\n"
            "1. Выберите, что хотите создать.\n"
            "2. Выберите нейросеть и режим генерации.\n"
            "3. Отправьте нужные файлы и описание.\n"
            "4. Выберите звук, разрешение, формат и длительность.\n"
            "5. Нажмите «Создать видео» и дождитесь результата.\n\n"
            "Бот проведёт вас по шагам.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "create_video":
        await chat.send_message(
            "Выберите нейросеть для генерации видео:",
            reply_markup=video_models_menu()
        )
        return

    if action == "create_image":
        await chat.send_message(
            "🖼 Создание изображений\n\n"
            "Этот раздел подключим следующим этапом.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "create_audio":
        await chat.send_message(
            "🎵 Создание аудио\n\n"
            "Этот раздел подключим следующим этапом.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    # ---- Not connected video models yet ----

    if action in [
        "model_grok_imagine_15",
        "model_kling_30_turbo",
        "model_happyhorse_11",
        "model_wan_27_video",
        "model_gemini_omni",
        "model_hailuo_23",
        "model_veo_31",
    ]:
        await chat.send_message(
            "Эту нейросеть подключим следующим этапом.\n\n"
            "Сейчас работаем с Seedance 2.0.",
            reply_markup=back_to_menu_keyboard(back_callback="create_video")
        )
        return

    # ---- Seedance ----

    if action == "model_seedance_2":
        user_states.pop(user_id, None)
        await chat.send_message(
            "🎬 Seedance 2.0\n\n"
            "Выберите режим генерации:",
            reply_markup=seedance_modes_menu()
        )
        return

    if action == "seedance_text_video":
        user_states[user_id] = {
            "model": "seedance_2",
            "mode": "text_to_video",
            "step": "waiting_prompt"
        }

        await ask_seedance_prompt(chat, back_callback="model_seedance_2")
        return

    if action == "seedance_image_video":
        user_states[user_id] = {
            "model": "seedance_2",
            "mode": "image_to_video",
            "step": "waiting_image"
        }

        await chat.send_message(
            "🖼 Отправьте картинку.\n\n"
            "Она станет первым кадром будущего видео.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    if action == "seedance_image_video_to_video":
        user_states[user_id] = {
            "model": "seedance_2",
            "mode": "image_video_to_video",
            "step": "waiting_image"
        }

        await chat.send_message(
            "🖼 Отправьте картинку.\n\n"
            "Она будет использоваться как исходное изображение для генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    if action == "seedance_audio_ai":
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        user_states[user_id]["audio_mode"] = "ai"
        user_states[user_id]["generate_audio"] = True
        user_states[user_id]["step"] = "choose_resolution"

        await ask_seedance_resolution(chat)
        return

    if action == "seedance_audio_off":
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        user_states[user_id]["audio_mode"] = "off"
        user_states[user_id]["generate_audio"] = False
        user_states[user_id]["step"] = "choose_resolution"

        await ask_seedance_resolution(chat)
        return

    if action == "seedance_audio_custom":
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        user_states[user_id]["audio_mode"] = "custom"
        user_states[user_id]["generate_audio"] = False
        user_states[user_id]["step"] = "waiting_audio"

        await chat.send_message(
            "🎵 Отправьте своё аудио.\n\n"
            "Поддерживаются обычные аудиофайлы и голосовые сообщения.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_audio")
        )
        return

    if action == "seedance_back_audio":
        if user_id not in user_states:
            await chat.send_message(
                "Сначала выберите режим генерации.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        await ask_seedance_audio(chat, back_callback="model_seedance_2")
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
        user_states[user_id]["step"] = "choose_aspect_ratio"

        await ask_seedance_aspect(chat)
        return

    if action == "seedance_back_resolution":
        await ask_seedance_resolution(chat)
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
        user_states[user_id]["step"] = "choose_duration"

        await ask_seedance_duration(chat)
        return

    if action == "seedance_back_aspect":
        await ask_seedance_aspect(chat)
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
        user_states[user_id]["step"] = "ready_to_generate"

        await ask_seedance_final(chat, user_id)
        return

    if action == "seedance_back_duration":
        await ask_seedance_duration(chat)
        return

    if action == "seedance_generate":
        if user_id not in user_states:
            await chat.send_message(
                "Сначала настройте генерацию.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        settings = user_states[user_id]
        mode = settings.get("mode", "")
        duration = settings.get("duration", "5")
        video_cost = get_seedance_price(mode, duration)

        if video_cost <= 0:
            await chat.send_message(
                "Для выбранного режима цена пока не настроена.",
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )
            return

        free_used, paid_credits = get_user(user_id)

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
            apply_referral_bonus(user_id, duration)

            try:
                with open(video_path, "rb") as video_file:
                    await chat.send_video(
                        video=video_file,
                        caption="✅ Готово! Вот твоё видео.",
                        read_timeout=3600,
                        write_timeout=3600,
                        connect_timeout=60,
                        pool_timeout=3600
                    )
            except Exception:
                await chat.send_message(
                    "⚠️ Видео было сгенерировано, но Telegram не смог его отправить.\n\n"
                    f"Напишите в поддержку:\n{SUPPORT_URL}",
                    disable_web_page_preview=True
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
                f"Если ошибка повторяется — напишите в поддержку:\n{SUPPORT_URL}",
                disable_web_page_preview=True,
                reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
            )

        user_states.pop(user_id, None)
        return

    await chat.send_message(
        "Этот раздел пока не подключен.",
        reply_markup=back_to_menu_keyboard()
    )


# =========================
# MESSAGE HANDLERS
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_states.get(user_id)

    if not state or state.get("model") != "seedance_2":
        await update.message.reply_text(
            "Сначала выберите режим генерации в меню.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if state.get("step") != "waiting_image":
        await update.message.reply_text(
            "Сейчас бот не ожидает картинку.\n\n"
            "Следуйте шагам на экране.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = make_temp_path(user_id, photo.file_unique_id, ".jpg")
    await file.download_to_drive(str(image_path))

    await update.message.reply_text("🖼 Картинка получена. Загружаю её в Kie...")

    try:
        image_url = upload_file_to_kie(str(image_path), upload_folder="xena-seedance/images")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Не удалось загрузить картинку:\n\n{e}",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    mode = state.get("mode")

    if mode == "image_to_video":
        state["first_frame_url"] = image_url
        state["step"] = "waiting_prompt"

        await ask_seedance_prompt(update.message, back_callback="seedance_image_video")
        return

    if mode == "image_video_to_video":
        state["reference_image_urls"] = [image_url]
        state["step"] = "waiting_video"

        await update.message.reply_text(
            "🎬 Теперь отправьте исходное видео.\n\n"
            "Оно будет использоваться как видео-референс для генерации.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_image_video_to_video")
        )
        return

    await update.message.reply_text(
        "Неизвестный режим генерации.",
        reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_states.get(user_id)

    if not state or state.get("model") != "seedance_2":
        await update.message.reply_text(
            "Сначала выберите режим генерации в меню.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if state.get("step") != "waiting_video":
        await update.message.reply_text(
            "Сейчас бот не ожидает видео.\n\n"
            "Следуйте шагам на экране.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    video = update.message.video or update.message.document

    if not video:
        await update.message.reply_text(
            "Не удалось получить видео. Попробуйте отправить MP4-файл.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    file = await context.bot.get_file(video.file_id)

    suffix = Path(getattr(video, "file_name", "") or "video.mp4").suffix or ".mp4"
    video_path = make_temp_path(user_id, video.file_unique_id, suffix)
    await file.download_to_drive(str(video_path))

    await update.message.reply_text("🎬 Видео получено. Загружаю его в Kie...")

    try:
        video_url = upload_file_to_kie(str(video_path), upload_folder="xena-seedance/videos")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Не удалось загрузить видео:\n\n{e}",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    state["reference_video_urls"] = [video_url]
    state["step"] = "waiting_prompt"

    await ask_seedance_prompt(update.message, back_callback="seedance_image_video_to_video")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    state = user_states.get(user_id)

    if not state or state.get("model") != "seedance_2":
        await update.message.reply_text(
            "Сначала выберите режим генерации в меню.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if state.get("step") != "waiting_audio":
        await update.message.reply_text(
            "Сейчас бот не ожидает аудио.\n\n"
            "Следуйте шагам на экране.",
            reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2")
        )
        return

    audio_obj = update.message.audio or update.message.voice or update.message.document

    if not audio_obj:
        await update.message.reply_text(
            "Не удалось получить аудио. Попробуйте отправить аудиофайл.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_audio")
        )
        return

    file = await context.bot.get_file(audio_obj.file_id)

    file_name = getattr(audio_obj, "file_name", "") or "audio.ogg"
    suffix = Path(file_name).suffix or ".ogg"
    audio_path = make_temp_path(user_id, audio_obj.file_unique_id, suffix)
    await file.download_to_drive(str(audio_path))

    await update.message.reply_text("🎵 Аудио получено. Загружаю его в Kie...")

    try:
        audio_url = upload_file_to_kie(str(audio_path), upload_folder="xena-seedance/audio")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Не удалось загрузить аудио:\n\n{e}",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_audio")
        )
        return

    state["reference_audio_urls"] = [audio_url]
    state["step"] = "choose_resolution"

    await ask_seedance_resolution(update.message)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    # Reply-keyboard compatibility
    if text == "🚀 Запустить бота":
        await send_main_menu(update.message)
        return

    if text == "📘 Инструкция: /help":
        await update.message.reply_text(
            "📘 Инструкция доступна в главном меню.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if text == "👤 Мой баланс: /profile":
        free_used, paid_credits = get_user(user_id)
        await update.message.reply_text(f"Баланс: {paid_credits} ₽")
        return

    if text == "🆘 Связаться с поддержкой":
        await update.message.reply_text(
            f"🆘 Написать в поддержку: {SUPPORT_URL}",
            disable_web_page_preview=True
        )
        return

    state = user_states.get(user_id)

    if state and state.get("model") == "seedance_2" and state.get("step") == "waiting_prompt":
        state["prompt"] = text
        state["step"] = "choose_audio"

        await ask_seedance_audio(update.message, back_callback="model_seedance_2")
        return

    await update.message.reply_text(
        "Выберите действие в главном меню.",
        reply_markup=back_to_menu_keyboard()
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    payload = update.message.successful_payment.invoice_payload

    if payload.startswith("topup_"):
        amount = int(payload.replace("topup_", ""))
        add_paid_credit(user_id, amount)
        apply_deposit_bonus(user_id, amount)

        _, paid_credits = get_user(user_id)

        await update.message.reply_text(
            f"✅ Баланс пополнен на {amount} ₽.\n\n"
            f"Текущий баланс: {paid_credits} ₽."
        )


# =========================
# APP
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
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
