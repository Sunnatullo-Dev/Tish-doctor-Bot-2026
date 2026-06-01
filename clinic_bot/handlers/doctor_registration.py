from clinic_bot.shared import *
from clinic_bot.helpers import *
from clinic_bot.keyboards import date_buttons
from clinic_bot.scheduler_jobs import schedule_reminder
from clinic_bot.storage import save_data


# Doctor appointment actions (doctor accepts / reschedules their assigned appointment)
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
