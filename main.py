import atexit

from clinic_bot.handlers import register_all
from clinic_bot.scheduler_jobs import schedule_reminder, should_schedule_appointment_jobs
from clinic_bot.shared import appointments, bot, logger, scheduler
from clinic_bot.storage import load_data, save_data


load_data()
restored_jobs = 0
skipped_jobs = 0
for appt_id, appt in list(appointments.items()):
    if should_schedule_appointment_jobs(appt):
        if schedule_reminder(appt_id):
            restored_jobs += 1
    else:
        skipped_jobs += 1
logger.info("Restored appointment scheduler jobs: %s active, %s skipped", restored_jobs, skipped_jobs)
register_all()


def on_exit():
    try:
        save_data()
    finally:
        scheduler.shutdown(wait=False)


atexit.register(on_exit)


if __name__ == "__main__":
    logger.info("Bot ishga tushdi (modular).")
    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30,
        allowed_updates=[
            "message",
            "callback_query",
            "edited_message",
            "channel_post",
        ],
    )
