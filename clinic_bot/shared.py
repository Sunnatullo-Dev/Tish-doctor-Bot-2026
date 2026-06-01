"""Shared runtime objects, configuration, and in-memory state for the clinic bot."""

import logging
import math
import uuid
import random
import json
import os
import io
import csv
import threading
from datetime import datetime, date, time, timedelta
import pytz

from telebot import ExceptionHandler, TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------- CONFIG ----------------
def load_env_file(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

TOKEN = os.getenv("BOT_TOKEN", "")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it to .env or environment variables.")

ADMIN_ID = int(os.getenv("ADMIN_ID", "7566796449"))
BOT_TZ = "Asia/Tashkent"
DATA_FILE = "clinic_bot_data_final.json"
BOT_WORKER_THREADS = int(os.getenv("BOT_WORKER_THREADS", "32"))

STICKER_FILE_IDS = []  # optional list of sticker file_ids

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- INIT ----------------
class LoggingExceptionHandler(ExceptionHandler):
    def handle(self, exception):
        logger.error(
            "Unhandled bot worker exception",
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        return True

data_lock = threading.RLock()
bot = TeleBot(
    TOKEN,
    parse_mode="HTML",
    threaded=True,
    num_threads=BOT_WORKER_THREADS,
    exception_handler=LoggingExceptionHandler(),
)
tz = pytz.timezone(BOT_TZ)
scheduler = BackgroundScheduler(timezone=tz)
scheduler.start()

# ---------------- DEFAULT DATA (single clinic) ----------------
clinics = [
    {
        "id": "c1",
        "name": "Smile Concept",
        "address": "Yunusabad tumani, Oloy Bozori, 64, Toshkent",
        "lat": 41.320674, "lon": 69.283426, "region": "Toshkent",
        "manager_phone": "+998781138300",
        "doctors": [
            {
                "id": "d_sun",
                "name": "Sunnatulla",
                "phone": "+998781138300",
                "experience": "5 yil",
                "price": "200000 so'm",
                "telegram_id": None,
                "rating_sum": 0,
                "rating_count": 0,
                "reviews": [],
                "photo_file_id": None
            }
        ]
    }
]

# ---------------- RUNTIME STRUCTURES ----------------
user_state = {}             # chat_id -> {"step": str, "data": {...}}
appointments = {}           # appt_id -> appointment dict
pending_doctors = {}        # pend_id -> dict
users = set()               # set of user ids for broadcast
users_info = {}             # "uid" -> {"first_start": iso, "starts": int}
admins = set([ADMIN_ID])    # admin ids
admin_history = []          # list of admin add/remove records
diagnosis_requests = {}     # req_id -> dict (ticket system)
mandatory_channels = {}     # channel_key -> channel config/status dict
channel_user_stats = {}     # user_id(str) -> channel_key -> latest membership/check data
# each diagnosis_requests[req_id] includes: notify_msgs: list of {"admin_id", "chat_id", "message_id"}
active_diag_chats = {}      # user_chat -> admin_id (legacy admin-user chat)
admin_active_diag = {}      # admin_id -> user_chat

# Doctor <-> user diagnostic chat (new)
active_doctor_chats = {}    # user_chat -> doctor_telegram_id
doctor_active_chats = {}    # doctor_telegram_id -> user_chat
diag_chat_mode = {}         # user_chat -> "sms" | "call"
diag_chat_req = {}          # user_chat -> req_id

admin_ad_state = {}         # admin_id -> "await_ad_text"
admin_add_state = {}        # admin_id -> "await_admin_id"

# locale arrays
UZ_MONTHS = ['yanvar','fevral','mart','aprel','may','iyun','iyul','avgust','sentyabr','oktyabr','noyabr','dekabr']
UZ_WEEK = ['dushanba','seshanba','chorshanba','payshanba','juma','shanba','yakshanba']

# ---------------- PERSISTENCE STATUS ----------------
data_loaded_successfully = False
