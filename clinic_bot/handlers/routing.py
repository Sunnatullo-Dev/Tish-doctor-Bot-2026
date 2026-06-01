from html import escape

from clinic_bot.shared import *
from clinic_bot.storage import save_data

# ---------------- MESSAGING ROUTER ----------------
# Routes messages between:
#   - user <-> assigned doctor  (NEW chat system, mode-aware: sms=text, call=audio/video)
#   - user <-> assigned admin   (legacy admin SMS chat)
# IMPORTANT: this handler must be registered AFTER all specific state-based handlers
# so it doesn't swallow them.

CALL_ALLOWED_TYPES = {'voice', 'audio', 'video', 'video_note'}
SMS_ALLOWED_TYPES = {'text'}


def _doctor_label(user_chat):
    """Return label like 'Dr. Sunnatulla' for the doctor user is chatting with."""
    req_id = diag_chat_req.get(user_chat)
    if req_id:
        req = diagnosis_requests.get(req_id)
        if req:
            full = req.get("assigned_doctor_name") or "Doktor"
            short = full.split(" — ")[0] if " — " in full else full
            return f"Dr. {short}".strip()
    return "Doktor"


def _user_label(user_chat):
    """Return the patient's name (form-entered name preferred, fallback to Telegram first_name)."""
    req_id = diag_chat_req.get(user_chat)
    if req_id:
        req = diagnosis_requests.get(req_id)
        if req:
            name = req.get("patient_name") or req.get("user_first_name")
            if name:
                # Keep it short for clean header
                first = name.strip().split()[0]
                return first
    return "Bemor"


def should_route_message(m: types.Message):
    uid = m.from_user.id
    # If user is in an active booking/admin flow, don't intercept
    st = user_state.get(m.chat.id, {})
    if st and st.get('step') not in (None, 'start'):
        return False
    if uid in admin_add_state or uid in admin_ad_state:
        return False
    # Doctor chats (new)
    if m.chat.id in active_doctor_chats or uid in doctor_active_chats:
        return True
    # Legacy admin chats
    if m.chat.id in active_diag_chats or uid in admin_active_diag:
        return True
    return False


def _forward_to_peer(peer_id, m: types.Message, header, content_filter=None):
    """Forward a message to peer_id with a bold header showing who it's from.

    `header` is the plain identifier (e.g. "Dr. Sunnatulla" or "👤 Aliyev").
    Always rendered bold above the message body for clarity.
    """
    if content_filter is not None and m.content_type not in content_filter:
        return False
    try:
        ct = m.content_type
        header_html = f"<b>{escape(header)}</b>"
        if ct == 'text':
            body = m.text or ""
            bot.send_message(peer_id, f"{header_html}\n{escape(body)}", parse_mode="HTML")
        elif ct == 'photo':
            cap = f"{header_html}\n{escape(m.caption)}" if m.caption else header_html
            bot.send_photo(peer_id, m.photo[-1].file_id, caption=cap, parse_mode="HTML")
        elif ct == 'video':
            cap = f"{header_html}\n{escape(m.caption)}" if m.caption else header_html
            bot.send_video(peer_id, m.video.file_id, caption=cap, parse_mode="HTML")
        elif ct == 'video_note':
            # Video notes don't support captions — send header first then the round video.
            bot.send_message(peer_id, f"{header_html}\n<i>(video xabar)</i>", parse_mode="HTML")
            bot.send_video_note(peer_id, m.video_note.file_id)
        elif ct == 'animation':
            cap = f"{header_html}\n{escape(m.caption)}" if m.caption else header_html
            bot.send_animation(peer_id, m.animation.file_id, caption=cap, parse_mode="HTML")
        elif ct == 'document':
            cap = f"{header_html}\n{escape(m.caption)}" if m.caption else header_html
            bot.send_document(peer_id, m.document.file_id, caption=cap, parse_mode="HTML")
        elif ct == 'voice':
            bot.send_voice(peer_id, m.voice.file_id, caption=header_html, parse_mode="HTML")
        elif ct == 'audio':
            bot.send_audio(peer_id, m.audio.file_id, caption=header_html, parse_mode="HTML")
        elif ct == 'contact':
            bot.send_message(peer_id, f"{header_html}\nKontakt: {escape(m.contact.phone_number or '-')}", parse_mode="HTML")
        elif ct == 'location':
            bot.send_message(peer_id, f"{header_html}\nLokatsiya: {m.location.latitude}, {m.location.longitude}", parse_mode="HTML")
        else:
            return False
        return True
    except Exception:
        logger.exception("forward to peer failed")
        return False


def _log_chat_message(req_id, who, m):
    if not req_id:
        return
    req = diagnosis_requests.get(req_id)
    if not req:
        return
    req.setdefault('messages', []).append({
        "from": who,
        "type": m.content_type,
        "text": getattr(m, 'text', None) or m.caption,
        "file_id": (
            (m.photo[-1].file_id if m.content_type == 'photo' and m.photo else None)
            or getattr(getattr(m, m.content_type, None), 'file_id', None)
        ),
        "ts": datetime.now(tz).isoformat(),
    })


@bot.message_handler(
    func=should_route_message,
    content_types=['text','photo','video','animation','document','audio','voice','contact','location','video_note']
)
def routing_messages(m: types.Message):
    uid = m.from_user.id

    # === NEW: user <-> doctor chats ===
    # User sending to doctor
    if m.chat.id in active_doctor_chats:
        doctor_tg = active_doctor_chats[m.chat.id]
        mode = diag_chat_mode.get(m.chat.id, 'sms')
        if mode == 'sms':
            if m.content_type not in SMS_ALLOWED_TYPES:
                bot.send_message(m.chat.id, "ℹ️ Bu SMS suhbat. Faqat matn yuboring.")
                return
        else:  # call mode
            if m.content_type not in CALL_ALLOWED_TYPES:
                bot.send_message(m.chat.id, "ℹ️ Bu audio/video suhbat. Faqat ovozli yoki video xabar yuboring.")
                return
        # Doctor sees the patient's name in bold
        patient_name = _user_label(m.chat.id)
        header = f"👤 {patient_name}"
        if _forward_to_peer(doctor_tg, m, header):
            _log_chat_message(diag_chat_req.get(m.chat.id), "user", m)
            save_data()
        return

    # Doctor sending to user
    if uid in doctor_active_chats:
        user_chat = doctor_active_chats[uid]
        mode = diag_chat_mode.get(user_chat, 'sms')
        if mode == 'sms':
            if m.content_type not in SMS_ALLOWED_TYPES:
                bot.send_message(m.chat.id, "ℹ️ Bu SMS suhbat. Faqat matn yuboring.")
                return
        else:
            if m.content_type not in CALL_ALLOWED_TYPES:
                bot.send_message(m.chat.id, "ℹ️ Bu audio/video suhbat. Faqat ovozli yoki video xabar yuboring.")
                return
        # User sees the doctor's name in bold — clear who they're chatting with
        doctor_name = _doctor_label(user_chat)
        header = f"👨‍⚕️ {doctor_name}"
        if _forward_to_peer(user_chat, m, header):
            _log_chat_message(diag_chat_req.get(user_chat), "doctor", m)
            save_data()
        return

    # === LEGACY: user <-> admin chats (kept for in-flight conversations) ===
    if uid in active_diag_chats:
        admin_id = active_diag_chats[uid]
        prefix = f"[Bemor {uid}] "
        _forward_to_peer(admin_id, m, prefix)
        for req in diagnosis_requests.values():
            if req.get('user_chat') == uid and req.get('assigned_admin') == admin_id and req.get('status') == 'assigned':
                req.setdefault('messages', []).append({"from":"user","type":m.content_type,"text": getattr(m, "text", None), "ts": datetime.now(tz).isoformat()})
                break
        save_data()
        return

    if uid in admin_active_diag:
        user = admin_active_diag[uid]
        first = m.from_user.first_name or str(uid)
        prefix = f"[Admin {first}]: "
        _forward_to_peer(user, m, prefix)
        for req in diagnosis_requests.values():
            if req.get('user_chat') == user and req.get('assigned_admin') == uid and req.get('status') == 'assigned':
                req.setdefault('messages', []).append({"from":"admin","type":m.content_type,"text": getattr(m, "text", None), "ts": datetime.now(tz).isoformat()})
                break
        save_data()
        return
