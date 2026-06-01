import re

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


_PHONE_RE = re.compile(r"^\+998\d{9}$")


def normalize_phone(raw):
    """Try to normalize a UZ phone to +998XXXXXXXXX. Return None if invalid."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if digits.startswith("998") and len(digits) == 12:
        candidate = "+" + digits
    elif len(digits) == 9:
        candidate = "+998" + digits
    elif digits.startswith("8") and len(digits) == 10:
        candidate = "+99" + digits
    else:
        candidate = "+" + digits if not raw.startswith("+") else raw
    return candidate if _PHONE_RE.match(candidate) else None


def is_slot_taken(doctor_id, dt, exclude_appt_id=None):
    """Check if a given doctor already has an active appointment at this datetime."""
    if not doctor_id or not dt:
        return False
    blocking_statuses = {
        'pending', 'accepted', 'accepted_by_doctor',
        'rescheduled_by_admin', 'rescheduled_by_patient', 'rescheduled_by_doctor',
        'reschedule_requested',
    }
    for appt_id, appt in appointments.items():
        if exclude_appt_id and appt_id == exclude_appt_id:
            continue
        if appt.get('status') not in blocking_statuses:
            continue
        doc = appt.get('doctor_obj')
        a_doc_id = (doc.get('id') if doc else None) or appt.get('doctor_id')
        if a_doc_id != doctor_id:
            continue
        appt_dt = appt.get('datetime')
        if not appt_dt:
            continue
        if appt_dt == dt:
            return True
    return False


def doctor_taken_slots(doctor_id, on_date):
    """Return a set of 'HH:MM' strings already booked for the doctor on a given date."""
    taken = set()
    if not doctor_id or not on_date:
        return taken
    blocking_statuses = {
        'pending', 'accepted', 'accepted_by_doctor',
        'rescheduled_by_admin', 'rescheduled_by_patient', 'rescheduled_by_doctor',
        'reschedule_requested',
    }
    for appt in appointments.values():
        if appt.get('status') not in blocking_statuses:
            continue
        doc = appt.get('doctor_obj')
        a_doc_id = (doc.get('id') if doc else None) or appt.get('doctor_id')
        if a_doc_id != doctor_id:
            continue
        appt_dt = appt.get('datetime')
        if not appt_dt or appt_dt.date() != on_date:
            continue
        taken.add(appt_dt.strftime("%H:%M"))
    return taken


def home_button():
    return InlineKeyboardButton("\ud83c\udfe0 Bosh menyu", callback_data="go_home")


def cancel_button():
    return InlineKeyboardButton("\u274c Bekor qilish", callback_data="cancel_flow")


def with_home_kb(extra_buttons=None):
    """Return InlineKeyboardMarkup with optional rows of buttons plus a Home button."""
    kb = InlineKeyboardMarkup()
    if extra_buttons:
        for row in extra_buttons:
            kb.row(*row)
    kb.row(home_button())
    return kb


def cancel_kb():
    kb = InlineKeyboardMarkup()
    kb.row(cancel_button())
    return kb

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
