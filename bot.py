import os
import json
import time
import sqlite3
import requests
from pathlib import Path

from telegram import Update, LabeledPrice, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
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
user_states = {}

ADMIN_IDS = {
    6164104276
}
VIDEO_PRICES = {
    "5": 98,
    "10": 147,
}
def paid_menu():
    keyboard = [
        ["💳 Пополнить баланс: /buy"],
        ["🎁 БЕСПЛАТНЫЕ генерации: /ref"],
        ["🚀 Запустить бота"],
        ["📘 Инструкция: /help"],
        ["👤 Мой баланс: /profile"],
        ["🆘 Связаться с поддержкой"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )
def duration_menu():
    keyboard = [
        ["5 секунд", "10 секунд"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )
def duration_menu_5_only():
    keyboard = [
        ["5 секунд"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )
def topup_inline_menu():
    keyboard = [
        [InlineKeyboardButton("250 ₽", callback_data="topup_250")],
        [InlineKeyboardButton("500 ₽", callback_data="topup_500")],
        [InlineKeyboardButton("1000 ₽", callback_data="topup_1000")],
        [InlineKeyboardButton("5000 ₽", callback_data="topup_5000")]
    ]
    return navigation_keyboard(keyboard, back_callback="main_menu")


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
        [InlineKeyboardButton("🆘 Поддержка", url="https://t.me/Vlad101ss")]
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_menu_keyboard(back_callback="main_menu"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)],
        [InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ])

def navigation_keyboard(buttons, back_callback="main_menu"):
    buttons.append([InlineKeyboardButton("⬅️ НАЗАД", callback_data=back_callback)])
    buttons.append([InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def back_to_partner_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Бесплатные генерации", callback_data="ref")],
        [InlineKeyboardButton("💸 Заработать", callback_data="earn")],
        [InlineKeyboardButton("⬅ Назад", callback_data="main_menu")]
    ])
def add_paid_credit(user_id: int, amount: int = 1):
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

    try:
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN ref_mode TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN partner_balance INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    
    
def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT free_used, paid_credits FROM users WHERE user_id = ?",
        (user_id,)
    )
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

    cur.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (username,)
    )

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

    cur.execute(
        "SELECT referrer_id, ref_mode FROM users WHERE user_id = ?",
        (user_id,)
    )

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

    cur.execute(
        "SELECT partner_balance FROM users WHERE user_id = ?",
        (user_id,)
    )

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

    if bonus <= 0:
        return

    add_partner_money(referrer_id, bonus)

def apply_referral_bonus(user_id: int, duration: str):
    referrer_id, ref_mode = get_referrer(user_id)

    if not referrer_id:
        return

    if ref_mode == "free":
        bonus = VIDEO_PRICES[duration]
        give_balance(referrer_id, bonus)

    if ref_mode == "money":
        if duration == "5":
            bonus = 50
        elif duration == "10":
            bonus = 100
        else:
            bonus = 0

        if bonus > 0:
            add_partner_money(referrer_id, bonus)

def get_all_partners():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, username, partner_balance
        FROM users
        WHERE partner_balance > 0
        ORDER BY partner_balance DESC
        """
    )

    rows = cur.fetchall()
    conn.close()

    return rows


def reset_partner_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET partner_balance = 0 WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


def increment_free_used(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


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
            "uploadPath": "images/tarantino-bot",
            "fileName": Path(image_path).name
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=3600)

    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Ошибка загрузки картинки в Kie: {result}")

    download_url = result["data"]["downloadUrl"]
    return download_url


def create_kie_video_task(image_url: str, prompt: str, duration: str) -> str:
    url = "https://api.kie.ai/api/v1/jobs/createTask"

    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
    "model": "grok-imagine-video-1-5-preview",
    "input": {
        "prompt": prompt,
        "image_urls": [
            image_url
        ],
        "aspect_ratio": "9:16",
        "resolution": "480p",
        "duration": int(duration)
    }
}

    response = requests.post(url, headers=headers, json=payload, timeout=3600)
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 200:
        raise RuntimeError(f"Ошибка создания видео-задачи Kie: {result}")

    return result["data"]["taskId"]


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
            result_json = json.loads(result_json_raw)

            video_urls = (
                result_json.get("resultUrls")
                or result_json.get("videoUrls")
                or result_json.get("videos")
                or []
            )

            if not video_urls:
                raise RuntimeError(f"Видео готово, но ссылка не найдена: {result_json}")

            return video_urls[0]

        if state == "fail":
            raise RuntimeError(f"Kie не смог сгенерировать видео: {data.get('failMsg')}")

        time.sleep(10)

    raise RuntimeError("Видео генерировалось слишком долго. Попробуй позже.")


def download_video(video_url: str, user_id: int) -> str:
    video_path = MEDIA_DIR / f"{user_id}_result.mp4"

    response = requests.get(video_url, timeout=3600)
    response.raise_for_status()

    with open(video_path, "wb") as f:
        f.write(response.content)

    return str(video_path)


def create_yookassa_payment(user_id: int, amount: int) -> str:
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
def generate_video_from_image(image_path: str, prompt: str, user_id: int, duration: str) -> str:
    image_url = upload_image_to_kie(image_path)
    task_id = create_kie_video_task(image_url, prompt, duration)
    video_url = wait_kie_video_result(task_id)
    video_path = download_video(video_url, user_id)
    return video_path

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
    except:
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
    except:
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
        await update.message.reply_text(
            "Партнёров с балансом нет."
        )
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
    except:
        await update.message.reply_text("Ошибка ID.")
        return

    reset_partner_balance(target_id)

    await update.message.reply_text(
        f"✅ Партнёрский баланс {target_id} обнулён."
    )
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
async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data

    try:
        await query.message.delete()
    except:
        pass

    if action == "main_menu":
        await send_main_menu(query.message.chat)
        return

    if action.startswith("checkpay_"):
        parts = action.split("_")
        payment_id = parts[1]
        amount = int(parts[2])

        try:
            paid = check_yookassa_payment(payment_id)
        except Exception as e:
            await query.message.chat.send_message(
                f"❌ Не удалось проверить оплату:\n\n{e}",
                reply_markup=back_to_menu_keyboard()
            )
            return

        if not paid:
            await query.message.chat.send_message(
                "⏳ Оплата пока не найдена.\n\n"
                "Если ты уже оплатил — подожди 10–20 секунд и нажми кнопку ещё раз.",
                reply_markup=navigation_keyboard([
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"checkpay_{payment_id}_{amount}")]
                ], back_callback="buy")
            )
            return

        add_paid_credit(user_id, amount)
        apply_deposit_bonus(user_id, amount)
        _, paid_credits = get_user(user_id)

        await query.message.chat.send_message(
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

        await query.message.chat.send_message(
            f"💳 Пополнение баланса на {amount} ₽\n\n"
            f"1. Нажми «Оплатить»\n"
            f"2. После оплаты вернись сюда\n"
            f"3. Нажми «✅ Проверить оплату»",
            reply_markup=keyboard
        )
        return

    if action == "buy":
        await query.message.chat.send_message(
            "💳 Выберите сумму пополнения:",
            reply_markup=topup_inline_menu()
        )
        return

    if action == "profile":
        free_used, paid_credits = get_user(user_id)

        await query.message.chat.send_message(
            f"👤 Твой баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Стоимость сейчас:\n"
            f"5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"10 секунд — {VIDEO_PRICES['10']} ₽",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "partner":
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        await query.message.chat.send_message(
            "🤝 Партнерка\n\n"
            "За каждого приведенного вами активного пользователя вы будете получать бонусы "
            "(70% от каждого его депозита) на свой бонусный счет.\n\n"
            "Заработанные бонусы вы сможете тратить на генерации.\n\n"
            "Информация о количестве бонусов будет отображаться в разделе «Кабинет партнера».\n\n"
            f"Ваша реферальная ссылка:\n"
            f"https://t.me/{bot_username}?start=partner_{user_id}",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "partner_profile":
        partner_balance = get_partner_balance(user_id)

        await query.message.chat.send_message(
            f"💼 Кабинет партнера\n\n"
            f"Бонусный счет: {partner_balance} бонусов\n\n"
            f"1 бонус = 1 ₽.\n\n"
            f"В дальнейшем перед генерацией можно будет выбрать способ оплаты: "
            f"деньгами или бонусами.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "help":
        await query.message.chat.send_message(
            "📘 Инструкция\n\n"
            "1. Выбери, что хочешь создать: видео, изображение или аудио.\n"
            "2. Выбери нейросеть или режим генерации.\n"
            "3. Отправь фото, текст или другой материал, если бот попросит.\n"
            "4. Опиши результат простыми словами.\n"
            "5. Дождись готового результата.\n\n"
            "Не нужно разбираться в нейросетях — бот сам проведет тебя по шагам.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "create_video":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Текст → Видео", callback_data="seedance_text_video")],
            [InlineKeyboardButton("🖼 Картинка → Видео", callback_data="seedance_image_video")],
            [InlineKeyboardButton("🎬 Видео + Картинка + Текст", callback_data="seedance_full_video")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])

        await query.message.chat.send_message(
            "🎬 Создание видео\n\n"
            "Выбери простой режим:\n\n"
            "🎥 Текст → Видео — просто опиши ролик.\n"
            "🖼 Картинка → Видео — оживи фото.\n"
            "🎬 Видео + Картинка + Текст — сложный режим с референсами.",
            reply_markup=keyboard
        )
        return

    if action == "create_image":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Текст → Изображение", callback_data="image_text_to_image")],
            [InlineKeyboardButton("🖼 Фото → Изображение", callback_data="image_image_to_image")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])

        await query.message.chat.send_message(
            "🖼 Создание изображения\n\n"
            "Выбери режим генерации:",
            reply_markup=keyboard
        )
        return

    if action == "create_audio":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎵 Текст → Аудио", callback_data="audio_text_to_audio")],
            [InlineKeyboardButton("🎙 Голос/звук → Аудио", callback_data="audio_reference")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])

        await query.message.chat.send_message(
            "🎵 Создание аудио\n\n"
            "Выбери режим генерации:",
            reply_markup=keyboard
        )
        return

    if action == "seedance_text_video":
        await query.message.chat.send_message(
            "🎥 Текст → Видео\n\n"
            "Этот режим будет работать через Seedance 2.0.\n\n"
            "Следующим шагом подключим:\n"
            "1. выбор длительности 5/10/15 сек\n"
            "2. ввод описания\n"
            "3. отправку задачи в Kie",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "seedance_image_video":
        await query.message.chat.send_message(
            "🖼 Картинка → Видео\n\n"
            "Этот режим будет работать через Seedance 2.0.\n\n"
            "Следующим шагом подключим:\n"
            "1. загрузку картинки\n"
            "2. выбор длительности\n"
            "3. ввод описания\n"
            "4. генерацию видео",
            reply_markup=back_to_menu_keyboard()
        )
        return

    if action == "seedance_full_video":
        await query.message.chat.send_message(
            "🎬 Видео + Картинка + Текст\n\n"
            "Сложный режим Seedance 2.0.\n\n"
            "Позже сюда добавим:\n"
            "• референсное видео\n"
            "• 1–5 картинок\n"
            "• текстовое описание\n"
            "• выбор длительности\n"
            "• звук включить/выключить",
            reply_markup=back_to_menu_keyboard()
        )
        return
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    free_used, paid_credits = get_user(user_id)

    if paid_credits < VIDEO_PRICES["5"]:
        await update.message.reply_text(
            "💳Недостаточно средств для генерации.\n\n"
            "👇Пополнить баланс или получить БЕСПЛАТНО👇"
        )

        await update.message.reply_text(
            "Меню бота",
            reply_markup=main_inline_menu()
        )
        return

    if free_used >= 1 and paid_credits < VIDEO_PRICES["5"]:
        await update.message.reply_text(
            "💳Недостаточно средств для генерации.\n\n"
            "👇Пополнить баланс или получить БЕСПЛАТНО👇"
        )

        await update.message.reply_text(
            "Меню бота",
            reply_markup=main_inline_menu()
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id] = {"image_path": str(image_path)}


    if paid_credits < VIDEO_PRICES["10"]:
        await update.message.reply_text(
            "✅ Картинку получил.\n\n"
            "Выбери длительность видео:",
            reply_markup=duration_menu_5_only()
        )
        return

    await update.message.reply_text(
        "✅ Картинку получил.\n\n"
        "Выбери длительность видео:",
        reply_markup=duration_menu()
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    prompt = update.message.text

    if prompt == "💳 Купить генерации: /buy":
        await buy(update, context)
        return

    if prompt.startswith("💳 Пополнить баланс на "):
        amount_text = (
            prompt
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
            f"1. Нажми «Оплатить»\n"
            f"2. После оплаты вернись сюда\n"
            f"3. Нажми «✅ Проверить оплату»",
            reply_markup=keyboard
        )
        return

    if prompt == "🎁 БЕСПЛАТНЫЕ генерации: /ref":
        await update.message.reply_text("🎁 Реферальную программу подключим следующим этапом.")
        return

    if prompt == "🚀 Запустить бота":
        await send_main_menu(update.message)
        return

    if prompt == "📘 Инструкция: /help":
        await update.message.reply_text(
            "📘 Инструкция:\n\n"
            "1. Отправьте картинку.\n"
            "Если хотите оживить человека, отправляйте фото, на котором будет хорошо видно лицо.\n"
            "2. Выберите длительность видео.\n"
            "На данный момент оптимальная длительность 5-10 секунд, дальше нейросеть начинает искажать происходящее, теряется качество и реалистичность.\n"
            "Более длительные AI ролики сейчас создают обьединяя много коротких роликов в один большой, используя последние кадры для сознания продолжения\n"
            "3. Составьте описание видео.\n"
            "Пишите очень подробно, что бы вы хотели видеть\n"
            "4. Дождись готового AI-видео.\n"
            "Нажимая старт, вы соглашаетесь с правилами использования бота, а именно:\n"
            "а) Запрещается использовать бот для создания с целью распространения контента, нарушающего законодательство или права третьих лиц, включая:\n"
            "незаконный контент\n"
            "материалы сексуального характера с несовершеннолетними\n"
            "экстремизм, терроризм, разжигание ненависти\n"
            "мошенничество и введение в заблуждение\n"
            "клевету и нарушение репутации\n"
            "незаконное использование чужих изображений, лиц или авторских материалов\n"
            "б) Бот является автоматическим инструментом генерации контента. Ответственность за использование результатов несёт пользователь."
        )
        return

    if prompt == "👤 Мой баланс: /profile":
        free_used, paid_credits = get_user(user_id)
        free_left = max(0, 1 - free_used)

        await update.message.reply_text(
            f"👤 Твой баланс:\n\n"
            f"Бесплатных генераций: {free_left}\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Стоимость:\n"
            f"5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"10 секунд — {VIDEO_PRICES['10']} ₽\n"
        )
        return

    if prompt == "🆘 Связаться с поддержкой":
        await update.message.reply_text(
            "🆘 Написать в поддержку: https://t.me/Vlad101ss",
            disable_web_page_preview=True
        )
        return

    if prompt in ["5 секунд", "10 секунд"]:
        if user_id not in user_states:
            await update.message.reply_text("Сначала отправь картинку.")
            return

        free_used, paid_credits = get_user(user_id)
        selected_duration = prompt.replace(" секунд", "")
        selected_cost = VIDEO_PRICES[selected_duration]

        if free_used >= 1 and paid_credits < selected_cost:
            await update.message.reply_text(
                "💳Недостаточно средств для генерации.\n\n"
                "👇Пополнить баланс или получить БЕСПЛАТНО👇"
            )

            await update.message.reply_text(
                "Меню бота",
                reply_markup=inline_menu()
            )
            return

        user_states[user_id]["duration"] = selected_duration

        await update.message.reply_text("✍️ Теперь отправь описание видео.")
        return

    if user_id not in user_states:
        await update.message.reply_text("Сначала отправь картинку.")
        return

    if "duration" not in user_states[user_id]:
        await update.message.reply_text(
            "Сначала выбери длительность видео:",
            reply_markup=duration_menu()
        )
        return

    free_used, paid_credits = get_user(user_id)

    image_path = user_states[user_id]["image_path"]
    duration = user_states[user_id]["duration"]
    video_cost = VIDEO_PRICES[duration]

    if free_used >= 1 and paid_credits < video_cost:
        await update.message.reply_text(
            f"Баланс: {paid_credits} ₽"
        )

        await update.message.reply_text(
            "💳Недостаточно средств для генерации.\n\n"
            "👇Пополнить баланс или получить БЕСПЛАТНО👇"
        )

        await update.message.reply_text(
            "Меню бота",
            reply_markup=inline_menu()
        )
        return

    await update.message.reply_text(
        "🎥 Запускаю нейросеть.\n\n"
        "Генерация видео может занять 2–10 минут. Не отправляй новую картинку, пока я работаю."
    )

    try:
        video_path = generate_video_from_image(image_path, prompt, user_id, duration)

        decrement_paid_credit(user_id, video_cost)
        apply_referral_bonus(user_id, duration)

        try:
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption="✅ Готово! Вот твоё AI-видео.",
                    read_timeout=3600,
                    write_timeout=3600,
                    connect_timeout=60,
                    pool_timeout=3600
                )
        except Exception:
            await update.message.reply_text(
                "⚠️ Видео было сгенерировано, но Telegram не смог его отправить.\n\n"
                "Напиши в поддержку:\n"
                "https://t.me/Vlad101ss",
                disable_web_page_preview=True
            )

        free_used_after, paid_credits_after = get_user(user_id)

        await update.message.reply_text(
            f"Баланс: {paid_credits_after} ₽"
        )

        if paid_credits_after <= 0:
            await update.message.reply_text(
                "💳Недостаточно средств для генерации.\n\n"
                "👇Пополнить баланс или получить БЕСПЛАТНО👇"
            )

            await update.message.reply_text(
                "Меню бота",
                reply_markup=inline_menu()
            )

    except Exception as e:
        import traceback
        print("GENERATION_ERROR:", repr(e))
        traceback.print_exc()

        error_text = str(e).lower()

        if (
            "internal error" in error_text
            or "try again later" in error_text
            or "kie не смог" in error_text
            or "timeout" in error_text
        ):
            await update.message.reply_text(
                "⚠️ Нейросеть временно перегружена или не смогла обработать запрос.\n\n"
                "Попробуй ещё раз через 1–2 минуты или немного измени описание видео."
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка генерации.\n\n"
                "Если проблема повторяется — напиши в поддержку:\n"
                "https://t.me/Vlad101ss",
                disable_web_page_preview=True
            )

    user_states.pop(user_id, None)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 Пополнение баланса:\n\n"
        "Стоимость генераций:\n"
        "5 секунд — 98 ₽\n"
        "10 секунд — 147 ₽\n"
        "Выбери сумму пополнения:",
        reply_markup=topup_menu()
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
            f"Текущий баланс: {paid_credits} ₽.\n\n"
            f"Теперь отправь картинку."
        )

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":    
    main()
