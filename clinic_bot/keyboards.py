from clinic_bot.shared import *
from clinic_bot.helpers import is_today_date, mk

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

def time_buttons(chosen_date: date = None):
    kb = InlineKeyboardMarkup()
    row = []
    times = []
    for h in range(9, 19):
        times.append(f"{h:02d}:00")
        times.append(f"{h:02d}:30")
    now_dt = datetime.now(tz)
    cutoff = None
    if chosen_date is not None and is_today_date(chosen_date):
        cutoff = now_dt.time()
    for t in times:
        hh, mm = map(int, t.split(":"))
        if cutoff and time(hh, mm) <= cutoff:
            continue
        btn = InlineKeyboardButton(t, callback_data=f"time|{t}")
        row.append(btn)
        if len(row) == 3:
            kb.row(*row); row = []
    if row: kb.row(*row)
    kb.row(mk("↩️ Orqaga", "back|to_date"))
    return kb
