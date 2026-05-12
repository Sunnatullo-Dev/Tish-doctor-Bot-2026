from clinic_bot.shared import *

# ---------------- FALLBACK ----------------
@bot.message_handler(func=lambda m: True)
def mh_fallback(m: types.Message):
    # If not handled, provide friendly hint
    try:
        bot.send_message(m.chat.id, "Men tushunmadim. /start bilan boshlang yoki tugmalardan foydalaning.")
    except Exception:
        logger.exception("fallback send failed")
