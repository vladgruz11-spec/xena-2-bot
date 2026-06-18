import os
import json
import time
import sqlite3
import requests
import random
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
INSTRUCTION_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/instruction.jpg"

MAIN_MENU_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/main_menu.jpg"

DEMO_MENU_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/demo_menu.jpg"

FREE_STYLE_PHOTO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/free_style.jpg"

PROMO_VIDEOS = [
    "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/promo_1.mp4",
    "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/promo_2.mp4",
    "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/promo_3.mp4",
    "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/promo_4.mp4",
    "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/promo_5.mp4",
]


WAVE_HAND_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/wave_hand.mp4"

EAT_ICE_CREAM_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/eat_ice_cream.mp4"

DANCE_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/dance.mp4"

JUMP_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/jump.mp4"

CHOP_WOOD_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/chop_wood.mp4"

DRINK_JUICE_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/drink_juice.mp4"

EAT_APPLE_VIDEO = "https://raw.githubusercontent.com/vladgruz11-spec/telegram-bot2/main/assets/eat_apple.mp4"

JUGGLE_VIDEO = "https://tempfileb.aiquickdraw.com/kieai/market/1781262544065_kNi0riur.mp4"

PROMPT_WAVE_HAND = """
Она снимает руками лифчик, так что видно ее сиськи и соски. Она сжимает сиськи руками с двух сторон, и сексуально смотрит. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная
"""

PROMPT_EAT_ICE_CREAM = """
Она становится на колени перед мужчиной и сосет его член. В видео не должно быть музыки. Должны быть только звуки, как она сосет. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная. Мужской член выглядит натурально и естественно
"""

PROMPT_DANCE = """
Она становится на четвереньки, снимает всю одежду ниже пояса руками, так, что попа оголяется полностью, мужчина подходит сзади, хватает ее руками за попу и жестко трахает ее своим членом в анус. В видео не должно быть музыки. Должно быть слышно как она стонет и шлепки по попе, когда он ее трахает. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная
"""

PROMPT_JUMP = """
Она становится на колени, снимает лифчик руками, так что видно сиськи и соски. Мужчина сидит перед ней и дрочит свой половой член, видно только его член и живот. Она берет свои сиськи, зажимает очень плотно ими его член своими сиськами и делает titjob, член полностью погружается между сисек. В видео не должно быть музыки. Должны быть только звуки дрочки члена, и стоны мужчины. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная
"""

PROMPT_CHOP_WOOD = """
Становится на колени перед мужчиной, он берет ее за волосы одной рукой, засовывает ей в рот, глубоко в горло свой половой член полностью так, что он полностью погружается в рот и мы его не видим. и жестко трахает, прижимая ее голову к себе. На видео не должно быть музыки, должно быть слышно как она сосет. Мужской член выглядит реалистично и натурально.
"""

PROMPT_DRINK_JUICE = """
Она становится на колени, снимает лифчик руками, так что видно сиськи и соски. Мужчина дрочит свой член рукой и кончает ей на сиськи полупрозрачной спермой из своего члена, сперма стекает по сиськам. Это Cumshot на сиськи! В видео не должно быть музыки. Должны быть только звуки дрочки члена, и стоны мужчины. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная
"""

PROMPT_EAT_APPLE = """
Она становится на колени, открывает рот. Мужчина дрочит свой член рукой и кончает ей в рот и на лицо полупрозрачной спермой из своего члена- это Cumshot.  В видео не должно быть музыки. Мужской член должен выглядеть натурально, правдоподобно и естественно. Должны быть только звуки дрочки члена, и стоны мужчины. Натуральное тело, обнаженная кожа, реалистичная анатомия, детализированная текстура кожи, фотореалистичная
"""

PROMPT_JUGGLE = """
Мужчина подходит сзади, хватает ее за жопу, вставляет член ей в жопу и  жестко трахает сзади в попку, девушка немного наклоняется, выгибая спину. Мужчина жестко трахает ее, член глубоко заходит ей в попку, она стонет, ей очень хорошо, она получает оргазм. В видео не должно быть музыки, все пропорции сохраняются, должна быть реалестичность
"""

STYLE_DATA = {
    "wave_hand": {
        "title": "Показывает сиськи",
        "button": "Показывает сиськи 🍊🍊",
        "video": WAVE_HAND_VIDEO,
        "prompt": PROMPT_WAVE_HAND
    },
    "eat_ice_cream": {
        "title": "Сосет член",
        "button": "Сосет член 👄",
        "video": EAT_ICE_CREAM_VIDEO,
        "prompt": PROMPT_EAT_ICE_CREAM
    },
    "dance": {
        "title": "Трахают сзади",
        "button": "Трахают сзади 🐕",
        "video": DANCE_VIDEO,
        "prompt": PROMPT_DANCE
    },
    "jump": {
        "title": "Между сисек",
        "button": "Между сисек 🍊🍌🍊",
        "video": JUMP_VIDEO,
        "prompt": PROMPT_JUMP
    },
    "chop_wood": {
        "title": "Глубокий минет",
        "button": "Глубокий минет 🍌",
        "video": CHOP_WOOD_VIDEO,
        "prompt": PROMPT_CHOP_WOOD
    },
    "drink_juice": {
        "title": "Кончают на грудь",
        "button": "Кончают на грудь 💦",
        "video": DRINK_JUICE_VIDEO,
        "prompt": PROMPT_DRINK_JUICE
    },
    "eat_apple": {
        "title": "Кончают в рот",
        "button": "Кончают в рот 💦",
        "video": EAT_APPLE_VIDEO,
        "prompt": PROMPT_EAT_APPLE
    },

    "juggle": {
        "title": "Трахают сзади",
        "button": "Трахают сзади 🦞",
        "video": JUGGLE_VIDEO,
        "prompt": PROMPT_JUGGLE
    },
}

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
user_states = {}

ADMIN_IDS = {
    6164104276
}
VIDEO_PRICES = {
    "5": 98,
    "10": 147,
}


EXAMPLES_CHANNEL_URL = "https://t.me/+qukafJOw1y8zZGMy"
MAIN_CHANNEL_URL = "https://t.me/Xena18H"

def main_inline_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 ПОРНО С ДЕВУШКОЙ", callback_data="video_menu")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("🎁 БЕСПЛАТНЫЕ генерации", callback_data="ref")],
        [InlineKeyboardButton("💸 ЗАРАБОТАТЬ с Xena", callback_data="earn")],
        [InlineKeyboardButton("💼 Кабинет партнёра", callback_data="partner_profile")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url="https://t.me/Vlad101ss")]
    ]
    return InlineKeyboardMarkup(keyboard)


def video_inline_menu():
    keyboard = [
        [
            InlineKeyboardButton("Показывает сиськи 🍊🍊", callback_data="style_wave_hand"),
            InlineKeyboardButton("Сосет член 👄", callback_data="style_eat_ice_cream"),
        ],
        [
            InlineKeyboardButton("Трахают сзади 🐕", callback_data="style_dance"),
            InlineKeyboardButton("Между сисек 🍊🍌🍊", callback_data="style_jump"),
        ],
        [
            InlineKeyboardButton("Глубокий минет 🍌", callback_data="style_chop_wood"),
            InlineKeyboardButton("Кончают на грудь 💦", callback_data="style_drink_juice"),
        ],
        [
            InlineKeyboardButton("Кончают в рот 💦", callback_data="style_eat_apple"),
            InlineKeyboardButton("Трахают сзади 🦞", callback_data="style_juggle"),
        ],
        [InlineKeyboardButton("🎨 СВОБОДНЫЙ СТИЛЬ", callback_data="free_style")],
        [InlineKeyboardButton("🏠 ГЛАВНОЕ МЕНЮ", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def style_action_menu(style_id: str):
    keyboard = [
        [InlineKeyboardButton("🎬 Оживить своё фото", callback_data=f"animate_style_{style_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="video_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def free_style_action_menu():
    keyboard = [
        [InlineKeyboardButton("🎬 Оживить своё фото", callback_data="animate_free_style")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="video_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def first_intro_menu():
    keyboard = [
        [InlineKeyboardButton("📘 Открыть инструкцию", callback_data="open_first_instruction")],
        [InlineKeyboardButton("✅ Ознакомился", callback_data="intro_understood")]
    ]
    return InlineKeyboardMarkup(keyboard)


def understood_menu(callback_data: str):
    keyboard = [
        [InlineKeyboardButton("✅ Ознакомился", callback_data=callback_data)]
    ]
    return InlineKeyboardMarkup(keyboard)


def after_generation_menu():
    keyboard = [
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="back_to_video_menu_no_delete")]
    ]
    return InlineKeyboardMarkup(keyboard)

def not_enough_balance_menu():
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("🎁 БЕСПЛАТНЫЕ генерации", callback_data="ref")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
def topup_menu():
    keyboard = [
        ["💳 Пополнить баланс на 196 ₽"],
        ["💳 Пополнить баланс на 490 ₽"],
        ["💳 Пополнить баланс на 1127 ₽"],
        ["🏠 Главное меню"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )
def inline_menu():
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="buy")],
        [InlineKeyboardButton("🎁 БЕСПЛАТНЫЕ генерации", callback_data="ref")],
        [InlineKeyboardButton("💸 ЗАРАБОТАТЬ с Xena", callback_data="earn")],
        [InlineKeyboardButton("💼 Кабинет партнёра", callback_data="partner_profile")],
        [InlineKeyboardButton("🚀 Запустить бота", callback_data="start")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="help")],
        [InlineKeyboardButton("👤 Мой баланс", callback_data="profile")],
        [InlineKeyboardButton("🆘 Связаться с поддержкой", url="https://t.me/Vlad101ss")]
    ]

    return InlineKeyboardMarkup(keyboard)
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id TEXT,
            video_cost INTEGER,
            duration TEXT,
            status TEXT DEFAULT 'waiting',
            created_at INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
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
    try:
        cur.execute("ALTER TABLE users ADD COLUMN generations_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN spent_total INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN instruction_seen INTEGER DEFAULT 0")
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

def has_seen_instruction(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT instruction_seen FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    conn.close()

    return bool(row and row[0])


def set_instruction_seen(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET instruction_seen = 1 WHERE user_id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()


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

def save_active_generation(user_id: int, task_id: str, video_cost: int, duration: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO active_generations (user_id, task_id, video_cost, duration, status, created_at)
        VALUES (?, ?, ?, ?, 'waiting', ?)
        """,
        (user_id, task_id, video_cost, duration, int(time.time()))
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
    "model": "wan/2-6-image-to-video",
    "input": {
        "prompt": prompt,
        "image_urls": [image_url],
        "duration": duration,
        "resolution": "720p",
        "nsfw_checker": False,
        "generate_audio": False
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
    print("STEP 1: upload image to Kie", flush=True)
    image_url = upload_image_to_kie(image_path)

    print("STEP 2: create Kie task", flush=True)
    task_id = create_kie_video_task(image_url, prompt, duration)

    print(f"STEP 2.5: Kie task created, task_id={task_id}", flush=True)

    print(f"STEP 3: wait Kie result, task_id={task_id}", flush=True)
    video_url = wait_kie_video_result(task_id)

    print(f"STEP 4: download video: {video_url}", flush=True)
    video_path = download_video(video_url, user_id)

    print(f"STEP 5: video downloaded: {video_path}", flush=True)
    return video_path

def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users")
    users = [row[0] for row in cur.fetchall()]

    conn.close()
    return users


def get_bot_setting(key: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cur.fetchone()

    conn.close()
    return row[0] if row else None


def set_bot_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
        (key, value)
    )

    conn.commit()
    conn.close()


def promo_video_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 ПОРНО С ДЕВУШКОЙ", callback_data="video_menu")]
    ])


async def send_promo_to_all_users(application):
    users = get_all_user_ids()
    video = random.choice(PROMO_VIDEOS)

    caption = (
        "🔞 Они готовы принять твой камшот прямо сейчас!\n\n"
        "Чего же ты ждешь? Действуй!"
    )

    sent = 0
    failed = 0

    for user_id in users:
        try:
            await application.bot.send_video(
                chat_id=user_id,
                video=video,
                caption=caption,
                reply_markup=promo_video_button()
            )
            sent += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"PROMO_SEND_FAILED user_id={user_id}: {repr(e)}", flush=True)
            failed += 1

    print(f"PROMO_SENT: sent={sent}, failed={failed}", flush=True)


async def promo_scheduler(application):
    moscow_tz = ZoneInfo("Europe/Moscow")

    while True:
        now = datetime.now(moscow_tz)
        last_sent = get_bot_setting("last_promo_sent")

        should_send = False

        if now.hour == 22 and now.minute == 0:
            if not last_sent:
                should_send = True
            else:
                last_dt = datetime.fromisoformat(last_sent)
                if now - last_dt >= timedelta(days=3):
                    should_send = True

        if should_send:
            print("PROMO_SCHEDULER: sending promo", flush=True)
            await send_promo_to_all_users(application)
            set_bot_setting("last_promo_sent", now.isoformat())

        await asyncio.sleep(60)


async def post_init(application):
    application.create_task(promo_scheduler(application))

async def send_main_menu_message(message):
    await message.reply_photo(
        photo=MAIN_MENU_PHOTO,
        caption=(
            f"1️⃣ Подпишись на канал, чтобы нас не потерять:\n{MAIN_CHANNEL_URL}\n\n"
            f"2️⃣ Примеры генераций:\n{EXAMPLES_CHANNEL_URL}"
        ),
        reply_markup=main_inline_menu()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_main_menu_message(update.message)

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

    if action == "open_first_instruction":
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_message(
            "📘 Инструкция:\n\n"
            "Бот Xena создает 18+ видео с участием человека, фото которого вы отправите.\n"
            "1. Нажмите СТАРТ.\n"
            "2. В Главном Меню нажмите кнопку ПОРНО С ДЕВУШКОЙ.\n"
            "3. Выберите, что хотите увидеть в ролике.\n"
            "Можете выбрать из списка, либо создать генерацию в СВОБОДНОМ СТИЛЕ.\n"
            "СВОБОДНЫЙ СТИЛЬ-режим, в котором вы сами пишете, что хотите видеть на экране.\n"
            "Если выбрали СВОБОДНЫЙ СТИЛЬ, очень подробно и детально составляйте описание, иначе нейросеть может вас не правильно понять, и результат не оправдает ожиданий.\n"
            "4. Выберите длительность видео.\n"
            "На данный момент доступна длительность 5 и 10 секунд. При большем времени, нейросеть начинает искажать картинку.\n"
            "Информацию о создании более долгих и качественных роликов вы найдете в нашем закрытом телеграмм-канале. Ссылка в Главном Меню.\n"
            "5. Если на вашем балансе не хватает средств для генирации, нажмите ПОПОЛНИТЬ БАЛАНС в Главном Меню.\n"
            "Так же доступна партнерская программа: за каждого, приглашенного пользователя вы можете получать ДЕНЬГИ или БЕСПЛАТНЫЕ генерации, на выбор!\n"
            "Подробнее смотри Главное Меню-разделы: БЕСПЛАТНЫЕ генерации и ЗАРАБОТАТЬ с Xena.\n"
            "6. Отправьте фото.\n"
            "7. Дождитесь окончания генерации (обычно, ожидание занимает 2-10 мин., но может затянуться, в зависимости от загруженности сервера).\n"
            "8. Получите готовый AI-порно ролик с участием девушки с вашего фото!\n"
            "При возникновении любых вопросов или трудностей, пишите в поддержку.\n"
            "ВНИМАНИЕ\n"
            "Нажимая старт, вы соглашаетесь с правилами использования бота, а именно:\n"
            "а) Запрещается использовать бот для создания с целью РАСПРОСТРАНЕНИЯ контента, нарушающего законодательство или права третьих лиц, включая:\n"
            "-незаконный контент\n"
            "-материалы сексуального характера с несовершеннолетними\n"
            "-экстремизм, терроризм, разжигание ненависти\n"
            "-мошенничество и введение в заблуждение\n"
            "-клевету и нарушение репутации\n"
            "-незаконное использование чужих изображений, лиц или авторских материалов\n"
            "-материалы, содержащие лгбт\n"
            "б) Бот является автоматическим инструментом генерации контента. Ответственность за использование результатов несёт пользователь.",
            reply_markup=understood_menu("instruction_understood")
        )
        return

    if action in ["intro_understood", "instruction_understood"]:
        try:
            await query.message.delete()
        except Exception:
            pass

        set_instruction_seen(user_id)
        await send_main_menu_message(query.message)
        return

    if action == "main_menu" or action == "start":
        try:
            await query.message.delete()
        except Exception:
            pass

        await send_main_menu_message(query.message)
        return

    if action == "back_to_video_menu_no_delete":
        await query.message.chat.send_photo(
            photo=DEMO_MENU_PHOTO,
            caption="🎬 Выбери, что мне сделать с фото:",
            reply_markup=video_inline_menu()
        )
        return
        
    if action == "video_menu":
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_photo(
            photo=DEMO_MENU_PHOTO,
            caption="🎬 Выбери, что мне сделать с фото:",
            reply_markup=video_inline_menu()
        )
        return

    if action.startswith("style_"):
        style_id = action.replace("style_", "")
        style = STYLE_DATA[style_id]

        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_video(
            video=style["video"],
            caption=f"🎬 Демонстрация: {style['title']}",
            reply_markup=style_action_menu(style_id)
        )
        return

    if action == "free_style":
        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_photo(
            photo=FREE_STYLE_PHOTO,
            caption=(
                "🎨 Свободный стиль\n\n"
                "Опиши своими словами, что ты хочешь увидеть в ролике.\n\n"
                "⚠️ Чем подробнее описание, тем лучше результат."
            ),
            reply_markup=free_style_action_menu()
        )
        return

    if action.startswith("animate_style_"):
        style_id = action.replace("animate_style_", "")
        style = STYLE_DATA[style_id]

        _, paid_credits = get_user(user_id)

        if paid_credits < VIDEO_PRICES["5"]:
            await query.message.reply_text(
                "💳 Недостаточно средств для генерации.\n\n"
                "👇 Пополни баланс или получи бесплатные генерации 👇",
                reply_markup=not_enough_balance_menu()
            )
            return

        user_states[user_id] = {
            "mode": "preset",
            "style_id": style_id,
            "prompt": style["prompt"]
        }

        print(f"STYLE_SELECTED: {user_id} -> {style_id}", flush=True)
        print(f"USER_STATE_AFTER_SELECT: {user_states.get(user_id)}", flush=True)

        await query.message.reply_text(
            "📸 Отправь фото для оживления.\n\n"
            "<b>Важно:</b> для лучшего результата старайся отправлять фото, как на примере!",
            parse_mode="HTML"
        )
        return

    if action == "animate_free_style":
        _, paid_credits = get_user(user_id)

        if paid_credits < VIDEO_PRICES["5"]:
            await query.message.reply_text(
                "💳 Недостаточно средств для генерации.\n\n"
                "👇 Пополни баланс или получи бесплатные генерации 👇",
                reply_markup=not_enough_balance_menu()
            )
            return

        user_states[user_id] = {
            "mode": "free_style_wait_photo"
        }

        await query.message.reply_text(
            "📸 Отправь фото для оживления.\n\n"
            "<b>Важно:</b> для лучшего результата старайся отправлять фото, как на примере!",
            parse_mode="HTML"
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
        _, paid_credits = get_user(user_id)

        await query.message.reply_text(
            f"✅ Оплата получена!\n\n"
            f"Баланс пополнен на {amount} ₽.\n"
            f"Текущий баланс: {paid_credits} ₽."
        )
        return

    if action == "buy":
        await query.message.reply_text(
            "💳 Пополнение баланса\n\n"
            "Стоимость генераций:\n"
            "🎬 5 секунд — 98 ₽\n"
            "🎬 10 секунд — 147 ₽\n\n"
            "Выбери сумму пополнения:",
            reply_markup=topup_menu()
        )
        return

    if action == "ref":
        await query.message.reply_text(
            f"🎁 БЕСПЛАТНЫЕ генерации\n\n"
            f"Твоя ссылка:\n"
            f"https://t.me/Xena18Bot?start=free_{user_id}"
        )
        return

    if action == "earn":
        await query.message.reply_text(
            f"💸 ЗАРАБОТАТЬ с Xena\n\n"
            f"Твоя ссылка:\n"
            f"https://t.me/Xena18Bot?start=money_{user_id}"
        )
        return

    if action == "partner_profile":
        partner_balance = get_partner_balance(user_id)

        await query.message.reply_text(
            f"💼 Кабинет партнёра\n\n"
            f"Баланс к выплате: {partner_balance} ₽\n\n"
            f"Когда хочешь получить выплату — напиши в поддержку."
        )
        return

    if action == "help":
        await query.message.reply_text(
            "📘 Инструкция:\n\n"
            "Бот Xena создает 18+ видео с участием человека, фото которого вы отправите.\n"
            "1. Нажмите СТАРТ.\n"
            "2. В Главном Меню нажмите кнопку ПОРНО С ДЕВУШКОЙ.\n"
            "3. Выберите, что хотите увидеть в ролике.\n"
            "Можете выбрать из списка, либо создать генерацию в СВОБОДНОМ СТИЛЕ.\n"
            "СВОБОДНЫЙ СТИЛЬ-режим, в котором вы сами пишете, что хотите видеть на экране.\n"
            "Если выбрали СВОБОДНЫЙ СТИЛЬ, очень подробно и детально составляйте описание, иначе нейросеть может вас не правильно понять, и результат не оправдает ожиданий.\n"
            "4. Выберите длительность видео.\n"
            "На данный момент доступна длительность 5 и 10 секунд. При большем времени, нейросеть начинает искажать картинку.\n"
            "Информацию о создании более долгих и качественных роликов вы найдете в нашем закрытом телеграмм-канале. Ссылка в Главном Меню.\n"
            "5. Если на вашем балансе не хватает средств для генирации, нажмите ПОПОЛНИТЬ БАЛАНС в Главном Меню.\n"
            "Так же доступна партнерская программа: за каждого, приглашенного пользователя вы можете получать ДЕНЬГИ или БЕСПЛАТНЫЕ генерации, на выбор!\n"
            "Подробнее смотри Главное Меню-разделы: БЕСПЛАТНЫЕ генерации и ЗАРАБОТАТЬ с Xena.\n"
            "6. Отправьте фото.\n"
            "7. Дождитесь окончания генерации (обычно, ожидание занимает 2-10 мин., но может затянуться, в зависимости от загруженности сервера).\n"
            "8. Получите готовый AI-порно ролик с участием девушки с вашего фото!\n"
            "При возникновении любых вопросов или трудностей, пишите в поддержку.\n"
            "ВНИМАНИЕ\n"
            "Нажимая старт, вы соглашаетесь с правилами использования бота, а именно:\n"
            "а) Запрещается использовать бот для создания с целью РАСПРОСТРАНЕНИЯ контента, нарушающего законодательство или права третьих лиц, включая:\n"
            "-незаконный контент\n"
            "-материалы сексуального характера с несовершеннолетними\n"
            "-экстремизм, терроризм, разжигание ненависти\n"
            "-мошенничество и введение в заблуждение\n"
            "-клевету и нарушение репутации\n"
            "-незаконное использование чужих изображений, лиц или авторских материалов\n"
            "-материалы, содержащие лгбт\n"
            "б) Бот является автоматическим инструментом генерации контента. Ответственность за использование результатов несёт пользователь."
        )
        return

    if action == "profile":
        free_used, paid_credits = get_user(user_id)

        await query.message.reply_text(
            f"👤 Твой баланс:\n\n"
            f"Баланс: {paid_credits} ₽\n\n"
            f"Стоимость:\n"
            f"5 секунд — {VIDEO_PRICES['5']} ₽\n"
            f"10 секунд — {VIDEO_PRICES['10']} ₽"
        )
        return
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_username(user_id, update.message.from_user.username)
    get_user(user_id)

    if context.args:
        ref_code = context.args[0]

        if ref_code.startswith("free_"):
            referrer_id = int(ref_code.replace("free_", ""))
            set_referrer(user_id, referrer_id, "free")

        if ref_code.startswith("money_"):
            referrer_id = int(ref_code.replace("money_", ""))
            set_referrer(user_id, referrer_id, "money")

    if has_seen_instruction(user_id):
        await send_main_menu_message(update.message)
        return

    await update.message.reply_photo(
        photo=INSTRUCTION_PHOTO,
        caption="📘 Перед тем как начать, ознакомьтесь с инструкцией!",
        reply_markup=first_intro_menu()
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    print(f"PHOTO_RECEIVED from user {user_id}", flush=True)
    print(f"USER_STATE: {user_states.get(user_id)}", flush=True)

    free_used, paid_credits = get_user(user_id)

    if user_id not in user_states or user_states[user_id].get("mode") not in ["preset", "free_style_wait_photo"]:
        await update.message.reply_photo(
            photo=DEMO_MENU_PHOTO,
            caption="🎬 Выбери, что мне сделать с фото:",
            reply_markup=video_inline_menu()
        )
        return

    if paid_credits < VIDEO_PRICES["5"]:
        await update.message.reply_text(
            "💳 Недостаточно средств для генерации.\n\n"
            "👇 Пополни баланс или получи бесплатные генерации 👇",
            reply_markup=not_enough_balance_menu()
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = MEDIA_DIR / f"{user_id}_{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(image_path))

    user_states[user_id]["image_path"] = str(image_path)

    if paid_credits < VIDEO_PRICES["10"]:
        await update.message.reply_text(
            "✅ Фото получил.\n\n"
            "⏱ Выбери длительность видео:",
            reply_markup=duration_menu_5_only()
        )
        return

    await update.message.reply_text(
        "✅ Фото получил.\n\n"
        "⏱ Выбери длительность видео:",
        reply_markup=duration_menu()
    )

async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    free_used, paid_credits = get_user(user_id)

    image_path = user_states[user_id]["image_path"]
    duration = user_states[user_id]["duration"]
    video_cost = VIDEO_PRICES[duration]

    if paid_credits < video_cost:
        await update.message.reply_text(
            f"💰 Баланс: {paid_credits} ₽\n\n"
            "💳 Недостаточно средств для генерации.\n\n"
            "👇 Пополни баланс или получи бесплатные генерации 👇",
            reply_markup=not_enough_balance_menu()
        )
        return

    if user_states[user_id].get("mode") == "preset":
        prompt = user_states[user_id]["prompt"]
    else:
        prompt = user_states[user_id]["prompt"]

    await update.message.reply_text(
        "🎥 Запускаю нейросеть.\n\n"
        "Генерация видео может занять 2–10 минут. Не отправляй новую картинку, пока я работаю."
    )

    try:
        print("GENERATION: upload image", flush=True)
        image_url = upload_image_to_kie(image_path)

        print("GENERATION: create Kie task", flush=True)
        task_id = create_kie_video_task(image_url, prompt, duration)

        print(f"GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)

        save_active_generation(user_id, task_id, video_cost, duration)

        decrement_paid_credit(user_id, video_cost)
        add_generation_stats(user_id, video_cost)
        apply_referral_bonus(user_id, duration)

        print(f"GENERATION: wait result {task_id}", flush=True)
        video_url = wait_kie_video_result(task_id)

        print(f"GENERATION: download video {video_url}", flush=True)
        video_path = download_video(video_url, user_id)

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
                    reply_markup=after_generation_menu()
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
            f"💰 Баланс: {paid_credits_after} ₽"
        )

        if paid_credits_after <= 0:
            await update.message.reply_text(
                "💳 Недостаточно средств для следующей генерации.\n\n"
                "👇 Пополни баланс или получи бесплатные генерации 👇",
                reply_markup=not_enough_balance_menu()
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
                "Попробуй ещё раз через 1–2 минуты или выбери другой стиль."
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка генерации.\n\n"
                "Если проблема повторяется — напиши в поддержку:\n"
                "https://t.me/Vlad101ss",
                disable_web_page_preview=True
            )

    user_states.pop(user_id, None)
    
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
            f"3. Нажми «✅ Проверить оплату»\n"
            f"Если не открывается ссылка, отключите VPN на время оплаты",
            reply_markup=keyboard
        )
        return

    if prompt == "🎁 БЕСПЛАТНЫЕ генерации: /ref":
        await update.message.reply_text("🎁 Реферальную программу подключим следующим этапом.")
        return

    if prompt == "🏠 Главное меню":
        await menu(update, context)
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

        if user_states[user_id].get("mode") == "preset":
            await start_generation(update, context, user_id)
            return

        await update.message.reply_text(
            "✍️ Теперь отправь описание видео.\n\n"
            "Чем подробнее описание, тем лучше результат."
        )
        return

    if user_id not in user_states:
        await update.message.reply_photo(
            photo=DEMO_MENU_PHOTO,
            caption="🎬 Выбери, что мне сделать с фото:",
            reply_markup=video_inline_menu()
        )
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

    if paid_credits < video_cost:
        await update.message.reply_text(
            f"💰 Баланс: {paid_credits} ₽\n\n"
            "💳 Недостаточно средств для генерации.\n\n"
            "👇 Пополни баланс или получи бесплатные генерации 👇",
            reply_markup=not_enough_balance_menu()
        )
        return

    user_states[user_id]["prompt"] = prompt

    print("FREE_STYLE_START_GENERATION", flush=True)

    await start_generation(update, context, user_id)
    return

    await update.message.reply_text(
        "🎥 Запускаю нейросеть.\n\n"
        "Генерация видео может занять 2–10 минут. Не отправляй новую картинку, пока я работаю."
    )

    try:
        print("GENERATION: upload image", flush=True)
        image_url = upload_image_to_kie(image_path)

        print("GENERATION: create Kie task", flush=True)
        task_id = create_kie_video_task(image_url, prompt, duration)

        print(f"GENERATION: Kie accepted task {task_id}. Charging user.", flush=True)

        save_active_generation(user_id, task_id, video_cost, duration)

        decrement_paid_credit(user_id, video_cost)
        add_generation_stats(user_id, video_cost)
        apply_referral_bonus(user_id, duration)

        print(f"GENERATION: wait result {task_id}", flush=True)
        video_url = wait_kie_video_result(task_id)

        print(f"GENERATION: download video {video_url}", flush=True)
        video_path = download_video(video_url, user_id)

        finish_active_generation(task_id)

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
    user_states.pop(user_id, None)
    payload = update.message.successful_payment.invoice_payload

    if payload.startswith("topup_"):
        amount = int(payload.replace("topup_", ""))
        add_paid_credit(user_id, amount)

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
    .post_init(post_init)
    .build()
)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("give", give))
    app.add_handler(CommandHandler("giveuser", giveuser))
    app.add_handler(CommandHandler("statsuser", statsuser))
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
