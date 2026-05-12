from clinic_bot.shared import *
from clinic_bot.helpers import mk, new_id
from clinic_bot.storage import save_data

# ---------------- ONLAYN TASHHIS / PROFESSIONAL TICKET SYSTEM ----------------
@bot.message_handler(func=lambda m: m.text == "🔎 Onlay tashhis")
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
        bot.send_message(chat, "Doktor chaqiruvi so'rovi qabul qilindi. Adminlar bilan bog'lanadi.")
        for aid in admins:
            try: bot.send_message(aid, f"📞 Chaquv so'rovi: foydalanuvchi {chat} Doktor chaqiruvi so‘radi.")
            except Exception: pass

@bot.message_handler(func=lambda m: user_state.get(m.chat.id,{}).get('step') == "diag_wait_text")
def mh_diag_text(m: types.Message):
    chat = m.chat.id; txt = m.text.strip()
    req_id = new_id("diag")
    diagnosis_requests[req_id] = {
        "id": req_id,
        "user_chat": chat,
        "user_first_name": m.from_user.first_name,
        "text": txt,
        "created_at": datetime.now(tz).isoformat(),
        "status": "pending",
        "assigned_admin": None,
        "messages": [],
        "notify_msgs": []   # will store {"admin_id","chat_id","message_id"} for each admin notification
    }
    kb = InlineKeyboardMarkup()
    kb.row(mk("✅ Qabul qilaman", f"diag_admin|accept|{req_id}"), mk("❌ Rad etish", f"diag_admin|reject|{req_id}"))
    # notify all admins and store message ids to later edit reply_markup when accepted
    for aid in admins:
        try:
            msg = bot.send_message(aid, f"🔔 <b>Yangi tashhis so'rovi</b>\nID: {req_id}\nFoydalanuvchi: {chat} ({m.from_user.first_name})\nMatn:\n{txt}", parse_mode="HTML", reply_markup=kb)
            diagnosis_requests[req_id]['notify_msgs'].append({"admin_id": aid, "chat_id": msg.chat.id, "message_id": msg.message_id})
        except Exception:
            logger.exception("notify admin failed")
    user_state.pop(chat, None); bot.send_message(chat, "Xabaringiz adminlarga yuborildi. Tez orada kimdir qabul qiladi."); save_data()

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
        # if already assigned
        if req.get('assigned_admin'):
            bot.send_message(call.message.chat.id, "Ushbu so'rovni boshqa admin qabul qilgan."); return
        # assign
        req['assigned_admin'] = call.from_user.id
        req['status'] = "assigned"
        active_diag_chats[req['user_chat']] = call.from_user.id
        admin_active_diag[call.from_user.id] = req['user_chat']
        save_data()
        # remove inline buttons from all admin notifications
        for nm in req.get('notify_msgs', []):
            try:
                bot.edit_message_reply_markup(nm['chat_id'], nm['message_id'], reply_markup=None)
            except Exception:
                pass
        # notify accepting admin and the user
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
        # remove buttons for all admin notifications
        for nm in req.get('notify_msgs', []):
            try:
                bot.edit_message_reply_markup(nm['chat_id'], nm['message_id'], reply_markup=None)
            except Exception:
                pass
        save_data()
        bot.send_message(call.from_user.id, "So'rov rad etildi.")
        try:
            bot.send_message(req['user_chat'], "Afsuski, so'rovingiz hozircha qabul qilinmadi. Keyinroq urinib ko'ring.")
        except Exception:
            pass
        return

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
