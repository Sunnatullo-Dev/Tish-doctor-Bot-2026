from clinic_bot.shared import *
from clinic_bot.channel_gate import (
    add_mandatory_channel,
    channel_button_text,
    channel_stats_text,
    delete_mandatory_channel,
    refresh_channel_member_count,
    set_channel_enabled,
)
from clinic_bot.helpers import *
from clinic_bot.keyboards import date_buttons
from clinic_bot.storage import save_data

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except Exception:
    PANDAS_AVAILABLE = False

ACTIVE_APPT_STATUSES = {
    'pending',
    'accepted',
    'accepted_by_doctor',
    'reschedule_requested',
    'rescheduled_by_admin',
    'rescheduled_by_patient',
    'rescheduled_by_doctor',
}


def appointment_belongs_to_clinic(appt, clinic_id):
    clinic = appt.get('clinic')
    if clinic and clinic.get('id') == clinic_id:
        return True
    return appt.get('clinic_id') == clinic_id


def appointment_belongs_to_doctor(appt, doctor_id):
    doc = appt.get('doctor_obj')
    if doc and doc.get('id') == doctor_id:
        return True
    return appt.get('doctor_id') == doctor_id


def clinic_metrics(clinic_id):
    related = [a for a in appointments.values() if appointment_belongs_to_clinic(a, clinic_id)]
    now_dt = datetime.now(tz)
    upcoming = [a for a in related if a.get('datetime') and a['datetime'] >= now_dt and a.get('status') != 'cancelled']
    active = [a for a in related if a.get('status') in ACTIVE_APPT_STATUSES]
    cancelled = [a for a in related if a.get('status') == 'cancelled']
    return {
        "total": len(related),
        "active": len(active),
        "upcoming": len(upcoming),
        "cancelled": len(cancelled),
    }


def doctor_metrics(doctor_id):
    related = [a for a in appointments.values() if appointment_belongs_to_doctor(a, doctor_id)]
    now_dt = datetime.now(tz)
    upcoming = [a for a in related if a.get('datetime') and a['datetime'] >= now_dt and a.get('status') != 'cancelled']
    accepted = [a for a in related if a.get('status') in ('accepted', 'accepted_by_doctor')]
    cancelled = [a for a in related if a.get('status') == 'cancelled']
    return {
        "total": len(related),
        "accepted": len(accepted),
        "upcoming": len(upcoming),
        "cancelled": len(cancelled),
    }


def send_clinic_analysis(chat_id, clinic):
    m = clinic_metrics(clinic['id'])
    text = (
        f"🏥 <b>{clinic['name']}</b>\n"
        f"Manzil: {clinic.get('address', '-')}\n"
        f"Telefon: {clinic.get('manager_phone', '-')}\n"
        f"Davlat/region: {clinic.get('region', '-')}\n\n"
        f"Doktorlar: {len(clinic.get('doctors', []))}\n"
        f"Jami yozuvlar: {m['total']}\n"
        f"Faol yozuvlar: {m['active']}\n"
        f"Kelgusi yozuvlar: {m['upcoming']}\n"
        f"Bekor qilingan: {m['cancelled']}"
    )
    bot.send_message(chat_id, text, parse_mode="HTML")


def send_doctor_analysis(chat_id, clinic, doctor):
    m = doctor_metrics(doctor['id'])
    text = (
        f"👨‍⚕️ <b>{doctor['name']}</b>\n"
        f"Klinika: {clinic['name']}\n"
        f"Telefon: {doctor.get('phone', '-')}\n"
        f"Tajriba: {doctor.get('experience', '-')}\n"
        f"Narx: {doctor.get('price', '-')}\n"
        f"Telegram ID: {doctor.get('telegram_id') or '-'}\n"
        f"Reyting: {round(get_doctor_rating(doctor), 1)} ({doctor.get('rating_count', 0)} ta baho)\n"
        f"Sharhlar: {len(doctor.get('reviews', []))}\n\n"
        f"Jami yozuvlar: {m['total']}\n"
        f"Qabul qilingan: {m['accepted']}\n"
        f"Kelgusi yozuvlar: {m['upcoming']}\n"
        f"Bekor qilingan: {m['cancelled']}"
    )
    bot.send_message(chat_id, text, parse_mode="HTML")


def start_add_clinic(chat_id):
    user_state[chat_id] = {"step":"admin_add_clinic_name","data":{}}
    bot.send_message(chat_id, "Klinika nomini kiriting:")


def cancel_appointment_jobs(appt_id):
    for job_id in (f"rem_{appt_id}", f"rating_{appt_id}"):
        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        except Exception:
            logger.exception("failed to remove scheduled job %s", job_id)


def send_clinic_picker(chat_id, title, callback_prefix):
    kb = InlineKeyboardMarkup()
    if not clinics:
        bot.send_message(chat_id, "Klinikalar ro'yxati bo'sh.")
        return
    for clinic in clinics:
        kb.add(mk(f"{clinic['name']} — {len(clinic.get('doctors', []))} doktor", f"{callback_prefix}|{clinic['id']}"))
    bot.send_message(chat_id, title, reply_markup=kb)


def send_doctor_picker(chat_id, title, callback_prefix):
    kb = InlineKeyboardMarkup()
    found = False
    for clinic in clinics:
        for doctor in clinic.get('doctors', []):
            found = True
            kb.add(mk(f"{doctor['name']} — {clinic['name']}", f"{callback_prefix}|{clinic['id']}|{doctor['id']}"))
    if not found:
        bot.send_message(chat_id, "Doktorlar ro'yxati bo'sh.")
        return
    bot.send_message(chat_id, title, reply_markup=kb)


def start_add_doctor(chat_id, clinic_id):
    clinic = find_clinic_by_id(clinic_id)
    if not clinic:
        bot.send_message(chat_id, "Klinika topilmadi.")
        return
    user_state[chat_id] = {"step":"admin_add_doctor_name","data":{"clinic_id": clinic_id}}
    bot.send_message(chat_id, f"{clinic['name']} uchun doktor ismini kiriting:")


def send_channel_menu(chat_id):
    kb = InlineKeyboardMarkup()
    kb.row(mk("➕ Kanal qo'shish", "settings|channel_add"))
    kb.row(mk("📊 Kanallar va statistika", "settings|channel_list"))
    bot.send_message(chat_id, "Majburiy kanal boshqaruvi:", reply_markup=kb)


def send_channel_list(chat_id):
    if not mandatory_channels:
        bot.send_message(chat_id, "Majburiy kanallar ro'yxati bo'sh.")
        return
    for channel in mandatory_channels.values():
        refresh_channel_member_count(channel)
        kb = InlineKeyboardMarkup()
        kb.row(mk("📊 Statistika", f"settings|channel_stats|{channel['chat_id']}"), mk("👥 Foydalanuvchilar", f"settings|channel_users|{channel['chat_id']}"))
        if channel.get("enabled", True):
            kb.row(mk("⏸ Muzlatish", f"settings|channel_freeze|{channel['chat_id']}"))
        else:
            kb.row(mk("▶️ Faollashtirish", f"settings|channel_enable|{channel['chat_id']}"))
        kb.row(mk("🗑️ O'chirish", f"settings|channel_delete_ask|{channel['chat_id']}"))
        bot.send_message(chat_id, channel_button_text(channel), reply_markup=kb)
    save_data()

# ---------------- ADMIN PANEL & BROADCAST & EXPORT ----------------
@bot.message_handler(commands=['admin'])
def cmd_admin(m: types.Message):
    chat = m.chat.id
    if not is_admin(m.from_user.id):
        bot.send_message(chat, "❌ Siz admin emassiz.")
        return
    clear_admin_states(m.from_user.id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Statistika", "📅 Bugungi yozuvlar")
    kb.row("📒 Onlayn daftar", "⏰ Vaqt o'zgartirish so'rovlari")
    kb.row("🦷 Klinikalar", "👨‍⚕️ Doktorlar")
    kb.row("➕ Klinika qo'shish", "📁 Eksport Excel")
    kb.row("🛡️ Adminlar boshqaruvi", "⚙️ Sozlamalar")
    kb.row("🔎 Onlay tashhis", "📢 Reklama yuborish")
    kb.row("❌ Yopish")
    bot.send_message(chat, "🛠 <b>ADMIN PANEL</b>\nKerakli bo‘limni tanlang:", parse_mode="HTML", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "❌ Yopish")
def admin_close(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    clear_admin_states(m.from_user.id)
    bot.send_message(m.chat.id, "Admin panel yopildi.", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def admin_stats(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    total_appts = len(appointments)
    accepted = len([a for a in appointments.values() if a['status'] in ('accepted','accepted_by_doctor')])
    cancelled = len([a for a in appointments.values() if a['status'] == 'cancelled'])
    doctors_count = sum(len(c['doctors']) for c in clinics)
    clinics_count = len(clinics)
    total_users = len(users)
    cutoff = datetime.now(tz) - timedelta(days=30)
    new_in_30 = 0
    for uid_str, info in users_info.items():
        try:
            dt = datetime.fromisoformat(info.get('first_start'))
            if dt.tzinfo is None: dt = tz.localize(dt)
            if dt >= cutoff: new_in_30 += 1
        except Exception:
            pass
    admin_count = len(admins)
    text = (
        f"📊 <b>STATISTIKA</b>\n\n"
        f"🏥 Klinikalar: {clinics_count}\n"
        f"👨‍⚕️ Doktorlar: {doctors_count}\n\n"
        f"📅 Jami yozuvlar: {total_appts}\n"
        f"✅ Qabul qilingan: {accepted}\n"
        f"❌ Bekor qilingan: {cancelled}\n\n"
        f"👥 Foydalanuvchilar (jami): {total_users}\n"
        f"🆕 Oxirgi 30 kun: {new_in_30}\n\n"
        f"🛡️ Adminlar soni: {admin_count}\n"
        f"📜 Admin tarix: {len(admin_history)} yozuv"
    )
    bot.send_message(m.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📅 Bugungi yozuvlar")
def admin_today_appts(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    today = datetime.now(tz).date()
    today_appts = [a for a in appointments.values() if a.get('datetime') and a['datetime'].date() == today]
    if not today_appts:
        bot.send_message(m.chat.id, "Bugunga yozuvlar yo‘q."); return
    for a in sorted(today_appts, key=lambda x: x['datetime']):
        clinic = a.get('clinic'); doc = a.get('doctor_obj')
        text = (f"📌 <b>{a['id']}</b>\n"
                f"👤 {a['patient_name']} ({a['patient_phone']})\n"
                f"🏥 {clinic['name'] if clinic else '—'}\n"
                f"👨‍⚕️ {doc['name'] if doc else '—'}\n"
                f"⏰ {fmt_datetime_readable(a['datetime'])}\n"
                f"📍 {a['status']}")
        kb = InlineKeyboardMarkup()
        kb.row(mk("✅ Qabul qilish", f"admin|appt|accept|{a['id']}"), mk("❌ Bekor qilish", f"admin|appt|cancel|{a['id']}"))
        kb.row(mk("🕑 Vaqtni o'zgartirish", f"admin|appt|reschedule|{a['id']}"))
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📒 Onlayn daftar")
def admin_online_book(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    now_dt = datetime.now(tz)
    upcoming = [a for a in appointments.values() if a.get('datetime') and a['datetime'] >= now_dt]
    if not upcoming:
        bot.send_message(m.chat.id, "📒 Onlayn daftar bo‘sh (kelgusi yozuvlar yo‘q)."); return
    for a in sorted(upcoming, key=lambda x: x['datetime']):
        clinic = a.get('clinic'); doc = a.get('doctor_obj')
        text = (f"📌 <b>{a['id']}</b>\n"
                f"👤 {a['patient_name']} ({a['patient_phone']})\n"
                f"🏥 {clinic['name'] if clinic else '—'}\n"
                f"👨‍⚕️ {doc['name'] if doc else '—'}\n"
                f"⏰ {fmt_datetime_readable(a['datetime'])}\n"
                f"📍 {a.get('status')}")
        kb = InlineKeyboardMarkup()
        # since accepted ones are already processed, just keep time-change option
        kb.row(mk("🕑 Vaqtni o'zgartirish", f"admin|appt|reschedule|{a['id']}"))
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "⏰ Vaqt o'zgartirish so'rovlari")
def admin_reschedule_requests(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    reqs = [a for a in appointments.values() if a.get('status') == 'reschedule_requested']
    if not reqs:
        bot.send_message(m.chat.id, "⏰ Vaqt o'zgartirish uchun so'rovlar yo'q."); return
    for a in sorted(reqs, key=lambda x: x.get('created_at', datetime.now(tz))):
        clinic = a.get('clinic'); doc = a.get('doctor_obj')
        text = (f"🔁 <b>{a['id']}</b>\n"
                f"👤 {a['patient_name']} ({a['patient_phone']})\n"
                f"🏥 {clinic['name'] if clinic else '—'}\n"
                f"👨‍⚕️ {doc['name'] if doc else '—'}\n"
                f"⏰ Hozirgi vaqt: {fmt_datetime_readable(a.get('datetime'))}\n"
                f"📍 Status: {a.get('status')}")
        kb = InlineKeyboardMarkup()
        kb.row(mk("🕑 Reschedule (admin qilishi)", f"admin|appt|reschedule|{a['id']}"), mk("❌ Bekor qilish", f"admin|appt|cancel|{a['id']}"))
        bot.send_message(m.chat.id, text, parse_mode="HTML", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🦷 Klinikalar")
def admin_clinics(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    kb = InlineKeyboardMarkup()
    for c in clinics:
        kb.add(mk(f"{c['name']} — {len(c['doctors'])} doctor", f"admin|clinic|{c['id']}"))
    kb.add(mk("➕ Klinika qo'shish", "settings|add_clinic"))
    bot.send_message(m.chat.id, "🏥 Klinikalar ro'yxati:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|clinic|"))
def cb_admin_clinic(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    cid = call.data.split("|",2)[2]
    clinic = find_clinic_by_id(cid)
    if not clinic:
        bot.send_message(call.message.chat.id, "Klinika topilmadi."); return
    text = f"🏥 <b>{clinic['name']}</b>\n{clinic['address']}\n📞 {clinic['manager_phone']}\n\n<b>Doktorlar:</b>"
    kb = InlineKeyboardMarkup()
    if clinic['doctors']:
        for d in clinic['doctors']:
            kb.add(mk(f"{d['name']} — {d.get('experience','')}", f"admin|docview|{d['id']}|{clinic['id']}"))
    else:
        kb.add(mk("Hozircha doktorlar yo'q", "noop"))
    kb.row(mk("📊 Tahlil", f"settings|analyze_clinic_show|{clinic['id']}"), mk("➕ Doktor qo'shish", f"settings|add_doctor_clinic|{clinic['id']}"))
    kb.row(mk("🗑️ Klinikani o'chirish", f"settings|del_clinic_ask|{clinic['id']}"))
    bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|docview|"))
def cb_admin_docview(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    _, _, docid, cid = call.data.split("|")
    clinic = find_clinic_by_id(cid)
    if not clinic:
        bot.send_message(call.message.chat.id, "Klinika topilmadi."); return
    d = next((x for x in clinic['doctors'] if x['id']==docid), None)
    if not d:
        bot.send_message(call.message.chat.id, "Doctor topilmadi."); return
    text = (f"👨‍⚕️ <b>{d['name']}</b>\n"
            f"Tel: {d.get('phone','-')}\n"
            f"Tajriba: {d.get('experience','-')}\n"
            f"Narx: {d.get('price','-')}\n"
            f"Reyting: {round(get_doctor_rating(d),1)} ({d.get('rating_count',0)})")
    kb = InlineKeyboardMarkup()
    kb.row(mk("📊 Tahlil", f"settings|analyze_doctor_show|{clinic['id']}|{d['id']}"))
    if d.get('telegram_id'):
        kb.row(mk("➕ Doktorga admin bering", f"admin|promote_doc|{d['telegram_id']}"))
    kb.row(mk("🗑️ Doktorni o'chirish", f"settings|del_doctor_ask|{clinic['id']}|{d['id']}"))
    bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|promote_doc|"))
def cb_promote_doc(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    _,_,_,tg_id = call.data.split("|")
    try:
        tg_id_int = int(tg_id)
        admins.add(tg_id_int)
        admin_history.append({"added_by": call.from_user.id, "new_admin": tg_id_int, "ts": datetime.now(tz).isoformat()})
        bot.send_message(call.message.chat.id, f"{tg_id_int} endi adminlar ro'yxatida.")
        save_data()
    except Exception:
        bot.send_message(call.message.chat.id, "ID noto'g'ri formatda.")

@bot.message_handler(func=lambda m: m.text == "👨‍⚕️ Doktorlar")
def admin_doctors(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    kb = InlineKeyboardMarkup()
    all_docs = []
    for c in clinics:
        for d in c['doctors']:
            all_docs.append((d,c))
    if not all_docs:
        bot.send_message(m.chat.id, "Doktorlar ro'yxati bo'sh."); return
    for d,c in all_docs:
        kb.add(mk(f"{d['name']} — {c['name']}", f"admin|docview|{d['id']}|{c['id']}"))
    bot.send_message(m.chat.id, "👨‍⚕️ Barcha doktorlar:", reply_markup=kb)

# EXPORT Excel/CSV
@bot.message_handler(func=lambda m: m.text == "📁 Eksport Excel")
def admin_export_excel(m: types.Message):
    if not is_admin(m.from_user.id): return
    clear_admin_states(m.from_user.id)
    users_rows = []
    for uid_str, info in users_info.items():
        uid = int(uid_str)
        user_appts = [a for a in appointments.values() if a.get('patient_chat') == uid]
        appt_count = len(user_appts)
        appt_lines = []
        for a in sorted(user_appts, key=lambda x: x.get('datetime') or datetime.now(tz)):
            appt_lines.append(f"{a.get('id')} | {fmt_datetime_readable(a.get('datetime'))} | {a.get('status')}")
        users_rows.append({"user_id": uid, "first_start": info.get('first_start'), "starts": info.get('starts',0), "appt_count": appt_count, "appointments": "\n".join(appt_lines)})
    appt_rows = []
    for a in appointments.values():
        appt_rows.append({"id": a.get('id'), "user_chat": a.get('patient_chat'), "name": a.get('patient_name'), "phone": a.get('patient_phone'), "clinic": a.get('clinic', {}).get('name') if a.get('clinic') else None, "doctor": a.get('doctor_obj', {}).get('name') if a.get('doctor_obj') else None, "datetime": a.get('datetime').isoformat() if isinstance(a.get('datetime'), datetime) else None, "status": a.get('status')})
    admin_hist_rows = admin_history.copy()
    stats = {"total_users": len(users), "total_appts": len(appointments), "total_admins": len(admins), "timestamp": datetime.now(tz).isoformat()}
    if PANDAS_AVAILABLE:
        try:
            writer_buf = io.BytesIO()
            with pd.ExcelWriter(writer_buf, engine='openpyxl') as writer:
                pd.DataFrame(users_rows).to_excel(writer, sheet_name='users', index=False)
                pd.DataFrame(appt_rows).to_excel(writer, sheet_name='appointments', index=False)
                pd.DataFrame(admin_hist_rows).to_excel(writer, sheet_name='admin_history', index=False)
                pd.DataFrame([stats]).to_excel(writer, sheet_name='stats', index=False)
            writer_buf.seek(0)
            bot.send_document(m.chat.id, ("clinic_export.xlsx", writer_buf))
        except Exception:
            logger.exception("excel export failed"); bot.send_message(m.chat.id, "Excel yaratishda xatolik yuz berdi.")
    else:
        try:
            buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=["user_id","first_start","starts","appt_count","appointments"]); w.writeheader()
            for r in users_rows: w.writerow(r)
            bot.send_document(m.chat.id, ("users_export.csv", io.BytesIO(buf.getvalue().encode('utf-8'))))
            buf2 = io.StringIO(); w2 = csv.DictWriter(buf2, fieldnames=["id","user_chat","name","phone","clinic","doctor","datetime","status"]); w2.writeheader()
            for r in appt_rows: w2.writerow(r)
            bot.send_document(m.chat.id, ("appts_export.csv", io.BytesIO(buf2.getvalue().encode('utf-8'))))
            if admin_hist_rows:
                buf3 = io.StringIO()
                keys = admin_hist_rows[0].keys()
                w3 = csv.DictWriter(buf3, fieldnames=list(keys)); w3.writeheader()
                for r in admin_hist_rows: w3.writerow(r)
                bot.send_document(m.chat.id, ("admin_history.csv", io.BytesIO(buf3.getvalue().encode('utf-8'))))
            bot.send_message(m.chat.id, f"Stats:\n{json.dumps(stats, ensure_ascii=False, indent=2)}")
        except Exception:
            logger.exception("csv export failed"); bot.send_message(m.chat.id, "CSV yaratishda xatolik yuz berdi.")

# ---- Klinika qo'shish ----
@bot.message_handler(func=lambda m: m.text == "➕ Klinika qo'shish")
def admin_add_clinic_start(m: types.Message):
    if not is_admin(m.from_user.id): return
    start_add_clinic(m.from_user.id)

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_clinic_name")
def admin_add_clinic_name(m: types.Message):
    data = user_state[m.chat.id]['data']; data['name'] = m.text.strip(); user_state[m.chat.id]['step'] = "admin_add_clinic_address"; bot.send_message(m.chat.id, "Klinika manzilini kiriting:")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_clinic_address")
def admin_add_clinic_address(m: types.Message):
    data = user_state[m.chat.id]['data']; data['address'] = m.text.strip(); user_state[m.chat.id]['step'] = "admin_add_clinic_phone"; bot.send_message(m.chat.id, "Klinika telefon raqamini kiriting (masalan +998...):")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_clinic_phone")
def admin_add_clinic_phone(m: types.Message):
    data = user_state[m.chat.id]['data']; data['phone'] = m.text.strip(); cid = new_id("c")
    new_clinic = {"id": cid, "name": data['name'], "address": data['address'], "lat": 0.0, "lon": 0.0, "region": "Unknown", "manager_phone": data['phone'], "doctors": []}
    with data_lock:
        clinics.append(new_clinic)
    save_data(); bot.send_message(m.chat.id, f"✅ Klinika qo'shildi: {data['name']}\nId: {cid}"); user_state.pop(m.chat.id, None)

# ---- Doktor qo'shish (admin orqali) ----
@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_doctor_name")
def admin_add_doctor_name(m: types.Message):
    data = user_state[m.chat.id]['data']
    data['name'] = m.text.strip()
    user_state[m.chat.id]['step'] = "admin_add_doctor_phone"
    bot.send_message(m.chat.id, "Doktor telefon raqamini kiriting:")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_doctor_phone")
def admin_add_doctor_phone(m: types.Message):
    data = user_state[m.chat.id]['data']
    data['phone'] = m.text.strip()
    user_state[m.chat.id]['step'] = "admin_add_doctor_experience"
    bot.send_message(m.chat.id, "Doktor tajribasini kiriting (masalan: 5 yil):")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_doctor_experience")
def admin_add_doctor_experience(m: types.Message):
    data = user_state[m.chat.id]['data']
    data['experience'] = m.text.strip()
    user_state[m.chat.id]['step'] = "admin_add_doctor_price"
    bot.send_message(m.chat.id, "Qabul narxini kiriting (masalan: 200000 so'm yoki kelishiladi):")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_doctor_price")
def admin_add_doctor_price(m: types.Message):
    data = user_state[m.chat.id]['data']
    data['price'] = m.text.strip()
    user_state[m.chat.id]['step'] = "admin_add_doctor_telegram"
    bot.send_message(m.chat.id, "Doktor Telegram ID sini kiriting yoki o'tkazish uchun '-' yuboring:")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "admin_add_doctor_telegram")
def admin_add_doctor_telegram(m: types.Message):
    data = user_state[m.chat.id]['data']
    raw_tg = m.text.strip()
    telegram_id = None
    if raw_tg not in ("-", "yo'q", "yoq", "skip", "o'tkazish", "otkazish"):
        try:
            telegram_id = int(raw_tg)
        except ValueError:
            bot.send_message(m.chat.id, "Telegram ID raqam bo'lishi kerak. Qayta kiriting yoki '-' yuboring:")
            return
    clinic = find_clinic_by_id(data.get('clinic_id'))
    if not clinic:
        bot.send_message(m.chat.id, "Klinika topilmadi. Jarayon bekor qilindi.")
        user_state.pop(m.chat.id, None)
        return
    new_doc = {
        "id": new_id("doc"),
        "name": data.get('name'),
        "phone": data.get('phone'),
        "experience": data.get('experience', '-'),
        "price": data.get('price', 'kelishiladi'),
        "telegram_id": telegram_id,
        "rating_sum": 0,
        "rating_count": 0,
        "reviews": [],
        "photo_file_id": None,
    }
    with data_lock:
        clinic.setdefault('doctors', []).append(new_doc)
    save_data()
    user_state.pop(m.chat.id, None)
    bot.send_message(m.chat.id, f"✅ Doktor qo'shildi: {new_doc['name']}\nKlinika: {clinic['name']}\nID: {new_doc['id']}")

# ---- Adminlar boshqaruvi ----
@bot.message_handler(func=lambda m: m.text == "🛡️ Adminlar boshqaruvi")
def admin_manage_menu(m: types.Message):
    if not is_admin(m.from_user.id): return
    kb = InlineKeyboardMarkup()
    kb.row(mk("➕ Admin qo'shish", "admin|manage|add"), mk("➖ Adminni o'chirish", "admin|manage|remove"))
    bot.send_message(m.chat.id, "Adminlarni boshqarish:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|manage|"))
def cb_admin_manage(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    action = call.data.split("|")[2]
    if action == "add":
        admin_add_state[call.from_user.id] = "await_admin_id"; bot.send_message(call.from_user.id, "Yangi admin telegram ID sini yuboring yoki contact yuboring:")
    elif action == "remove":
        kb = InlineKeyboardMarkup()
        for a in sorted(admins):
            kb.add(mk(f"{a}", f"admin|remove_confirm|{a}"))
        bot.send_message(call.from_user.id, "O'chirish uchun admin ID ni tanlang:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|remove_confirm|"))
def cb_admin_remove_confirm(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    _,_,_,aid = call.data.split("|")
    try:
        aid_int = int(aid)
        if aid_int in admins:
            admins.remove(aid_int)
            admin_history.append({"removed_by": call.from_user.id, "removed_admin": aid_int, "ts": datetime.now(tz).isoformat()})
            save_data(); bot.send_message(call.from_user.id, f"✅ Admin {aid_int} o'chirildi.")
        else:
            bot.send_message(call.from_user.id, "Admin topilmadi.")
    except Exception:
        bot.send_message(call.from_user.id, "ID noto'g'ri formatda.")

@bot.message_handler(func=lambda m: m.from_user.id in admin_add_state and admin_add_state.get(m.from_user.id) == "await_admin_id", content_types=['text','contact'])
def admin_add_receive(m: types.Message):
    admin_add_state.pop(m.from_user.id, None)
    if m.content_type == "contact" and m.contact.user_id:
        new_admin = m.contact.user_id
    else:
        try: new_admin = int(m.text.strip())
        except:
            bot.send_message(m.chat.id, "ID noto'g'ri. Bekor qilindi."); return
    admins.add(new_admin)
    admin_history.append({"added_by": m.from_user.id, "new_admin": new_admin, "ts": datetime.now(tz).isoformat()})
    save_data(); bot.send_message(m.chat.id, f"✅ {new_admin} adminlarga qo'shildi.")

# ---- Sozlamalar (majburiy kanal, o'chirish) ----
@bot.message_handler(func=lambda m: m.text == "⚙️ Sozlamalar")
def admin_settings(m: types.Message):
    if not is_admin(m.from_user.id): return
    kb = InlineKeyboardMarkup()
    kb.row(mk("📌 Majburiy kanal o'rnatish", "settings|channel"))
    kb.row(mk("➕ Klinika qo'shish", "settings|add_clinic"), mk("➕ Doktor qo'shish", "settings|add_doctor"))
    kb.row(mk("📊 Klinika tahlili", "settings|analyze_clinic"), mk("📊 Doktor tahlili", "settings|analyze_doctor"))
    kb.row(mk("🗑️ Klinika o'chirish", "settings|del_clinic"), mk("🗑️ Doktor o'chirish", "settings|del_doctor"))
    bot.send_message(m.chat.id, "Sozlamalar va boshqaruv:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in (
    "settings|channel",
    "settings|add_clinic",
    "settings|add_doctor",
    "settings|analyze_clinic",
    "settings|analyze_doctor",
    "settings|del_clinic",
    "settings|del_doctor",
))
def cb_settings(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    action = call.data.split("|",1)[1]
    if action == "channel":
        send_channel_menu(call.from_user.id)
    elif action == "add_clinic":
        start_add_clinic(call.from_user.id)
    elif action == "add_doctor":
        send_clinic_picker(call.from_user.id, "Qaysi klinikaga doktor qo'shiladi?", "settings|add_doctor_clinic")
    elif action == "analyze_clinic":
        send_clinic_picker(call.from_user.id, "Tahlil qilish uchun klinikani tanlang:", "settings|analyze_clinic_show")
    elif action == "analyze_doctor":
        send_doctor_picker(call.from_user.id, "Tahlil qilish uchun doktorni tanlang:", "settings|analyze_doctor_show")
    elif action == "del_clinic":
        send_clinic_picker(call.from_user.id, "O'chirish uchun klinikani tanlang:", "settings|del_clinic_ask")
    elif action == "del_doctor":
        send_doctor_picker(call.from_user.id, "O'chirish uchun doktorni tanlang:", "settings|del_doctor_ask")

@bot.callback_query_handler(func=lambda c: c.data == "settings|channel_add")
def cb_channel_add(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    user_state[call.from_user.id] = {"step": "settings_channel_add", "data": {}}
    bot.send_message(
        call.from_user.id,
        "Kanal username yoki ID sini yuboring.\nMasalan: @kanal_nomi\n\nEslatma: bot o'sha kanalda admin bo'lishi kerak.",
    )

@bot.callback_query_handler(func=lambda c: c.data == "settings|channel_list")
def cb_channel_list(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    send_channel_list(call.from_user.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_stats|"))
def cb_channel_stats(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = mandatory_channels.get(chat_id)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi.")
        return
    bot.send_message(call.from_user.id, channel_stats_text(channel), parse_mode="HTML")
    save_data()

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_users|"))
def cb_channel_users(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = mandatory_channels.get(chat_id)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi.")
        return
    rows = []
    for uid, per_channel in channel_user_stats.items():
        row = per_channel.get(chat_id)
        if not row:
            continue
        rows.append({
            "user_id": uid,
            "is_subscribed": row.get("is_subscribed"),
            "status": row.get("status"),
            "checked_at": row.get("checked_at"),
            "first_subscribed_at": row.get("first_subscribed_at"),
            "last_subscribed_at": row.get("last_subscribed_at"),
        })
    if not rows:
        bot.send_message(call.from_user.id, "Bu kanal bo'yicha hali foydalanuvchi tekshirilmagan.")
        return
    buf = io.StringIO()
    fieldnames = ["user_id", "is_subscribed", "status", "checked_at", "first_subscribed_at", "last_subscribed_at"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = io.BytesIO(buf.getvalue().encode("utf-8"))
    safe_title = (channel.get("username") or channel.get("title") or "channel").replace("@", "").replace(" ", "_")
    bot.send_document(call.from_user.id, (f"{safe_title}_users.csv", payload))

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_freeze|"))
def cb_channel_freeze(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = set_channel_enabled(chat_id, False)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi.")
        return
    bot.send_message(call.from_user.id, f"⏸ Kanal muzlatildi: {channel.get('title')}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_enable|"))
def cb_channel_enable(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = set_channel_enabled(chat_id, True)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi.")
        return
    bot.send_message(call.from_user.id, f"▶️ Kanal faollashtirildi: {channel.get('title')}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_delete_ask|"))
def cb_channel_delete_ask(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = mandatory_channels.get(chat_id)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi.")
        return
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Ha, o'chirish", f"settings|channel_delete_confirm|{chat_id}"), mk("❌ Bekor qilish", "noop"))
    bot.send_message(call.from_user.id, f"Majburiy kanal o'chirilsinmi?\n{channel.get('title')}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|channel_delete_confirm|"))
def cb_channel_delete_confirm(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    chat_id = call.data.split("|", 2)[2]
    channel = delete_mandatory_channel(chat_id)
    if not channel:
        bot.send_message(call.from_user.id, "Kanal topilmadi yoki allaqachon o'chirilgan.")
        return
    bot.send_message(call.from_user.id, f"✅ Kanal o'chirildi: {channel.get('title')}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|add_doctor_clinic|"))
def cb_add_doctor_clinic(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    clinic_id = call.data.split("|")[-1]
    start_add_doctor(call.from_user.id, clinic_id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|analyze_clinic_show|"))
def cb_analyze_clinic(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    clinic_id = call.data.split("|")[-1]
    clinic = find_clinic_by_id(clinic_id)
    if not clinic:
        bot.send_message(call.from_user.id, "Klinika topilmadi.")
        return
    send_clinic_analysis(call.from_user.id, clinic)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|analyze_doctor_show|"))
def cb_analyze_doctor(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.from_user.id, "Tugma noto'g'ri.")
        return
    clinic = find_clinic_by_id(parts[2])
    if not clinic:
        bot.send_message(call.from_user.id, "Klinika topilmadi.")
        return
    doctor = next((d for d in clinic.get('doctors', []) if d.get('id') == parts[3]), None)
    if not doctor:
        bot.send_message(call.from_user.id, "Doktor topilmadi.")
        return
    send_doctor_analysis(call.from_user.id, clinic, doctor)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|del_clinic_ask|"))
def cb_del_clinic_ask(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    clinic_id = call.data.split("|")[-1]
    clinic = find_clinic_by_id(clinic_id)
    if not clinic:
        bot.send_message(call.from_user.id, "Klinika topilmadi.")
        return
    m = clinic_metrics(clinic_id)
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Ha, o'chirish", f"settings|del_clinic_confirm|{clinic_id}"), mk("❌ Bekor qilish", "noop"))
    bot.send_message(
        call.from_user.id,
        f"Diqqat: <b>{clinic['name']}</b> o'chiriladi.\n"
        f"Doktorlar: {len(clinic.get('doctors', []))}\n"
        f"Faol yozuvlar: {m['active']}\n"
        f"Jami yozuvlar: {m['total']}\n\n"
        f"O'chirishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb,
    )

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|del_doctor_ask|"))
def cb_del_doctor_ask(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.from_user.id, "Tugma noto'g'ri.")
        return
    clinic_id, doctor_id = parts[2], parts[3]
    clinic = find_clinic_by_id(clinic_id)
    if not clinic:
        bot.send_message(call.from_user.id, "Klinika topilmadi.")
        return
    doctor = next((d for d in clinic.get('doctors', []) if d.get('id') == doctor_id), None)
    if not doctor:
        bot.send_message(call.from_user.id, "Doktor topilmadi.")
        return
    m = doctor_metrics(doctor_id)
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Ha, o'chirish", f"settings|del_doctor_confirm|{clinic_id}|{doctor_id}"), mk("❌ Bekor qilish", "noop"))
    bot.send_message(
        call.from_user.id,
        f"Diqqat: <b>{doctor['name']}</b> doktori o'chiriladi.\n"
        f"Klinika: {clinic['name']}\n"
        f"Kelgusi yozuvlar: {m['upcoming']}\n"
        f"Jami yozuvlar: {m['total']}\n\n"
        f"O'chirishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb,
    )

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|del_clinic_confirm|"))
def cb_del_clinic_confirm(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    cid = call.data.split("|")[-1]
    with data_lock:
        clinic = find_clinic_by_id(cid)
        if not clinic:
            bot.send_message(call.from_user.id, "Klinika topilmadi yoki allaqachon o'chirilgan.")
            return
        clinic_name = clinic.get('name', cid)
        affected = 0
        for appt_id, appt in appointments.items():
            if appointment_belongs_to_clinic(appt, cid):
                affected += 1
                appt['clinic_id'] = cid
                appt['clinic_name_deleted'] = clinic_name
                appt['clinic'] = None
                if appt.get('status') in ACTIVE_APPT_STATUSES:
                    appt['status'] = 'cancelled_clinic_deleted'
                    cancel_appointment_jobs(appt_id)
        clinics[:] = [c for c in clinics if c['id'] != cid]
    save_data()
    bot.send_message(call.from_user.id, f"✅ Klinika o'chirildi: {clinic_name}\nBog'langan yozuvlar yangilandi: {affected}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("settings|del_doctor_confirm|"))
def cb_del_doctor_confirm(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    _,_,_,cid,did = call.data.split("|")
    with data_lock:
        clinic = find_clinic_by_id(cid)
        if not clinic:
            bot.send_message(call.from_user.id, "Klinika topilmadi.")
            return
        doctor = next((d for d in clinic.get('doctors', []) if d.get('id') == did), None)
        if not doctor:
            bot.send_message(call.from_user.id, "Doktor topilmadi yoki allaqachon o'chirilgan.")
            return
        doctor_name = doctor.get('name', did)
        affected = 0
        for appt_id, appt in appointments.items():
            if appointment_belongs_to_doctor(appt, did):
                affected += 1
                appt['doctor_id'] = did
                appt['doctor_name_deleted'] = doctor_name
                appt['doctor_obj'] = None
                if appt.get('status') in ACTIVE_APPT_STATUSES:
                    appt['status'] = 'cancelled_doctor_deleted'
                    cancel_appointment_jobs(appt_id)
        clinic['doctors'] = [d for d in clinic.get('doctors', []) if d.get('id') != did]
    save_data()
    bot.send_message(call.from_user.id, f"✅ Doktor o'chirildi: {doctor_name}\nBog'langan yozuvlar yangilandi: {affected}")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id,{}).get('step') == "settings_channel_add")
def mh_settings_channel_add(m: types.Message):
    if not is_admin(m.from_user.id): return
    try:
        channel = add_mandatory_channel(m.text.strip(), m.from_user.id)
    except PermissionError as exc:
        bot.send_message(m.chat.id, f"❌ {exc}")
        return
    except Exception:
        logger.exception("failed to add mandatory channel")
        bot.send_message(m.chat.id, "❌ Kanal qo'shilmadi. Username/ID to'g'riligini va bot kanalda admin ekanini tekshiring.")
        return
    user_state.pop(m.chat.id, None)
    bot.send_message(
        m.chat.id,
        f"✅ Majburiy kanal qo'shildi va faollashtirildi:\n{channel.get('title')}\nObunachilar: {channel.get('last_member_count', '-')}",
    )
