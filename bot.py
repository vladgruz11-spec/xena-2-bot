import os
import json
import time
import sqlite3
import requests
from pathlib import Path

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KIE_API_KEY = os.getenv("KIE_API_KEY")

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

SUPPORT_URL = "https://t.me/Vlad101ss"

# Видео сначала пробуем через Grok на Kie
KIE_VIDEO_MODEL = os.getenv("KIE_VIDEO_MODEL", "grok-imagine-video-1-5-preview")

# ВАЖНО: модель для картинок может отличаться.
# Если Kie даст другое название text-to-image модели — поменяешь переменную KIE_IMAGE_MODEL на Render.
KIE_IMAGE_MODEL = os.getenv("KIE_IMAGE_MODEL", "grok-2-image")

ASPECT_RATIO = "9:16"
VIDEO_RESOLUTION = "480p"

IMAGE_PRICE = 50
VIDEO_PRICES = {
    "5": 100,
    "10": 180,
    "15": 250,
}

TOPUP_AMOUNTS = [500, 1000, 1500]

DB_PATH = os.getenv("DB_PATH", "/var/data/users.db")
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

ADMIN_IDS = {
    6164104276
}

user_states = {}

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден!")

if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден!")

if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден!")

if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден!")


# =========================
# МЕНЮ
# =========================

def main_inline_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="video_menu")],
        [InlineKeyboardButton("🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ", callback_data="image_start")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url=SUPPORT_URL)],
    ])


def video_type_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Видео из фото", callback_data="video_image_start")],
        [InlineKeyboardButton("📝 Видео по описанию", callback_data="video_text_start")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")],
    ])


def duration_inline_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 секунд — 100 ₽", callback_data="duration_5")],
        [InlineKeyboardButton("10 секунд — 180 ₽", callback_data="duration_10")],
        [InlineKeyboardButton("15 секунд — 250 ₽", callback_data="duration_15")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="video_menu")],
    ])


def not_enough_balance_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ])


def topup_menu():
    keyboard = [
        [f"💳 Пополнить баланс на {amount} ₽"] for amount in TOPUP_AMOUNTS
    ]
    keyboard.append(["🏠 Главное меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =========================
# БАЗА ДАННЫХ
# =========================

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            paid_credits INTEGER DEFAULT 0,
            generations_count INTEGER DEFAULT 0,
            images_count INTEGER DEFAULT 0,
            spent_total INTEGER DEFAULT 0,
            created_at INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id TEXT,
            cost INTEGER,
            kind TEXT,
            status TEXT DEFAULT 'waiting',
            created_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


def save_user(user_id: int, username=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username, paid_credits, generations_count, images_count, spent_total, created_at)
        VALUES (?, ?, 0, 0, 0, 0, ?)
        """,
        (user_id, username.lower() if username else None, int(time.time()))
    )

    if username:
        cur.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username.lower(), user_id)
        )

    conn.commit()
    conn.close()


def get_user(user_id: int):
    save_user(user_id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT paid_credits, generations_count, images_count, spent_total FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return 0, 0, 0, 0

    return row


def add_paid_credit(user_id: int, amount: int):
    save_user(user_id)

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


def add_generation_stats(user_id: int, cost: int, kind: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if kind == "image":
        cur.execute(
            """
            UPDATE users
            SET images_count = images_count + 1,
                spent_total = spent_total + ?
            WHERE user_id = ?
            """,
            (cost, user_id)
        )
    else:
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


def save_active_generation(user_id: int, task_id: str, cost: int, kind: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO active_generations (user_id, task_id, cost, kind, status, created_at)
        VALUES (?, ?, ?, ?, 'waiting', ?)
        """,
        (user_id, task_id, cost, kind, int(time.time()))
    )
    conn.commit()
    conn.close()


def finish_active_generation(task_id: str):
    conn = sqlite3.connect(DB_PATH)
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

def create_yookassa_payment(user_id: int, amount: int):
    url = "https://api.yookassa.ru/v3/payments"

    headers = {
        "Idempotence-Key": f"topup_{user_id}_{amount}_{int(time.time())}",
        "Content-Type": "application/json",
    }

    payload = {
        "amount": {
            "value": f"{amount}.00",
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/",
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
# KIE
# =========================

def upload_image_to_kie(image_path: str) -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
    }

    with open(image_path, "rb") as f:
        files = {
            "file": (Path(image_path).name, f, "image/jpeg"),
        }
        data = {
            "uploadPath": "images/xena-2-bot",
            "fileName": Path(image_path).name,
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=3600)

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки картинки в Kie: {result}")

    return result["data"]["downloadUrl"]


def create_kie_task(payload: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=3600)

    try:
        response.raise_for_status()
    except requests.HTTPError:
        raise RuntimeError(f"KIE_HTTP_ERROR {response.status_code}: {response.text}")

    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"KIE_CREATE_ERROR: {result}")

    return result["data"]["taskId"]


def create_kie_video_task(prompt: str, duration: str, image_url: str | None = None) -> str:
    input_data = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": VIDEO_RESOLUTION,
        "duration": int(duration),
    }

    if image_url:
        input_data["image_urls"] = [image_url]

    payload = {
        "model": KIE_VIDEO_MODEL,
        "input": input_data,
    }

    return create_kie_task(payload)


def create_kie_image_task(prompt: str) -> str:
    payload = {
        "model": KIE_IMAGE_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": ASPECT_RATIO,
        },
    }

    return create_kie_task(payload)


def wait_kie_result(task_id: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
    }

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

        data = result.get("data", {})
        state = data.get("state")

        if state == "success":
            result_json_raw = data.get("resultJson")
            result_json = json.loads(result_json_raw) if isinstance(result_json_raw, str) else (result_json_raw or {})

            urls = (
                result_json.get("resultUrls")
                or result_json.get("imageUrls")
                or result_json.get("videoUrls")
                or result_json.get("videos")
                or result_json.get("images")
                or []
            )

            if not urls:
                raise RuntimeError(f"Результат готов, но ссылка не найдена: {result_json}")

            if isinstance(urls[0], dict):
                return urls[0].get("url") or urls[0].get("imageUrl") or urls[0].get("videoUrl")

            return urls[0]

        if state == "fail":
            raise RuntimeError(f"Kie не смог выполнить задачу: {data.get('failMsg')}")

        time.sleep(10)

    raise RuntimeError("Генерация заняла слишком много времени. Попробуй позже.")


def download_file(file_url: str, user_id: int, suffix: str) -> str:
    path = MEDIA_DIR / f"{user_id}_{int(time.time())}.{suffix}"

    response = requests.get(file_url, timeout=3600)
    response.raise_for_status()

    with open(path, "wb") as f:
        f.write(response.content)

    return str(path)


# =========================
# СООБЩЕНИЯ
# =========================

async def send_main_menu_message(message):
    await message.reply_text(
        "🤖 Xena 2.0\n\n"
        "Создавай изображения и вертикальные AI-видео в формате 9:16.",
        reply_markup=main_inline_menu(),
    )


async def show_help(message):
    await message.reply_text(
        "📘 Инструкция Xena 2.0\n\n"
        "1. Нажми «🎬 СОЗДАТЬ ВИДЕО» или «🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ».\n"
        "2. Для видео выбери режим: из фото или по описанию.\n"
        "3. Отправь фото, если выбрал видео из фото.\n"
        "4. Напиши подробное описание результата.\n"
        "5. Выбери длительность видео: 5, 10 или 15 секунд.\n"
        "6. Дождись окончания генерации.\n\n"
        "Стоимость:\n"
        "🖼 Изображение — 50 ₽\n"
        "🎬 Видео 5 сек — 100 ₽\n"
        "🎬 Видео 10 сек — 180 ₽\n"
        "🎬 Видео 15 сек — 250 ₽\n\n"
        "Чем подробнее описание, тем лучше результат.",
    )


async def send_not_enough_balance(message, balance: int, cost: int):
    await message.reply_text(
        f"💰 Баланс: {balance} ₽\n"
        f"💳 Нужно: {cost} ₽\n\n"
        "Недостаточно средств для генерации.",
        reply_markup=not_enough_balance_menu(),
    )


def is_censorship_error(error_text: str) -> bool:
    error_text = error_text.lower()
    return (
        "422" in error_text
        or "please try again" in error_text
        or "change your input files or prompt" in error_text
    )


async def send_generation_error(message, error_text: str):
    if is_censorship_error(error_text):
        await message.reply_text(
            "⚠️ Нейросеть не приняла этот запрос.\n\n"
            "Скорее всего, фото или описание не прошли проверку безопасности.\n\n"
            "Попробуй:\n"
            "— заменить фото;\n"
            "— смягчить описание;\n"
            "— убрать слишком откровенные или запрещённые детали."
        )
        return

    if (
        "internal error" in error_text.lower()
        or "try again later" in error_text.lower()
        or "timeout" in error_text.lower()
        or "слишком много времени" in error_text.lower()
    ):
        await message.reply_text(
            "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
            "Попробуй ещё раз через 1–2 минуты или немного измени описание."
        )
        return

    await message.reply_text(
        "❌ Произошла ошибка генерации.\n\n"
        "Если проблема повторяется — напиши в поддержку:\n"
        f"{SUPPORT_URL}",
        disable_web_page_preview=True,
    )


# =========================
# ГЕНЕРАЦИИ
# =========================

async def run_image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, prompt: str):
    paid_credits, _, _, _ = get_user(user_id)
    cost = IMAGE_PRICE

    if paid_credits < cost:
        await send_not_enough_balance(update.message, paid_credits, cost)
        return

    await update.message.reply_text(
        "🖼 Запускаю генерацию изображения.\n\n"
        "Обычно это занимает 1–3 минуты."
    )

    try:
        print("IMAGE_GENERATION: create Kie task", flush=True)
        task_id = create_kie_image_task(prompt)

        print(f"IMAGE_GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)
        save_active_generation(user_id, task_id, cost, "image")
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost, "image")

        print(f"IMAGE_GENERATION: wait result {task_id}", flush=True)
        image_url = wait_kie_result(task_id)

        print(f"IMAGE_GENERATION: download image {image_url}", flush=True)
        image_path = download_file(image_url, user_id, "jpg")

        finish_active_generation(task_id)

        try:
            with open(image_path, "rb") as image_file:
                await update.message.reply_photo(
                    photo=image_file,
                    caption="✅ Готово! Вот твоё изображение.",
                )
        except Exception:
            await update.message.reply_text(
                "⚠️ Изображение было сгенерировано, но Telegram не смог его отправить.\n\n"
                f"Напиши в поддержку:\n{SUPPORT_URL}",
                disable_web_page_preview=True,
            )

        paid_credits_after, _, _, _ = get_user(user_id)
        await update.message.reply_text(f"💰 Баланс: {paid_credits_after} ₽")

    except Exception as e:
        import traceback
        print("IMAGE_GENERATION_ERROR:", repr(e), flush=True)
        traceback.print_exc()
        await send_generation_error(update.message, str(e))

    user_states.pop(user_id, None)


async def run_video_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id, {})
    prompt = state.get("prompt")
    duration = state.get("duration")
    image_path = state.get("image_path")

    paid_credits, _, _, _ = get_user(user_id)
    cost = VIDEO_PRICES[duration]

    if paid_credits < cost:
        await send_not_enough_balance(update.message, paid_credits, cost)
        return

    await update.message.reply_text(
        "🎥 Запускаю генерацию видео.\n\n"
        "Генерация может занять 2–15 минут. Не отправляй новую задачу, пока я работаю."
    )

    try:
        image_url = None

        if image_path:
            print("VIDEO_GENERATION: upload image", flush=True)
            image_url = upload_image_to_kie(image_path)

        print("VIDEO_GENERATION: create Kie task", flush=True)
        task_id = create_kie_video_task(prompt, duration, image_url=image_url)

        print(f"VIDEO_GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)
        save_active_generation(user_id, task_id, cost, "video")
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost, "video")

        print(f"VIDEO_GENERATION: wait result {task_id}", flush=True)
        video_url = wait_kie_result(task_id)

        print(f"VIDEO_GENERATION: download video {video_url}", flush=True)
        video_path = download_file(video_url, user_id, "mp4")

        finish_active_generation(task_id)

        try:
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption="✅ Готово! Вот твоё AI-видео.",
                    read_timeout=3600,
                    write_timeout=3600,
                    connect_timeout=60,
                    pool_timeout=3600,
                )
        except Exception:
            await update.message.reply_text(
                "⚠️ Видео было сгенерировано, но Telegram не смог его отправить.\n\n"
                f"Напиши в поддержку:\n{SUPPORT_URL}",
                disable_web_page_preview=True,
            )

        paid_credits_after, _, _, _ = get_user(user_id)
        await update.message.reply_text(f"💰 Баланс: {paid_credits_after} ₽")

    except Exception as e:
        import traceback
        print("VIDEO_GENERATION_ERROR:", repr(e), flush=True)
        traceback.print_exc()
        await send_generation_error(update.message, str(e))

    user_states.pop(user_id, None)


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    save_user(user_id, username)

    await send_main_menu_message(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu_message(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_user(user_id, update.message.from_user.username)
    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса\n\n"
        "Выбери сумму пополнения:",
        reply_markup=topup_menu(),
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
            "/giveuser @username 500"
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
    user_id = get_user_id_by_username(username)

    if not user_id:
        await update.message.reply_text("❌ Пользователь не найден.")
        return

    paid_credits, generations_count, images_count, spent_total = get_user(user_id)

    await update.message.reply_text(
        f"👤 Статистика пользователя:\n\n"
        f"@{username}\n"
        f"ID: {user_id}\n\n"
        f"🎬 Видео: {generations_count or 0}\n"
        f"🖼 Изображений: {images_count or 0}\n"
        f"💸 Потратил: {spent_total or 0} ₽\n"
        f"💰 Баланс: {paid_credits or 0} ₽"
    )


# =========================
# CALLBACK-КНОПКИ
# =========================

async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    save_user(user_id, query.from_user.username)

    action = query.data

    if action == "main_menu":
        try:
            await query.message.delete()
        except Exception:
            pass
        await send_main_menu_message(query.message)
        return

    if action == "video_menu":
        await query.message.reply_text(
            "🎬 Выбери режим создания видео:",
            reply_markup=video_type_menu(),
        )
        return

    if action == "image_start":
        paid_credits, _, _, _ = get_user(user_id)

        if paid_credits < IMAGE_PRICE:
            await send_not_enough_balance(query.message, paid_credits, IMAGE_PRICE)
            return

        user_states[user_id] = {
            "mode": "image_wait_prompt",
        }

        await query.message.reply_text(
            "🖼 Отправь описание изображения.\n\n"
            "Например: девушка в красном платье на пляже, вертикальный кадр, реалистично."
        )
        return

    if action == "video_image_start":
        user_states[user_id] = {
            "mode": "video_image_wait_photo",
        }

        await query.message.reply_text(
            "📸 Отправь фото, которое хочешь оживить."
        )
        return

    if action == "video_text_start":
        user_states[user_id] = {
            "mode": "video_text_wait_prompt",
        }

        await query.message.reply_text(
            "📝 Отправь описание видео.\n\n"
            "Например: девушка идёт по ночному городу, камера медленно приближается, кинематографично."
        )
        return

    if action.startswith("duration_"):
        duration = action.replace("duration_", "")

        if user_id not in user_states:
            await query.message.reply_text(
                "Сначала выбери режим генерации.",
                reply_markup=main_inline_menu(),
            )
            return

        user_states[user_id]["duration"] = duration
        await run_video_generation(update, context, user_id)
        return

    if action == "buy":
        await query.message.reply_text(
            "💳 Пополнение баланса\n\n"
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
        paid_credits, _, _, _ = get_user(user_id)

        await query.message.reply_text(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽."
        )
        return

    if action == "profile":
        paid_credits, generations_count, images_count, spent_total = get_user(user_id)

        await query.message.reply_text(
            f"👤 Твой баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"🖼 Изображение — {IMAGE_PRICE} ₽\n"
            f"🎬 5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"🎬 10 секунд — {VIDEO_PRICES['10']} ₽\n"
            f"🎬 15 секунд — {VIDEO_PRICES['15']} ₽"
        )
        return

    if action == "help":
        await show_help(query.message)
        return


# =========================
# СООБЩЕНИЯ
# =========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_user(user_id, update.message.from_user.username)

    state = user_states.get(user_id)

    if not state or state.get("mode") != "video_image_wait_photo":
        await update.message.reply_text(
            "Сначала выбери режим:\n\n"
            "🎬 СОЗДАТЬ ВИДЕО → 📸 Видео из фото",
            reply_markup=main_inline_menu(),
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id]["image_path"] = str(image_path)
    user_states[user_id]["mode"] = "video_image_wait_prompt"

    await update.message.reply_text(
        "✅ Фото получил.\n\n"
        "Теперь отправь описание видео."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    save_user(user_id, update.message.from_user.username)

    if text == "🏠 Главное меню":
        await send_main_menu_message(update.message)
        return

    if text.startswith("💳 Пополнить баланс на "):
        amount_text = (
            text
            .replace("💳 Пополнить баланс на ", "")
            .replace(" ₽", "")
            .strip()
        )
        amount = int(amount_text)

        payment_url, payment_id = create_yookassa_payment(user_id, amount)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")],
        ])

        await update.message.reply_text(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            "1. Нажми «Оплатить»\n"
            "2. После оплаты вернись сюда\n"
            "3. Нажми «✅ Проверить оплату»",
            reply_markup=keyboard,
        )
        return

    state = user_states.get(user_id)

    if not state:
        await update.message.reply_text(
            "Выбери действие в меню:",
            reply_markup=main_inline_menu(),
        )
        return

    mode = state.get("mode")

    if mode == "image_wait_prompt":
        await run_image_generation(update, context, user_id, text)
        return

    if mode == "video_text_wait_prompt":
        user_states[user_id]["prompt"] = text
        user_states[user_id]["mode"] = "video_text_wait_duration"

        await update.message.reply_text(
            "⏱ Выбери длительность видео:",
            reply_markup=duration_inline_menu(),
        )
        return

    if mode == "video_image_wait_prompt":
        user_states[user_id]["prompt"] = text
        user_states[user_id]["mode"] = "video_image_wait_duration"

        await update.message.reply_text(
            "⏱ Выбери длительность видео:",
            reply_markup=duration_inline_menu(),
        )
        return

    await update.message.reply_text(
        "Выбери действие в меню:",
        reply_markup=main_inline_menu(),
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
    app.add_handler(CommandHandler("giveuser", giveuser))
    app.add_handler(CommandHandler("statsuser", statsuser))

    app.add_handler(CallbackQueryHandler(menu_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Xena 2.0 bot started...", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
