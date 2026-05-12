from html import escape

from clinic_bot.shared import *
from clinic_bot.helpers import button_matches, find_clinic_by_id, get_doctor_rating, is_admin, mk, new_id
from clinic_bot.storage import save_data


# ---------------- ONLAYN TASHHIS / PROFESSIONAL TICKET SYSTEM ----------------
CALL_URGENCY_LABELS = {
    "normal": "Oddiy",
    "soon": "Bugun kerak",
    "urgent": "Shoshilinch",
}


def all_doctors():
    rows = []
    for clinic in clinics:
        for doctor in clinic.get("doctors", []):
            rows.append((clinic, doctor))
    return rows


def doctor_by_ids(clinic_id, doctor_id):
    clinic = find_clinic_by_id(clinic_id)
    if not clinic:
        return None, None
    doctor = next((d for d in clinic.get("doctors", []) if d.get("id") == doctor_id), None)
    return clinic, doctor


def doctor_title(clinic, doctor):
    rating = round(get_doctor_rating(doctor), 1)
    return f"{doctor.get('name', '-')} — {clinic.get('name', '-')} | {doctor.get('experience', '-')} | {rating}⭐"


def doctor_choice_keyboard(prefix, include_admin_choice=True):
    kb = InlineKeyboardMarkup()
    for clinic, doctor in all_doctors():
        kb.add(mk(doctor_title(clinic, doctor), f"{prefix}|{clinic['id']}|{doctor['id']}"))
    if include_admin_choice:
        kb.add(mk("Admin doktor tanlasin", f"{prefix}|any"))
    return kb


def remove_notify_buttons(req):
    for msg in req.get("notify_msgs", []):
        try:
            bot.edit_message_reply_markup(msg["chat_id"], msg["message_id"], reply_markup=None)
        except Exception:
            pass


def call_request_text(req):
    preferred = req.get("preferred_doctor_name") or "Admin tanlaydi"
    assigned = req.get("assigned_doctor_name") or "-"
    urgency = CALL_URGENCY_LABELS.get(req.get("urgency"), req.get("urgency") or "-")
    return (
        f"📞 <b>Doktorga chaqiruv</b>\n"
        f"ID: <code>{req['id']}</code>\n"
        f"Holat: {escape(str(req.get('status', '-')))}\n"
        f"Bemor: {escape(str(req.get('patient_name') or '-'))}\n"
        f"Telefon: {escape(str(req.get('patient_phone') or '-'))}\n"
        f"Manzil: {escape(str(req.get('address') or '-'))}\n"
        f"Shoshilinchlik: {escape(str(urgency))}\n"
        f"Tanlangan doktor: {escape(str(preferred))}\n"
        f"Tayinlangan doktor: {escape(str(assigned))}\n\n"
        f"<b>Muammo:</b>\n{escape(str(req.get('details') or '-'))}"
    )


def call_admin_keyboard(req_id, accepted=False):
    kb = InlineKeyboardMarkup()
    if not accepted:
        kb.row(mk("✅ Qabul qilish", f"diag_call_admin|accept|{req_id}"), mk("❌ Rad etish", f"diag_call_admin|reject|{req_id}"))
    kb.row(mk("👨‍⚕️ Doktor tanlash", f"diag_call_admin|choose_doctor|{req_id}"))
    kb.row(mk("🔚 Yopish", f"diag_call_admin|close|{req_id}"))
    return kb


def notify_call_admins(req):
    req.setdefault("notify_msgs", [])
    for admin_id in list(admins):
        try:
            msg = bot.send_message(
                admin_id,
                call_request_text(req),
                parse_mode="HTML",
                reply_markup=call_admin_keyboard(req["id"]),
            )
            req["notify_msgs"].append({"admin_id": admin_id, "chat_id": msg.chat.id, "message_id": msg.message_id})
        except Exception:
            logger.exception("notify admin about call request failed")


def create_call_request(chat_id, from_user, data):
    req_id = new_id("call")
    req = {
        "id": req_id,
        "type": "doctor_call",
        "user_chat": chat_id,
        "user_first_name": from_user.first_name,
        "patient_name": data.get("patient_name"),
        "patient_phone": data.get("patient_phone"),
        "address": data.get("address"),
        "details": data.get("details"),
        "urgency": data.get("urgency"),
        "preferred_clinic_id": data.get("preferred_clinic_id"),
        "preferred_doctor_id": data.get("preferred_doctor_id"),
        "preferred_doctor_name": data.get("preferred_doctor_name"),
        "assigned_admin": None,
        "assigned_doctor_id": None,
        "assigned_doctor_name": None,
        "assigned_doctor_telegram_id": None,
        "created_at": datetime.now(tz).isoformat(),
        "status": "pending",
        "events": [{"type": "created", "ts": datetime.now(tz).isoformat(), "by": chat_id}],
        "notify_msgs": [],
    }
    diagnosis_requests[req_id] = req
    notify_call_admins(req)
    save_data()
    return req


def send_call_management_panel(admin_id, req):
    bot.send_message(
        admin_id,
        call_request_text(req),
        parse_mode="HTML",
        reply_markup=call_admin_keyboard(req["id"], accepted=True),
    )


@bot.message_handler(func=lambda m: button_matches(m.text, "🔎 Onlay tashhis"))
def user_diag_menu(m: types.Message):
    kb = InlineKeyboardMarkup()
    kb.row(mk("✉️ SMS yozish", "diag|sms"), mk("📞 Doktorga chaqiruv", "diag|call"))
    bot.send_message(m.chat.id, "Onlayn tashhisni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "diag_menu")
def cb_diag_menu(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    user_diag_menu(call.message)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag|"))
def cb_diag_choice(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    typ = call.data.split("|",1)[1]; chat = call.message.chat.id
    if typ == "sms":
        user_state[chat] = {"step":"diag_wait_text","data":{}}
        bot.send_message(chat, "Iltimos simptomlaringizni batafsil yozing. Ushbu xabar adminlarga yuboriladi va kimdir qabul qilgach siz bilan shu admin orqali suhbat boshlanadi.")
    elif typ == "call":
        user_state[chat] = {
            "step": "diag_call_name",
            "data": {"patient_name": call.from_user.first_name or ""}
        }
        bot.send_message(chat, "Doktor chaqiruvi uchun bemor ism-familiyasini kiriting:")


@bot.message_handler(func=lambda m: user_state.get(m.chat.id,{}).get('step') == "diag_wait_text")
def mh_diag_text(m: types.Message):
    chat = m.chat.id; txt = m.text.strip()
    req_id = new_id("diag")
    diagnosis_requests[req_id] = {
        "id": req_id,
        "type": "sms",
        "user_chat": chat,
        "user_first_name": m.from_user.first_name,
        "text": txt,
        "created_at": datetime.now(tz).isoformat(),
        "status": "pending",
        "assigned_admin": None,
        "messages": [],
        "notify_msgs": []
    }
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Qabul qilaman", f"diag_admin|accept|{req_id}"), mk("❌ Rad etish", f"diag_admin|reject|{req_id}"))
    for aid in admins:
        try:
            first_name = escape(str(m.from_user.first_name or "-"))
            msg = bot.send_message(aid, f"🔔 <b>Yangi tashhis so'rovi</b>\nID: {req_id}\nFoydalanuvchi: {chat} ({first_name})\nMatn:\n{escape(txt)}", parse_mode="HTML", reply_markup=kb)
            diagnosis_requests[req_id]['notify_msgs'].append({"admin_id": aid, "chat_id": msg.chat.id, "message_id": msg.message_id})
        except Exception:
            logger.exception("notify admin failed")
    user_state.pop(chat, None); bot.send_message(chat, "Xabaringiz adminlarga yuborildi. Tez orada kimdir qabul qiladi."); save_data()


@bot.message_handler(func=lambda m: user_state.get(m.chat.id,{}).get('step') in ("diag_call_name", "diag_call_phone", "diag_call_address", "diag_call_details"))
def mh_diag_call_text(m: types.Message):
    chat = m.chat.id
    st = user_state.get(chat)
    if not st:
        return
    step = st.get("step")
    data = st.setdefault("data", {})
    text = (m.text or "").strip()
    if step == "diag_call_name":
        if not text:
            bot.send_message(chat, "Ism bo'sh bo'lmasin. Qayta kiriting:")
            return
        data["patient_name"] = text
        st["step"] = "diag_call_phone"
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("Kontaktni yuborish", request_contact=True))
        bot.send_message(chat, "Telefon raqamingizni yuboring yoki matn qilib kiriting:", reply_markup=kb)
        return
    if step == "diag_call_phone":
        if not text:
            bot.send_message(chat, "Telefon raqam bo'sh bo'lmasin. Qayta kiriting:")
            return
        data["patient_phone"] = text
        st["step"] = "diag_call_address"
        bot.send_message(chat, "Doktor borishi kerak bo'lgan manzilni kiriting:", reply_markup=types.ReplyKeyboardRemove())
        return
    if step == "diag_call_address":
        if not text:
            bot.send_message(chat, "Manzil bo'sh bo'lmasin. Qayta kiriting:")
            return
        data["address"] = text
        st["step"] = "diag_call_details"
        bot.send_message(chat, "Muammo yoki simptomlarni qisqacha yozing:")
        return
    if step == "diag_call_details":
        if not text:
            bot.send_message(chat, "Muammo matni bo'sh bo'lmasin. Qayta kiriting:")
            return
        data["details"] = text
        st["step"] = "diag_call_urgency"
        kb = InlineKeyboardMarkup()
        kb.row(mk("Oddiy", "diag_call_urgency|normal"), mk("Bugun kerak", "diag_call_urgency|soon"))
        kb.row(mk("Shoshilinch", "diag_call_urgency|urgent"))
        bot.send_message(chat, "Chaqiruv qanchalik shoshilinch?", reply_markup=kb)


@bot.message_handler(
    func=lambda m: user_state.get(m.chat.id,{}).get('step') == "diag_call_phone",
    content_types=['contact']
)
def mh_diag_call_contact(m: types.Message):
    chat = m.chat.id
    user_state[chat]['data']['patient_phone'] = m.contact.phone_number
    user_state[chat]['step'] = "diag_call_address"
    bot.send_message(chat, "Doktor borishi kerak bo'lgan manzilni kiriting:", reply_markup=types.ReplyKeyboardRemove())


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_call_urgency|"))
def cb_diag_call_urgency(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    st = user_state.get(chat)
    if not st or st.get("step") != "diag_call_urgency":
        bot.send_message(chat, "Chaqiruv holati topilmadi. /start orqali qayta boshlang.")
        return
    urgency = call.data.split("|", 1)[1]
    st.setdefault("data", {})["urgency"] = urgency
    st["step"] = "diag_call_choose_doctor"
    kb = doctor_choice_keyboard("diag_call_doctor", include_admin_choice=True)
    if not all_doctors():
        bot.send_message(chat, "Hozircha ro'yxatda doktor yo'q. So'rov adminlarga yuboriladi.")
        req = create_call_request(chat, call.from_user, st["data"])
        user_state.pop(chat, None)
        bot.send_message(chat, f"Chaqiruv so'rovingiz qabul qilindi. ID: {req['id']}. Adminlar tez orada bog'lanadi.")
        return
    bot.send_message(chat, "Qaysi doktorni chaqirmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_call_doctor|"))
def cb_diag_call_doctor(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    st = user_state.get(chat)
    if not st or st.get("step") != "diag_call_choose_doctor":
        bot.send_message(chat, "Chaqiruv holati topilmadi. /start orqali qayta boshlang.")
        return
    data = st.setdefault("data", {})
    parts = call.data.split("|")
    if len(parts) >= 2 and parts[1] == "any":
        data["preferred_clinic_id"] = None
        data["preferred_doctor_id"] = None
        data["preferred_doctor_name"] = None
    elif len(parts) >= 3:
        clinic, doctor = doctor_by_ids(parts[1], parts[2])
        if not doctor:
            bot.send_message(chat, "Doktor topilmadi. Boshqa doktorni tanlang.")
            return
        data["preferred_clinic_id"] = clinic["id"]
        data["preferred_doctor_id"] = doctor["id"]
        data["preferred_doctor_name"] = doctor_title(clinic, doctor)
    req = create_call_request(chat, call.from_user, data)
    user_state.pop(chat, None)
    bot.send_message(chat, f"Chaqiruv so'rovingiz qabul qilindi. ID: {req['id']}. Adminlar tez orada bog'lanadi.")


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_admin|"))
def cb_diag_admin(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3: return
    action = parts[1]; req_id = parts[2]
    req = diagnosis_requests.get(req_id)
    if not req:
        bot.send_message(call.message.chat.id, "So'rov topilmadi yoki allaqachon qayta ishlangan."); return
    if action == "accept":
        if req.get('assigned_admin'):
            bot.send_message(call.message.chat.id, "Ushbu so'rovni boshqa admin qabul qilgan."); return
        req['assigned_admin'] = call.from_user.id
        req['status'] = "assigned"
        active_diag_chats[req['user_chat']] = call.from_user.id
        admin_active_diag[call.from_user.id] = req['user_chat']
        save_data()
        remove_notify_buttons(req)
        bot.send_message(call.from_user.id, f"✅ Siz {req_id} so'rovini qabul qildingiz. Endi bemor bilan shu admin orqali yozishishingiz mumkin.\nSuhbatni tugatish uchun /enddiag yoki quyidagi tugma.")
        try:
            kb = InlineKeyboardMarkup()
            kb.row(mk("🔚 Suhbatni yopish", f"diag_end|{req_id}"))
            bot.send_message(req['user_chat'], f"✅ Admin {call.from_user.first_name or call.from_user.id} sizning so'rovingizni qabul qildi. Endi shu admin bilan yozishishingiz mumkin.", reply_markup=kb)
        except Exception:
            pass
        return
    if action == "reject":
        req['status'] = "rejected"
        remove_notify_buttons(req)
        save_data()
        bot.send_message(call.from_user.id, "So'rov rad etildi.")
        try:
            bot.send_message(req['user_chat'], "Afsuski, so'rovingiz hozircha qabul qilinmadi. Keyinroq urinib ko'ring.")
        except Exception:
            pass
        return


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_call_admin|"))
def cb_diag_call_admin(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Siz admin emassiz.")
        return
    parts = call.data.split("|")
    if len(parts) < 3:
        return
    action, req_id = parts[1], parts[2]
    req = diagnosis_requests.get(req_id)
    if not req or req.get("type") != "doctor_call":
        bot.send_message(call.message.chat.id, "Chaqiruv so'rovi topilmadi.")
        return
    if req.get("status") in ("closed", "rejected") and action != "close":
        bot.send_message(call.from_user.id, "Bu chaqiruv allaqachon yakunlangan.")
        return

    if action == "accept":
        if req.get("assigned_admin") and req.get("assigned_admin") != call.from_user.id:
            bot.send_message(call.from_user.id, "Bu chaqiruvni boshqa admin qabul qilgan.")
            return
        req["assigned_admin"] = call.from_user.id
        req["status"] = "admin_accepted"
        req.setdefault("events", []).append({"type": "admin_accepted", "by": call.from_user.id, "ts": datetime.now(tz).isoformat()})
        remove_notify_buttons(req)
        save_data()
        send_call_management_panel(call.from_user.id, req)
        try:
            bot.send_message(req["user_chat"], f"✅ Doktorga chaqiruv so'rovingiz admin tomonidan qabul qilindi. ID: {req_id}")
        except Exception:
            pass
        return

    if action == "reject":
        req["status"] = "rejected"
        req["rejected_by"] = call.from_user.id
        req["rejected_at"] = datetime.now(tz).isoformat()
        req.setdefault("events", []).append({"type": "rejected", "by": call.from_user.id, "ts": datetime.now(tz).isoformat()})
        remove_notify_buttons(req)
        save_data()
        bot.send_message(call.from_user.id, "Chaqiruv rad etildi.")
        try:
            bot.send_message(req["user_chat"], "Afsuski, doktorga chaqiruv so'rovingiz rad etildi. Qo'shimcha ma'lumot uchun klinika bilan bog'laning.")
        except Exception:
            pass
        return

    if action == "choose_doctor":
        if not all_doctors():
            bot.send_message(call.from_user.id, "Doktorlar ro'yxati bo'sh. Avval doktor qo'shing.")
            return
        bot.send_message(call.from_user.id, "Chaqiruv uchun doktorni tanlang:", reply_markup=doctor_choice_keyboard(f"diag_call_assign|{req_id}", include_admin_choice=False))
        return

    if action == "close":
        req["status"] = "closed"
        req["closed_by"] = call.from_user.id
        req["closed_at"] = datetime.now(tz).isoformat()
        req.setdefault("events", []).append({"type": "closed", "by": call.from_user.id, "ts": datetime.now(tz).isoformat()})
        remove_notify_buttons(req)
        save_data()
        bot.send_message(call.from_user.id, "Chaqiruv yopildi.")
        try:
            bot.send_message(req["user_chat"], f"Doktorga chaqiruv yopildi. ID: {req_id}")
        except Exception:
            pass
        doctor_tg = req.get("assigned_doctor_telegram_id")
        if doctor_tg:
            try:
                bot.send_message(doctor_tg, f"Chaqiruv yopildi. ID: {req_id}")
            except Exception:
                pass
        return


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_call_assign|"))
def cb_diag_call_assign(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Siz admin emassiz.")
        return
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.from_user.id, "Tugma noto'g'ri.")
        return
    req_id, clinic_id, doctor_id = parts[1], parts[2], parts[3]
    req = diagnosis_requests.get(req_id)
    if not req or req.get("type") != "doctor_call":
        bot.send_message(call.from_user.id, "Chaqiruv so'rovi topilmadi.")
        return
    if req.get("status") in ("closed", "rejected"):
        bot.send_message(call.from_user.id, "Bu chaqiruv allaqachon yakunlangan.")
        return
    clinic, doctor = doctor_by_ids(clinic_id, doctor_id)
    if not doctor:
        bot.send_message(call.from_user.id, "Doktor topilmadi.")
        return

    req["assigned_admin"] = req.get("assigned_admin") or call.from_user.id
    req["assigned_clinic_id"] = clinic["id"]
    req["assigned_doctor_id"] = doctor["id"]
    req["assigned_doctor_name"] = doctor_title(clinic, doctor)
    req["assigned_doctor_telegram_id"] = doctor.get("telegram_id")
    req["status"] = "doctor_assigned"
    req.setdefault("events", []).append({"type": "doctor_assigned", "doctor_id": doctor["id"], "by": call.from_user.id, "ts": datetime.now(tz).isoformat()})
    save_data()

    bot.send_message(call.from_user.id, f"✅ Doktor tayinlandi:\n{req['assigned_doctor_name']}")
    try:
        bot.send_message(req["user_chat"], f"👨‍⚕️ Sizning chaqiruvingiz uchun doktor tayinlandi:\n{req['assigned_doctor_name']}\nAdmin tez orada bog'lanadi.")
    except Exception:
        pass

    if doctor.get("telegram_id"):
        kb = InlineKeyboardMarkup()
        kb.row(mk("✅ Chaqiruvni qabul qilaman", f"doctor_call|accept|{req_id}"))
        kb.row(mk("❌ Bora olmayman", f"doctor_call|reject|{req_id}"))
        try:
            bot.send_message(doctor["telegram_id"], call_request_text(req), parse_mode="HTML", reply_markup=kb)
        except Exception:
            logger.exception("notify assigned doctor failed")
            bot.send_message(call.from_user.id, "Doktorga Telegram orqali xabar yuborilmadi. Telefon orqali bog'laning.")
    else:
        bot.send_message(call.from_user.id, f"Doktor Telegram ID ulanmagan. Telefon: {doctor.get('phone', '-')}")


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("doctor_call|"))
def cb_doctor_call(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3:
        return
    action, req_id = parts[1], parts[2]
    req = diagnosis_requests.get(req_id)
    if not req or req.get("type") != "doctor_call":
        bot.send_message(call.from_user.id, "Chaqiruv topilmadi.")
        return
    if req.get("status") in ("closed", "rejected"):
        bot.send_message(call.from_user.id, "Bu chaqiruv allaqachon yopilgan.")
        return
    if req.get("assigned_doctor_telegram_id") != call.from_user.id:
        bot.send_message(call.from_user.id, "Bu chaqiruv sizga biriktirilmagan.")
        return
    if action == "accept":
        req["status"] = "doctor_confirmed"
        event_type = "doctor_confirmed"
        user_msg = f"✅ Doktor chaqiruvingizni tasdiqladi: {req.get('assigned_doctor_name')}"
        doctor_msg = "Chaqiruv qabul qilindi. Admin va bemorga xabar berildi."
    elif action == "reject":
        req["status"] = "doctor_rejected"
        event_type = "doctor_rejected"
        user_msg = "Doktor hozircha bora olmasligini bildirdi. Admin boshqa doktor bilan bog'lanadi."
        doctor_msg = "Javob qabul qilindi. Admin boshqa doktor tanlashi mumkin."
    else:
        return
    req.setdefault("events", []).append({"type": event_type, "by": call.from_user.id, "ts": datetime.now(tz).isoformat()})
    save_data()
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.send_message(call.from_user.id, doctor_msg)
    try:
        bot.send_message(req["user_chat"], user_msg)
    except Exception:
        pass
    admin_id = req.get("assigned_admin")
    if admin_id:
        try:
            bot.send_message(admin_id, f"Doktor javobi: {CALL_URGENCY_LABELS.get(req.get('urgency'), '-')}\n{call_request_text(req)}", parse_mode="HTML", reply_markup=call_admin_keyboard(req_id, accepted=True))
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_end|"))
def cb_diag_end(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    req_id = call.data.split("|",1)[1]
    req = diagnosis_requests.get(req_id)
    if not req:
        bot.send_message(call.from_user.id, "So'rov topilmadi."); return
    user = req['user_chat']; admin = req.get('assigned_admin')
    active_diag_chats.pop(user, None)
    if admin: admin_active_diag.pop(admin, None)
    req['status'] = "closed"; save_data()
    bot.send_message(call.from_user.id, "Suhbat yopildi.")
    try:
        bot.send_message(user, "Suhbat administrator tomonidan tugatildi. /start orqali qayta boshlang.")
    except Exception:
        pass


@bot.message_handler(commands=['enddiag'])
def cmd_enddiag(m: types.Message):
    admin = m.from_user.id
    if admin not in admin_active_diag:
        bot.send_message(m.chat.id, "Sizda faol tashhis yo'q."); return
    user = admin_active_diag.pop(admin); active_diag_chats.pop(user, None)
    for req in diagnosis_requests.values():
        if req.get('user_chat') == user and req.get('assigned_admin') == admin and req.get('status') == 'assigned':
            req['status'] = 'closed'; break
    save_data(); bot.send_message(m.chat.id, "Suhbat muvaffaqiyatli yopildi.")
    try: bot.send_message(user, "Admin suhbatni tugatdi. /start bilan qayta boshlashingiz mumkin.")
    except Exception: pass
