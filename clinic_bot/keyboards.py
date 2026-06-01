from clinic_bot.shared import *
from clinic_bot.helpers import is_today_date, mk, doctor_taken_slots

# ---------------- UI builders ----------------
def date_label(d: date):
    label = f"{d.day} {UZ_MONTHS[d.month-1]}, {UZ_WEEK[d.weekday()]}"
    if is_today_date(d):
        return f"🌟 Bugun — {label}"
    return label

def date_buttons(days=14):
    today = datetime.now(tz).date()
    kb = InlineKeyboardMarkup()
    row = []
    for i in range(days):
        d = today + timedelta(days=i)
        label = date_label(d)
        row.append(InlineKeyboardButton(label, callback_data=f"date|{d.isoformat()}"))
        if len(row) == 2:
            kb.row(*row); row = []
    if row: kb.row(*row)
    kb.row(mk("↩️ Orqaga", "back|to_clinic"))
    return kb


def _doctor_hours(doctor):
    """Return (start_hour, start_min, end_hour, end_min) for the doctor's working window."""
    wh = (doctor or {}).get('working_hours') or {}
    def _parse(v, default):
        try:
            hh, mm = v.split(":")
            return int(hh), int(mm)
        except Exception:
            return default
    sh, sm = _parse(wh.get('start', '09:00'), (9, 0))
    eh, em = _parse(wh.get('end', '19:00'), (19, 0))
    return sh, sm, eh, em


def time_buttons(chosen_date: date = None, doctor=None, exclude_appt_id=None):
    kb = InlineKeyboardMarkup()
    row = []
    sh, sm, eh, em = _doctor_hours(doctor)
    times = []
    # 30-minute slots from start to end (exclusive end)
    cur_h, cur_m = sh, sm
    while (cur_h, cur_m) < (eh, em):
        times.append(f"{cur_h:02d}:{cur_m:02d}")
        cur_m += 30
        if cur_m >= 60:
            cur_m -= 60
            cur_h += 1
    now_dt = datetime.now(tz)
    cutoff = None
    if chosen_date is not None and is_today_date(chosen_date):
        cutoff = now_dt.time()
    taken = set()
    if doctor and chosen_date is not None:
        taken = doctor_taken_slots(doctor.get('id'), chosen_date)
    available_count = 0
    for t in times:
        hh, mm = map(int, t.split(":"))
        if cutoff and time(hh, mm) <= cutoff:
            continue
        if t in taken:
            continue
        btn = InlineKeyboardButton(t, callback_data=f"time|{t}")
        row.append(btn)
        available_count += 1
        if len(row) == 3:
            kb.row(*row); row = []
    if row: kb.row(*row)
    if available_count == 0:
        kb.row(mk("⛔ Bu kunga bo'sh vaqt yo'q", "noop"))
    kb.row(mk("↩️ Orqaga", "back|to_date"))
    return kb
