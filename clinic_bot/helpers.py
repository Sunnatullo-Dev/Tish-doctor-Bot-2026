from clinic_bot.shared import *

# ---------------- HELPERS ----------------
def _button_key(value):
    value = (value or "").replace("\ufe0f", "").replace("\u200d", "").strip()
    if not value:
        return ""
    parts = value.split(maxsplit=1)
    if len(parts) == 2 and not any(ch.isalnum() for ch in parts[0]):
        value = parts[1]
    return " ".join(value.casefold().split())

def button_matches(actual, expected):
    return _button_key(actual) == _button_key(expected)

def new_id(prefix="id"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def mk(text, cb): return InlineKeyboardButton(text, callback_data=cb)

def send_random_sticker(chat_id):
    if not STICKER_FILE_IDS:
        return
    try:
        bot.send_sticker(chat_id, random.choice(STICKER_FILE_IDS))
    except Exception:
        logger.exception("sticker send failed")

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c*1000

def find_clinic_by_id(cid):
    return next((c for c in clinics if c['id'] == cid), None)

def find_doctor_by_id(docid):
    for c in clinics:
        for d in c['doctors']:
            if d['id'] == docid:
                return d, c
    return None, None

def fmt_uz_date(d: date):
    return f"{d.year}-yil {d.day} {UZ_MONTHS[d.month-1]}, {UZ_WEEK[d.weekday()]}"

def fmt_datetime_readable(dt):
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return f"{fmt_uz_date(dt.date())}, {dt.strftime('%H:%M')}"

def is_today_date(d: date):
    return d == datetime.now(tz).date()

def get_doctor_rating(d):
    if d.get('rating_count',0) > 0:
        return d.get('rating_sum',0) / d.get('rating_count',1)
    return 0.0

def is_admin(uid: int) -> bool:
    return uid in admins

def clear_admin_states(uid: int):
    admin_ad_state.pop(uid, None)
    admin_add_state.pop(uid, None)
