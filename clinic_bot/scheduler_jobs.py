from clinic_bot.shared import *
from clinic_bot.helpers import fmt_datetime_readable, mk

# ---------------- SCHEDULER: reminders & rating prompt ----------------
def schedule_reminder(appt_id):
    appt = appointments.get(appt_id)
    if not appt:
        return
    if appt.get('status') == 'cancelled':
        return
    job_id = f"rem_{appt_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            logger.exception("failed to remove existing job")
    appt_dt = appt.get('datetime')
    if not appt_dt:
        return
    if appt_dt.tzinfo is None:
        appt_dt = tz.localize(appt_dt)
    remind_time = appt_dt - timedelta(hours=1)
    if remind_time > datetime.now(tz):
        try:
            scheduler.add_job(send_reminder_job, 'date', run_date=remind_time, args=[appt_id], id=job_id)
            logger.info("Scheduled reminder %s -> %s", appt_id, remind_time.isoformat())
        except Exception:
            logger.exception("scheduling reminder failed")
    # rating prompt 1 hour after appointment
    try:
        rating_job_id = f"rating_{appt_id}"
        rating_run = appt_dt + timedelta(hours=1)
        existing_rating = scheduler.get_job(rating_job_id)
        if existing_rating:
            try:
                scheduler.remove_job(rating_job_id)
            except Exception:
                logger.exception("failed to remove existing rating job")
        if rating_run > datetime.now(tz):
            scheduler.add_job(send_rating_prompt, 'date', run_date=rating_run, args=[appt_id], id=rating_job_id)
            logger.info("Scheduled rating %s -> %s", appt_id, rating_run.isoformat())
    except Exception:
        logger.exception("failed scheduling rating job")

def send_reminder_job(appt_id):
    appt = appointments.get(appt_id)
    if not appt: return
    if appt.get('status') == 'cancelled':
        return
    try:
        bot.send_message(appt['patient_chat'], f"⏰ Eslatma: Sizning uchrashuvingiz {fmt_datetime_readable(appt['datetime'])}. 1 soat qoldi.")
    except Exception:
        logger.exception("failed to send reminder to patient")
    doc = appt.get('doctor_obj')
    if doc and doc.get('telegram_id'):
        try:
            bot.send_message(doc['telegram_id'], f"⏰ Eslatma: {appt['patient_name']} uchrashuvi {fmt_datetime_readable(appt['datetime'])}.")
        except Exception:
            logger.exception("failed to send reminder to doctor")

def send_rating_prompt(appt_id):
    appt = appointments.get(appt_id)
    if not appt: return
    if appt.get('status') == 'cancelled':
        return
    if appt.get('rated'):
        return
    try:
        kb = InlineKeyboardMarkup()
        for i in range(1,6):
            kb.add(mk(f"⭐ {i}", f"rate|{appt_id}|{i}"))
        bot.send_message(appt['patient_chat'], f"Uchrashuv uchun rahmat! Iltimos doktorni baholang: {fmt_datetime_readable(appt['datetime'])}", reply_markup=kb)
    except Exception:
        logger.exception("send rating prompt failed")
