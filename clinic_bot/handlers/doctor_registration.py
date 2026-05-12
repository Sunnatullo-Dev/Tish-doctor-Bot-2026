from clinic_bot.shared import *
from clinic_bot.helpers import *
from clinic_bot.keyboards import date_buttons
from clinic_bot.scheduler_jobs import schedule_reminder
from clinic_bot.storage import save_data

# ---------------- DOCTOR REGISTRATION ----------------
def clean_optional_text(value, fallback="-"):
    value = (value or "").strip()
    if value.lower() in ("-", "yo'q", "yoq", "skip", "o'tkazish", "otkazish"):
        return fallback
    return value or fallback


def clinic_label_from_data(data):
    clinic = find_clinic_by_id(data.get('clinic_id'))
    if clinic:
        return clinic['name']
    request = data.get('clinic_request') or {}
    return f"Yangi klinika: {request.get('name', '-')}"


def resolve_pending_clinic(pend):
    clinic = find_clinic_by_id(pend.get('clinic_id'))
    if clinic:
        return clinic, False

    request = pend.get('clinic_request') or {}
    name = clean_optional_text(request.get('name'), "")
    if not name:
        return None, False

    new_clinic = {
        "id": new_id("c"),
        "name": name,
        "address": clean_optional_text(request.get('address'), "Manzil ko'rsatilmagan"),
        "lat": 0.0,
        "lon": 0.0,
        "region": "Yangi klinika",
        "manager_phone": clean_optional_text(request.get('phone'), pend.get('phone', "-")),
        "doctors": [],
        "created_from_doctor_request": pend.get('id'),
        "created_at": datetime.now(tz).isoformat(),
    }
    clinics.append(new_clinic)
    return new_clinic, True


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("docreg|clinic|"))
def cb_docreg(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.from_user.id
    parts = call.data.split("|")
    if len(parts) >= 3 and parts[1] == "clinic":
        if parts[2] == "other":
            user_state[chat] = {"step":"doc_other_clinic_name", "data":{"clinic_id": None, "clinic_request": {}}}
            bot.send_message(chat, "Klinika nomini kiriting:")
            return
        clinic_id = parts[2]
        user_state[chat] = {"step":"doc_name", "data":{"clinic_id": clinic_id, "clinic_request": None}}
        bot.send_message(chat, "Iltimos ismingizni kiriting:")

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') in ("doc_other_clinic_name","doc_other_clinic_address","doc_other_clinic_phone","doc_name","doc_age","doc_experience","doc_phone","doc_certificate","doc_selfie"))
def mh_doc_reg(m: types.Message):
    chat = m.chat.id
    st = user_state.get(chat)
    if not st: return
    step = st['step']; data = st.setdefault('data', {})
    txt = m.text.strip()
    if step == "doc_other_clinic_name":
        if not txt:
            bot.send_message(chat, "Klinika nomi bo'sh bo'lmasin. Qayta kiriting:")
            return
        data.setdefault('clinic_request', {})['name'] = txt
        st['step'] = "doc_other_clinic_address"
        bot.send_message(chat, "Klinika manzilini kiriting (bilmasangiz '-' yuboring):")
        return
    if step == "doc_other_clinic_address":
        data.setdefault('clinic_request', {})['address'] = clean_optional_text(txt, "Manzil ko'rsatilmagan")
        st['step'] = "doc_other_clinic_phone"
        bot.send_message(chat, "Klinika telefon raqamini kiriting (bilmasangiz '-' yuboring):")
        return
    if step == "doc_other_clinic_phone":
        data.setdefault('clinic_request', {})['phone'] = clean_optional_text(txt, "-")
        st['step'] = "doc_name"
        bot.send_message(chat, "Endi o'zingiz haqingizda ma'lumot kiritamiz.\nIltimos ismingizni kiriting:")
        return
    if step == "doc_name":
        data['name'] = txt; st['step'] = "doc_age"; bot.send_message(chat, "Yoshingizni kiriting:"); return
    if step == "doc_age":
        data['age'] = txt; st['step'] = "doc_experience"; bot.send_message(chat, "Tajriba (yillar):"); return
    if step == "doc_experience":
        data['experience'] = txt; st['step'] = "doc_phone"; bot.send_message(chat, "Telefon raqamingizni kiriting:"); return
    if step == "doc_phone":
        data['phone'] = txt; st['step'] = "doc_certificate"; bot.send_message(chat, "Iltimos sertifikat yoki diplom rasmini yuboring (photo):"); return

@bot.message_handler(
    func=lambda m: user_state.get(m.chat.id, {}).get('step') in ("doc_certificate", "doc_selfie"),
    content_types=['photo']
)
def mh_doc_photo(m: types.Message):
    chat = m.chat.id
    st = user_state.get(chat)
    # If it's part of doctor registration
    if st and st.get('step') in ("doc_certificate","doc_selfie"):
        step = st['step']; data = st['data']
        if step == "doc_certificate":
            data['certificate_file_id'] = m.photo[-1].file_id
            st['step'] = "doc_selfie"
            bot.send_message(chat, "✅ Sertifikat qabul qilindi!\nEndi o'zingizning aniq rasmingizni yuboring (selfie):")
            return
        if step == "doc_selfie":
            data['selfie_file_id'] = m.photo[-1].file_id
            pend_id = new_id("pd")
            pending_doctors[pend_id] = {
                "id": pend_id,
                "telegram_id": chat,
                "clinic_id": data.get('clinic_id'),
                "clinic_request": data.get('clinic_request'),
                "name": data.get('name'),
                "age": data.get('age'),
                "experience": data.get('experience'),
                "phone": data.get('phone'),
                "certificate_file_id": data.get('certificate_file_id'),
                "selfie_file_id": data.get('selfie_file_id'),
                "created_at": datetime.now(tz).isoformat()
            }
            clinic_name = clinic_label_from_data(data)
            caption = (f"🔔 <b>Yangi doktor arizasi</b>\nID: {pend_id}\nIsm: {pending_doctors[pend_id]['name']}\nYosh: {pending_doctors[pend_id]['age']}\n"
                       f"Tajriba: {pending_doctors[pend_id]['experience']}\nTel: {pending_doctors[pend_id]['phone']}\nKlinika: {clinic_name}")
            kb = InlineKeyboardMarkup()
            kb.row(mk("✅ Qabul qilish", f"admin|doc|approve|{pend_id}"), mk("❌ Rad etish", f"admin|doc|reject|{pend_id}"))
            try:
                bot.send_photo(ADMIN_ID, data['certificate_file_id'], caption="Sertifikat")
                bot.send_photo(ADMIN_ID, data['selfie_file_id'], caption=caption, parse_mode="HTML", reply_markup=kb)
            except Exception:
                bot.send_message(ADMIN_ID, caption + "\n(Rasmlar yuborilmadi)", parse_mode="HTML", reply_markup=kb)
            bot.send_message(chat, "Sizning arizangiz admin ga yuborildi. Javobni kuting. Rahmat!")
            send_random_sticker(chat)
            user_state.pop(chat, None)
            save_data()
            return
    # else: photo may be admin broadcast etc. Let other handlers handle.

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|doc|"))
def cb_admin_doc(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.message.chat.id, "Tugma formatida xatolik."); return
    action = parts[2]; pend_id = parts[3]
    pend = pending_doctors.get(pend_id)
    if not pend:
        bot.send_message(call.message.chat.id, "Ariza topilmadi yoki allaqachon ko'rilgan."); return
    if action == "approve":
        new_doc = {
            "id": f"doc_{pend_id}",
            "name": pend['name'],
            "phone": pend['phone'],
            "experience": pend.get('experience','-'),
            "price": "kelishiladi",
            "telegram_id": pend['telegram_id'],
            "rating_sum": 0,
            "rating_count": 0,
            "reviews": [],
            "photo_file_id": pend.get('selfie_file_id')
        }
        with data_lock:
            clinic, created_clinic = resolve_pending_clinic(pend)
            if not clinic:
                bot.send_message(
                    call.message.chat.id,
                    "Arizada klinika ma'lumoti topilmadi. Doktordan arizani qayta yuborishini so'rang yoki arizani rad eting."
                )
                return
            clinic['doctors'].append(new_doc)
        save_data()
        try:
            bot.send_message(pend['telegram_id'], f"🎉 Hurmatli {pend['name']}, siz qabul qilindingiz va {clinic['name']} ga qo'shildingiz. 🎉")
        except Exception:
            logger.exception("notify approved doctor failed")
        created_text = "\nYangi klinika ham yaratildi." if created_clinic else ""
        bot.send_message(call.message.chat.id, f"✅ {pend['name']} qabul qilindi va {clinic['name']} ga qo'shildi.{created_text}")
    else:
        try:
            bot.send_message(pend['telegram_id'], "Afsuski, arizangiz rad etildi. Qo'shimcha ma'lumot uchun admin bilan bog'laning.")
        except Exception:
            logger.exception("notify rejected doctor failed")
        bot.send_message(call.message.chat.id, "Ariza rad etildi.")
    pending_doctors.pop(pend_id, None)
    save_data()

# Doctor appointment actions
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("doctor|appt|"))
def cb_doctor_appt(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.message.chat.id, "Tugma noto'g'ri."); return
    cmd = parts[2]; appt_id = parts[3]
    with data_lock:
        appt = appointments.get(appt_id)
        if not appt:
            bot.send_message(call.message.chat.id, "Buyurtma topilmadi."); return
        doc = appt.get('doctor_obj')
        if not doc or doc.get('telegram_id') != call.from_user.id:
            bot.send_message(call.message.chat.id, "Siz ushbu uchrashuvga taalluqli doktor emassiz yoki ro'yxatdan o'tmagansiz."); return
        if appt.get('status') == 'cancelled':
            bot.send_message(call.message.chat.id, "Bu uchrashuv bekor qilingan."); return
        if cmd == "accept":
            appt['status'] = "accepted_by_doctor"
        elif cmd == "reschedule":
            user_state[call.from_user.id] = {"step":"doc_reschedule_choose_date","data":{"appt_id":appt_id}}
        else:
            bot.send_message(call.message.chat.id, "Noma'lum amal."); return
    if cmd == "accept":
        try:
            bot.send_message(appt['patient_chat'], f"✅ Doktor uchrashuvni tasdiqladi: {fmt_datetime_readable(appt['datetime'])}")
        except Exception:
            logger.exception("notify patient after doctor accept failed")
        schedule_reminder(appt_id)
        save_data()
    elif cmd == "reschedule":
        bot.send_message(call.from_user.id, "Yangi sanani tanlang (doctor):", reply_markup=date_buttons(14))
