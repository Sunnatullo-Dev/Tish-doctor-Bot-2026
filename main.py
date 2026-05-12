import atexit

from clinic_bot.handlers import register_all
from clinic_bot.scheduler_jobs import schedule_reminder
from clinic_bot.shared import appointments, bot, logger, scheduler
from clinic_bot.storage import load_data, save_data


load_data()
for appt_id in list(appointments):
    schedule_reminder(appt_id)
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
