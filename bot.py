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
# ENV
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KIE_API_KEY = os.getenv("KIE_API_KEY")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# Модели Kie. Если нужно, потом поменяем в Render Environment.
KIE_IMAGE_TO_VIDEO_MODEL = os.getenv("KIE_IMAGE_TO_VIDEO_MODEL", "grok-imagine-video-1-5-preview")
KIE_TEXT_TO_VIDEO_MODEL = os.getenv("KIE_TEXT_TO_VIDEO_MODEL", "grok-imagine-video-1-5-preview")
KIE_TEXT_TO_IMAGE_MODEL = os.getenv("KIE_TEXT_TO_IMAGE_MODEL", "gpt-4o-image")

SUPPORT_URL = "https://t.me/Vlad101ss"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден!")

if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден!")

if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден!")

if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден!")


# =========================
# SETTINGS
# =========================

DB_PATH = "/var/data/users.db"
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

user_states = {}

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


# =========================
# MENUS
# =========================

def main_inline_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="video_menu")],
        [InlineKeyboardButton("🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ", callback_data="image_menu")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url=SUPPORT_URL)],
    ]
    return InlineKeyboardMarkup(keyboard)


def video_type_menu():
    keyboard = [
        [InlineKeyboardButton("📸 Видео из изображения", callback_data="video_from_image")],
        [InlineKeyboardButton("📝 Видео по описанию", callback_data="video_from_text")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def duration_inline_menu():
    keyboard = [
        [InlineKeyboardButton("5 секунд — 100 ₽", callback_data="duration_5")],
        [InlineKeyboardButton("10 секунд — 180 ₽", callback_data="duration_10")],
        [InlineKeyboardButton("15 секунд — 250 ₽", callback_data="duration_15")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="video_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def not_enough_balance_menu():
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def topup_menu():
    keyboard = [[f"💳 Пополнить баланс на {amount} ₽"] for amount in TOPUP_AMOUNTS]
    keyboard.append(["🏠 Главное меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


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

    # На случай, если база уже была создана старым кодом.
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


def save_user(user_id: int, username):
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT paid_credits FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT OR IGNORE INTO users (user_id, paid_credits, generations_count, spent_total) VALUES (?, 0, 0, 0)",
            (user_id,)
        )
        conn.commit()
        paid_credits = 0
    else:
        paid_credits = row[0] or 0

    conn.close()
    return paid_credits


def add_paid_credit(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, paid_credits, generations_count, spent_total) VALUES (?, 0, 0, 0)",
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
    username = username.replace("@", "").lower()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()

    conn.close()
    return row[0] if row else None


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
            "return_url": "https://t.me/Xena20Bot",
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


def check_yookassa_payment(payment_id: str):
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

def upload_image_to_kie(image_path: str):
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
            "fileName": Path(image_path).name,
        }

        response = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=3600,
        )

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки картинки в Kie: {result}")

    return result["data"]["downloadUrl"]


def create_kie_task(mode: str, prompt: str, duration: str = None, image_url: str = None):
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }

    if mode == "image":
        payload = {
            "model": KIE_TEXT_TO_IMAGE_MODEL,
            "input": {
                "prompt": prompt,
                "aspect_ratio": ASPECT_RATIO,
            }
        }

    elif mode == "text_to_video":
        payload = {
            "model": KIE_TEXT_TO_VIDEO_MODEL,
            "input": {
                "prompt": prompt,
                "aspect_ratio": ASPECT_RATIO,
                "resolution": VIDEO_RESOLUTION,
                "duration": int(duration),
            }
        }

    elif mode == "image_to_video":
        payload = {
            "model": KIE_IMAGE_TO_VIDEO_MODEL,
            "input": {
                "prompt": prompt,
                "image_urls": [image_url],
                "aspect_ratio": ASPECT_RATIO,
                "resolution": VIDEO_RESOLUTION,
                "duration": int(duration),
            }
        }

    else:
        raise RuntimeError(f"Неизвестный режим генерации: {mode}")

    print(f"KIE_CREATE_TASK mode={mode} payload={payload}", flush=True)

    response = requests.post(url, headers=headers, json=payload, timeout=3600)

    if response.status_code == 422:
        raise RuntimeError(f"KIE_422_CENSOR: {response.text}")

    try:
        response.raise_for_status()
    except Exception:
        raise RuntimeError(f"KIE_HTTP_ERROR {response.status_code}: {response.text}")

    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"KIE_CREATE_ERROR: {result}")

    return result["data"]["taskId"]


def wait_kie_result(task_id: str):
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

            if isinstance(result_json_raw, str):
                result_json = json.loads(result_json_raw)
            else:
                result_json = result_json_raw or {}

            urls = (
                result_json.get("resultUrls")
                or result_json.get("videoUrls")
                or result_json.get("imageUrls")
                or result_json.get("images")
                or result_json.get("videos")
                or result_json.get("urls")
                or []
            )

            if isinstance(urls, str):
                urls = [urls]

            if not urls:
                raise RuntimeError(f"Результат готов, но ссылка не найдена: {result_json}")

            return urls[0]

        if state == "fail":
            fail_msg = data.get("failMsg") or data.get("errorMsg") or str(data)
            if "please try again" in fail_msg.lower() or "change your input files or prompt" in fail_msg.lower():
                raise RuntimeError(f"KIE_422_CENSOR: {fail_msg}")
            raise RuntimeError(f"Kie не смог сгенерировать результат: {fail_msg}")

        time.sleep(10)

    raise RuntimeError("Генерация заняла слишком много времени. Попробуй позже.")


def download_file(file_url: str, user_id: int, suffix: str):
    file_path = MEDIA_DIR / f"{user_id}_result{suffix}"

    response = requests.get(file_url, timeout=3600)
    response.raise_for_status()

    with open(file_path, "wb") as f:
        f.write(response.content)

    return str(file_path)


# =========================
# GENERATION
# =========================

def censor_error_text():
    return (
        "⚠️ Нейросеть не приняла этот запрос.\n\n"
        "Скорее всего, фото или описание не прошли проверку безопасности.\n\n"
        "Попробуй:\n"
        "— заменить фото;\n"
        "— смягчить описание;\n"
        "— убрать слишком откровенные или запрещённые детали."
    )


def default_generation_error_text():
    return (
        "❌ Произошла ошибка генерации.\n\n"
        "Если проблема повторяется — напиши в поддержку:\n"
        f"{SUPPORT_URL}"
    )


async def start_paid_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    state = user_states.get(user_id, {})
    mode = state.get("mode")
    prompt = state.get("prompt")
    duration = state.get("duration")
    image_path = state.get("image_path")

    if mode == "image":
        cost = IMAGE_PRICE
    else:
        cost = VIDEO_PRICES[duration]

    paid_credits = get_user(user_id)

    if paid_credits < cost:
        await update.message.reply_text(
            f"💰 Баланс: {paid_credits} ₽\n\n"
            "💳 Недостаточно средств для генерации.",
            reply_markup=not_enough_balance_menu()
        )
        return

    if mode == "image":
        await update.message.reply_text(
            "🖼 Запускаю генерацию изображения.\n\n"
            "Обычно это занимает 1–3 минуты."
        )
    else:
        await update.message.reply_text(
            "🎥 Запускаю генерацию видео.\n\n"
            "Обычно это занимает 2–10 минут. Не отправляй новые данные, пока я работаю."
        )

    try:
        image_url = None

        if mode == "image_to_video":
            print("GENERATION: upload image to Kie", flush=True)
            image_url = upload_image_to_kie(image_path)

        print("GENERATION: create Kie task", flush=True)
        task_id = create_kie_task(
            mode=mode,
            prompt=prompt,
            duration=duration,
            image_url=image_url,
        )

        print(f"GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)

        # Деньги списываем сразу после того, как Kie принял задачу.
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost)

        print(f"GENERATION: wait result {task_id}", flush=True)
        result_url = wait_kie_result(task_id)

        print(f"GENERATION: result url {result_url}", flush=True)

        if mode == "image":
            try:
                image_file = download_file(result_url, user_id, ".jpg")
                with open(image_file, "rb") as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption="✅ Готово! Вот твоё AI-изображение."
                    )
            except Exception:
                await update.message.reply_text(
                    "⚠️ Изображение было сгенерировано, но Telegram не смог его отправить.\n\n"
                    f"Напиши в поддержку:\n{SUPPORT_URL}",
                    disable_web_page_preview=True
                )
        else:
            try:
                video_file = download_file(result_url, user_id, ".mp4")
                with open(video_file, "rb") as f:
                    await update.message.reply_video(
                        video=f,
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
                    disable_web_page_preview=True
                )

        paid_credits_after = get_user(user_id)

        await update.message.reply_text(
            f"💰 Баланс: {paid_credits_after} ₽"
        )

    except Exception as e:
        import traceback
        print("GENERATION_ERROR:", repr(e), flush=True)
        traceback.print_exc()

        error_text = str(e).lower()

        if (
            "kie_422_censor" in error_text
            or "422" in error_text
            or "please try again" in error_text
            or "change your input files or prompt" in error_text
        ):
            await update.message.reply_text(censor_error_text())
        elif (
            "internal error" in error_text
            or "try again later" in error_text
            or "timeout" in error_text
            or "слишком много времени" in error_text
        ):
            await update.message.reply_text(
                "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
                "Попробуй ещё раз через 1–2 минуты или немного измени описание."
            )
        else:
            await update.message.reply_text(
                default_generation_error_text(),
                disable_web_page_preview=True
            )

    user_states.pop(user_id, None)


# =========================
# BOT HANDLERS
# =========================

async def send_main_menu_message(message):
    await message.reply_text(
        "👋 Привет! Я Xena 2.0.\n\n"
        "Создаю изображения и вертикальные AI-видео в формате 9:16.",
        reply_markup=main_inline_menu()
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    save_user(user_id, username)

    await send_main_menu_message(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu_message(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    save_user(user_id, username)

    await update.message.reply_text(f"Твой Telegram ID:\n{user_id}")


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
            "/statsuser @username\n\n"
            "Пример:\n"
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

    if row is None:
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


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data

    save_user(user_id, query.from_user.username)

    if action == "main_menu":
        try:
            await query.message.delete()
        except Exception:
            pass

        await send_main_menu_message(query.message)
        return

    if action == "video_menu":
        await query.message.reply_text(
            "🎬 Выбери тип видео:",
            reply_markup=video_type_menu()
        )
        return

    if action == "image_menu":
        paid_credits = get_user(user_id)

        if paid_credits < IMAGE_PRICE:
            await query.message.reply_text(
                f"💰 Баланс: {paid_credits} ₽\n\n"
                f"🖼 Создание изображения стоит {IMAGE_PRICE} ₽.\n"
                "Пополните баланс.",
                reply_markup=not_enough_balance_menu()
            )
            return

        user_states[user_id] = {
            "mode": "image",
            "step": "waiting_prompt"
        }

        await query.message.reply_text(
            "🖼 Пришли описание изображения.\n\n"
            "Чем подробнее описание, тем лучше результат."
        )
        return

    if action == "video_from_text":
        user_states[user_id] = {
            "mode": "text_to_video",
            "step": "waiting_prompt"
        }

        await query.message.reply_text(
            "📝 Пришли описание видео.\n\n"
            "Опиши, что должно происходить в кадре."
        )
        return

    if action == "video_from_image":
        user_states[user_id] = {
            "mode": "image_to_video",
            "step": "waiting_photo"
        }

        await query.message.reply_text(
            "📸 Пришли изображение, которое хочешь оживить."
        )
        return

    if action.startswith("duration_"):
        duration = action.replace("duration_", "")

        if user_id not in user_states:
            await query.message.reply_text(
                "Сначала выбери режим генерации.",
                reply_markup=main_inline_menu()
            )
            return

        user_states[user_id]["duration"] = duration

        await start_paid_generation(query, context, user_id)
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
        paid_credits = get_user(user_id)

        await query.message.reply_text(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽."
        )
        return

    if action == "buy":
        await query.message.reply_text(
            "💳 Пополнение баланса\n\n"
            "Выбери сумму пополнения:",
            reply_markup=topup_menu()
        )
        return

    if action == "profile":
        paid_credits = get_user(user_id)

        await query.message.reply_text(
            f"👤 Твой баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Стоимость:\n"
            f"🖼 Изображение — {IMAGE_PRICE} ₽\n"
            f"🎬 Видео 5 сек — {VIDEO_PRICES['5']} ₽\n"
            f"🎬 Видео 10 сек — {VIDEO_PRICES['10']} ₽\n"
            f"🎬 Видео 15 сек — {VIDEO_PRICES['15']} ₽"
        )
        return

    if action == "help":
        await query.message.reply_text(
            "📘 Инструкция Xena 2.0\n\n"
            "1. Нажми 🎬 СОЗДАТЬ ВИДЕО или 🖼 СОЗДАТЬ ИЗОБРАЖЕНИЕ.\n"
            "2. Для видео выбери: видео из изображения или видео по описанию.\n"
            "3. Пришли фото или описание.\n"
            "4. Выбери длительность видео: 5, 10 или 15 секунд.\n"
            "5. Дождись готового результата.\n\n"
            "Чем подробнее описание, тем лучше результат.\n\n"
            "Формат видео: 9:16 — подходит для TikTok, Reels и Shorts."
        )
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    save_user(user_id, username)

    state = user_states.get(user_id)

    if not state or state.get("mode") != "image_to_video" or state.get("step") != "waiting_photo":
        await update.message.reply_text(
            "Сначала выбери режим: 🎬 СОЗДАТЬ ВИДЕО → 📸 Видео из изображения.",
            reply_markup=main_inline_menu()
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id]["image_path"] = str(image_path)
    user_states[user_id]["step"] = "waiting_prompt"

    await update.message.reply_text(
        "✅ Изображение получил.\n\n"
        "Теперь пришли описание видео."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    text = update.message.text

    save_user(user_id, username)

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
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
        ])

        await update.message.reply_text(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            "1. Нажми «Оплатить»\n"
            "2. После оплаты вернись сюда\n"
            "3. Нажми «✅ Проверить оплату»\n\n"
            "Если не открывается ссылка, отключи VPN на время оплаты.",
            reply_markup=keyboard
        )
        return

    if text == "🏠 Главное меню":
        await send_main_menu_message(update.message)
        return

    state = user_states.get(user_id)

    if not state:
        await update.message.reply_text(
            "Выбери, что хочешь создать:",
            reply_markup=main_inline_menu()
        )
        return

    mode = state.get("mode")
    step = state.get("step")

    if step == "waiting_prompt":
        user_states[user_id]["prompt"] = text

        if mode == "image":
            await start_paid_generation(update, context, user_id)
            return

        if mode in ["text_to_video", "image_to_video"]:
            user_states[user_id]["step"] = "waiting_duration"
            await update.message.reply_text(
                "⏱ Выбери длительность видео:",
                reply_markup=duration_inline_menu()
            )
            return

    await update.message.reply_text(
        "Не понял команду. Вернись в главное меню.",
        reply_markup=main_inline_menu()
    )


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса\n\n"
        "Выбери сумму пополнения:",
        reply_markup=topup_menu()
    )


# Старые handlers платежей Telegram оставлены пустыми на случай, если они не используются.
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


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
