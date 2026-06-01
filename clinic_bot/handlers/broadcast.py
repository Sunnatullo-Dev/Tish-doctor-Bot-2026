from clinic_bot.shared import *
from clinic_bot.helpers import button_matches, is_admin
from clinic_bot.storage import save_data

# ---------------- BROADCAST (admin) ----------------
@bot.message_handler(func=lambda m: button_matches(m.text, "📢 Reklama yuborish"))
def admin_ad_start(m: types.Message):
    if not is_admin(m.from_user.id): return
    admin_ad_state[m.from_user.id] = "await_ad_text"
    total = len(users)
    bot.send_message(m.chat.id, f"📢 Reklama: Matn, rasm, video yoki fayl jo'nating.\nJami foydalanuvchilar: {total}\nBekor qilish uchun: Bekor qilish")

@bot.message_handler(
    func=lambda m: admin_ad_state.get(m.from_user.id) == "await_ad_text",
    content_types=['text','photo','video','animation','document']
)
def admin_send_ad(m: types.Message):
    if m.content_type == "text" and m.text.strip().lower() in ("bekor qilish", "bekor", "cancel"):
        admin_ad_state.pop(m.from_user.id, None)
        bot.send_message(m.chat.id, "Reklama yuborish bekor qilindi.")
        return
    admin_ad_state.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, f"⏳ Reklama {len(users)} ta foydalanuvchiga yuborilmoqda...")
    sent = 0; failed = 0; blocked = 0
    for uid in list(users):
        try:
            if m.content_type == "text":
                bot.send_message(uid, m.text)
            elif m.content_type == "photo":
                bot.send_photo(uid, m.photo[-1].file_id, caption=m.caption or "")
            elif m.content_type == "video":
                bot.send_video(uid, m.video.file_id, caption=m.caption or "")
            elif m.content_type == "animation":
                bot.send_animation(uid, m.animation.file_id, caption=m.caption or "")
            elif m.content_type == "document":
                bot.send_document(uid, m.document.file_id, caption=m.caption or "")
            sent += 1
        except Exception as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "deactivated" in err_str or "not found" in err_str:
                blocked += 1
            else:
                failed += 1
    bot.send_message(
        m.chat.id,
        f"✅ Reklama yuborildi!\n"
        f"📤 Yuborildi: {sent}\n"
        f"🚫 Bloklagan/o'chirilgan: {blocked}\n"
        f"❌ Xatolik: {failed}"
    )
    save_data()
