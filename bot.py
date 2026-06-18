import os
import json
import time
import sqlite3
import requests
from pathlib import Path
from typing import Optional, Tuple, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# ENV / SETTINGS
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KIE_API_KEY = os.getenv("KIE_API_KEY")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# Можно менять модели через Render Environment Variables без правки кода
KIE_IMAGE_TO_VIDEO_MODEL = os.getenv("KIE_IMAGE_TO_VIDEO_MODEL", "grok-imagine-video-1-5-preview")
KIE_TEXT_TO_VIDEO_MODEL = os.getenv("KIE_TEXT_TO_VIDEO_MODEL", "grok-imagine-video-1-5-preview")
KIE_TEXT_TO_IMAGE_MODEL = os.getenv("KIE_TEXT_TO_IMAGE_MODEL", "gpt-4o-image")

SUPPORT_URL = "https://t.me/Vlad101ss"
BOT_RETURN_URL = os.getenv("BOT_RETURN_URL", "https://t.me/Xena20Bot")

DB_PATH = os.getenv("DB_PATH", "/var/data/users.db")
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "media"))
MEDIA_DIR.mkdir(exist_ok=True)

ADMIN_IDS = {6164104276}

ASPECT_RATIO = "9:16"
RESOLUTION = "480p"

IMAGE_PRICE = 50
VIDEO_PRICES = {
    "5": 100,
    "10": 180,
    "15": 250,
}
TOPUP_AMOUNTS = [500, 1000, 1500]

user_states = {}

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден в Render Environment Variables")
if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден в Render Environment Variables")
if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден в Render Environment Variables")
if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден в Render Environment Variables")


# =========================
# MENUS
# =========================

def main_inline_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="video_menu")],
        [InlineKeyboardButton("🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ", callback_data="image_start")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url=SUPPORT_URL)],
    ]
    return InlineKeyboardMarkup(keyboard)


def video_mode_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📸 Видео из изображения", callback_data="video_image")],
        [InlineKeyboardButton("📝 Видео по описанию", callback_data="video_text")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def duration_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("5 секунд — 100 ₽", callback_data="duration_5")],
        [InlineKeyboardButton("10 секунд — 180 ₽", callback_data="duration_10")],
        [InlineKeyboardButton("15 секунд — 250 ₽", callback_data="duration_15")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="video_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def topup_menu() -> ReplyKeyboardMarkup:
    keyboard = [[f"💳 Пополнить баланс на {amount} ₽"] for amount in TOPUP_AMOUNTS]
    keyboard.append(["🏠 Главное меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def not_enough_balance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
    ])


def after_generation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ЕЩЁ", callback_data="video_menu")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
    ])


# =========================
# DATABASE
# =========================

def db_connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            paid_credits INTEGER DEFAULT 0,
            generations_count INTEGER DEFAULT 0,
            spent_total INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT 0
        )
    """)

    # Для совместимости, если база уже была создана старым ботом
    for sql in [
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE users ADD COLUMN paid_credits INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN generations_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN spent_total INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN created_at INTEGER DEFAULT 0",
    ]:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id TEXT,
            mode TEXT,
            cost INTEGER,
            status TEXT DEFAULT 'waiting',
            created_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


def ensure_user(user_id: int, username: Optional[str] = None):
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, paid_credits, generations_count, spent_total, created_at) VALUES (?, ?, 0, 0, 0, ?)",
        (user_id, username.lower() if username else None, int(time.time()))
    )

    if username:
        cur.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username.lower(), user_id)
        )

    conn.commit()
    conn.close()


def get_user(user_id: int) -> Tuple[int, int, int]:
    ensure_user(user_id)
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT paid_credits, generations_count, spent_total FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0, 0, 0
    return row[0] or 0, row[1] or 0, row[2] or 0


def add_paid_credit(user_id: int, amount: int):
    ensure_user(user_id)
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET paid_credits = paid_credits + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def decrement_paid_credit(user_id: int, amount: int):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET paid_credits = paid_credits - ? WHERE user_id = ? AND paid_credits >= ?",
        (amount, user_id, amount)
    )
    conn.commit()
    conn.close()


def add_generation_stats(user_id: int, cost: int):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET generations_count = generations_count + 1,
            spent_total = spent_total + ?
        WHERE user_id = ?
        """,
        (cost, user_id)
    )
    conn.commit()
    conn.close()


def get_user_id_by_username(username: str) -> Optional[int]:
    username = username.replace("@", "").lower().strip()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def give_balance(user_id: int, amount: int):
    ensure_user(user_id)
    add_paid_credit(user_id, amount)


def save_active_generation(user_id: int, task_id: str, mode: str, cost: int):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO active_generations (user_id, task_id, mode, cost, status, created_at)
        VALUES (?, ?, ?, ?, 'waiting', ?)
        """,
        (user_id, task_id, mode, cost, int(time.time()))
    )
    conn.commit()
    conn.close()


def finish_active_generation(task_id: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE active_generations SET status = 'done' WHERE task_id = ?",
        (task_id,)
    )
    conn.commit()
    conn.close()


# =========================
# YOOKASSA
# =========================

def create_yookassa_payment(user_id: int, amount: int) -> Tuple[str, str]:
    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": f"topup_{user_id}_{amount}_{int(time.time())}",
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": BOT_RETURN_URL,
        },
        "description": f"Пополнение баланса Xena 2.0 на {amount} рублей",
        "metadata": {
            "user_id": str(user_id),
            "amount": str(amount),
        },
    }

    response = requests.post(
        url,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    return result["confirmation"]["confirmation_url"], result["id"]


def check_yookassa_payment(payment_id: str) -> bool:
    url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
    response = requests.get(
        url,
        auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY),
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    return result.get("status") == "succeeded"


# =========================
# KIE API
# =========================

def upload_file_to_kie(file_path: str) -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "application/octet-stream")}
        data = {
            "uploadPath": "images/xena-2-bot",
            "fileName": Path(file_path).name,
        }
        response = requests.post(url, headers=headers, files=files, data=data, timeout=3600)

    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки файла в Kie: {result}")
    return result["data"]["downloadUrl"]


def create_kie_task(model: str, input_data: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": input_data}

    response = requests.post(url, headers=headers, json=payload, timeout=3600)

    # Важно: Kie иногда возвращает 422 именно тут
    if response.status_code == 422:
        raise RuntimeError("KIE_422: Please try again, or change your input files or prompt.")

    response.raise_for_status()
    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания задачи Kie: {result}")

    task_id = result.get("data", {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"Kie не вернул taskId: {result}")
    return task_id


def wait_kie_result(task_id: str) -> List[str]:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}

    for _ in range(3600):
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"taskId": task_id},
                timeout=3600,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.Timeout:
            time.sleep(10)
            continue

        data = result.get("data", {}) or {}
        state = data.get("state")

        if state == "success":
            raw = data.get("resultJson")
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})

            urls = (
                parsed.get("resultUrls")
                or parsed.get("videoUrls")
                or parsed.get("videos")
                or parsed.get("imageUrls")
                or parsed.get("images")
                or parsed.get("urls")
                or []
            )

            if isinstance(urls, str):
                urls = [urls]

            if not urls:
                # Иногда ссылка бывает глубже
                for value in parsed.values():
                    if isinstance(value, str) and value.startswith("http"):
                        urls = [value]
                        break
                    if isinstance(value, list):
                        found = [x for x in value if isinstance(x, str) and x.startswith("http")]
                        if found:
                            urls = found
                            break

            if not urls:
                raise RuntimeError(f"Результат готов, но ссылка не найдена: {parsed}")
            return urls

        if state == "fail":
            fail_msg = data.get("failMsg") or data.get("errorMessage") or str(data)
            if "please try again" in fail_msg.lower() or "change your input" in fail_msg.lower():
                raise RuntimeError("KIE_422: Please try again, or change your input files or prompt.")
            raise RuntimeError(f"Kie не смог выполнить задачу: {fail_msg}")

        time.sleep(10)

    raise RuntimeError("Задача Kie выполнялась слишком долго. Попробуй позже.")


def download_file(url: str, user_id: int, suffix: str) -> str:
    path = MEDIA_DIR / f"{user_id}_{int(time.time())}_{suffix}"
    response = requests.get(url, timeout=3600)
    response.raise_for_status()
    with open(path, "wb") as f:
        f.write(response.content)
    return str(path)


def create_image_to_video_task(image_url: str, prompt: str, duration: str) -> str:
    input_data = {
        "prompt": prompt,
        "image_urls": [image_url],
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": int(duration),
    }
    return create_kie_task(KIE_IMAGE_TO_VIDEO_MODEL, input_data)


def create_text_to_video_task(prompt: str, duration: str) -> str:
    input_data = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "duration": int(duration),
    }
    return create_kie_task(KIE_TEXT_TO_VIDEO_MODEL, input_data)


def create_text_to_image_task(prompt: str) -> str:
    input_data = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
    }
    return create_kie_task(KIE_TEXT_TO_IMAGE_MODEL, input_data)


# =========================
# TEXTS
# =========================

def censor_error_text() -> str:
    return (
        "⚠️ Нейросеть не приняла этот запрос.\n\n"
        "Скорее всего, фото или описание не прошли проверку безопасности.\n\n"
        "Попробуй:\n"
        "— заменить фото;\n"
        "— смягчить описание;\n"
        "— убрать слишком откровенные или запрещённые детали."
    )


def common_generation_error_text() -> str:
    return (
        "❌ Произошла ошибка генерации.\n\n"
        "Если проблема повторяется — напиши в поддержку:\n"
        f"{SUPPORT_URL}"
    )


def temporary_error_text() -> str:
    return (
        "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
        "Попробуй ещё раз через 1–2 минуты или немного измени описание."
    )


# =========================
# BOT MESSAGE HELPERS
# =========================

async def send_main_menu_message(message):
    await message.reply_text(
        "👋 Добро пожаловать в Xena 2.0\n\n"
        "Создавай изображения и вертикальные видео 9:16 для TikTok, Reels и Shorts.",
        reply_markup=main_inline_menu(),
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.message.from_user.id, update.message.from_user.username)
    user_states.pop(update.message.from_user.id, None)
    await send_main_menu_message(update.message)


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    ensure_user(user_id, update.message.from_user.username)
    user_states.pop(user_id, None)
    await send_main_menu_message(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    ensure_user(user_id, update.message.from_user.username)
    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


async def give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Используй:\n/give USER_ID СУММА\n\nПример:\n/give 123456789 500")
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
    admin_id = update.message.from_user.id
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Используй:\n/giveuser @username СУММА\n\nПример:\n/giveuser @username 500")
        return

    username = context.args[0]
    try:
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Ошибка суммы.")
        return

    target_id = get_user_id_by_username(username)
    if target_id is None:
        await update.message.reply_text("❌ Пользователь не найден. Он должен сначала написать боту /start.")
        return

    give_balance(target_id, amount)
    await update.message.reply_text(f"✅ {username} выдано {amount} ₽")


async def statsuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id
    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Используй:\n/statsuser @username")
        return

    username = context.args[0].replace("@", "").lower()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, paid_credits, generations_count, spent_total FROM users WHERE username = ?",
        (username,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("❌ Пользователь не найден. Он должен сначала написать боту /start.")
        return

    user_id, uname, paid_credits, generations_count, spent_total = row
    await update.message.reply_text(
        f"👤 Статистика пользователя:\n\n"
        f"@{uname}\n"
        f"ID: {user_id}\n\n"
        f"🎬 Генераций: {generations_count or 0}\n"
        f"💸 Потратил: {spent_total or 0} ₽\n"
        f"💰 Баланс: {paid_credits or 0} ₽"
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса\n\n"
        "Выбери сумму пополнения:",
        reply_markup=topup_menu(),
    )


# =========================
# CALLBACKS
# =========================

async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    ensure_user(user_id, query.from_user.username)
    action = query.data

    if action == "main_menu":
        user_states.pop(user_id, None)
        await query.message.reply_text(
            "Главное меню:",
            reply_markup=main_inline_menu(),
        )
        return

    if action == "video_menu":
        user_states.pop(user_id, None)
        await query.message.reply_text(
            "🎬 Выбери тип генерации видео:",
            reply_markup=video_mode_menu(),
        )
        return

    if action == "video_image":
        user_states[user_id] = {"mode": "image_to_video_wait_photo"}
        await query.message.reply_text(
            "📸 Отправь изображение, которое нужно оживить."
        )
        return

    if action == "video_text":
        user_states[user_id] = {"mode": "text_to_video_wait_prompt"}
        await query.message.reply_text(
            "📝 Опиши видео, которое хочешь создать.\n\n"
            "Например: девушка идёт по ночному городу, камера плавно приближается, киношный свет."
        )
        return

    if action == "image_start":
        paid_credits, _, _ = get_user(user_id)
        if paid_credits < IMAGE_PRICE:
            await query.message.reply_text(
                f"💰 Баланс: {paid_credits} ₽\n\n"
                f"💳 Для создания изображения нужно {IMAGE_PRICE} ₽.",
                reply_markup=not_enough_balance_menu(),
            )
            return

        user_states[user_id] = {"mode": "text_to_image_wait_prompt"}
        await query.message.reply_text(
            "🖼 Пришли описание изображения.\n\n"
            "Стоимость генерации: 50 ₽."
        )
        return

    if action.startswith("duration_"):
        duration = action.replace("duration_", "")
        if duration not in VIDEO_PRICES:
            await query.message.reply_text("❌ Неверная длительность.")
            return

        if user_id not in user_states:
            await query.message.reply_text("Сначала выбери тип генерации.", reply_markup=video_mode_menu())
            return

        paid_credits, _, _ = get_user(user_id)
        cost = VIDEO_PRICES[duration]
        if paid_credits < cost:
            await query.message.reply_text(
                f"💰 Баланс: {paid_credits} ₽\n\n"
                f"💳 Для генерации на {duration} секунд нужно {cost} ₽.",
                reply_markup=not_enough_balance_menu(),
            )
            return

        user_states[user_id]["duration"] = duration
        mode = user_states[user_id].get("mode")

        if mode == "image_to_video_wait_duration":
            await query.message.reply_text(
                "✍️ Теперь отправь описание видео.\n\n"
                "Чем подробнее описание, тем лучше результат."
            )
            user_states[user_id]["mode"] = "image_to_video_wait_prompt"
            return

        if mode == "text_to_video_wait_duration":
            await run_generation(update, context, user_id)
            return

        await query.message.reply_text("❌ Состояние генерации сбилось. Начни заново.", reply_markup=video_mode_menu())
        user_states.pop(user_id, None)
        return

    if action == "buy":
        await query.message.reply_text(
            "💳 Пополнение баланса\n\n"
            "Стоимость:\n"
            "🖼 Изображение — 50 ₽\n"
            "🎬 Видео 5 секунд — 100 ₽\n"
            "🎬 Видео 10 секунд — 180 ₽\n"
            "🎬 Видео 15 секунд — 250 ₽\n\n"
            "Выбери сумму пополнения:",
            reply_markup=topup_menu(),
        )
        return

    if action.startswith("checkpay_"):
        parts = action.split("_")
        payment_id = parts[1]
        amount = int(parts[2])

        try:
            paid = check_yookassa_payment(payment_id)
        except Exception as e:
            await query.message.reply_text(f"❌ Не удалось проверить оплату:\n\n{e}")
            return

        if not paid:
            await query.message.reply_text(
                "⏳ Оплата пока не найдена.\n\n"
                "Если ты уже оплатил — подожди 10–20 секунд и нажми кнопку ещё раз."
            )
            return

        add_paid_credit(user_id, amount)
        paid_credits, _, _ = get_user(user_id)
        await query.message.reply_text(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽.",
            reply_markup=main_inline_menu(),
        )
        return

    if action == "profile":
        paid_credits, generations_count, spent_total = get_user(user_id)
        await query.message.reply_text(
            f"👤 Твой профиль:\n\n"
            f"💰 Баланс: {paid_credits} ₽\n"
            f"🎬 Генераций: {generations_count}\n"
            f"💸 Потрачено: {spent_total} ₽\n\n"
            f"Стоимость:\n"
            f"🖼 Изображение — {IMAGE_PRICE} ₽\n"
            f"🎬 5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"🎬 10 секунд — {VIDEO_PRICES['10']} ₽\n"
            f"🎬 15 секунд — {VIDEO_PRICES['15']} ₽"
        )
        return

    if action == "help":
        await query.message.reply_text(
            "📘 Инструкция Xena 2.0\n\n"
            "1. Нажми 🎬 СОЗДАТЬ ВИДЕО или 🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ.\n"
            "2. Для видео выбери: видео из изображения или видео по описанию.\n"
            "3. При необходимости отправь фото.\n"
            "4. Напиши подробное описание.\n"
            "5. Выбери длительность: 5, 10 или 15 секунд.\n"
            "6. Дождись результата.\n\n"
            "Формат видео: 9:16 — подходит для TikTok, Reels и Shorts.\n"
            "Чем подробнее описание, тем лучше результат."
        )
        return


# =========================
# MESSAGE HANDLERS
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    ensure_user(user_id, update.message.from_user.username)

    if user_id not in user_states or user_states[user_id].get("mode") != "image_to_video_wait_photo":
        await update.message.reply_text(
            "Сначала выбери режим: 🎬 СОЗДАТЬ ВИДЕО → 📸 Видео из изображения.",
            reply_markup=main_inline_menu(),
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id]["image_path"] = str(image_path)
    user_states[user_id]["mode"] = "image_to_video_wait_duration"

    await update.message.reply_text(
        "✅ Изображение получил.\n\nВыбери длительность видео:",
        reply_markup=duration_menu(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    ensure_user(user_id, update.message.from_user.username)

    if text == "🏠 Главное меню":
        user_states.pop(user_id, None)
        await send_main_menu_message(update.message)
        return

    if text.startswith("💳 Пополнить баланс на "):
        amount_text = text.replace("💳 Пополнить баланс на ", "").replace(" ₽", "").strip()
        try:
            amount = int(amount_text)
        except Exception:
            await update.message.reply_text("❌ Не смог распознать сумму.")
            return

        if amount not in TOPUP_AMOUNTS:
            await update.message.reply_text("❌ Недоступная сумма пополнения.")
            return

        payment_url, payment_id = create_yookassa_payment(user_id, amount)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Оплатить {amount} ₽", url=payment_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")],
        ])

        await update.message.reply_text(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            f"1. Нажми «Оплатить {amount} ₽»\n"
            f"2. После оплаты вернись сюда\n"
            f"3. Нажми «✅ Проверить оплату»",
            reply_markup=keyboard,
        )
        return

    if user_id not in user_states:
        await update.message.reply_text(
            "Выбери действие в меню:",
            reply_markup=main_inline_menu(),
        )
        return

    mode = user_states[user_id].get("mode")

    if mode == "text_to_image_wait_prompt":
        user_states[user_id]["prompt"] = text
        await run_generation(update, context, user_id)
        return

    if mode == "text_to_video_wait_prompt":
        user_states[user_id]["prompt"] = text
        user_states[user_id]["mode"] = "text_to_video_wait_duration"
        await update.message.reply_text(
            "✅ Описание получил.\n\nВыбери длительность видео:",
            reply_markup=duration_menu(),
        )
        return

    if mode == "image_to_video_wait_prompt":
        user_states[user_id]["prompt"] = text
        await run_generation(update, context, user_id)
        return

    await update.message.reply_text("Сейчас я не жду текст. Выбери действие в меню.", reply_markup=main_inline_menu())


# =========================
# GENERATION RUNNER
# =========================

async def run_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id, {})
    mode = state.get("mode")
    prompt = state.get("prompt")

    if not prompt:
        await update.effective_message.reply_text("❌ Не найдено описание. Начни заново.")
        user_states.pop(user_id, None)
        return

    if mode == "text_to_image_wait_prompt":
        cost = IMAGE_PRICE
        generation_type = "text_to_image"
    elif mode == "text_to_video_wait_duration":
        duration = state.get("duration")
        cost = VIDEO_PRICES[duration]
        generation_type = "text_to_video"
    elif mode == "image_to_video_wait_prompt":
        duration = state.get("duration")
        cost = VIDEO_PRICES[duration]
        generation_type = "image_to_video"
    else:
        await update.effective_message.reply_text("❌ Состояние генерации сбилось. Начни заново.")
        user_states.pop(user_id, None)
        return

    paid_credits, _, _ = get_user(user_id)
    if paid_credits < cost:
        await update.effective_message.reply_text(
            f"💰 Баланс: {paid_credits} ₽\n\n"
            f"💳 Недостаточно средств. Нужно: {cost} ₽.",
            reply_markup=not_enough_balance_menu(),
        )
        return

    await update.effective_message.reply_text(
        "🎥 Запускаю нейросеть.\n\n"
        "Генерация может занять несколько минут. Не отправляй новые сообщения, пока я работаю."
    )

    task_id = None
    try:
        if generation_type == "text_to_image":
            print("GENERATION: create text-to-image task", flush=True)
            task_id = create_text_to_image_task(prompt)

        elif generation_type == "text_to_video":
            duration = state["duration"]
            print("GENERATION: create text-to-video task", flush=True)
            task_id = create_text_to_video_task(prompt, duration)

        elif generation_type == "image_to_video":
            image_path = state.get("image_path")
            if not image_path:
                await update.effective_message.reply_text("❌ Не найдено изображение. Начни заново.")
                user_states.pop(user_id, None)
                return

            print("GENERATION: upload image", flush=True)
            image_url = upload_file_to_kie(image_path)
            duration = state["duration"]

            print("GENERATION: create image-to-video task", flush=True)
            task_id = create_image_to_video_task(image_url, prompt, duration)

        print(f"GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)
        save_active_generation(user_id, task_id, generation_type, cost)
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost)

        print(f"GENERATION: wait result {task_id}", flush=True)
        result_urls = wait_kie_result(task_id)
        finish_active_generation(task_id)

        result_url = result_urls[0]
        print(f"GENERATION: result {result_url}", flush=True)

        if generation_type == "text_to_image":
            try:
                await update.effective_message.reply_photo(
                    photo=result_url,
                    caption="✅ Готово! Вот твоё изображение.",
                    reply_markup=main_inline_menu(),
                )
            except Exception:
                path = download_file(result_url, user_id, "result.jpg")
                with open(path, "rb") as f:
                    await update.effective_message.reply_photo(
                        photo=f,
                        caption="✅ Готово! Вот твоё изображение.",
                        reply_markup=main_inline_menu(),
                    )
        else:
            try:
                await update.effective_message.reply_video(
                    video=result_url,
                    caption="✅ Готово! Вот твоё AI-видео.",
                    read_timeout=3600,
                    write_timeout=3600,
                    connect_timeout=60,
                    pool_timeout=3600,
                    reply_markup=after_generation_menu(),
                )
            except Exception:
                try:
                    path = download_file(result_url, user_id, "result.mp4")
                    with open(path, "rb") as f:
                        await update.effective_message.reply_video(
                            video=f,
                            caption="✅ Готово! Вот твоё AI-видео.",
                            read_timeout=3600,
                            write_timeout=3600,
                            connect_timeout=60,
                            pool_timeout=3600,
                            reply_markup=after_generation_menu(),
                        )
                except Exception:
                    await update.effective_message.reply_text(
                        "⚠️ Видео было сгенерировано, но Telegram не смог его отправить.\n\n"
                        f"Напиши в поддержку:\n{SUPPORT_URL}",
                        disable_web_page_preview=True,
                    )

        paid_after, _, _ = get_user(user_id)
        await update.effective_message.reply_text(f"💰 Баланс: {paid_after} ₽")

    except Exception as e:
        import traceback
        print("GENERATION_ERROR:", repr(e), flush=True)
        traceback.print_exc()

        error_text = str(e).lower()

        if (
            "kie_422" in error_text
            or "422" in error_text
            or "please try again" in error_text
            or "change your input files or prompt" in error_text
        ):
            await update.effective_message.reply_text(censor_error_text())
        elif (
            "internal error" in error_text
            or "try again later" in error_text
            or "timeout" in error_text
            or "too long" in error_text
            or "перегруж" in error_text
        ):
            await update.effective_message.reply_text(temporary_error_text())
        else:
            await update.effective_message.reply_text(
                common_generation_error_text(),
                disable_web_page_preview=True,
            )

    finally:
        user_states.pop(user_id, None)


# =========================
# MAIN
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
    app.add_handler(CommandHandler("statsuser", statsuser))
    app.add_handler(CallbackQueryHandler(menu_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Xena 2.0 bot started...", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
