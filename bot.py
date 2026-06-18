import os
import json
import time
import sqlite3
import requests
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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
    raise RuntimeError("TELEGRAM_TOKEN не найден в переменных Render")
if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден в переменных Render")
if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден в переменных Render")
if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден в переменных Render")

# =========================
# SETTINGS
# =========================

BOT_NAME = "Xena 2.0"
SUPPORT_URL = "https://t.me/Vlad101ss"

DB_PATH = os.getenv("DB_PATH", "/var/data/users.db")
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

ADMIN_IDS = {
    6164104276
}

IMAGE_PRICE = 50

VIDEO_PRICES = {
    "5": 100,
    "10": 180,
    "15": 250,
}

TOPUP_AMOUNTS = [500, 1000, 1500]

ASPECT_RATIO = "9:16"
VIDEO_RESOLUTION = "480p"

# Основная модель для видео. Если захочешь Seedance — поменяем тут.
KIE_VIDEO_MODEL = os.getenv("KIE_VIDEO_MODEL", "grok-imagine-video-1-5-preview")

# Модель для text-to-image. Если Kie даст другое название модели — поменяем в Render ENV KIE_IMAGE_MODEL.
# ВАЖНО: название может отличаться у Kie. Если будет ошибка модели — пришлёшь лог, заменим.
KIE_IMAGE_MODEL = os.getenv("KIE_IMAGE_MODEL", "gpt-4o-image")

user_states = {}

# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            paid_credits INTEGER DEFAULT 0,
            generations_count INTEGER DEFAULT 0,
            spent_total INTEGER DEFAULT 0
        )
    """)

    # Безопасно добавляем колонки, если база была старая
    for sql in [
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE users ADD COLUMN paid_credits INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN generations_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN spent_total INTEGER DEFAULT 0",
    ]:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


def ensure_user(user_id: int, username: str | None = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, paid_credits, generations_count, spent_total) VALUES (?, ?, 0, 0, 0)",
        (user_id, username.lower() if username else None)
    )

    if username:
        cur.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username.lower(), user_id)
        )

    conn.commit()
    conn.close()


def get_user(user_id: int):
    ensure_user(user_id)

    conn = sqlite3.connect(DB_PATH)
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

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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


def add_generation_stats(user_id: int, cost: int):
    conn = sqlite3.connect(DB_PATH)
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


def get_user_id_by_username(username: str):
    username = username.replace("@", "").lower().strip()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    conn.close()

    return row[0] if row else None


# =========================
# MENUS
# =========================

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="video_menu")],
        [InlineKeyboardButton("🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ", callback_data="image_start")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url=SUPPORT_URL)],
    ])


def video_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Видео из изображения", callback_data="video_image")],
        [InlineKeyboardButton("📝 Видео по описанию", callback_data="video_text")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")],
    ])


def duration_menu(mode: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 секунд — 100 ₽", callback_data=f"duration_{mode}_5")],
        [InlineKeyboardButton("10 секунд — 180 ₽", callback_data=f"duration_{mode}_10")],
        [InlineKeyboardButton("15 секунд — 250 ₽", callback_data=f"duration_{mode}_15")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="video_menu")],
    ])


def topup_menu():
    return ReplyKeyboardMarkup(
        [
            ["💳 Пополнить баланс на 500 ₽"],
            ["💳 Пополнить баланс на 1000 ₽"],
            ["💳 Пополнить баланс на 1500 ₽"],
            ["🏠 Главное меню"],
        ],
        resize_keyboard=True
    )


def not_enough_balance_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
    ])


# =========================
# TEXTS
# =========================

MAIN_TEXT = (
    "🔥 Xena 2.0\n\n"
    "Создавай изображения и вертикальные AI-видео в формате 9:16.\n\n"
    "Выбери, что хочешь сделать:"
)

HELP_TEXT = (
    "📘 Инструкция Xena 2.0\n\n"
    "1. Нажми «🎬 СОЗДАТЬ ВИДЕО» или «🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ».\n"
    "2. Для видео выбери режим: из изображения или по описанию.\n"
    "3. Отправь фото, если выбрал видео из изображения.\n"
    "4. Напиши описание того, что должно получиться.\n"
    "5. Выбери длительность видео: 5, 10 или 15 секунд.\n"
    "6. Дождись готового результата.\n\n"
    "💰 Стоимость:\n"
    "🖼 Изображение — 50 ₽\n"
    "🎬 Видео 5 сек — 100 ₽\n"
    "🎬 Видео 10 сек — 180 ₽\n"
    "🎬 Видео 15 сек — 250 ₽\n\n"
    "Чем подробнее описание, тем лучше результат."
)

CENSORED_TEXT = (
    "⚠️ Нейросеть не приняла этот запрос.\n\n"
    "Скорее всего, фото или описание не прошли проверку безопасности.\n\n"
    "Попробуй:\n"
    "— заменить фото;\n"
    "— смягчить описание;\n"
    "— убрать слишком откровенные или запрещённые детали."
)

GENERIC_ERROR_TEXT = (
    "❌ Произошла ошибка генерации.\n\n"
    "Если проблема повторяется — напиши в поддержку:\n"
    f"{SUPPORT_URL}"
)

TELEGRAM_SEND_ERROR_VIDEO = (
    "⚠️ Видео было сгенерировано, но Telegram не смог его отправить.\n\n"
    "Напиши в поддержку:\n"
    f"{SUPPORT_URL}"
)

TELEGRAM_SEND_ERROR_IMAGE = (
    "⚠️ Изображение было сгенерировано, но Telegram не смог его отправить.\n\n"
    "Напиши в поддержку:\n"
    f"{SUPPORT_URL}"
)


# =========================
# YOOKASSA
# =========================

def create_yookassa_payment(user_id: int, amount: int):
    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": f"topup_{user_id}_{amount}_{int(time.time())}",
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB"
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/Xena20Bot"
        },
        "description": f"Пополнение баланса Xena 2.0 на {amount} рублей",
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
# KIE
# =========================

def upload_image_to_kie(image_path: str) -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}"
    }

    with open(image_path, "rb") as f:
        files = {
            "file": (Path(image_path).name, f, "image/jpeg")
        }
        data = {
            "uploadPath": "images/xena-2-bot",
            "fileName": Path(image_path).name
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=3600)

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки файла в Kie: {result}")

    return result["data"]["downloadUrl"]


def create_kie_video_task(prompt: str, duration: str, image_url: str | None = None) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }

    input_data = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": VIDEO_RESOLUTION,
        "duration": int(duration)
    }

    if image_url:
        input_data["image_urls"] = [image_url]

    payload = {
        "model": KIE_VIDEO_MODEL,
        "input": input_data
    }

    response = requests.post(url, headers=headers, json=payload, timeout=3600)

    if response.status_code == 422:
        raise RuntimeError(f"KIE_422: {response.text}")

    response.raise_for_status()
    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания видео-задачи Kie: {result}")

    return result["data"]["taskId"]


def create_kie_image_task(prompt: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": KIE_IMAGE_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": ASPECT_RATIO
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=3600)

    if response.status_code == 422:
        raise RuntimeError(f"KIE_422: {response.text}")

    response.raise_for_status()
    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания image-задачи Kie: {result}")

    return result["data"]["taskId"]


def wait_kie_result(task_id: str) -> list[str]:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}"
    }

    for _ in range(3600):
        response = requests.get(
            url,
            headers=headers,
            params={"taskId": task_id},
            timeout=3600
        )

        response.raise_for_status()
        result = response.json()

        data = result.get("data", {})
        state = data.get("state")

        if state == "success":
            raw = data.get("resultJson")
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})

            urls = (
                parsed.get("resultUrls")
                or parsed.get("videoUrls")
                or parsed.get("imageUrls")
                or parsed.get("images")
                or parsed.get("videos")
                or []
            )

            if isinstance(urls, str):
                urls = [urls]

            if not urls:
                raise RuntimeError(f"Результат готов, но ссылка не найдена: {parsed}")

            return urls

        if state == "fail":
            raise RuntimeError(f"Kie не смог сгенерировать результат: {data.get('failMsg')}")

        time.sleep(10)

    raise RuntimeError("Генерация шла слишком долго. Попробуй позже.")


def download_file(url: str, user_id: int, suffix: str):
    file_path = MEDIA_DIR / f"{user_id}_{int(time.time())}.{suffix}"

    response = requests.get(url, timeout=3600)
    response.raise_for_status()

    with open(file_path, "wb") as f:
        f.write(response.content)

    return str(file_path)


# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    ensure_user(user_id, username)
    user_states.pop(user_id, None)

    await update.message.reply_text(
        MAIN_TEXT,
        reply_markup=main_menu()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса\n\n"
        "Выбери сумму пополнения:",
        reply_markup=topup_menu()
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    ensure_user(user_id, username)

    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


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
            "/giveuser @vlad 500"
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

    add_paid_credit(target_id, amount)

    await update.message.reply_text(
        f"✅ @{username.replace('@', '')} выдано {amount} ₽"
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
            "/give 123456789 500"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Ошибка формата.")
        return

    add_paid_credit(target_id, amount)

    await update.message.reply_text(
        f"✅ Пользователю {target_id} выдано {amount} ₽"
    )


async def statsuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.message.from_user.id

    if admin_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Используй:\n"
            "/statsuser @username"
        )
        return

    username = context.args[0].replace("@", "").lower()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, username, paid_credits, generations_count, spent_total
        FROM users
        WHERE username = ?
        """,
        (username,)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            "❌ Пользователь не найден.\n"
            "Он должен сначала написать боту /start."
        )
        return

    user_id, username, paid_credits, generations_count, spent_total = row

    await update.message.reply_text(
        f"👤 Статистика пользователя:\n\n"
        f"@{username}\n"
        f"ID: {user_id}\n\n"
        f"🎬 Генераций заказал: {generations_count or 0}\n"
        f"💸 Потратил: {spent_total or 0} ₽\n"
        f"💰 Текущий баланс: {paid_credits or 0} ₽"
    )


# =========================
# CALLBACKS
# =========================

async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    username = query.from_user.username
    ensure_user(user_id, username)

    action = query.data

    if action == "main_menu":
        user_states.pop(user_id, None)
        await query.message.reply_text(
            MAIN_TEXT,
            reply_markup=main_menu()
        )
        return

    if action == "video_menu":
        user_states.pop(user_id, None)
        await query.message.reply_text(
            "🎬 Выбери тип видео:",
            reply_markup=video_menu()
        )
        return

    if action == "video_image":
        user_states[user_id] = {"mode": "video_image_wait_photo"}
        await query.message.reply_text(
            "📸 Отправь фото, которое хочешь оживить."
        )
        return

    if action == "video_text":
        user_states[user_id] = {"mode": "video_text_wait_prompt"}
        await query.message.reply_text(
            "📝 Напиши описание видео.\n\n"
            "Например: девушка идёт по улице, камера плавно приближается, кинематографичный свет."
        )
        return

    if action == "image_start":
        user_states[user_id] = {"mode": "image_wait_prompt"}
        await query.message.reply_text(
            f"🖼 Создание изображения — {IMAGE_PRICE} ₽\n\n"
            "Напиши описание изображения."
        )
        return

    if action.startswith("duration_"):
        parts = action.split("_")
        # duration_video_image_5 или duration_video_text_5
        duration = parts[-1]
        mode = "_".join(parts[1:-1])

        if user_id not in user_states:
            await query.message.reply_text(
                "Сессия устарела. Начни заново.",
                reply_markup=main_menu()
            )
            return

        user_states[user_id]["duration"] = duration

        if mode == "video_image":
            if "image_path" not in user_states[user_id]:
                await query.message.reply_text("Сначала отправь фото.")
                return
            await query.message.reply_text(
                "✍️ Теперь напиши описание видео."
            )
            user_states[user_id]["mode"] = "video_image_wait_prompt"
            return

        if mode == "video_text":
            await run_video_generation(update, context, user_id)
            return

    if action == "buy":
        await query.message.reply_text(
            "💳 Пополнение баланса\n\n"
            "Выбери сумму пополнения:",
            reply_markup=topup_menu()
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
        balance, _, _ = get_user(user_id)

        await query.message.reply_text(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {balance} ₽.",
            reply_markup=main_menu()
        )
        return

    if action == "profile":
        balance, generations_count, spent_total = get_user(user_id)

        await query.message.reply_text(
            f"👤 Твой баланс:\n\n"
            f"💰 Баланс: {balance} ₽\n"
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
        await query.message.reply_text(HELP_TEXT)
        return


# =========================
# MESSAGE HANDLERS
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    ensure_user(user_id, username)

    if user_id not in user_states or user_states[user_id].get("mode") != "video_image_wait_photo":
        await update.message.reply_text(
            "Сначала выбери режим генерации.",
            reply_markup=main_menu()
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id]["image_path"] = str(image_path)

    await update.message.reply_text(
        "✅ Фото получил.\n\n"
        "Теперь выбери длительность видео:",
        reply_markup=duration_menu("video_image")
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    text = update.message.text.strip()

    ensure_user(user_id, username)

    if text.startswith("💳 Пополнить баланс на "):
        amount_text = (
            text.replace("💳 Пополнить баланс на ", "")
            .replace(" ₽", "")
            .strip()
        )

        try:
            amount = int(amount_text)
        except Exception:
            await update.message.reply_text("❌ Ошибка суммы.")
            return

        if amount not in TOPUP_AMOUNTS:
            await update.message.reply_text("❌ Такой суммы пополнения нет.")
            return

        payment_url, payment_id = create_yookassa_payment(user_id, amount)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Оплатить {amount} ₽", url=payment_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
        ])

        await update.message.reply_text(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            "1. Нажми «Оплатить»\n"
            "2. После оплаты вернись сюда\n"
            "3. Нажми «✅ Проверить оплату»",
            reply_markup=keyboard
        )
        return

    if text == "🏠 Главное меню":
        user_states.pop(user_id, None)
        await update.message.reply_text(MAIN_TEXT, reply_markup=main_menu())
        return

    if user_id not in user_states:
        await update.message.reply_text(
            "Выбери действие:",
            reply_markup=main_menu()
        )
        return

    mode = user_states[user_id].get("mode")

    if mode == "video_text_wait_prompt":
        user_states[user_id]["prompt"] = text
        user_states[user_id]["mode"] = "video_text_wait_duration"

        await update.message.reply_text(
            "✅ Описание получил.\n\n"
            "Выбери длительность видео:",
            reply_markup=duration_menu("video_text")
        )
        return

    if mode == "video_image_wait_prompt":
        user_states[user_id]["prompt"] = text
        await run_video_generation(update, context, user_id)
        return

    if mode == "image_wait_prompt":
        user_states[user_id]["prompt"] = text
        await run_image_generation(update, context, user_id)
        return

    await update.message.reply_text(
        "Выбери действие:",
        reply_markup=main_menu()
    )


# =========================
# GENERATION LOGIC
# =========================

def is_censorship_error(error_text: str) -> bool:
    error_text = error_text.lower()
    return (
        "kie_422" in error_text
        or "422" in error_text
        or "please try again" in error_text
        or "change your input files or prompt" in error_text
    )


async def run_video_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id, {})
    duration = state.get("duration")
    prompt = state.get("prompt")

    if not duration or not prompt:
        await update.effective_message.reply_text(
            "Не хватает данных для генерации. Начни заново.",
            reply_markup=main_menu()
        )
        user_states.pop(user_id, None)
        return

    cost = VIDEO_PRICES[duration]
    balance, _, _ = get_user(user_id)

    if balance < cost:
        await update.effective_message.reply_text(
            f"💰 Баланс: {balance} ₽\n\n"
            "💳 Недостаточно средств для генерации.",
            reply_markup=not_enough_balance_menu()
        )
        return

    await update.effective_message.reply_text(
        "🎥 Запускаю нейросеть.\n\n"
        "Генерация видео может занять 2–10 минут."
    )

    try:
        image_url = None

        if state.get("image_path"):
            print("GENERATION_VIDEO: upload image", flush=True)
            image_url = upload_image_to_kie(state["image_path"])

        print("GENERATION_VIDEO: create Kie task", flush=True)
        task_id = create_kie_video_task(prompt=prompt, duration=duration, image_url=image_url)

        print(f"GENERATION_VIDEO: Kie accepted task {task_id}. Charging user.", flush=True)
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost)

        print(f"GENERATION_VIDEO: wait result {task_id}", flush=True)
        urls = wait_kie_result(task_id)
        result_url = urls[0]

        print(f"GENERATION_VIDEO: download {result_url}", flush=True)
        video_path = download_file(result_url, user_id, "mp4")

        try:
            with open(video_path, "rb") as video_file:
                await update.effective_message.reply_video(
                    video=video_file,
                    caption="✅ Готово! Вот твоё AI-видео.",
                    read_timeout=3600,
                    write_timeout=3600,
                    connect_timeout=60,
                    pool_timeout=3600,
                    reply_markup=main_menu()
                )
        except Exception:
            await update.effective_message.reply_text(
                TELEGRAM_SEND_ERROR_VIDEO,
                disable_web_page_preview=True
            )

        balance_after, _, _ = get_user(user_id)
        await update.effective_message.reply_text(f"💰 Баланс: {balance_after} ₽")

    except Exception as e:
        import traceback
        print("GENERATION_VIDEO_ERROR:", repr(e), flush=True)
        traceback.print_exc()

        error_text = str(e)

        if is_censorship_error(error_text):
            await update.effective_message.reply_text(CENSORED_TEXT)
        elif "timeout" in error_text.lower() or "internal error" in error_text.lower() or "try again later" in error_text.lower():
            await update.effective_message.reply_text(
                "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
                "Попробуй ещё раз через 1–2 минуты."
            )
        else:
            await update.effective_message.reply_text(
                GENERIC_ERROR_TEXT,
                disable_web_page_preview=True
            )

    user_states.pop(user_id, None)


async def run_image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id, {})
    prompt = state.get("prompt")

    if not prompt:
        await update.effective_message.reply_text(
            "Не хватает описания. Начни заново.",
            reply_markup=main_menu()
        )
        user_states.pop(user_id, None)
        return

    balance, _, _ = get_user(user_id)

    if balance < IMAGE_PRICE:
        await update.effective_message.reply_text(
            f"💰 Баланс: {balance} ₽\n\n"
            "💳 Недостаточно средств для генерации изображения.",
            reply_markup=not_enough_balance_menu()
        )
        return

    await update.effective_message.reply_text(
        "🖼 Запускаю генерацию изображения.\n\n"
        "Это может занять несколько минут."
    )

    try:
        print("GENERATION_IMAGE: create Kie task", flush=True)
        task_id = create_kie_image_task(prompt=prompt)

        print(f"GENERATION_IMAGE: Kie accepted task {task_id}. Charging user.", flush=True)
        decrement_paid_credit(user_id, IMAGE_PRICE)
        add_generation_stats(user_id, IMAGE_PRICE)

        print(f"GENERATION_IMAGE: wait result {task_id}", flush=True)
        urls = wait_kie_result(task_id)
        result_url = urls[0]

        print(f"GENERATION_IMAGE: download {result_url}", flush=True)
        image_path = download_file(result_url, user_id, "jpg")

        try:
            with open(image_path, "rb") as image_file:
                await update.effective_message.reply_photo(
                    photo=image_file,
                    caption="✅ Готово! Вот твоё изображение.",
                    reply_markup=main_menu()
                )
        except Exception:
            await update.effective_message.reply_text(
                TELEGRAM_SEND_ERROR_IMAGE,
                disable_web_page_preview=True
            )

        balance_after, _, _ = get_user(user_id)
        await update.effective_message.reply_text(f"💰 Баланс: {balance_after} ₽")

    except Exception as e:
        import traceback
        print("GENERATION_IMAGE_ERROR:", repr(e), flush=True)
        traceback.print_exc()

        error_text = str(e)

        if is_censorship_error(error_text):
            await update.effective_message.reply_text(CENSORED_TEXT)
        elif "timeout" in error_text.lower() or "internal error" in error_text.lower() or "try again later" in error_text.lower():
            await update.effective_message.reply_text(
                "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
                "Попробуй ещё раз через 1–2 минуты."
            )
        else:
            await update.effective_message.reply_text(
                GENERIC_ERROR_TEXT,
                disable_web_page_preview=True
            )

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

    print("Xena 2.0 bot started", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
