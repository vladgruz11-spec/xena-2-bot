import os
import json
import time
import sqlite3
import requests
import mimetypes
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
SEEDANCE_PRICE_IMAGE_URL = "https://raw.githubusercontent.com/vladgruz11-spec/xena-2-bot/refs/heads/main/seedance_price_v2.png"

user_states = {}
ADMIN_IDS = {6164104276}

# Цены Seedance 2.0. Ключи: режим -> разрешение -> длительность.
# 4K временно убран из интерфейса.
SEEDANCE_PRICES = {
    "text_to_video": {
        "480p": {"5": 99, "10": 199, "15": 299},
        "720p": {"5": 209, "10": 419, "15": 629},
        "1080p": {"5": 429, "10": 849, "15": 1269},
    },
    "image_to_video": {
        "480p": {"5": 99, "10": 199, "15": 299},
        "720p": {"5": 209, "10": 419, "15": 629},
        "1080p": {"5": 429, "10": 849, "15": 1269},
    },
    "image_video_to_video": {
        "480p": {"5": 109, "10": 219, "15": 319},
        "720p": {"5": 229, "10": 459, "15": 689},
        "1080p": {"5": 469, "10": 929, "15": 1389},
    },
}


def navigation_keyboard(buttons, back_callback="main_menu"):
    buttons.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)])
    buttons.append([InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def back_to_menu_keyboard(back_callback="main_menu"):
    return navigation_keyboard([], back_callback=back_callback)


def support_keyboard(back_callback="main_menu"):
    return navigation_keyboard(
        [[InlineKeyboardButton("🆘 Написать в поддержку", url=SUPPORT_URL)]],
        back_callback=back_callback
    )


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
        [InlineKeyboardButton("🆘 Поддержка", url=SUPPORT_URL)]
    ])


def topup_inline_menu(back_callback="main_menu"):
    return navigation_keyboard([
        [InlineKeyboardButton("250 ₽", callback_data="topup_250")],
        [InlineKeyboardButton("500 ₽", callback_data="topup_500")],
        [InlineKeyboardButton("1000 ₽", callback_data="topup_1000")],
        [InlineKeyboardButton("5000 ₽", callback_data="topup_5000")]
    ], back_callback=back_callback)


def video_models_menu():
    return navigation_keyboard([
        [InlineKeyboardButton("🎬 Seedance 2.0 (от 99 ₽)", callback_data="model_seedance_2")],
        [InlineKeyboardButton("🧠 Grok Imagine Video 1.5", callback_data="model_grok_imagine_15")],
        [InlineKeyboardButton("⚡ Kling 3.0 Turbo", callback_data="model_kling_30_turbo")],
        [InlineKeyboardButton("🐎 HappyHorse-1.1", callback_data="model_happyhorse_11")],
        [InlineKeyboardButton("🎞 Wan 2.7 Video", callback_data="model_wan_27_video")],
        [InlineKeyboardButton("💎 Gemini Omni", callback_data="model_gemini_omni")],
        [InlineKeyboardButton("🌊 Hailuo 2.3", callback_data="model_hailuo_23")],
        [InlineKeyboardButton("🎥 Veo 3.1", callback_data="model_veo_31")]
    ], back_callback="main_menu")


def seedance_modes_menu():
    return navigation_keyboard([
        [InlineKeyboardButton("💰 Прайс Seedance 2.0", callback_data="seedance_price_list")],
        [InlineKeyboardButton("🎥 Текст → Видео", callback_data="seedance_mode_text")],
        [InlineKeyboardButton("📷 Изображение → Видео", callback_data="seedance_mode_image")],
        [InlineKeyboardButton("🎬 Изображение + Видео → Видео", callback_data="seedance_mode_image_video")]
    ], back_callback="create_video")


def seedance_price_caption():
    return "💰 Прайс Seedance 2.0"


def seedance_price_keyboard():
    return navigation_keyboard([
        [InlineKeyboardButton("💳 ПОПОЛНИТЬ БАЛАНС", callback_data="buy_seedance_prices")]
    ], back_callback="model_seedance_2")


def seedance_image_type_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("1️⃣ 1 изображение", callback_data="seedance_image_first")],
        [InlineKeyboardButton("2️⃣ Первый и последний кадр", callback_data="seedance_image_first_last")],
        [InlineKeyboardButton("3️⃣ Несколько изображений", callback_data="seedance_image_reference_pack")]
    ], back_callback=back_callback)


def seedance_audio_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("🔊 Сгенерировать AI-звук", callback_data="seedance_audio_on")],
        [InlineKeyboardButton("🔇 Без звука", callback_data="seedance_audio_off")]
    ], back_callback=back_callback)


def seedance_resolution_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("480p", callback_data="seedance_resolution_480p")],
        [InlineKeyboardButton("720p", callback_data="seedance_resolution_720p")],
        [InlineKeyboardButton("1080p", callback_data="seedance_resolution_1080p")]
    ], back_callback=back_callback)


def seedance_aspect_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("16:9", callback_data="seedance_aspect_16_9")],
        [InlineKeyboardButton("4:3", callback_data="seedance_aspect_4_3")],
        [InlineKeyboardButton("1:1", callback_data="seedance_aspect_1_1")],
        [InlineKeyboardButton("3:4", callback_data="seedance_aspect_3_4")],
        [InlineKeyboardButton("9:16", callback_data="seedance_aspect_9_16")],
        [InlineKeyboardButton("21:9", callback_data="seedance_aspect_21_9")]
    ], back_callback=back_callback)


def seedance_duration_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("5 секунд", callback_data="seedance_duration_5")],
        [InlineKeyboardButton("10 секунд", callback_data="seedance_duration_10")],
        [InlineKeyboardButton("15 секунд", callback_data="seedance_duration_15")]
    ], back_callback=back_callback)


def seedance_generate_menu(back_callback):
    return navigation_keyboard([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="seedance_generate")]
    ], back_callback=back_callback)


# ========================= БАЗА =========================

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
        "ALTER TABLE users ADD COLUMN partner_balance INTEGER DEFAULT 0"
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
        cur.execute("INSERT INTO users (user_id, free_used, paid_credits) VALUES (?, 0, 0)", (user_id,))
        conn.commit()
        row = (0, 0)
    conn.close()
    return row


def save_username(user_id: int, username):
    if not username:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, free_used, paid_credits, username) VALUES (?, 0, 0, ?)",
        (user_id, username.lower())
    )
    cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username.lower(), user_id))
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
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, paid_credits) VALUES (?, 0, 0)", (user_id,))
    cur.execute("UPDATE users SET paid_credits = paid_credits + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def reset_user_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, paid_credits) VALUES (?, 0, 0)", (user_id,))
    cur.execute("UPDATE users SET paid_credits = 0 WHERE user_id = ?", (user_id,))
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


def charge_user_balance(user_id: int, amount: int) -> bool:
    """Атомарно списывает деньги. Возвращает True, если списание прошло."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET paid_credits = paid_credits - ? WHERE user_id = ? AND paid_credits >= ?",
        (amount, user_id, amount)
    )
    charged = cur.rowcount == 1
    conn.commit()
    conn.close()
    return charged


def refund_user_balance(user_id: int, amount: int):
    """Возвращает деньги пользователю на баланс."""
    if amount <= 0:
        return
    give_balance(user_id, amount)


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
    cur.execute("UPDATE users SET referrer_id = ?, ref_mode = ? WHERE user_id = ?", (referrer_id, ref_mode, user_id))
    conn.commit()
    conn.close()


def add_partner_money(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET partner_balance = partner_balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def apply_deposit_bonus(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        bonus = int(amount * 0.7)
        if bonus > 0:
            add_partner_money(row[0], bonus)


def get_partner_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT partner_balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


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


# ========================= KIE =========================

class KieTaskCreateError(Exception):
    """Kie не принял задачу, taskId не создан."""


class KieGenerationFailed(Exception):
    """Kie принял задачу, но вернул ошибку генерации."""


class KieGenerationTimeout(Exception):
    """Kie принял задачу, но результат не был получен за время ожидания."""


def upload_file_to_kie(file_path: str, upload_path: str) -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, mime_type)}
        data = {"uploadPath": upload_path, "fileName": Path(file_path).name}
        response = requests.post(url, headers=headers, files=files, data=data, timeout=3600)
    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки файла: {result}")
    return result["data"]["downloadUrl"]


def build_seedance_payload(settings: dict):
    mode = settings.get("mode")
    input_data = {
        "prompt": settings.get("prompt", ""),
        "generate_audio": settings.get("generate_audio", False),
        "resolution": settings.get("resolution", "480p"),
        "aspect_ratio": settings.get("aspect_ratio", "9:16"),
        "duration": int(settings.get("duration", "5"))
    }
    image_type = settings.get("image_type")

    if mode == "text_to_video":
        pass

    elif mode == "image_to_video":
        # В Seedance нельзя смешивать first_frame/last_frame и reference_image_urls.
        # Поэтому каждый вариант загрузки собирает отдельный, не конфликтующий payload.
        if image_type == "first":
            input_data["first_frame_url"] = settings["first_frame_url"]
        elif image_type == "first_last":
            input_data["first_frame_url"] = settings["first_frame_url"]
            input_data["last_frame_url"] = settings["last_frame_url"]
        elif image_type == "reference_pack":
            input_data["reference_image_urls"] = settings["reference_image_urls"]

    elif mode == "image_video_to_video":
        # Kie/Seedance возвращает 422, если одновременно передать reference_video_urls
        # и first_frame_url/last_frame_url/reference_image_urls. Для режима с исходным
        # видео отправляем только исходное видео + описание + настройки.
        input_data["reference_video_urls"] = [settings["reference_video_url"]]

    return {"model": "bytedance/seedance-2", "input": input_data}


def create_seedance_task(settings: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    headers = {"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"}
    payload = build_seedance_payload(settings)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        # Задача не подтверждена Kie, taskId нет. Деньги пользователю не списываем.
        raise KieTaskCreateError(str(e))

    if result.get("code") != 200:
        # Kie отклонил задачу до создания taskId. Деньги пользователю не списываем.
        raise KieTaskCreateError(f"Ошибка создания задачи Seedance: {result}")

    try:
        return result["data"]["taskId"]
    except Exception:
        raise KieTaskCreateError(f"Kie не вернул taskId: {result}")


def wait_kie_video_result(task_id: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    for _ in range(360):
        response = requests.get(url, headers=headers, params={"taskId": task_id}, timeout=60)
        response.raise_for_status()
        result = response.json()
        data = result.get("data", {})
        state = data.get("state")
        if state == "success":
            raw = data.get("resultJson")
            result_json = json.loads(raw) if isinstance(raw, str) else raw
            video_urls = result_json.get("resultUrls") or result_json.get("videoUrls") or result_json.get("videos") or []
            if not video_urls:
                raise RuntimeError(f"Видео готово, но ссылка не найдена: {result_json}")
            return video_urls[0]
        if state == "fail":
            raise KieGenerationFailed(f"Kie не смог сгенерировать видео: {data.get('failMsg')}")
        time.sleep(10)
    raise KieGenerationTimeout("Видео генерировалось слишком долго.")


def download_video(video_url: str, user_id: int) -> str:
    video_path = MEDIA_DIR / f"{user_id}_seedance_result.mp4"
    response = requests.get(video_url, timeout=3600)
    response.raise_for_status()
    with open(video_path, "wb") as f:
        f.write(response.content)
    return str(video_path)


# ========================= ОПЛАТА =========================

def create_yookassa_payment(user_id: int, amount: int):
    url = "https://api.yookassa.ru/v3/payments"
    headers = {"Idempotence-Key": f"topup_{user_id}_{amount}_{int(time.time())}", "Content-Type": "application/json"}
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": "https://t.me/Xena18Bot"},
        "description": f"Пополнение баланса Telegram-бота на {amount} рублей",
        "metadata": {"user_id": str(user_id), "amount": str(amount)}
    }
    response = requests.post(url, auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY), headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    return result["confirmation"]["confirmation_url"], result["id"]


def check_yookassa_payment(payment_id: str) -> bool:
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
    response = requests.get(url, auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY), timeout=60)
    response.raise_for_status()
    return response.json().get("status") == "succeeded"


# ========================= СООБЩЕНИЯ =========================

async def send_to_target(target, text, reply_markup=None, **kwargs):
    if hasattr(target, "send_message"):
        return await target.send_message(text, reply_markup=reply_markup, **kwargs)
    if hasattr(target, "reply_text"):
        return await target.reply_text(text, reply_markup=reply_markup, **kwargs)
    raise RuntimeError("Неизвестный тип получателя.")


async def send_main_menu(target):
    caption = f"Наш канал (ГАЛЕРЕЯ+ПРОМПТЫ):\n{MAIN_CHANNEL_URL}\nПодпишись, чтобы нас не потерять!"
    if hasattr(target, "reply_photo"):
        await target.reply_photo(photo=MAIN_MENU_PHOTO, caption=caption, reply_markup=main_inline_menu())
    else:
        await target.send_photo(photo=MAIN_MENU_PHOTO, caption=caption, reply_markup=main_inline_menu())


async def send_kie_error(chat, back_callback="model_seedance_2"):
    await chat.send_message(
        "❌ Ошибка генерации.\n\nЕсли проблема повторяется — свяжитесь с поддержкой.",
        reply_markup=support_keyboard(back_callback=back_callback),
        disable_web_page_preview=True
    )


async def ask_seedance_image_type(chat, back_callback="model_seedance_2"):
    await chat.send_message("Выберите вариант загрузки изображений:", reply_markup=seedance_image_type_menu(back_callback))


async def ask_seedance_prompt(target, back_callback="model_seedance_2"):
    await send_to_target(
        target,
        "✍️ Добавьте описание видео.\n\nНапишите, что должно происходить в ролике.",
        reply_markup=back_to_menu_keyboard(back_callback=back_callback)
    )


async def ask_seedance_audio(target, back_callback):
    await send_to_target(target, "🎵 Настройка звука:", reply_markup=seedance_audio_menu(back_callback))


async def ask_next_image_upload(chat, user_id: int):
    state = user_states[user_id]
    image_type = state.get("image_type")
    if image_type == "first":
        state["step"] = "waiting_first_frame"
        await chat.send_message("Загрузите изображение.", reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type"))
    elif image_type == "first_last":
        state["step"] = "waiting_first_frame"
        await chat.send_message(
            "Загрузите изображения.\n\nСначала отправьте первый кадр.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type")
        )
    else:
        state["step"] = "waiting_reference_images"
        state["reference_image_urls"] = []
        await chat.send_message(
            "Загрузите изображения.\n\nОтправьте от 1 до 9 изображений. Когда закончите — нажмите «Продолжить».",
            reply_markup=navigation_keyboard([[InlineKeyboardButton("✅ Продолжить", callback_data="seedance_images_done")]], back_callback="seedance_back_to_image_type")
        )


async def after_images_ready(chat, user_id: int):
    state = user_states[user_id]
    if state.get("mode") == "image_video_to_video":
        state["step"] = "waiting_video"
        await chat.send_message(
            "🎬 Теперь отправьте исходное видео.\n\nЗагрузите видео длительностью до 15 секунд. Длительность готового ролика будет выставлена автоматически по длительности исходного видео.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type")
        )
        return
    state["step"] = "waiting_prompt"
    await ask_seedance_prompt(chat, back_callback="seedance_back_to_image_type")


def reset_seedance_files(user_id: int):
    if user_id not in user_states:
        return
    for key in ["first_frame_url", "last_frame_url", "reference_image_urls", "reference_video_url", "local_files", "video_duration"]:
        user_states[user_id].pop(key, None)


def seedance_price(settings: dict) -> int:
    mode = settings.get("mode", "text_to_video")
    resolution = settings.get("resolution", "480p")
    duration = str(settings.get("duration", "5"))
    return SEEDANCE_PRICES.get(mode, {}).get(resolution, {}).get(duration, 0)


def normalize_video_duration(seconds: int) -> str:
    """Приводим длительность исходного видео к тарифной длительности Seedance."""
    if seconds <= 5:
        return "5"
    if seconds <= 10:
        return "10"
    return "15"


async def send_seedance_ready(chat, user_id: int, back_callback="seedance_back_to_aspect"):
    user_states[user_id]["step"] = "ready_to_generate"
    price = seedance_price(user_states[user_id])
    resolution = user_states[user_id].get("resolution", "480p")
    duration = user_states[user_id].get("duration", "5")
    await chat.send_message(
        f"✅ Всё готово.\n\nРазрешение: {resolution}\nДлительность: {duration} сек.\nСтоимость генерации: {price} ₽.\n\nНажмите кнопку ниже, чтобы создать видео.",
        reply_markup=seedance_generate_menu(back_callback=back_callback)
    )


def clean_aspect(action: str) -> str:
    return action.replace("seedance_aspect_", "").replace("_", ":")


# ========================= КОМАНДЫ =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_username(user_id, update.message.from_user.username)
    get_user(user_id)
    if context.args and context.args[0].startswith("partner_"):
        set_referrer(user_id, int(context.args[0].replace("partner_", "")), "bonus")
    await send_main_menu(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_username(user_id, update.message.from_user.username)
    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Используй:\n/give USER_ID СУММА")
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Ошибка формата.")
        return
    give_balance(target_id, amount)
    await update.message.reply_text(f"✅ Пользователю {target_id} выдано {amount} ₽")


async def giveuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Используй:\n/giveuser @username СУММА")
        return
    target_id = get_user_id_by_username(context.args[0])
    if target_id is None:
        await update.message.reply_text("❌ Пользователь не найден. Он должен сначала написать боту /start.")
        return
    amount = int(context.args[1])
    give_balance(target_id, amount)
    await update.message.reply_text(f"✅ {context.args[0]} выдано {amount} ₽")


async def resetuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Используй:\n"
            "/resetuser @username\n\n"
            "Пример:\n"
            "/resetuser @username"
        )
        return

    username = context.args[0]
    target_id = get_user_id_by_username(username)

    if target_id is None:
        await update.message.reply_text(
            "❌ Пользователь не найден.\n"
            "Он должен сначала написать боту /start."
        )
        return

    reset_user_balance(target_id)

    await update.message.reply_text(
        f"✅ Баланс {username} обнулён."
    )


async def partners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    rows = get_all_partners()
    if not rows:
        await update.message.reply_text("Партнёров с балансом нет.")
        return
    text = "💼 Партнёрские выплаты:\n\n"
    for user_id, username, balance in rows:
        text += f"ID: {user_id}\n@{username or 'без username'}\nК выплате: {balance} ₽\n\n"
    await update.message.reply_text(text)


async def paypartner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Используй:\n/paypartner USER_ID")
        return
    reset_partner_balance(int(context.args[0]))
    await update.message.reply_text(f"✅ Партнёрский баланс {context.args[0]} обнулён.")


# ========================= CALLBACK =========================

async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    action = query.data
    try:
        await query.message.delete()
    except Exception:
        pass
    chat = query.message.chat

    if action == "main_menu":
        user_states.pop(user_id, None)
        await send_main_menu(chat)
        return

    if action == "create_video":
        await chat.send_message("Выберите нейросеть для генерации видео:", reply_markup=video_models_menu())
        return

    if action == "model_seedance_2":
        user_states.pop(user_id, None)
        await chat.send_message(
            "🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:",
            reply_markup=seedance_modes_menu()
        )
        return

    if action == "seedance_price_list":
        try:
            await chat.send_photo(
                photo=SEEDANCE_PRICE_IMAGE_URL,
                caption=seedance_price_caption(),
                reply_markup=seedance_price_keyboard()
            )
        except Exception:
            await chat.send_message(
                "💰 Прайс Seedance 2.0\n\nНе удалось загрузить изображение прайса. Попробуйте открыть прайс позже или напишите в поддержку.",
                reply_markup=support_keyboard(back_callback="model_seedance_2")
            )
        return

    if action in ["model_grok_imagine_15", "model_kling_30_turbo", "model_happyhorse_11", "model_wan_27_video", "model_gemini_omni", "model_hailuo_23", "model_veo_31"]:
        await chat.send_message("Эту нейросеть подключим следующим этапом.", reply_markup=back_to_menu_keyboard(back_callback="create_video"))
        return

    if action == "seedance_mode_text":
        user_states[user_id] = {"model": "seedance_2", "mode": "text_to_video", "step": "waiting_prompt"}
        await ask_seedance_prompt(chat, back_callback="model_seedance_2")
        return

    if action == "seedance_mode_image":
        user_states[user_id] = {"model": "seedance_2", "mode": "image_to_video", "step": "choose_image_type"}
        await ask_seedance_image_type(chat, back_callback="model_seedance_2")
        return

    if action == "seedance_mode_image_video":
        user_states[user_id] = {"model": "seedance_2", "mode": "image_video_to_video", "step": "choose_image_type"}
        await ask_seedance_image_type(chat, back_callback="model_seedance_2")
        return

    if action == "seedance_back_to_image_type":
        if user_id in user_states:
            reset_seedance_files(user_id)
            user_states[user_id]["step"] = "choose_image_type"
        await ask_seedance_image_type(chat, back_callback="model_seedance_2")
        return

    if action in ["seedance_image_first", "seedance_image_first_last", "seedance_image_reference_pack"]:
        if user_id not in user_states:
            await chat.send_message("🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:", reply_markup=seedance_modes_menu())
            return
        reset_seedance_files(user_id)
        if action == "seedance_image_first":
            user_states[user_id]["image_type"] = "first"
        elif action == "seedance_image_first_last":
            user_states[user_id]["image_type"] = "first_last"
        else:
            user_states[user_id]["image_type"] = "reference_pack"
        await ask_next_image_upload(chat, user_id)
        return

    if action == "seedance_images_done":
        if user_id not in user_states or not user_states[user_id].get("reference_image_urls"):
            await chat.send_message("Сначала загрузите хотя бы одно изображение.", reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type"))
            return
        await after_images_ready(chat, user_id)
        return

    if action == "seedance_back_to_prompt":
        if user_id in user_states:
            user_states[user_id]["step"] = "waiting_prompt"
        await ask_seedance_prompt(chat, back_callback="model_seedance_2")
        return

    if action in ["seedance_audio_on", "seedance_audio_off"]:
        if user_id not in user_states:
            await chat.send_message("🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:", reply_markup=seedance_modes_menu())
            return
        user_states[user_id]["generate_audio"] = action == "seedance_audio_on"
        user_states[user_id]["step"] = "choose_resolution"
        await chat.send_message("📺 Выберите разрешение:", reply_markup=seedance_resolution_menu(back_callback="seedance_back_to_audio"))
        return

    if action == "seedance_back_to_audio":
        if user_id in user_states:
            user_states[user_id]["step"] = "choose_audio"
        await ask_seedance_audio(chat, back_callback="seedance_back_to_prompt")
        return

    if action.startswith("seedance_resolution_"):
        if user_id not in user_states:
            await chat.send_message("🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:", reply_markup=seedance_modes_menu())
            return
        user_states[user_id]["resolution"] = action.replace("seedance_resolution_", "")
        user_states[user_id]["step"] = "choose_aspect"
        await chat.send_message("📐 Выберите формат видео:", reply_markup=seedance_aspect_menu(back_callback="seedance_back_to_resolution"))
        return

    if action == "seedance_back_to_resolution":
        if user_id in user_states:
            user_states[user_id]["step"] = "choose_resolution"
        await chat.send_message("📺 Выберите разрешение:", reply_markup=seedance_resolution_menu(back_callback="seedance_back_to_audio"))
        return

    if action.startswith("seedance_aspect_"):
        if user_id not in user_states:
            await chat.send_message("🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:", reply_markup=seedance_modes_menu())
            return
        user_states[user_id]["aspect_ratio"] = clean_aspect(action)

        if user_states[user_id].get("mode") == "image_video_to_video":
            video_duration = user_states[user_id].get("video_duration")
            if video_duration is None:
                await chat.send_message(
                    "Сначала загрузите исходное видео.",
                    reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type")
                )
                return
            user_states[user_id]["duration"] = normalize_video_duration(int(video_duration))
            await send_seedance_ready(chat, user_id, back_callback="seedance_back_to_aspect")
            return

        user_states[user_id]["step"] = "choose_duration"
        await chat.send_message("⏱ Выберите длительность:", reply_markup=seedance_duration_menu(back_callback="seedance_back_to_aspect"))
        return

    if action == "seedance_back_to_aspect":
        if user_id in user_states:
            user_states[user_id]["step"] = "choose_aspect"
        await chat.send_message("📐 Выберите формат видео:", reply_markup=seedance_aspect_menu(back_callback="seedance_back_to_resolution"))
        return

    if action.startswith("seedance_duration_"):
        if user_id not in user_states:
            await chat.send_message("🎬 Seedance 2.0\n\nОзнакомьтесь с ценами и выберите режим генерации:", reply_markup=seedance_modes_menu())
            return
        duration = action.replace("seedance_duration_", "")
        video_duration = user_states[user_id].get("video_duration")
        if video_duration is not None and int(duration) != int(video_duration):
            await chat.send_message(
                f"⚠️ Длительность исходного видео: {video_duration} секунд.\n\nВыберите такую же длительность генерации или загрузите другое видео.",
                reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_duration")
            )
            return
        user_states[user_id]["duration"] = duration
        await send_seedance_ready(chat, user_id, back_callback="seedance_back_to_duration")
        return

    if action == "seedance_back_to_duration":
        if user_id in user_states:
            user_states[user_id]["step"] = "choose_duration"
        await chat.send_message("⏱ Выберите длительность:", reply_markup=seedance_duration_menu(back_callback="seedance_back_to_aspect"))
        return

    if action == "seedance_generate":
        await handle_seedance_generate(chat, user_id)
        return

    if action == "buy_seedance_prices":
        user_states[user_id] = {"payment_return": "seedance_modes"}
        await chat.send_message("💳 Выберите сумму пополнения:", reply_markup=topup_inline_menu(back_callback="seedance_price_list"))
        return

    if action == "buy":
        if user_states.get(user_id, {}).get("payment_return"):
            user_states.pop(user_id, None)
        await chat.send_message("💳 Выберите сумму пополнения:", reply_markup=topup_inline_menu())
        return

    if action.startswith("topup_"):
        await handle_topup(chat, user_id, action)
        return

    if action.startswith("checkpay_"):
        await handle_checkpay(chat, user_id, action)
        return

    if action == "profile":
        _, paid_credits = get_user(user_id)
        await chat.send_message(f"👤 Твой баланс:\n\nБаланс: {paid_credits} ₽", reply_markup=back_to_menu_keyboard())
        return

    if action == "partner":
        bot_info = await context.bot.get_me()
        await chat.send_message(
            "🤝 Партнерка\n\nЗа каждого приведенного активного пользователя вы будете получать бонусы на свой бонусный счет.\n\n"
            f"Ваша реферальная ссылка:\nhttps://t.me/{bot_info.username}?start=partner_{user_id}",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "partner_profile":
        await chat.send_message(f"💼 Кабинет партнера\n\nБонусный счет: {get_partner_balance(user_id)} бонусов\n\n1 бонус = 1 ₽.", reply_markup=back_to_menu_keyboard())
        return

    if action == "help":
        await chat.send_message(
            "📘 Инструкция\n\n1. Выберите, что хотите создать.\n2. Выберите нейросеть.\n3. Бот проведет вас по шагам.\n4. Добавьте нужные файлы и описание.\n5. Дождитесь результата.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "create_image":
        await chat.send_message("🖼 Раздел изображений подключим следующим этапом.", reply_markup=back_to_menu_keyboard())
        return

    if action == "create_audio":
        await chat.send_message("🎵 Раздел аудио подключим следующим этапом.", reply_markup=back_to_menu_keyboard())
        return


async def handle_seedance_generate(chat, user_id: int):
    if user_id not in user_states:
        await chat.send_message("Сначала настройте генерацию.", reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2"))
        return

    settings = user_states[user_id]
    price = seedance_price(settings)

    if price <= 0:
        await chat.send_message("Цена для выбранных настроек пока не задана.", reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2"))
        return

    _, paid_credits = get_user(user_id)
    if paid_credits < price:
        await chat.send_message(
            f"💳 Недостаточно средств.\n\nСтоимость: {price} ₽\nВаш баланс: {paid_credits} ₽",
            reply_markup=navigation_keyboard([[InlineKeyboardButton("💳 ПОПОЛНИТЬ БАЛАНС", callback_data="buy")]], back_callback="model_seedance_2")
        )
        return

    await chat.send_message(
        "🎬 Генерация запущена.\n\n"
        "Обычно это занимает несколько минут. Если нейросеть перегружена, ожидание может продлиться до 30 минут."
    )

    charged = False
    task_id = None

    try:
        # 1. Сначала отправляем задачу в Kie.
        # Если Kie не принял задачу и taskId не создан — деньги не списываем.
        task_id = create_seedance_task(settings)

        # 2. Как только Kie подтвердил задачу и вернул taskId — сразу списываем деньги в боте.
        # Это защищает от ситуации, когда Kie уже начал платную генерацию, а баланс клиента не списался.
        charged = charge_user_balance(user_id, price)
        if not charged:
            await chat.send_message(
                "💳 Недостаточно средств.\n\n"
                "Задача уже была отправлена в нейросеть, но списание с баланса не прошло. Свяжитесь с поддержкой.",
                reply_markup=support_keyboard(back_callback="model_seedance_2"),
                disable_web_page_preview=True
            )
            user_states.pop(user_id, None)
            return

        video_url = wait_kie_video_result(task_id)
        video_path = download_video(video_url, user_id)

        try:
            with open(video_path, "rb") as video_file:
                await chat.send_video(
                    video=video_file,
                    caption="✅ Готово! Вот ваше видео.",
                    read_timeout=3600,
                    write_timeout=3600,
                    connect_timeout=60,
                    pool_timeout=3600
                )
        except Exception as e:
            # Kie уже успешно сгенерировал видео, значит деньги на Kie могли быть списаны.
            # Пользователю деньги не возвращаем, а отправляем в поддержку.
            print("TELEGRAM_SEND_VIDEO_ERROR:", repr(e))
            await chat.send_message(
                "⚠️ Видео было создано, но Telegram не смог отправить его в чат.\n\n"
                "Свяжитесь с поддержкой, мы поможем получить результат.",
                reply_markup=support_keyboard(back_callback="main_menu"),
                disable_web_page_preview=True
            )

        _, paid_after = get_user(user_id)
        await chat.send_message(f"Баланс: {paid_after} ₽", reply_markup=back_to_menu_keyboard(back_callback="main_menu"))

    except KieTaskCreateError as e:
        # Kie не подтвердил задачу, taskId не создан. Денег Kie списать не должен, баланс клиента не трогаем.
        print("SEEDANCE_TASK_CREATE_ERROR:", repr(e))
        await send_kie_error(chat, back_callback="model_seedance_2")

    except KieGenerationFailed as e:
        # Kie принял задачу, но вернул fail. В таком случае возвращаем клиенту деньги.
        print("SEEDANCE_KIE_FAILED:", repr(e))
        if charged:
            refund_user_balance(user_id, price)
        await chat.send_message(
            "❌ Ошибка генерации. Деньги возвращены на баланс.\n\n"
            "Если проблема повторяется — свяжитесь с поддержкой.",
            reply_markup=support_keyboard(back_callback="model_seedance_2"),
            disable_web_page_preview=True
        )

    except KieGenerationTimeout as e:
        # Таймаут не означает, что Kie не списал деньги: задача могла продолжать выполняться.
        # Поэтому деньги не возвращаем автоматически, чтобы не было ситуации: Kie списал, а клиент нет.
        print("SEEDANCE_KIE_TIMEOUT:", repr(e))
        await chat.send_message(
            "⚠️ Генерация заняла слишком много времени.\n\n"
            "Задача могла продолжить выполняться на стороне нейросети. Свяжитесь с поддержкой, мы проверим результат.",
            reply_markup=support_keyboard(back_callback="main_menu"),
            disable_web_page_preview=True
        )

    except Exception as e:
        # Неизвестная ошибка после создания задачи может быть связана с Telegram/Render/загрузкой результата.
        # Если Kie уже получил задачу, деньги не возвращаем автоматически.
        import traceback
        print("SEEDANCE_GENERATION_ERROR:", repr(e))
        traceback.print_exc()
        await send_kie_error(chat, back_callback="model_seedance_2")

    finally:
        user_states.pop(user_id, None)


async def handle_topup(chat, user_id: int, action: str):
    amount = int(action.replace("topup_", ""))
    payment_return = user_states.get(user_id, {}).get("payment_return", "")
    return_suffix = "_seedance" if payment_return == "seedance_modes" else ""
    back_callback = "seedance_price_list" if payment_return == "seedance_modes" else "buy"

    payment_url, payment_id = create_yookassa_payment(user_id, amount)
    keyboard = navigation_keyboard([
        [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}{return_suffix}")]
    ], back_callback=back_callback)

    await chat.send_message(
        f"💳 Пополнение баланса на {amount} ₽\n\n"
        f"⚠️ На время оплаты отключите VPN.\n\n"
        f"1. Нажмите «Оплатить»\n"
        f"2. После оплаты вернитесь сюда\n"
        f"3. Нажмите «✅ Проверить оплату»",
        reply_markup=keyboard
    )

async def handle_checkpay(chat, user_id: int, action: str):
    parts = action.split("_")
    payment_id = parts[1]
    amount = int(parts[2])
    return_to_seedance = len(parts) > 3 and parts[3] == "seedance"

    try:
        paid = check_yookassa_payment(payment_id)
    except Exception as e:
        await chat.send_message(f"❌ Не удалось проверить оплату:\n\n{e}", reply_markup=back_to_menu_keyboard())
        return

    if not paid:
        suffix = "_seedance" if return_to_seedance else ""
        back_callback = "seedance_price_list" if return_to_seedance else "buy"
        await chat.send_message(
            "⏳ Оплата пока не найдена.\n\nЕсли вы уже оплатили — подождите 10–20 секунд и нажмите кнопку ещё раз.",
            reply_markup=navigation_keyboard(
                [[InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}{suffix}")]],
                back_callback=back_callback
            )
        )
        return

    give_balance(user_id, amount)
    apply_deposit_bonus(user_id, amount)
    _, paid_credits = get_user(user_id)

    if return_to_seedance:
        user_states.pop(user_id, None)
        await chat.send_message(
            f"✅ Баланс пополнен на {amount} ₽.\nТекущий баланс: {paid_credits} ₽.",
            reply_markup=navigation_keyboard(
                [[InlineKeyboardButton("🎬 Вернуться к выбору режимов", callback_data="model_seedance_2")]],
                back_callback="main_menu"
            )
        )
        return

    await chat.send_message(
        f"✅ Оплата получена!\n\nБаланс пополнен на {amount} ₽.\nТекущий баланс: {paid_credits} ₽.",
        reply_markup=back_to_menu_keyboard()
    )

# ========================= ФАЙЛЫ И ТЕКСТ =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_states:
        await update.message.reply_text("Сначала выберите режим генерации.", reply_markup=main_inline_menu())
        return
    state = user_states[user_id]
    step = state.get("step")
    if step not in ["waiting_first_frame", "waiting_last_frame", "waiting_reference_images"]:
        await update.message.reply_text("Сейчас бот ожидает не изображение.", reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2"))
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    local_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(local_path))
    try:
        kie_url = upload_file_to_kie(str(local_path), "images/xena-seedance")
    except Exception:
        await send_kie_error(update.message.chat, back_callback="model_seedance_2")
        return
    state.setdefault("local_files", []).append(str(local_path))

    if step == "waiting_first_frame":
        if state.get("image_type") == "reference_pack":
            state.setdefault("reference_image_urls", []).append(kie_url)
            state["step"] = "waiting_reference_images"
            await update.message.reply_text(
                f"✅ Изображение получено. Всего: {len(state['reference_image_urls'])}.\n\nМожно отправить еще изображения или нажать «Продолжить».",
                reply_markup=navigation_keyboard([[InlineKeyboardButton("✅ Продолжить", callback_data="seedance_images_done")]], back_callback="seedance_back_to_image_type")
            )
            return
        state["first_frame_url"] = kie_url
        if state.get("image_type") == "first_last":
            state["step"] = "waiting_last_frame"
            await update.message.reply_text("✅ Первый кадр получен.\n\nТеперь загрузите последнее изображение.", reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type"))
            return
        await after_images_ready(update.message.chat, user_id)
        return

    if step == "waiting_last_frame":
        state["last_frame_url"] = kie_url
        await after_images_ready(update.message.chat, user_id)
        return

    if step == "waiting_reference_images":
        urls = state.setdefault("reference_image_urls", [])
        if len(urls) >= 9:
            await update.message.reply_text(
                "Можно загрузить максимум 9 изображений.\n\nНажмите «Продолжить».",
                reply_markup=navigation_keyboard([[InlineKeyboardButton("✅ Продолжить", callback_data="seedance_images_done")]], back_callback="seedance_back_to_image_type")
            )
            return
        urls.append(kie_url)
        await update.message.reply_text(
            f"✅ Изображение получено. Всего: {len(urls)}.\n\nМожно отправить еще изображения или нажать «Продолжить».",
            reply_markup=navigation_keyboard([[InlineKeyboardButton("✅ Продолжить", callback_data="seedance_images_done")]], back_callback="seedance_back_to_image_type")
        )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_states:
        await update.message.reply_text("Сначала выберите режим генерации.", reply_markup=main_inline_menu())
        return
    state = user_states[user_id]
    if state.get("step") != "waiting_video":
        await update.message.reply_text("Сейчас бот ожидает не видео.", reply_markup=back_to_menu_keyboard(back_callback="model_seedance_2"))
        return
    video = update.message.video
    if video is None:
        await update.message.reply_text("Отправьте видео как обычный видеофайл, чтобы бот мог проверить длительность.", reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type"))
        return
    duration = int(round(video.duration or 0))
    if duration <= 0:
        await update.message.reply_text(
            "⚠️ Не удалось определить длительность видео.\n\nЗагрузите другое видео или отправьте его как обычный видеофайл.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type")
        )
        return
    if duration > 15:
        await update.message.reply_text(
            "⚠️ Исходное видео должно быть не длиннее 15 секунд.\n\nЗагрузите другое видео.",
            reply_markup=back_to_menu_keyboard(back_callback="seedance_back_to_image_type")
        )
        return
    file = await context.bot.get_file(video.file_id)
    local_path = MEDIA_DIR / f"{user_id}_{video.file_unique_id}.mp4"
    await file.download_to_drive(str(local_path))
    try:
        kie_url = upload_file_to_kie(str(local_path), "videos/xena-seedance")
    except Exception:
        await send_kie_error(update.message.chat, back_callback="model_seedance_2")
        return
    state.setdefault("local_files", []).append(str(local_path))
    state["reference_video_url"] = kie_url
    state["video_duration"] = duration
    state["duration"] = normalize_video_duration(duration)
    state["step"] = "waiting_prompt"
    await update.message.reply_text(
        f"✅ Видео получено. Длительность: {duration} секунд.\n\nДлительность генерации будет выставлена автоматически: {state["duration"]} секунд.",
    )
    await ask_seedance_prompt(update.message, back_callback="seedance_back_to_image_type")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    if text == "🚀 Запустить бота":
        await send_main_menu(update.message)
        return
    if text == "🆘 Связаться с поддержкой":
        await update.message.reply_text(f"🆘 Написать в поддержку: {SUPPORT_URL}", disable_web_page_preview=True)
        return
    if user_id in user_states and user_states[user_id].get("step") == "waiting_prompt":
        user_states[user_id]["prompt"] = text
        user_states[user_id]["step"] = "choose_audio"
        await ask_seedance_audio(update.message, back_callback="seedance_back_to_prompt")
        return
    await update.message.reply_text("Выберите действие в меню.", reply_markup=main_inline_menu())


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Пополнение баланса:", reply_markup=topup_inline_menu())


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    payload = update.message.successful_payment.invoice_payload
    if payload.startswith("topup_"):
        amount = int(payload.replace("topup_", ""))
        give_balance(user_id, amount)
        apply_deposit_bonus(user_id, amount)
        _, paid_credits = get_user(user_id)
        await update.message.reply_text(f"✅ Баланс пополнен на {amount} ₽.\n\nТекущий баланс: {paid_credits} ₽.")


# ========================= MAIN =========================

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
    app.add_handler(CommandHandler("resetuser", resetuser))
    app.add_handler(CommandHandler("partners", partners))
    app.add_handler(CommandHandler("paypartner", paypartner))
    app.add_handler(CallbackQueryHandler(handle_menu_button))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
