from clinic_bot.shared import *
from clinic_bot.storage import save_data

# ---------------- MESSAGING ROUTER (patient <-> assigned admin) ----------------
# IMPORTANT: this handler must be after all specific handlers so it doesn't swallow them.
def should_route_message(m: types.Message):
    uid = m.from_user.id
    if m.chat.id in user_state:
        return False
    if uid in admin_add_state or uid in admin_ad_state:
        return False
    return uid in active_diag_chats or uid in admin_active_diag


@bot.message_handler(func=should_route_message, content_types=['text','photo','video','animation','document','audio','voice','contact','location'])
def routing_messages(m: types.Message):
    uid = m.from_user.id

    # If user is in active diag session, forward to assigned admin
    if uid in active_diag_chats:
        admin_id = active_diag_chats[uid]
        prefix = f"[Bemor {uid}] "
        try:
            if m.content_type == 'text':
                bot.send_message(admin_id, prefix + m.text)
            elif m.content_type == 'photo':
                bot.send_photo(admin_id, m.photo[-1].file_id, caption=prefix + (m.caption or ""))
            elif m.content_type == 'video':
                bot.send_video(admin_id, m.video.file_id, caption=prefix + (m.caption or ""))
            elif m.content_type == 'animation':
                bot.send_animation(admin_id, m.animation.file_id, caption=prefix + (m.caption or ""))
            elif m.content_type == 'document':
                bot.send_document(admin_id, m.document.file_id, caption=prefix + (m.caption or ""))
            elif m.content_type == 'voice':
                bot.send_voice(admin_id, m.voice.file_id, caption=prefix)
            elif m.content_type == 'audio':
                bot.send_audio(admin_id, m.audio.file_id, caption=prefix)
            elif m.content_type == 'contact':
                bot.send_message(admin_id, prefix + f"Kontakt: {m.contact.phone_number}")
            elif m.content_type == 'location':
                bot.send_message(admin_id, prefix + f"Lokatsiya: {m.location.latitude}, {m.location.longitude}")
            # log
            for req in diagnosis_requests.values():
                if req.get('user_chat') == uid and req.get('assigned_admin') == admin_id and req.get('status') == 'assigned':
                    req.setdefault('messages', []).append({"from":"user","type":m.content_type,"text": getattr(m, "text", None), "file_id": getattr(m, "file_id", None), "ts": datetime.now(tz).isoformat()})
                    break
            save_data()
        except Exception:
            logger.exception("forward user->admin failed")
        return

    # If sender is admin who is in active diag session, send to user
    if uid in admin_active_diag:
        user = admin_active_diag[uid]
        try:
            if m.content_type == 'text':
                bot.send_message(user, f"[Admin {m.from_user.first_name or uid}]: {m.text}")
            elif m.content_type == 'photo':
                bot.send_photo(user, m.photo[-1].file_id, caption=f"[Admin]: {m.caption or ''}")
            elif m.content_type == 'video':
                bot.send_video(user, m.video.file_id, caption=f"[Admin]: {m.caption or ''}")
            elif m.content_type == 'animation':
                bot.send_animation(user, m.animation.file_id, caption=f"[Admin]: {m.caption or ''}")
            elif m.content_type == 'document':
                bot.send_document(user, m.document.file_id, caption=f"[Admin]: {m.caption or ''}")
            elif m.content_type == 'voice':
                bot.send_voice(user, m.voice.file_id)
            elif m.content_type == 'audio':
                bot.send_audio(user, m.audio.file_id)
            for req in diagnosis_requests.values():
                if req.get('user_chat') == user and req.get('assigned_admin') == uid and req.get('status') == 'assigned':
                    req.setdefault('messages', []).append({"from":"admin","type":m.content_type,"text": getattr(m, "text", None), "file_id": getattr(m, "file_id", None), "ts": datetime.now(tz).isoformat()})
                    break
            save_data()
        except Exception:
            logger.exception("forward admin->user failed")
        return

    # not part of diag session & not in state: ignore here and let fallback handle or other handlers pick up
    return
