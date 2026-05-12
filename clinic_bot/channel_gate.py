"""Mandatory channel management and subscription checks."""

from clinic_bot.shared import *
from clinic_bot.helpers import is_admin, mk, new_id
from clinic_bot.storage import save_data

SUBSCRIBED_STATUSES = {"creator", "administrator", "member"}


def normalize_channel_ref(raw):
    ref = (raw or "").strip()
    if ref.startswith("https://t.me/"):
        ref = "@" + ref.rstrip("/").split("/")[-1]
    if ref.startswith("t.me/"):
        ref = "@" + ref.rstrip("/").split("/")[-1]
    return ref


def active_channels():
    return [ch for ch in mandatory_channels.values() if ch.get("enabled", True)]


def channel_button_text(channel):
    status = "Faol" if channel.get("enabled", True) else "Muzlatilgan"
    count = channel.get("last_member_count")
    count_text = f" | {count} obuna" if count is not None else ""
    return f"{channel.get('title') or channel.get('username') or channel.get('chat_id')} ({status}{count_text})"


def channel_public_url(channel):
    username = channel.get("username")
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    chat_id = str(channel.get("chat_id", ""))
    if chat_id.startswith("-100"):
        return f"https://t.me/c/{chat_id[4:]}"
    return None


def refresh_channel_member_count(channel):
    try:
        count = bot.get_chat_member_count(channel["chat_id"])
        channel["last_member_count"] = count
        channel["last_count_checked_at"] = datetime.now(tz).isoformat()
        return count
    except Exception:
        logger.exception("failed to get channel member count for %s", channel.get("chat_id"))
        return channel.get("last_member_count")


def add_mandatory_channel(raw_ref, added_by):
    ref = normalize_channel_ref(raw_ref)
    if not ref:
        raise ValueError("Kanal username yoki ID yuboring.")
    chat = bot.get_chat(ref)
    chat_id = str(chat.id)
    bot_info = bot.get_me()
    bot_member = bot.get_chat_member(chat.id, bot_info.id)
    if bot_member.status not in ("administrator", "creator"):
        raise PermissionError("Bot kanalga admin qilinmagan. Avval botni kanalga admin qilib qo'ying.")

    channel = mandatory_channels.get(chat_id, {})
    channel.update({
        "id": channel.get("id") or new_id("chan"),
        "chat_id": chat_id,
        "title": getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id),
        "username": getattr(chat, "username", None),
        "enabled": True,
        "added_by": channel.get("added_by") or added_by,
        "added_at": channel.get("added_at") or datetime.now(tz).isoformat(),
        "updated_at": datetime.now(tz).isoformat(),
    })
    mandatory_channels[chat_id] = channel
    refresh_channel_member_count(channel)
    save_data()
    return channel


def set_channel_enabled(chat_id, enabled):
    key = str(chat_id)
    channel = mandatory_channels.get(key)
    if not channel:
        return None
    channel["enabled"] = enabled
    channel["updated_at"] = datetime.now(tz).isoformat()
    save_data()
    return channel


def delete_mandatory_channel(chat_id):
    key = str(chat_id)
    channel = mandatory_channels.pop(key, None)
    if channel:
        for per_user in channel_user_stats.values():
            per_user.pop(key, None)
        save_data()
    return channel


def record_user_channel_status(user_id, channel, status, is_subscribed):
    uid = str(user_id)
    key = str(channel["chat_id"])
    now_iso = datetime.now(tz).isoformat()
    user_row = channel_user_stats.setdefault(uid, {})
    prev = user_row.get(key, {})
    row = {
        "channel_id": key,
        "status": status,
        "is_subscribed": is_subscribed,
        "checked_at": now_iso,
        "first_subscribed_at": prev.get("first_subscribed_at"),
        "last_subscribed_at": prev.get("last_subscribed_at"),
    }
    if is_subscribed:
        row["first_subscribed_at"] = row["first_subscribed_at"] or now_iso
        row["last_subscribed_at"] = now_iso
    user_row[key] = row


def check_user_subscriptions(user_id):
    missing = []
    checked = []
    for channel in active_channels():
        try:
            member = bot.get_chat_member(channel["chat_id"], user_id)
            status = member.status
            is_subscribed = status in SUBSCRIBED_STATUSES
        except Exception:
            logger.exception("failed to check subscription: user=%s channel=%s", user_id, channel.get("chat_id"))
            status = "unknown"
            is_subscribed = False
        record_user_channel_status(user_id, channel, status, is_subscribed)
        checked.append(channel)
        if not is_subscribed:
            missing.append(channel)
    save_data()
    return missing, checked


def subscription_prompt(channels):
    kb = InlineKeyboardMarkup()
    for channel in channels:
        url = channel_public_url(channel)
        title = channel.get("title") or channel.get("username") or channel.get("chat_id")
        if url:
            kb.add(InlineKeyboardButton(f"Kanalga o'tish: {title}", url=url))
        else:
            kb.add(mk(f"Kanal: {title}", "noop"))
    kb.add(mk("✅ Obunani tekshirish", "check_subscriptions"))
    return kb


def subscribed_user_count(channel_id):
    key = str(channel_id)
    return sum(1 for stats in channel_user_stats.values() if stats.get(key, {}).get("is_subscribed"))


def channel_stats_text(channel):
    refresh_channel_member_count(channel)
    key = str(channel["chat_id"])
    checked_users = sum(1 for stats in channel_user_stats.values() if key in stats)
    subscribed_users = subscribed_user_count(key)
    status = "Faol" if channel.get("enabled", True) else "Muzlatilgan"
    username_line = f"Username: @{channel.get('username')}\n" if channel.get("username") else ""
    return (
        f"?? <b>{channel.get('title')}</b>\n"
        f"Holat: {status}\n"
        f"{username_line}"
        f"Telegram obunachilar soni: {channel.get('last_member_count', '-')}\n"
        f"Bot tekshirgan foydalanuvchilar: {checked_users}\n"
        f"Bot bo'yicha obuna bo'lganlar: {subscribed_users}\n"
        f"Oxirgi yangilanish: {channel.get('last_count_checked_at', '-')}"
    )


def send_subscription_required(chat_id, missing_channels):
    bot.send_message(
        chat_id,
        "Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling, keyin tekshirish tugmasini bosing.",
        reply_markup=subscription_prompt(missing_channels),
    )


def ensure_user_subscribed(chat_id, user_id):
    if is_admin(user_id):
        return True
    missing, _ = check_user_subscriptions(user_id)
    if missing:
        send_subscription_required(chat_id, missing)
        return False
    return True
