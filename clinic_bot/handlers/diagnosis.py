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
    specialty = doctor.get('specialty') or doctor.get('experience', '-')
    return f"👨‍⚕️ Dr. {doctor.get('name', '-')} • {specialty} • {rating}⭐"


def doctor_choice_keyboard(prefix, include_admin_choice=True):
    kb = InlineKeyboardMarkup()
    for clinic, doctor in all_doctors():
        kb.add(mk(doctor_title(clinic, doctor), f"{prefix}|{clinic['id']}|{doctor['id']}"))
    if include_admin_choice:
        kb.add(mk("🛡️ Admin doktor tanlasin", f"{prefix}|any"))
    return kb


def doctors_with_telegram():
    rows = []
    for clinic in clinics:
        for doctor in clinic.get("doctors", []):
            if doctor.get("telegram_id"):
                rows.append((clinic, doctor))
    return rows


def doctor_assignable_keyboard(prefix):
    """Keyboard listing only doctors with telegram_id (can receive chat through bot)."""
    kb = InlineKeyboardMarkup()
    for clinic, doctor in doctors_with_telegram():
        kb.add(mk(doctor_title(clinic, doctor), f"{prefix}|{clinic['id']}|{doctor['id']}"))
    return kb


def start_doctor_chat(req, mode):
    """Establish user <-> doctor chat (mode: 'sms' or 'call'). Returns True on success."""
    user_chat = req.get("user_chat")
    doctor_tg = req.get("assigned_doctor_telegram_id")
    if user_chat is None or doctor_tg is None:
        return False
    # Drop any previous chats on either side
    end_doctor_chat_for_user(user_chat, notify=False)
    end_doctor_chat_for_doctor(doctor_tg, notify=False)
    active_doctor_chats[user_chat] = doctor_tg
    doctor_active_chats[doctor_tg] = user_chat
    diag_chat_mode[user_chat] = mode
    diag_chat_req[user_chat] = req["id"]
    req["status"] = "chat_active"
    req.setdefault("events", []).append({
        "type": "chat_started", "mode": mode,
        "by": doctor_tg, "ts": datetime.now(tz).isoformat()
    })
    return True


def end_doctor_chat_for_user(user_chat, notify=True, closed_by=None):
    """End chat from user side (or admin force-close)."""
    doctor_tg = active_doctor_chats.pop(user_chat, None)
    if doctor_tg is not None:
        doctor_active_chats.pop(doctor_tg, None)
    mode = diag_chat_mode.pop(user_chat, None)
    req_id = diag_chat_req.pop(user_chat, None)
    if req_id:
        req = diagnosis_requests.get(req_id)
        if req:
            req["status"] = "closed"
            req["closed_at"] = datetime.now(tz).isoformat()
            if closed_by is not None:
                req["closed_by"] = closed_by
            req.setdefault("events", []).append({
                "type": "chat_closed", "by": closed_by, "ts": datetime.now(tz).isoformat()
            })
    if notify and doctor_tg:
        try:
            bot.send_message(doctor_tg, "Bemor suhbatni tugatdi.")
        except Exception:
            pass
    return doctor_tg, mode


def end_doctor_chat_for_doctor(doctor_tg, notify=True, closed_by=None):
    """End chat from doctor side."""
    user_chat = doctor_active_chats.pop(doctor_tg, None)
    if user_chat is not None:
        active_doctor_chats.pop(user_chat, None)
        mode = diag_chat_mode.pop(user_chat, None)
        req_id = diag_chat_req.pop(user_chat, None)
        if req_id:
            req = diagnosis_requests.get(req_id)
            if req:
                req["status"] = "closed"
                req["closed_at"] = datetime.now(tz).isoformat()
                if closed_by is not None:
                    req["closed_by"] = closed_by
                req.setdefault("events", []).append({
                    "type": "chat_closed", "by": closed_by, "ts": datetime.now(tz).isoformat()
                })
        if notify:
            try:
                bot.send_message(user_chat, "Doktor suhbatni tugatdi. Yangi suhbat boshlash uchun /start.")
            except Exception:
                pass
        return user_chat
    return None


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
    kb.row(mk("👨‍⚕️ Doktorga yuborish", f"diag_call_admin|send_to_doctor|{req_id}"),
           mk("❌ Rad etish", f"diag_call_admin|reject|{req_id}"))
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
    kb.row(mk("💬 SMS yozish", "diag|sms"), mk("📞 Doktorga chaqiruv", "diag|call"))
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
    chat = m.chat.id
    if not m.text:
        bot.send_message(chat, "Iltimos matn yuboring.")
        return
    txt = m.text.strip()
    if not txt:
        bot.send_message(chat, "Bo'sh xabar. Qayta yuboring.")
        return
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
        "assigned_doctor_id": None,
        "assigned_doctor_name": None,
        "assigned_doctor_telegram_id": None,
        "messages": [],
        "notify_msgs": []
    }
    kb = InlineKeyboardMarkup()
    kb.row(mk("👨‍⚕️ Doktorga yuborish", f"diag_admin|send_to_doctor|{req_id}"),
           mk("❌ Rad etish", f"diag_admin|reject|{req_id}"))
    for aid in admins:
        try:
            first_name = escape(str(m.from_user.first_name or "-"))
            msg = bot.send_message(aid,
                f"🔔 <b>Yangi SMS so'rovi</b>\nID: <code>{req_id}</code>\nBemor: {chat} ({first_name})\nMatn:\n{escape(txt)}",
                parse_mode="HTML", reply_markup=kb)
            diagnosis_requests[req_id]['notify_msgs'].append({"admin_id": aid, "chat_id": msg.chat.id, "message_id": msg.message_id})
        except Exception:
            logger.exception("notify admin failed")
    user_state.pop(chat, None)
    bot.send_message(chat, "✉️ Xabaringiz adminlarga yuborildi. Admin doktorni tanlaganidan keyin siz doktor bilan to'g'ridan-to'g'ri yozisha olasiz.")
    save_data()


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
        kb.row(mk("🟢 Oddiy", "diag_call_urgency|normal"), mk("🟡 Bugun kerak", "diag_call_urgency|soon"))
        kb.row(mk("🔴 Shoshilinch", "diag_call_urgency|urgent"))
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
    if not is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    parts = call.data.split("|")
    if len(parts) < 3: return
    action = parts[1]; req_id = parts[2]
    req = diagnosis_requests.get(req_id)
    if not req:
        bot.send_message(call.message.chat.id, "So'rov topilmadi yoki allaqachon qayta ishlangan."); return
    if action in ("accept", "send_to_doctor"):
        # New flow: admin picks doctor to forward SMS to
        if req.get("status") in ("closed", "rejected", "chat_active"):
            bot.send_message(call.from_user.id, "Bu so'rov allaqachon ishlangan.")
            return
        if not doctors_with_telegram():
            bot.send_message(call.from_user.id,
                "Telegram ID ulangan doktor yo'q. Avval doktor qo'shing yoki mavjud doktorga Telegram ID kiriting.")
            return
        kb = doctor_assignable_keyboard(f"diag_assign|sms|{req_id}")
        bot.send_message(call.from_user.id,
            f"So'rov <code>{req_id}</code> uchun doktorni tanlang:",
            parse_mode="HTML", reply_markup=kb)
        return
    if action == "reject":
        if req.get('assigned_admin') and req.get('assigned_admin') != call.from_user.id:
            bot.send_message(call.from_user.id, "Ushbu so'rovni boshqa admin allaqachon ko'rgan.")
            return
        req['status'] = "rejected"
        req['rejected_by'] = call.from_user.id
        req['rejected_at'] = datetime.now(tz).isoformat()
        remove_notify_buttons(req)
        save_data()
        bot.send_message(call.from_user.id, "So'rov rad etildi.")
        try:
            bot.send_message(req['user_chat'], "Afsuski, so'rovingiz hozircha qabul qilinmadi. Keyinroq urinib ko'ring.")
        except Exception:
            pass
        return


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_assign|"))
def cb_diag_assign(call: types.CallbackQuery):
    """Admin assigns a request (SMS or call) to a specific doctor."""
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id):
        bot.send_message(call.from_user.id, "Siz admin emassiz."); return
    parts = call.data.split("|")
    if len(parts) < 5:
        bot.send_message(call.from_user.id, "Tugma noto'g'ri."); return
    _, rtype, req_id, clinic_id, doctor_id = parts[:5]
    req = diagnosis_requests.get(req_id)
    if not req:
        bot.send_message(call.from_user.id, "So'rov topilmadi."); return
    if req.get("status") in ("closed", "rejected", "chat_active"):
        bot.send_message(call.from_user.id, "Bu so'rov allaqachon ishlangan.")
        return
    clinic, doctor = doctor_by_ids(clinic_id, doctor_id)
    if not doctor:
        bot.send_message(call.from_user.id, "Doktor topilmadi."); return
    if not doctor.get("telegram_id"):
        bot.send_message(call.from_user.id, "Doktor Telegram ID ga ega emas. Boshqasini tanlang.")
        return
    # Update request
    req["assigned_admin"] = req.get("assigned_admin") or call.from_user.id
    req["assigned_clinic_id"] = clinic["id"]
    req["assigned_doctor_id"] = doctor["id"]
    req["assigned_doctor_name"] = doctor_title(clinic, doctor)
    req["assigned_doctor_telegram_id"] = doctor["telegram_id"]
    req["status"] = "doctor_pending"
    req.setdefault("events", []).append({
        "type": "doctor_assigned", "doctor_id": doctor["id"],
        "by": call.from_user.id, "ts": datetime.now(tz).isoformat()
    })
    save_data()
    # Notify doctor
    kb = InlineKeyboardMarkup()
    if rtype == "sms":
        kb.row(mk("✅ SMS suhbatni qabul qilaman", f"diag_doctor|accept|{req_id}"))
    else:
        kb.row(mk("✅ Audio/video suhbatni qabul qilaman", f"diag_doctor|accept|{req_id}"))
    kb.row(mk("❌ Rad etish", f"diag_doctor|reject|{req_id}"))
    if rtype == "sms":
        intro = (f"📩 <b>Sizga SMS suhbat yuborildi</b>\n"
                 f"ID: <code>{req_id}</code>\n"
                 f"Bemor: {escape(str(req.get('user_first_name') or '-'))}\n\n"
                 f"<b>Bemorning muammosi:</b>\n{escape(str(req.get('text') or '-'))}")
    else:
        intro = "📞 <b>Sizga audio/video chaqiruv yuborildi</b>\n\n" + call_request_text(req)
    try:
        bot.send_message(doctor["telegram_id"], intro, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("notify doctor failed")
        bot.send_message(call.from_user.id, "Doktorga Telegram orqali xabar yuborilmadi.")
        return
    bot.send_message(call.from_user.id, f"✅ Doktor tanlandi: {req['assigned_doctor_name']}. Doktor javobi kutilmoqda.")
    try:
        bot.send_message(req["user_chat"],
            f"👨‍⚕️ Sizning so'rovingiz uchun doktor tanlandi:\n<b>{escape(req['assigned_doctor_name'])}</b>\nDoktor javobini kuting.",
            parse_mode="HTML")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("diag_doctor|"))
def cb_diag_doctor(call: types.CallbackQuery):
    """Doctor accepts or rejects a request (SMS or call). On accept, start user<->doctor chat."""
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3:
        return
    action, req_id = parts[1], parts[2]
    req = diagnosis_requests.get(req_id)
    if not req:
        bot.send_message(call.from_user.id, "So'rov topilmadi."); return
    if req.get("assigned_doctor_telegram_id") != call.from_user.id:
        bot.send_message(call.from_user.id, "Bu so'rov sizga biriktirilmagan.")
        return
    if req.get("status") in ("closed", "rejected", "chat_active") and action == "accept":
        bot.send_message(call.from_user.id, "Bu so'rov hozir qabul qilinishi mumkin emas (allaqachon ishlangan).")
        return
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    if action == "accept":
        # Determine mode
        mode = "call" if req.get("type") == "doctor_call" else "sms"
        if not start_doctor_chat(req, mode):
            bot.send_message(call.from_user.id, "Suhbat ochishda xatolik.")
            return
        save_data()

        # Look up the doctor object for richer card
        clinic_id = req.get("assigned_clinic_id")
        doctor_id = req.get("assigned_doctor_id")
        doc_clinic, doc_obj = doctor_by_ids(clinic_id, doctor_id) if (clinic_id and doctor_id) else (None, None)
        doc_short_name = (doc_obj.get("name") if doc_obj else None) or req.get("assigned_doctor_name", "Doktor").split(" — ")[0]
        doc_specialty = (doc_obj.get("specialty") if doc_obj else None) or "-"
        doc_experience = (doc_obj.get("experience") if doc_obj else None) or "-"
        doc_photo = doc_obj.get("photo_file_id") if doc_obj else None
        user_first = req.get("user_first_name") or "Bemor"
        patient_phone = req.get("patient_phone")

        # ---- Message to the patient (user) ----
        if mode == "sms":
            user_card = (
                f"✅ <b>Suhbat boshlandi</b>\n\n"
                f"👨‍⚕️ Siz hozir <b>Dr. {escape(str(doc_short_name))}</b> bilan yozishyapsiz.\n"
                f"🎓 Mutaxassis: {escape(str(doc_specialty))}\n"
                f"📅 Tajriba: {escape(str(doc_experience))}\n\n"
                f"💬 Endi xabaringizni shu yerga yozing — doktorga to'g'ridan-to'g'ri yetkaziladi.\n"
                f"🔚 Tugatish: /tugatish"
            )
        else:
            user_card = (
                f"✅ <b>Audio/video suhbat boshlandi</b>\n\n"
                f"👨‍⚕️ Siz hozir <b>Dr. {escape(str(doc_short_name))}</b> bilan bog'landingiz.\n"
                f"🎓 Mutaxassis: {escape(str(doc_specialty))}\n"
                f"📅 Tajriba: {escape(str(doc_experience))}\n\n"
                f"🎙 Faqat <b>ovozli xabar</b> yoki <b>video xabar</b> yuboring.\n"
                f"🔚 Tugatish: /tugatish"
            )
        try:
            if doc_photo:
                bot.send_photo(req["user_chat"], doc_photo, caption=user_card, parse_mode="HTML")
            else:
                bot.send_message(req["user_chat"], user_card, parse_mode="HTML")
        except Exception:
            try:
                bot.send_message(req["user_chat"], user_card, parse_mode="HTML")
            except Exception:
                logger.exception("notify user about chat start failed")

        # ---- Message to the doctor ----
        original_text = req.get("text") or req.get("details") or "-"
        if mode == "sms":
            doctor_card = (
                f"✅ <b>SMS suhbat boshlandi</b>\n\n"
                f"👤 Bemor: <b>{escape(str(user_first))}</b>\n"
                + (f"☎️ Telefon: <code>{escape(str(patient_phone))}</code>\n" if patient_phone else "")
                + f"\n📝 Dastlabki xabar:\n<i>{escape(str(original_text))}</i>\n\n"
                f"💬 Javobingizni shu yerga yozing.\n"
                f"🔚 Tugatish: /tugatish"
            )
        else:
            address = req.get("address") or "-"
            urgency = CALL_URGENCY_LABELS.get(req.get("urgency"), req.get("urgency") or "-")
            doctor_card = (
                f"✅ <b>Audio/video suhbat boshlandi</b>\n\n"
                f"👤 Bemor: <b>{escape(str(user_first))}</b>\n"
                + (f"☎️ Telefon: <code>{escape(str(patient_phone))}</code>\n" if patient_phone else "")
                + f"🏠 Manzil: {escape(str(address))}\n"
                f"⚡ Shoshilinchlik: {escape(str(urgency))}\n\n"
                f"📝 Muammo:\n<i>{escape(str(original_text))}</i>\n\n"
                f"🎙 Faqat <b>ovozli</b> yoki <b>video xabar</b> yuboring.\n"
                f"🔚 Tugatish: /tugatish"
            )
        bot.send_message(call.from_user.id, doctor_card, parse_mode="HTML")

        # Notify admin
        admin_id = req.get("assigned_admin")
        if admin_id and admin_id != call.from_user.id:
            try:
                mode_label = "Audio/video" if mode == "call" else "SMS"
                bot.send_message(admin_id, f"ℹ️ Doktor so'rov <code>{req_id}</code> ni qabul qildi. {mode_label} suhbat boshlandi.", parse_mode="HTML")
            except Exception:
                pass
        return
    if action == "reject":
        req["status"] = "doctor_rejected"
        req.setdefault("events", []).append({"type":"doctor_rejected","by":call.from_user.id,"ts":datetime.now(tz).isoformat()})
        save_data()
        bot.send_message(call.from_user.id, "Siz so'rovni rad etdingiz.")
        # Let user know
        try:
            bot.send_message(req["user_chat"], "Doktor hozircha bog'lana olmasligini bildirdi. Admin boshqa doktor bilan urinadi.")
        except Exception:
            pass
        # Notify admins so they can reassign
        rtype = "sms" if req.get("type") == "sms" else "call"
        kb = InlineKeyboardMarkup()
        kb.row(mk("👨‍⚕️ Boshqa doktorga yuborish",
                  f"diag_admin|send_to_doctor|{req_id}" if rtype == "sms"
                  else f"diag_call_admin|send_to_doctor|{req_id}"))
        for aid in admins:
            try:
                bot.send_message(aid,
                    f"⚠️ Doktor so'rov <code>{req_id}</code> ni rad etdi.\nBoshqa doktorga yuboring.",
                    parse_mode="HTML", reply_markup=kb)
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

    if action in ("accept", "send_to_doctor", "choose_doctor"):
        # All admin first-touch actions now lead to doctor picker
        if req.get("status") in ("closed", "rejected", "chat_active"):
            bot.send_message(call.from_user.id, "Bu chaqiruv allaqachon ishlangan.")
            return
        if not doctors_with_telegram():
            bot.send_message(call.from_user.id,
                "Telegram ID ulangan doktor yo'q. Avval doktor qo'shing yoki doktorga Telegram ID kiriting.")
            return
        req["assigned_admin"] = req.get("assigned_admin") or call.from_user.id
        save_data()
        kb = doctor_assignable_keyboard(f"diag_assign|call|{req_id}")
        bot.send_message(call.from_user.id,
            f"Chaqiruv <code>{req_id}</code> uchun doktorni tanlang:",
            parse_mode="HTML", reply_markup=kb)
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
        kb.row(mk("✅ Audio/video suhbatni qabul qilaman", f"diag_doctor|accept|{req_id}"))
        kb.row(mk("❌ Rad etish", f"diag_doctor|reject|{req_id}"))
        try:
            bot.send_message(doctor["telegram_id"], call_request_text(req), parse_mode="HTML", reply_markup=kb)
        except Exception:
            logger.exception("notify assigned doctor failed")
            bot.send_message(call.from_user.id, "Doktorga Telegram orqali xabar yuborilmadi. Telefon orqali bog'laning.")
    else:
        bot.send_message(call.from_user.id, f"Doktor Telegram ID ulanmagan. Telefon: {doctor.get('phone', '-')}")


# Legacy compatibility: old doctor_call|accept/reject buttons (still floating in admin/doctor chats)
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("doctor_call|"))
def cb_doctor_call(call: types.CallbackQuery):
    """Legacy handler. Redirects to the new diag_doctor flow."""
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3:
        return
    action, req_id = parts[1], parts[2]
    # Translate to new callback and reuse handler
    call.data = f"diag_doctor|{action}|{req_id}"
    cb_diag_doctor(call)


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
    uid = m.from_user.id
    # admin side
    if uid in admin_active_diag:
        user = admin_active_diag.pop(uid); active_diag_chats.pop(user, None)
        for req in diagnosis_requests.values():
            if req.get('user_chat') == user and req.get('assigned_admin') == uid and req.get('status') == 'assigned':
                req['status'] = 'closed'; break
        save_data(); bot.send_message(m.chat.id, "Suhbat muvaffaqiyatli yopildi.")
        try: bot.send_message(user, "Admin suhbatni tugatdi. /start bilan qayta boshlashingiz mumkin.")
        except Exception: pass
        return
    # user side
    chat = m.chat.id
    if chat in active_diag_chats:
        admin = active_diag_chats.pop(chat)
        admin_active_diag.pop(admin, None)
        for req in diagnosis_requests.values():
            if req.get('user_chat') == chat and req.get('assigned_admin') == admin and req.get('status') == 'assigned':
                req['status'] = 'closed'; break
        save_data()
        bot.send_message(chat, "Suhbat yopildi. /start orqali qayta boshlashingiz mumkin.")
        try: bot.send_message(admin, f"Bemor {chat} suhbatni tugatdi.")
        except Exception: pass
        return
    bot.send_message(m.chat.id, "Sizda faol tashhis suhbati yo'q.")


@bot.message_handler(commands=['tugatish'])
def cmd_tugatish(m: types.Message):
    """End an active doctor<->user chat from either side."""
    uid = m.from_user.id
    chat = m.chat.id
    # Doctor side
    if uid in doctor_active_chats:
        user_chat = end_doctor_chat_for_doctor(uid, notify=True, closed_by=uid)
        save_data()
        bot.send_message(chat, "✅ Suhbat yopildi.")
        return
    # User side
    if chat in active_doctor_chats:
        doctor_tg, _ = end_doctor_chat_for_user(chat, notify=True, closed_by=chat)
        save_data()
        bot.send_message(chat, "✅ Suhbat yopildi. /start orqali qayta boshlashingiz mumkin.")
        return
    # Fallback: legacy admin chats
    if uid in admin_active_diag or chat in active_diag_chats:
        # Delegate to legacy enddiag
        cmd_enddiag(m)
        return
    bot.send_message(chat, "Sizda faol suhbat yo'q.")
