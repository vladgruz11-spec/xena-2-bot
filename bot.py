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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KIE_API_KEY = os.getenv("KIE_API_KEY")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Xena20Bot")

SUPPORT_URL = "https://t.me/Vlad101ss"
DB_PATH = "users.db"
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

ADMIN_IDS = {6164104276}
ASPECT_RATIO = "9:16"
RESOLUTION = "480p"
IMAGE_PRICE = 50
VIDEO_PRICES = {"5": 100, "10": 180, "15": 250}
TOPUP_AMOUNTS = [500, 1000, 1500]

GROK_VIDEO_MODEL = "grok-imagine-video-1-5-preview"
TEXT_TO_IMAGE_MODEL = os.getenv("KIE_TEXT_TO_IMAGE_MODEL", "gpt-4o-image")

user_states = {}

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден!")
if not KIE_API_KEY:
    raise RuntimeError("KIE_API_KEY не найден!")
if not YOOKASSA_SHOP_ID:
    raise RuntimeError("YOOKASSA_SHOP_ID не найден!")
if not YOOKASSA_SECRET_KEY:
    raise RuntimeError("YOOKASSA_SECRET_KEY не найден!")


def main_inline_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 СОЗДАТЬ ВИДЕО", callback_data="video_menu")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url=SUPPORT_URL)],
    ])


def video_mode_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Фото → Видео", callback_data="mode_image_to_video")],
        [InlineKeyboardButton("📝 Текст → Видео", callback_data="mode_text_to_video")],
        [InlineKeyboardButton("🖼 Текст → Картинка", callback_data="mode_text_to_image")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="main_menu")],
    ])


def duration_inline_menu(mode: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"5 секунд — {VIDEO_PRICES['5']} ₽", callback_data=f"duration_{mode}_5")],
        [InlineKeyboardButton(f"10 секунд — {VIDEO_PRICES['10']} ₽", callback_data=f"duration_{mode}_10")],
        [InlineKeyboardButton(f"15 секунд — {VIDEO_PRICES['15']} ₽", callback_data=f"duration_{mode}_15")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="video_menu")],
    ])


def topup_menu():
    keyboard = [[f"💳 Пополнить баланс на {amount} ₽"] for amount in TOPUP_AMOUNTS]
    keyboard.append(["🏠 Главное меню"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()


def ensure_user(user_id: int, username: str | None = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, paid_credits, generations_count, spent_total, created_at) VALUES (?, ?, 0, 0, 0, ?)",
        (user_id, (username or "").lower(), int(time.time()))
    )
    if username:
        cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username.lower(), user_id))
    conn.commit()
    conn.close()


def get_balance(user_id: int) -> int:
    ensure_user(user_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT paid_credits FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def add_paid_credit(user_id: int, amount: int):
    ensure_user(user_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET paid_credits = paid_credits + ? WHERE user_id = ?", (amount, user_id))
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
        "UPDATE users SET generations_count = generations_count + 1, spent_total = spent_total + ? WHERE user_id = ?",
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


def give_balance(user_id: int, amount: int):
    ensure_user(user_id)
    add_paid_credit(user_id, amount)


def create_yookassa_payment(user_id: int, amount: int):
    url = "https://api.yookassa.ru/v3/payments"
    headers = {
        "Idempotence-Key": f"xena2_topup_{user_id}_{amount}_{int(time.time())}",
        "Content-Type": "application/json",
    }
    payload = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": f"https://t.me/{BOT_USERNAME}"},
        "description": f"Пополнение баланса Xena 2.0 на {amount} ₽",
        "metadata": {"user_id": str(user_id), "amount": str(amount)},
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


def kie_headers_json():
    return {"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"}


def kie_headers_auth():
    return {"Authorization": f"Bearer {KIE_API_KEY}"}


def upload_image_to_kie(image_path: str) -> str:
    url = "https://kieai.redpandaai.co/api/file-stream-upload"
    with open(image_path, "rb") as f:
        files = {"file": (Path(image_path).name, f, "image/jpeg")}
        data = {"uploadPath": "images/xena-2-bot", "fileName": Path(image_path).name}
        response = requests.post(url, headers=kie_headers_auth(), files=files, data=data, timeout=3600)
    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки картинки в Kie: {result}")
    return result["data"]["downloadUrl"]


def create_kie_task(payload: dict) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"
    response = requests.post(url, headers=kie_headers_json(), json=payload, timeout=3600)
    if response.status_code == 422:
        raise RuntimeError("KIE_422_INPUT_REJECTED")
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        err = str(result).lower()
        if "422" in err or "please try again" in err or "change your input files or prompt" in err:
            raise RuntimeError("KIE_422_INPUT_REJECTED")
        raise RuntimeError(f"Ошибка создания задачи Kie: {result}")
    return result["data"]["taskId"]


def create_kie_image_to_video_task(image_url: str, prompt: str, duration: str) -> str:
    payload = {
        "model": GROK_VIDEO_MODEL,
        "input": {
            "prompt": prompt,
            "image_urls": [image_url],
            "aspect_ratio": ASPECT_RATIO,
            "resolution": RESOLUTION,
            "duration": int(duration),
        },
    }
    return create_kie_task(payload)


def create_kie_text_to_video_task(prompt: str, duration: str) -> str:
    payload = {
        "model": GROK_VIDEO_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": ASPECT_RATIO,
            "resolution": RESOLUTION,
            "duration": int(duration),
        },
    }
    return create_kie_task(payload)


def create_kie_image_task(prompt: str) -> str:
    payload = {
        "model": TEXT_TO_IMAGE_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": ASPECT_RATIO,
            "resolution": RESOLUTION,
        },
    }
    return create_kie_task(payload)


def extract_urls(result_json: dict):
    urls = []
    for key in ["resultUrls", "videoUrls", "videos", "imageUrls", "images", "urls"]:
        value = result_json.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    for k in ["url", "src", "downloadUrl"]:
                        if item.get(k):
                            urls.append(item[k])
        elif isinstance(value, str):
            urls.append(value)
    return urls


def wait_kie_result(task_id: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/recordInfo"
    for _ in range(360):
        response = requests.get(url, headers=kie_headers_auth(), params={"taskId": task_id}, timeout=60)
        response.raise_for_status()
        result = response.json()
        data = result.get("data", {})
        state = data.get("state")
        if state == "success":
            raw = data.get("resultJson")
            if not raw:
                raise RuntimeError(f"Kie вернул success, но resultJson пустой: {data}")
            result_json = json.loads(raw)
            urls = extract_urls(result_json)
            if not urls:
                raise RuntimeError(f"Результат готов, но ссылка не найдена: {result_json}")
            return urls[0]
        if state == "fail":
            fail_msg = str(data.get("failMsg") or "")
            if "please try again" in fail_msg.lower() or "change your input files or prompt" in fail_msg.lower():
                raise RuntimeError("KIE_422_INPUT_REJECTED")
            raise RuntimeError(f"Kie не смог выполнить задачу: {fail_msg}")
        time.sleep(10)
    raise RuntimeError("Задача генерировалась слишком долго. Попробуй позже.")


def download_file(url: str, user_id: int, suffix: str) -> str:
    path = MEDIA_DIR / f"{user_id}_{int(time.time())}.{suffix}"
    response = requests.get(url, timeout=3600)
    response.raise_for_status()
    with open(path, "wb") as f:
        f.write(response.content)
    return str(path)


def instruction_text():
    return (
        "📘 Инструкция Xena 2.0\n\n"
        "1. Нажми 🎬 СОЗДАТЬ ВИДЕО.\n"
        "2. Выбери режим: Фото → Видео, Текст → Видео или Текст → Картинка.\n"
        "3. Для видео выбери длительность: 5, 10 или 15 секунд.\n"
        "4. Отправь фото или описание.\n"
        "5. Дождись результата.\n\n"
        "Формат генераций: 9:16 — вертикальный формат для TikTok, Reels и Shorts.\n\n"
        "⚠️ Если нейросеть не принимает фото или описание, измени запрос: убери запрещённые, слишком откровенные или опасные детали.\n\n"
        "Ответственность за использование результата несёт пользователь."
    )


def kie_422_text():
    return (
        "⚠️ Нейросеть не приняла этот запрос.\n\n"
        "Скорее всего, фото или описание не прошли проверку безопасности.\n\n"
        "Попробуй:\n"
        "— заменить фото;\n"
        "— смягчить описание;\n"
        "— убрать слишком откровенные или запрещённые детали."
    )


async def send_main_menu(message):
    await message.reply_text("🔥 Xena 2.0\n\nВыбери действие:", reply_markup=main_inline_menu())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    ensure_user(user.id, user.username)
    await update.message.reply_text("🔥 Добро пожаловать в Xena 2.0!\n\nЯ создаю AI-видео и изображения в формате 9:16.")
    await send_main_menu(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    ensure_user(user.id, user.username)
    await send_main_menu(update.message)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    ensure_user(user.id, user.username)
    await update.message.reply_text(f"Твой Telegram ID:\n{user.id}")


async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Пополнение баланса\n\nВыбери сумму:", reply_markup=topup_menu())


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
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Используй:\n/statsuser @username")
        return
    username = context.args[0].replace("@", "").lower()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, paid_credits, generations_count, spent_total FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    user_id, username, balance, generations_count, spent_total = row
    await update.message.reply_text(
        f"👤 Статистика пользователя:\n\n@{username}\nID: {user_id}\n\n🎬 Генераций: {generations_count or 0}\n💸 Потратил: {spent_total or 0} ₽\n💰 Баланс: {balance or 0} ₽"
    )


async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id, query.from_user.username)
    action = query.data

    if action == "main_menu":
        await query.message.reply_text("Главное меню:", reply_markup=main_inline_menu())
        return
    if action == "video_menu":
        await query.message.reply_text("🎬 Что создаём?", reply_markup=video_mode_menu())
        return
    if action == "mode_image_to_video":
        user_states[user_id] = {"mode": "image_to_video_wait_duration"}
        await query.message.reply_text("⏱ Выбери длительность видео:", reply_markup=duration_inline_menu("image_to_video"))
        return
    if action == "mode_text_to_video":
        user_states[user_id] = {"mode": "text_to_video_wait_duration"}
        await query.message.reply_text("⏱ Выбери длительность видео:", reply_markup=duration_inline_menu("text_to_video"))
        return
    if action == "mode_text_to_image":
        balance = get_balance(user_id)
        if balance < IMAGE_PRICE:
            await query.message.reply_text(f"💳 Недостаточно средств.\n\nСтоимость картинки: {IMAGE_PRICE} ₽\nТвой баланс: {balance} ₽", reply_markup=main_inline_menu())
            return
        user_states[user_id] = {"mode": "text_to_image_wait_prompt"}
        await query.message.reply_text("🖼 Напиши описание картинки.\n\nСтоимость: 50 ₽.")
        return
    if action.startswith("duration_"):
        parts = action.split("_")
        duration = parts[-1]
        mode = "_".join(parts[1:-1])
        cost = VIDEO_PRICES[duration]
        balance = get_balance(user_id)
        if balance < cost:
            await query.message.reply_text(f"💳 Недостаточно средств.\n\nСтоимость: {cost} ₽\nТвой баланс: {balance} ₽", reply_markup=main_inline_menu())
            return
        if mode == "image_to_video":
            user_states[user_id] = {"mode": "image_to_video_wait_photo", "duration": duration}
            await query.message.reply_text("📸 Отправь фото, которое хочешь оживить.")
            return
        if mode == "text_to_video":
            user_states[user_id] = {"mode": "text_to_video_wait_prompt", "duration": duration}
            await query.message.reply_text("📝 Напиши описание видео.\n\nЧем подробнее описание, тем лучше результат.")
            return
    if action == "buy":
        await query.message.reply_text("💳 Пополнение баланса\n\nВыбери сумму:", reply_markup=topup_menu())
        return
    if action == "profile":
        balance = get_balance(user_id)
        await query.message.reply_text(
            f"👤 Мой баланс\n\nБаланс: {balance} ₽\n\nСтоимость:\n🖼 Картинка — {IMAGE_PRICE} ₽\n🎬 5 секунд — {VIDEO_PRICES['5']} ₽\n🎬 10 секунд — {VIDEO_PRICES['10']} ₽\n🎬 15 секунд — {VIDEO_PRICES['15']} ₽"
        )
        return
    if action == "help":
        await query.message.reply_text(instruction_text())
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
            await query.message.reply_text("⏳ Оплата пока не найдена.\n\nЕсли уже оплатил — подожди 10–20 секунд и нажми кнопку ещё раз.")
            return
        add_paid_credit(user_id, amount)
        await query.message.reply_text(f"✅ Оплата получена!\n\nБаланс пополнен на {amount} ₽.\nТекущий баланс: {get_balance(user_id)} ₽.", reply_markup=main_inline_menu())
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    ensure_user(user_id, user.username)
    state = user_states.get(user_id)
    if not state or state.get("mode") != "image_to_video_wait_photo":
        await update.message.reply_text("Сначала нажми 🎬 СОЗДАТЬ ВИДЕО → 📸 Фото → Видео.")
        return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))
    state["image_path"] = str(image_path)
    state["mode"] = "image_to_video_wait_prompt"
    user_states[user_id] = state
    await update.message.reply_text("✅ Фото получил.\n\nТеперь напиши описание видео.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    ensure_user(user_id, user.username)
    text = update.message.text.strip()
    if text == "🏠 Главное меню":
        await send_main_menu(update.message)
        return
    if text.startswith("💳 Пополнить баланс на "):
        try:
            amount = int(text.replace("💳 Пополнить баланс на ", "").replace(" ₽", "").strip())
        except Exception:
            await update.message.reply_text("❌ Не удалось понять сумму.")
            return
        if amount not in TOPUP_AMOUNTS:
            await update.message.reply_text("❌ Неверная сумма пополнения.")
            return
        payment_url, payment_id = create_yookassa_payment(user_id, amount)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")],
        ])
        await update.message.reply_text(
            f"💳 Пополнение баланса на {amount} ₽\n\n1. Нажми «Оплатить»\n2. После оплаты вернись сюда\n3. Нажми «✅ Проверить оплату»\n\nЕсли ссылка не открывается, отключи VPN на время оплаты.",
            reply_markup=keyboard,
        )
        return
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("Выбери действие в меню.", reply_markup=main_inline_menu())
        return
    mode = state.get("mode")
    if mode == "image_to_video_wait_prompt":
        state["prompt"] = text
        await run_image_to_video(update, user_id)
        return
    if mode == "text_to_video_wait_prompt":
        state["prompt"] = text
        await run_text_to_video(update, user_id)
        return
    if mode == "text_to_image_wait_prompt":
        state["prompt"] = text
        await run_text_to_image(update, user_id)
        return
    await update.message.reply_text("Не понял команду. Открой главное меню.", reply_markup=main_inline_menu())


async def run_image_to_video(update: Update, user_id: int):
    state = user_states[user_id]
    duration = state["duration"]
    cost = VIDEO_PRICES[duration]
    if get_balance(user_id) < cost:
        await update.message.reply_text(f"💳 Недостаточно средств.\n\nБаланс: {get_balance(user_id)} ₽\nСтоимость: {cost} ₽", reply_markup=main_inline_menu())
        user_states.pop(user_id, None)
        return
    await update.message.reply_text("🎥 Запускаю нейросеть.\n\nГенерация может занять 2–10 минут. Не отправляй новый запрос, пока я работаю.")
    try:
        image_url = upload_image_to_kie(state["image_path"])
        task_id = create_kie_image_to_video_task(image_url, state["prompt"], duration)
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost)
        result_url = wait_kie_result(task_id)
        video_path = download_file(result_url, user_id, "mp4")
        with open(video_path, "rb") as video_file:
            await update.message.reply_video(video=video_file, caption="✅ Готово! Вот твоё AI-видео.", read_timeout=3600, write_timeout=3600, connect_timeout=60, pool_timeout=3600)
        await update.message.reply_text(f"💰 Баланс: {get_balance(user_id)} ₽", reply_markup=main_inline_menu())
    except Exception as e:
        await handle_generation_exception(update, e)
    user_states.pop(user_id, None)


async def run_text_to_video(update: Update, user_id: int):
    state = user_states[user_id]
    duration = state["duration"]
    cost = VIDEO_PRICES[duration]
    if get_balance(user_id) < cost:
        await update.message.reply_text(f"💳 Недостаточно средств.\n\nБаланс: {get_balance(user_id)} ₽\nСтоимость: {cost} ₽", reply_markup=main_inline_menu())
        user_states.pop(user_id, None)
        return
    await update.message.reply_text("🎥 Запускаю нейросеть.\n\nГенерация может занять 2–10 минут. Не отправляй новый запрос, пока я работаю.")
    try:
        task_id = create_kie_text_to_video_task(state["prompt"], duration)
        decrement_paid_credit(user_id, cost)
        add_generation_stats(user_id, cost)
        result_url = wait_kie_result(task_id)
        video_path = download_file(result_url, user_id, "mp4")
        with open(video_path, "rb") as video_file:
            await update.message.reply_video(video=video_file, caption="✅ Готово! Вот твоё AI-видео.", read_timeout=3600, write_timeout=3600, connect_timeout=60, pool_timeout=3600)
        await update.message.reply_text(f"💰 Баланс: {get_balance(user_id)} ₽", reply_markup=main_inline_menu())
    except Exception as e:
        await handle_generation_exception(update, e)
    user_states.pop(user_id, None)


async def run_text_to_image(update: Update, user_id: int):
    if get_balance(user_id) < IMAGE_PRICE:
        await update.message.reply_text(f"💳 Недостаточно средств.\n\nБаланс: {get_balance(user_id)} ₽\nСтоимость: {IMAGE_PRICE} ₽", reply_markup=main_inline_menu())
        user_states.pop(user_id, None)
        return
    await update.message.reply_text("🖼 Запускаю генерацию картинки.\n\nОбычно это занимает 1–3 минуты.")
    try:
        task_id = create_kie_image_task(user_states[user_id]["prompt"])
        decrement_paid_credit(user_id, IMAGE_PRICE)
        add_generation_stats(user_id, IMAGE_PRICE)
        result_url = wait_kie_result(task_id)
        image_path = download_file(result_url, user_id, "jpg")
        with open(image_path, "rb") as image_file:
            await update.message.reply_photo(photo=image_file, caption="✅ Готово! Вот твоё изображение.")
        await update.message.reply_text(f"💰 Баланс: {get_balance(user_id)} ₽", reply_markup=main_inline_menu())
    except Exception as e:
        await handle_generation_exception(update, e)
    user_states.pop(user_id, None)


async def handle_generation_exception(update: Update, e: Exception):
    import traceback
    print("GENERATION_ERROR:", repr(e), flush=True)
    traceback.print_exc()
    error_text = str(e).lower()
    if "kie_422_input_rejected" in error_text or "422" in error_text or "please try again" in error_text or "change your input files or prompt" in error_text:
        await update.message.reply_text(kie_422_text())
        return
    if "internal error" in error_text or "try again later" in error_text or "timeout" in error_text or "temporarily" in error_text:
        await update.message.reply_text("⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\nПопробуй ещё раз через 1–2 минуты или немного измени описание.")
        return
    await update.message.reply_text(f"❌ Произошла ошибка генерации.\n\nЕсли проблема повторяется — напиши в поддержку:\n{SUPPORT_URL}", disable_web_page_preview=True)


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
    print("Бот Xena 2.0 запущен...", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()

