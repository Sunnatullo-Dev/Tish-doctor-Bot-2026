from clinic_bot.shared import *
from clinic_bot.channel_gate import ensure_user_subscribed
from clinic_bot.helpers import *
from clinic_bot.keyboards import date_buttons, time_buttons
from clinic_bot.scheduler_jobs import schedule_reminder
from clinic_bot.storage import save_data

# ---------------- HANDLERS ----------------

def send_main_menu(chat, name=""):
    greet = f"Assalomu Aleykum {name}" if name else "Assalomu Aleykum"
    kb = InlineKeyboardMarkup()
    kb.row(mk("Qabulga yozilish", "flow|booking"), mk("Men doktorman", "flow|doctor"))
    kb.row(mk("Klinikalar ro'yxati", "list_clinics"), mk("Mening yozuvlarim", "flow|my_appts"))
    kb.row(mk("Onlay tashhis", "diag_menu"))
    send_random_sticker(chat)
    bot.send_message(chat, f"<b>{greet}</b>\n\nQuyidagilardan birini tanlang:", parse_mode="HTML", reply_markup=kb)


# /start
@bot.message_handler(commands=['start'])
def cmd_start(m: types.Message):
    chat = m.chat.id
    uid = m.from_user.id
    users.add(uid)
    now_iso = datetime.now(tz).isoformat()
    ui = users_info.get(str(uid))
    if not ui:
        users_info[str(uid)] = {"first_start": now_iso, "starts": 1}
    else:
        ui['starts'] = ui.get('starts', 0) + 1
    name = (m.from_user.first_name or "").strip()
    user_state[chat] = {"step":"start", "data":{}}
    if not ensure_user_subscribed(chat, uid):
        save_data()
        return
    send_main_menu(chat, name)
    save_data()

@bot.callback_query_handler(func=lambda c: c.data == "check_subscriptions")
def cb_check_subscriptions(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    uid = call.from_user.id
    if not ensure_user_subscribed(chat, uid):
        return
    name = (call.from_user.first_name or "").strip()
    user_state[chat] = {"step":"start", "data":{}}
    send_main_menu(chat, name)

# Flow buttons (booking/doctor/help/my_appts)
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("flow|"))
def cb_flow(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    if not ensure_user_subscribed(chat, call.from_user.id):
        return
    action = call.data.split("|",1)[1]
    if action == "booking":
        user_state[chat] = {"step":"booking_start", "data":{}}
        kb = InlineKeyboardMarkup()
        kb.row(mk("🏥 Klinikalar ro'yxati", "list_clinics"))
        bot.send_message(chat, "Klinikani tanlang:", reply_markup=kb)
        return
    if action == "doctor":
        user_state[chat] = {"step":"doc_choose_clinic", "data":{}}
        kb = InlineKeyboardMarkup()
        for c in clinics:
            kb.add(mk(f"{c['name']} ({c['region']})", f"docreg|clinic|{c['id']}"))
        kb.row(mk("Boshqa klinika (yozaman)", "docreg|clinic|other"))
        bot.send_message(chat, "Qaysi klinikada ishlaysiz? Tanlang:", reply_markup=kb)
        return
    if action == "my_appts":
        user_appts = [a for a in appointments.values() if a['patient_chat']==chat]
        if not user_appts:
            bot.send_message(chat, "Sizda yozuvlar mavjud emas.")
            return
        for a in sorted(user_appts, key=lambda x: x.get('datetime') or datetime.now(tz)):
            doc = a.get('doctor_obj'); clinic = a.get('clinic')
            kb = InlineKeyboardMarkup()
            kb.row(mk("❌ Bekor qilish", f"appt|cancel|{a['id']}"), mk("🔁 Vaqtni o'zgartirish", f"appt|reschedule|{a['id']}"))
            kb.row(mk("📱 Telefonni yuborish", f"phone_req|{a['id']}"))
            bot.send_message(chat, f"📌 ID: {a['id']}\nKlinika: {clinic['name'] if clinic else '---'}\nDoctor: {doc['name'] if doc else '---'}\nVaqt: {fmt_datetime_readable(a.get('datetime'))}\nHolat: {a.get('status')}", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("phone_req|"))
def cb_phone_req(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    appt_id = call.data.split("|", 1)[1]
    appt = appointments.get(appt_id)
    if not appt or appt.get("patient_chat") != call.message.chat.id:
        bot.send_message(call.message.chat.id, "Yozuv topilmadi.")
        return
    phone = appt.get("patient_phone") or "Telefon kiritilmagan"
    bot.send_message(call.message.chat.id, f"Ushbu yozuvdagi telefon: {phone}")

# list clinics
@bot.callback_query_handler(func=lambda c: c.data == "list_clinics")
def cb_list_clinics(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    if not ensure_user_subscribed(chat, call.from_user.id):
        return
    kb = InlineKeyboardMarkup()
    for c in clinics:
        kb.add(mk(f"{c['name']} — {c['address']}", f"clinic|{c['id']}"))
    bot.send_message(chat, "Klinikani tanlang:", reply_markup=kb)

# clinic selection
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("clinic|"))
def cb_clinic(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    if not ensure_user_subscribed(chat, call.from_user.id):
        return
    cid = call.data.split("|",1)[1]
    clinic = find_clinic_by_id(cid)
    if not clinic:
        bot.send_message(chat, "Klinika topilmadi.")
        return
    user_state.setdefault(chat, {})['data'] = user_state.get(chat, {}).get('data', {})
    user_state[chat]['data']['clinic'] = clinic
    user_state[chat]['step'] = "choosing_doctor"
    txt = f"🏥 <b>{clinic['name']}</b>\n{clinic['address']}\n📞 {clinic['manager_phone']}\n\n<b>Doktorlar:</b>"
    kb = InlineKeyboardMarkup()
    if clinic['doctors']:
        for d in clinic['doctors']:
            kb.add(mk(f"{d['name']} — {d.get('experience','')}", f"doctor|{d['id']}|{clinic['id']}"))
    else:
        kb.add(mk("Hozircha doktorlar yo'q", "nodoc"))
    kb.row(mk("📞 Klinika bilan bog'lanish", f"contact|{clinic['id']}"))
    bot.send_message(chat, txt, parse_mode="HTML", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "nodoc")
def cb_nodoc(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Bu klinikada hozir doktorlar yo'q. Agar siz doktor bo'lsangiz 'Men doktorman' orqali ro'yxatdan o'ting.")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("contact|"))
def cb_contact(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not ensure_user_subscribed(call.message.chat.id, call.from_user.id):
        return
    cid = call.data.split("|",1)[1]
    clinic = find_clinic_by_id(cid)
    if clinic:
        bot.send_message(call.message.chat.id, f"📞 Klinika raqami: {clinic['manager_phone']}")
    else:
        bot.send_message(call.message.chat.id, "Klinika topilmadi.")

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("back|"))
def cb_back(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    target = call.data.split("|", 1)[1]
    st = user_state.get(chat, {})
    if target == "to_clinic":
        kb = InlineKeyboardMarkup()
        for c in clinics:
            kb.add(mk(f"{c['name']} ({c['region']})", f"clinic|{c['id']}"))
        bot.send_message(chat, "Klinikani tanlang:", reply_markup=kb)
        return
    if target == "to_date":
        step = st.get("step")
        if step == "admin_reschedule_choose_time":
            st["step"] = "admin_reschedule_choose_date"
        elif step == "patient_reschedule_choose_time":
            st["step"] = "patient_reschedule_choose_date"
        elif step == "doc_reschedule_choose_time":
            st["step"] = "doc_reschedule_choose_date"
        else:
            st["step"] = "choosing_date"
        bot.send_message(chat, "Sanani tanlang:", reply_markup=date_buttons(14))

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("doctor|") and not c.data.startswith("doctor|appt|"))
def cb_doctor(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not ensure_user_subscribed(call.message.chat.id, call.from_user.id):
        return
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.send_message(call.message.chat.id, "Tugma noto'g'ri.")
        return
    docid = parts[1]; cid = parts[2]
    clinic = find_clinic_by_id(cid)
    if not clinic:
        bot.send_message(call.message.chat.id, "Klinika topilmadi."); return
    doctor = next((d for d in clinic['doctors'] if d['id']==docid), None)
    if not doctor:
        bot.send_message(call.message.chat.id, "Shifokor topilmadi."); return
    chat = call.message.chat.id
    user_state.setdefault(chat, {})['data'] = {}
    user_state[chat]['data']['clinic'] = clinic
    user_state[chat]['data']['doctor'] = doctor
    user_state[chat]['step'] = "choosing_date"
    caption = f"👨‍⚕️ <b>{doctor['name']}</b>\nTajriba: {doctor.get('experience','')}\nNarxi: {doctor.get('price','kelishiladi')}\nReyting: {round(get_doctor_rating(doctor),1)}"
    if doctor.get('photo_file_id'):
        try:
            bot.send_photo(chat, doctor['photo_file_id'], caption=caption, parse_mode="HTML")
        except Exception:
            bot.send_message(chat, caption, parse_mode="HTML")
    else:
        bot.send_message(chat, caption, parse_mode="HTML")
    bot.send_message(chat, "📅 Sana tanlash:", reply_markup=date_buttons(14))

# central date/time handler
@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("date|") or c.data.startswith("time|")))
def cb_date_time(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    st = user_state.get(chat, {})
    step = st.get('step')
    data = st.get('data', {})
    # DATE
    if call.data.startswith("date|"):
        payload = call.data.split("|",1)[1]
        try:
            chosen_date = date.fromisoformat(payload)
        except Exception:
            bot.send_message(chat, "Sana formati xato."); return
        if step == "choosing_date":
            data['chosen_date'] = chosen_date
            st['step'] = "choosing_time"
            bot.send_message(chat, "⏰ Vaqt tanlang:", reply_markup=time_buttons(chosen_date))
            return
        if step == "admin_reschedule_choose_date":
            st['data']['chosen_date'] = chosen_date
            st['step'] = "admin_reschedule_choose_time"
            bot.send_message(chat, "Admin: vaqtni tanlang:", reply_markup=time_buttons(chosen_date))
            return
        if step == "patient_reschedule_choose_date":
            st['data']['chosen_date'] = chosen_date
            st['step'] = "patient_reschedule_choose_time"
            bot.send_message(chat, "Yangi vaqtni tanlang:", reply_markup=time_buttons(chosen_date))
            return
        if step == "doc_reschedule_choose_date":
            st['data']['chosen_date'] = chosen_date
            st['step'] = "doc_reschedule_choose_time"
            bot.send_message(chat, "Doctor: vaqtni tanlang:", reply_markup=time_buttons(chosen_date))
            return
        return
    # TIME
    if call.data.startswith("time|"):
        tstr = call.data.split("|",1)[1]
        try:
            hh, mm = map(int, tstr.split(":"))
        except:
            bot.send_message(chat, "Vaqt formatida xatolik."); return
        if step == "choosing_time":
            chosen_date = data.get('chosen_date')
            if not chosen_date:
                bot.send_message(chat, "Sana topilmadi."); return
            dt_local = datetime.combine(chosen_date, time(hh, mm))
            dt_local = tz.localize(dt_local)
            data['datetime'] = dt_local
            st['step'] = "confirm_time"
            kb = InlineKeyboardMarkup()
            kb.row(mk("✅ Ha, vaqt to'g'ri", "time_confirm|yes"), mk("❌ Yo'q, qayta tanlash", "time_confirm|no"))
            bot.send_message(chat, f"<b>Siz tanladingiz: {fmt_datetime_readable(dt_local)}</b>\n\nVaqt to'g'rimi?", parse_mode="HTML", reply_markup=kb)
            return
        # admin/doc/patient reschedule handling (same as earlier; updated save_data calls)
        if step == "admin_reschedule_choose_time":
            appt_id = st['data'].get('appt_id')
            appt = appointments.get(appt_id)
            if not appt:
                bot.send_message(chat, "Buyurtma topilmadi."); user_state.pop(chat, None); return
            chosen_date = st['data'].get('chosen_date')
            if not chosen_date:
                bot.send_message(chat, "Sana topilmadi."); return
            dt_local = tz.localize(datetime.combine(chosen_date, time(hh, mm)))
            appt['datetime'] = dt_local; appt['status'] = "rescheduled_by_admin"
            try: bot.send_message(appt['patient_chat'], f"Sizning uchrashuvingiz admin tomonidan yangi vaqtda belgilandi: {fmt_datetime_readable(dt_local)}.")
            except Exception: logger.exception("notify patient failed")
            doc = appt.get('doctor_obj')
            if doc and doc.get('telegram_id'):
                try: bot.send_message(doc['telegram_id'], f"Uchrashuv vaqti admin tomonidan o'zgardi: {fmt_datetime_readable(dt_local)}")
                except Exception: logger.exception("notify doctor failed")
            schedule_reminder(appt_id); user_state.pop(chat, None)
            bot.send_message(chat, "Vaqt yangilandi va bemorga xabar berildi."); save_data(); return
        if step == "patient_reschedule_choose_time":
            appt_id = st['data'].get('appt_id'); appt = appointments.get(appt_id)
            if not appt:
                bot.send_message(chat, "Buyurtma topilmadi."); user_state.pop(chat, None); return
            chosen_date = st['data'].get('chosen_date'); dt_local = tz.localize(datetime.combine(chosen_date, time(hh, mm)))
            appt['datetime'] = dt_local; appt['status'] = "rescheduled_by_patient"
            try: bot.send_message(chat, f"Vaqt o'zgartirildi: {fmt_datetime_readable(dt_local)}. Doktor va adminga xabar yuborildi.")
            except Exception: logger.exception("notify patient failed")
            doc = appt.get('doctor_obj')
            if doc and doc.get('telegram_id'):
                try: bot.send_message(doc['telegram_id'], f"Bemor uchrashuv vaqtini o'zgartirdi: {fmt_datetime_readable(dt_local)}")
                except Exception: logger.exception("notify doctor failed")
            try: bot.send_message(ADMIN_ID, f"Uchrashuv {appt_id} bemor tomonidan o'zgartirildi: {fmt_datetime_readable(dt_local)}")
            except Exception: logger.exception("notify admin failed")
            schedule_reminder(appt_id); user_state.pop(chat, None); save_data(); return
        if step == "doc_reschedule_choose_time":
            appt_id = st['data'].get('appt_id'); appt = appointments.get(appt_id)
            if not appt:
                bot.send_message(chat, "Buyurtma topilmadi."); user_state.pop(chat, None); return
            chosen_date = st['data'].get('chosen_date'); dt_local = tz.localize(datetime.combine(chosen_date, time(hh, mm)))
            appt['datetime'] = dt_local; appt['status'] = "rescheduled_by_doctor"
            try: bot.send_message(appt['patient_chat'], f"Doktor tomonidan yangi vaqt belgilandi: {fmt_datetime_readable(dt_local)}")
            except Exception: logger.exception("notify patient failed")
            try: bot.send_message(ADMIN_ID, f"Uchrashuv {appt_id} doctor tomonidan o'zgartirildi: {fmt_datetime_readable(dt_local)}")
            except Exception: logger.exception("notify admin failed")
            schedule_reminder(appt_id); user_state.pop(chat, None); save_data(); return

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("time_confirm|"))
def cb_time_confirm(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    chat = call.message.chat.id
    ans = call.data.split("|",1)[1]
    if user_state.get(chat, {}).get('step') != "confirm_time":
        bot.send_message(chat, "Hech qanday tasdiqlanayotgan vaqt topilmadi."); return
    if ans == "yes":
        user_state[chat]['step'] = "enter_name"
        bot.send_message(chat, "Vaqt tasdiqlandi ✅\nIltimos ismingizni kiriting (yoki 'o'tkazish'):")
    else:
        user_state[chat]['step'] = "choosing_date"
        bot.send_message(chat, "Yaxshi, qayta sana tanlang:", reply_markup=date_buttons(14))

# name and phone
@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "enter_name")
def mh_enter_name(m: types.Message):
    chat = m.chat.id
    txt = m.text.strip()
    if txt.lower() in ["yoq","bekor","no","cancel","o'tkazish","otkazish"]:
        user_state[chat]['data']['patient_name'] = "Anonim"
    else:
        user_state[chat]['data']['patient_name'] = txt
    user_state[chat]['step'] = "enter_phone"
    kb = InlineKeyboardMarkup()
    kb.row(mk("📱 Avtomatik yuborish", "phone_choice|auto"), mk("✍️ Qo'lda kiritish", "phone_choice|manual"))
    bot.send_message(chat, "Telefonni qanday yubormoqchisiz?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("phone_choice|"))
def cb_phone_choice(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    mode = call.data.split("|",1)[1]
    chat = call.message.chat.id
    if mode == "auto":
        rk = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        rk.add(KeyboardButton("📲 Kontaktni yuborish", request_contact=True))
        bot.send_message(chat, "Iltimos 'Kontaktni yuborish' tugmasini bosing:", reply_markup=rk)
        user_state[chat]['step'] = "await_contact_auto"
    else:
        user_state[chat]['step'] = "await_contact_manual"
        bot.send_message(chat, "Iltimos telefon raqamingizni matn ko'rinishida yuboring (masalan +998901234567):")

@bot.message_handler(
    func=lambda m: (
        user_state.get(m.chat.id, {}).get('step') == "await_contact_auto"
        or admin_add_state.get(m.from_user.id) == "await_admin_id"
    ),
    content_types=['contact']
)
def mh_contact(m: types.Message):
    chat = m.chat.id
    st = user_state.get(chat, {})
    if st and st.get('step') == "await_contact_auto":
        phone = m.contact.phone_number
        user_state[chat]['data']['patient_phone'] = phone
        create_appointment_from_state(chat)
        return
    # admin add via contact
    if m.from_user.id in admin_add_state and admin_add_state[m.from_user.id] == "await_admin_id":
        if m.contact.user_id:
            new_admin = m.contact.user_id
            admins.add(new_admin)
            admin_history.append({"added_by": m.from_user.id, "new_admin": new_admin, "ts": datetime.now(tz).isoformat()})
            admin_add_state.pop(m.from_user.id, None)
            bot.send_message(m.chat.id, f"✅ {new_admin} adminlarga qo'shildi.")
            save_data()
            return

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "await_contact_manual")
def mh_contact_manual(m: types.Message):
    chat = m.chat.id
    phone = m.text.strip()
    user_state[chat]['data']['patient_phone'] = phone
    create_appointment_from_state(chat)

def create_appointment_from_state(chat):
    data = user_state[chat]['data']
    appt_id = new_id("appt")
    appt = {
        "id": appt_id,
        "patient_chat": chat,
        "patient_name": data.get('patient_name'),
        "patient_phone": data.get('patient_phone'),
        "clinic": data.get('clinic'),
        "doctor_obj": data.get('doctor'),
        "datetime": data.get('datetime'),
        "status": "pending",
        "created_at": datetime.now(tz).isoformat(),
        "rated": False
    }
    appointments[appt_id] = appt
    try:
        schedule_reminder(appt_id)
    except Exception:
        logger.exception("schedule reminder failed on create")
    txt = (f"🆕 <b>Yangi buyurtma</b>\nID: {appt_id}\nIsm: {appt['patient_name']}\nTel: {appt['patient_phone']}\n"
           f"Klinika: {appt['clinic']['name'] if appt['clinic'] else '---'}\nDoctor: {appt['doctor_obj']['name'] if appt['doctor_obj'] else '---'}\n"
           f"Vaqt: {fmt_datetime_readable(appt['datetime'])}")
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Qabul qilish", f"admin|appt|accept|{appt_id}"), mk("❌ Bekor qilish", f"admin|appt|cancel|{appt_id}"))
    kb.row(mk("🕑 Vaqtni o'zgartirish", f"admin|appt|reschedule|{appt_id}"))
    # send to all admins and main admin specifically
    for aid in list(admins):
        try:
            bot.send_message(aid, txt, parse_mode="HTML", reply_markup=kb)
        except Exception:
            logger.exception("send to admin failed")
    bot.send_message(chat, "Sizning so'rovingiz admin ga yuborildi. Javobni kuting.")
    send_random_sticker(chat)
    user_state.pop(chat, None)
    save_data()

def cancel_appointment_jobs(appt_id):
    for job_id in (f"rem_{appt_id}", f"rating_{appt_id}"):
        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        except Exception:
            logger.exception("failed to remove scheduled job %s", job_id)

# Admin handles appointment actions
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin|appt|"))
def cb_admin_appt(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id):
        bot.send_message(call.message.chat.id, "Siz admin emassiz."); return
    parts = call.data.split("|")
    if len(parts) < 4:
        bot.send_message(call.message.chat.id, "Tugma noto'g'ri."); return
    action = parts[2]; appt_id = parts[3]
    appt = appointments.get(appt_id)
    if not appt:
        bot.send_message(call.message.chat.id, "Buyurtma topilmadi."); return
    if action == "accept":
        appt['status'] = "accepted"
        try:
            bot.send_message(appt['patient_chat'], f"✅ Sizning buyurtmangiz qabul qilindi: {fmt_datetime_readable(appt['datetime'])}")
        except Exception:
            logger.exception("notify patient on accept failed")
        doc = appt.get('doctor_obj')
        if doc and doc.get('telegram_id'):
            try:
                bot.send_message(doc['telegram_id'], f"✅ Sizga yangi uchrashuv: {appt['patient_name']} — {fmt_datetime_readable(appt['datetime'])}",
                                 reply_markup=InlineKeyboardMarkup().row(
                                     mk("Qabul qilaman", f"doctor|appt|accept|{appt_id}"),
                                     mk("Vaqtni o'zgartirish", f"doctor|appt|reschedule|{appt_id}")
                                 ))
            except Exception:
                logger.exception("notify doctor failed")
        try:
            schedule_reminder(appt_id)
        except Exception:
            logger.exception("schedule reminder on admin accept failed")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        save_data()
    elif action == "cancel":
        appt['status'] = "cancelled"
        cancel_appointment_jobs(appt_id)
        try:
            bot.send_message(appt['patient_chat'], "Afsus, buyurtmangiz bekor qilindi (admin tomonidan).")
        except Exception:
            logger.exception("notify patient on cancel failed")
        save_data()
    elif action == "reschedule":
        user_state[call.from_user.id] = {"step":"admin_reschedule_choose_date", "data":{"appt_id": appt_id}}
        bot.send_message(call.from_user.id, "Yangi sanani tanlang (admin):", reply_markup=date_buttons(14))

# appointment cancel/reschedule from user's /myappts
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("appt|"))
def cb_appt_user(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.send_message(call.message.chat.id, "Tugma noto'g'ri."); return
    action = parts[1]; appt_id = parts[2]
    appt = appointments.get(appt_id)
    if not appt:
        bot.send_message(call.message.chat.id, "Buyurtma topilmadi."); return
    if appt.get('patient_chat') != call.from_user.id:
        bot.send_message(call.message.chat.id, "Bu yozuv sizga tegishli emas."); return
    if action == "cancel":
        appt['status'] = "cancelled"
        cancel_appointment_jobs(appt_id)
        bot.send_message(call.message.chat.id, "Yozuv bekor qilindi.")
        doc = appt.get('doctor_obj')
        if doc and doc.get('telegram_id'):
            try:
                bot.send_message(doc['telegram_id'], f"Bemorga bog'liq uchrashuv bekor qilindi: {appt['patient_name']} — {fmt_datetime_readable(appt['datetime'])}")
            except Exception:
                logger.exception("notify doctor on cancel failed")
        save_data()
    elif action == "reschedule":
        appt['status'] = 'reschedule_requested'
        user_state[call.from_user.id] = {"step":"patient_reschedule_choose_date","data":{"appt_id":appt_id}}
        bot.send_message(call.from_user.id, "Yangi sanani tanlang:", reply_markup=date_buttons(14))
        try:
            bot.send_message(ADMIN_ID, f"🔁 Bemor {appt['patient_name']} uchrashuvini qayta belgilashni so'radi: {appt['id']}")
        except Exception:
            logger.exception("notify admin about reschedule request failed")
        save_data()

# rating handler
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("rate|"))
def cb_rate(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    parts = call.data.split("|")
    if len(parts) < 3:
        bot.send_message(call.message.chat.id, "Tugma noto'g'ri."); return
    appt_id = parts[1]
    try:
        score = int(parts[2])
    except ValueError:
        bot.send_message(call.message.chat.id, "Baho noto'g'ri formatda."); return
    appt = appointments.get(appt_id)
    if not appt:
        bot.send_message(call.message.chat.id, "Buyurtma topilmadi."); return
    if appt.get('patient_chat') != call.from_user.id:
        bot.send_message(call.message.chat.id, "Bu yozuv sizga tegishli emas."); return
    if appt.get('rated'):
        bot.send_message(call.message.chat.id, "Bu uchrashuv avval baholangan."); return
    if score < 1 or score > 5:
        bot.send_message(call.message.chat.id, "Baho 1 dan 5 gacha bo'lishi kerak."); return
    doc = appt.get('doctor_obj')
    if not doc:
        bot.send_message(call.message.chat.id, "Doctor ma'lumoti topilmadi."); return
    doc['rating_sum'] = doc.get('rating_sum',0) + score
    doc['rating_count'] = doc.get('rating_count',0) + 1
    appt['rated'] = True
    bot.send_message(call.message.chat.id, "Rahmat! Bahoyingiz qabul qilindi.")
    user_state[call.message.chat.id] = {"step":"leave_review","data":{"appt_id":appt_id}}
    bot.send_message(call.message.chat.id, "Agar xohlasangiz qisqacha fikringizni yozing (yoki 'o'tkazish'):")
    save_data()

@bot.message_handler(func=lambda m: user_state.get(m.chat.id, {}).get('step') == "leave_review")
def mh_leave_review(m: types.Message):
    chat = m.chat.id; txt = m.text.strip()
    st = user_state.get(chat)
    if not st:
        return
    appt_id = st['data'].get('appt_id')
    appt = appointments.get(appt_id)
    if not appt:
        bot.send_message(chat, "Buyurtma topilmadi."); user_state.pop(chat,None); return
    doc = appt.get('doctor_obj')
    if doc is not None and txt.lower() not in ("o'tkazish","otkazish","skip"):
        doc.setdefault('reviews', []).append({"from": chat, "text": txt, "date": datetime.now(tz).isoformat()})
        bot.send_message(chat, "Rahmat! Fikringiz qabul qilindi.")
    else:
        bot.send_message(chat, "Rahmat!")
    user_state.pop(chat,None)
    save_data()
