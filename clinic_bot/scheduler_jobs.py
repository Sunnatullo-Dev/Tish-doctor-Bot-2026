from clinic_bot.shared import *
from clinic_bot.helpers import fmt_datetime_readable, mk

# ---------------- SCHEDULER: reminders & rating prompt ----------------
REMINDER_ELIGIBLE_APPT_STATUSES = {
    'pending',
    'accepted',
    'accepted_by_doctor',
    'rescheduled_by_admin',
    'rescheduled_by_patient',
    'rescheduled_by_doctor',
}

RATING_ELIGIBLE_APPT_STATUSES = {
    'accepted',
    'accepted_by_doctor',
    'rescheduled_by_admin',
    'rescheduled_by_patient',
    'rescheduled_by_doctor',
}

TERMINAL_APPT_STATUSES = {
    'cancelled',
    'cancelled_clinic_deleted',
    'cancelled_doctor_deleted',
    'completed',
    'closed',
    'rejected',
}


def appt_status(appt):
    return str((appt or {}).get('status') or '').strip().lower()


def is_terminal_appointment(appt):
    status = appt_status(appt)
    return status in TERMINAL_APPT_STATUSES or status.startswith('cancelled')


def should_schedule_appointment_jobs(appt):
    if not appt or not appt.get('datetime'):
        return False
    if is_terminal_appointment(appt):
        return False
    return appt_status(appt) in REMINDER_ELIGIBLE_APPT_STATUSES


def should_schedule_rating_prompt(appt):
    if not should_schedule_appointment_jobs(appt):
        return False
    if appt.get('rated'):
        return False
    return appt_status(appt) in RATING_ELIGIBLE_APPT_STATUSES


def cancel_appointment_jobs(appt_id):
    for job_id in (f"rem_{appt_id}", f"rating_{appt_id}"):
        try:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
        except Exception:
            logger.exception("failed to remove scheduled job %s", job_id)


def schedule_reminder(appt_id):
    appt = appointments.get(appt_id)
    if not appt:
        cancel_appointment_jobs(appt_id)
        return False
    if not should_schedule_appointment_jobs(appt):
        cancel_appointment_jobs(appt_id)
        logger.info("Skipped scheduler jobs for inactive appointment %s (%s)", appt_id, appt.get('status'))
        return False
    job_id = f"rem_{appt_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            logger.exception("failed to remove existing job")
    appt_dt = appt.get('datetime')
    if not appt_dt:
        cancel_appointment_jobs(appt_id)
        return False
    if appt_dt.tzinfo is None:
        appt_dt = tz.localize(appt_dt)
    now = datetime.now(tz)
    # reminder offset: per-clinic config (hours), default 1h
    clinic = appt.get('clinic') or (clinics[0] if clinics else {})
    try:
        hours_before = float(clinic.get('reminder_hours_before', 1))
    except Exception:
        hours_before = 1
    remind_time = appt_dt - timedelta(hours=hours_before)
    # If preferred remind_time already passed but appointment is still in the future
    # by at least 5 minutes, send a short-notice reminder soon.
    if remind_time <= now and appt_dt - now >= timedelta(minutes=5):
        remind_time = now + timedelta(minutes=1)
    if remind_time > now:
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
        if should_schedule_rating_prompt(appt) and rating_run > datetime.now(tz):
            scheduler.add_job(send_rating_prompt, 'date', run_date=rating_run, args=[appt_id], id=rating_job_id)
            logger.info("Scheduled rating %s -> %s", appt_id, rating_run.isoformat())
    except Exception:
        logger.exception("failed scheduling rating job")
    return True

def send_reminder_job(appt_id):
    appt = appointments.get(appt_id)
    if not appt:
        cancel_appointment_jobs(appt_id)
        return
    if not should_schedule_appointment_jobs(appt):
        cancel_appointment_jobs(appt_id)
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
    if not appt:
        cancel_appointment_jobs(appt_id)
        return
    if not should_schedule_rating_prompt(appt):
        cancel_appointment_jobs(appt_id)
        return
    try:
        kb = InlineKeyboardMarkup()
        for i in range(1,6):
            kb.add(mk(f"⭐ {i}", f"rate|{appt_id}|{i}"))
        bot.send_message(appt['patient_chat'], f"Uchrashuv uchun rahmat! Iltimos doktorni baholang: {fmt_datetime_readable(appt['datetime'])}", reply_markup=kb)
    except Exception:
        logger.exception("send rating prompt failed")
