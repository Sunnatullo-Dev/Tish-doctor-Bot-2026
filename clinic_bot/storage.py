"""JSON persistence for clinics, appointments, admins, and diagnosis tickets."""

import copy as copy_module
import sys

from clinic_bot import shared as s


def parse_iso_datetime(value):
    if not value:
        return s.datetime.min.replace(tzinfo=s.tz)
    try:
        parsed = s.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return s.tz.localize(parsed)
        return parsed
    except Exception:
        return s.datetime.min.replace(tzinfo=s.tz)


def restore_active_diagnosis_chats():
    s.active_diag_chats.clear()
    s.admin_active_diag.clear()
    s.active_doctor_chats.clear()
    s.doctor_active_chats.clear()
    s.diag_chat_mode.clear()
    s.diag_chat_req.clear()

    # Legacy: admin <-> user SMS chats (status == 'assigned')
    admin_candidates = []
    for req_id, req in s.diagnosis_requests.items():
        if req.get("type", "sms") != "sms":
            continue
        if req.get("status") != "assigned":
            continue
        user_chat = req.get("user_chat")
        assigned_admin = req.get("assigned_admin")
        if user_chat is None or assigned_admin is None:
            continue
        try:
            user_chat = int(user_chat)
            assigned_admin = int(assigned_admin)
        except (TypeError, ValueError):
            s.logger.warning("Skipping diagnosis chat restore for %s: invalid user/admin ids", req_id)
            continue
        if assigned_admin not in s.admins:
            s.logger.warning("Skipping diagnosis chat restore for %s: admin %s is not active", req_id, assigned_admin)
            continue
        admin_candidates.append((parse_iso_datetime(req.get("created_at")), req_id, user_chat, assigned_admin))

    restored_admin = 0
    used_users = set()
    used_admins = set()
    for _, req_id, user_chat, assigned_admin in sorted(admin_candidates, reverse=True):
        if user_chat in used_users or assigned_admin in used_admins:
            s.logger.warning("Skipping duplicate active diagnosis chat during restore: %s", req_id)
            continue
        s.active_diag_chats[user_chat] = assigned_admin
        s.admin_active_diag[assigned_admin] = user_chat
        used_users.add(user_chat)
        used_admins.add(assigned_admin)
        restored_admin += 1

    # New: doctor <-> user chats (status == 'chat_active')
    doctor_candidates = []
    for req_id, req in s.diagnosis_requests.items():
        if req.get("status") != "chat_active":
            continue
        user_chat = req.get("user_chat")
        doctor_tg = req.get("assigned_doctor_telegram_id")
        if user_chat is None or doctor_tg is None:
            continue
        try:
            user_chat = int(user_chat); doctor_tg = int(doctor_tg)
        except (TypeError, ValueError):
            continue
        doctor_candidates.append((parse_iso_datetime(req.get("created_at")), req_id, user_chat, doctor_tg, req.get("type", "sms")))

    restored_doctor = 0
    used_users_d = set()
    used_doctors = set()
    for _, req_id, user_chat, doctor_tg, rtype in sorted(doctor_candidates, reverse=True):
        if user_chat in used_users_d or doctor_tg in used_doctors:
            s.logger.warning("Skipping duplicate active doctor chat during restore: %s", req_id)
            continue
        if user_chat in used_users:
            s.logger.warning("User %s already has admin chat; skipping doctor restore for %s", user_chat, req_id)
            continue
        s.active_doctor_chats[user_chat] = doctor_tg
        s.doctor_active_chats[doctor_tg] = user_chat
        s.diag_chat_mode[user_chat] = "call" if rtype == "doctor_call" else "sms"
        s.diag_chat_req[user_chat] = req_id
        used_users_d.add(user_chat)
        used_doctors.add(doctor_tg)
        restored_doctor += 1

    s.logger.info("Restored chats — admin: %s, doctor: %s", restored_admin, restored_doctor)
    return restored_admin + restored_doctor


def load_data():
    with s.data_lock:
        if not s.os.path.exists(s.DATA_FILE):
            s.logger.info("No data file found ? using defaults")
            s.data_loaded_successfully = True
            restore_active_diagnosis_chats()
            return
        try:
            with open(s.DATA_FILE, "r", encoding="utf-8") as f:
                data = s.json.load(f)

            loaded_clinics = data.get("clinics")
            if isinstance(loaded_clinics, list):
                s.clinics[:] = loaded_clinics

            loaded_pending = data.get("pending_doctors", {})
            if isinstance(loaded_pending, dict):
                s.pending_doctors.clear()
                s.pending_doctors.update(loaded_pending)

            users_list = data.get("users", [])
            s.users.clear()
            s.users.update(users_list)

            s.users_info.clear()
            s.users_info.update(data.get("users_info", {}))

            if "admins" in data and isinstance(data["admins"], list):
                s.admins.clear()
                s.admins.update(data["admins"])

            s.admin_history[:] = data.get("admin_history", s.admin_history)

            loaded_diagnosis = data.get("diagnosis_requests", {})
            s.diagnosis_requests.clear()
            if isinstance(loaded_diagnosis, dict):
                s.diagnosis_requests.update(loaded_diagnosis)
            else:
                s.logger.warning("Ignoring invalid diagnosis_requests data")
            restore_active_diagnosis_chats()

            s.mandatory_channels.clear()
            s.mandatory_channels.update(data.get("mandatory_channels", {}))

            s.channel_user_stats.clear()
            s.channel_user_stats.update(data.get("channel_user_stats", {}))

            s.appointments.clear()
            appts_raw = data.get("appointments", {})
            for k, v in appts_raw.items():
                copy = v.copy()
                dt_iso = copy.get("datetime_iso")
                if dt_iso:
                    try:
                        dt = s.datetime.fromisoformat(dt_iso)
                        if dt.tzinfo is None:
                            dt = s.tz.localize(dt)
                        copy["datetime"] = dt
                    except Exception:
                        copy["datetime"] = None
                else:
                    copy["datetime"] = None

                doc_id = copy.get("doctor_id")
                clinic_id = copy.get("clinic_id")
                if clinic_id:
                    clinic = next((x for x in s.clinics if x["id"] == clinic_id), None)
                    if clinic:
                        copy["clinic"] = clinic
                        if doc_id:
                            doc = next((d for d in clinic["doctors"] if d["id"] == doc_id), None)
                            copy["doctor_obj"] = doc
                s.appointments[k] = copy

            s.logger.info("Loaded persistent data from %s", s.DATA_FILE)
            s.data_loaded_successfully = True
        except Exception as e:
            s.logger.error("CRITICAL: load_data failed: %s", e)
            s.logger.error("Stopping bot to prevent data loss. Please check your JSON file.")
            s.data_loaded_successfully = False
            sys.exit(1)


def save_data():
    with s.data_lock:
        if not s.data_loaded_successfully:
            s.logger.warning("Data was not loaded successfully. Skipping save to prevent data loss.")
            return
        try:
            clinics_snapshot = copy_module.deepcopy(s.clinics)
            pending_snapshot = copy_module.deepcopy(s.pending_doctors)
            users_snapshot = list(s.users)
            users_info_snapshot = copy_module.deepcopy(s.users_info)
            admins_snapshot = list(s.admins)
            admin_history_snapshot = copy_module.deepcopy(s.admin_history)
            diagnosis_snapshot = copy_module.deepcopy(s.diagnosis_requests)
            mandatory_channels_snapshot = copy_module.deepcopy(s.mandatory_channels)
            channel_user_stats_snapshot = copy_module.deepcopy(s.channel_user_stats)
            appointments_snapshot = copy_module.deepcopy(list(s.appointments.items()))

            to_save = {
                "clinics": clinics_snapshot,
                "pending_doctors": pending_snapshot,
                "appointments": {},
                "users": users_snapshot,
                "users_info": users_info_snapshot,
                "admins": admins_snapshot,
                "admin_history": admin_history_snapshot,
                "diagnosis_requests": diagnosis_snapshot,
                "mandatory_channels": mandatory_channels_snapshot,
                "channel_user_stats": channel_user_stats_snapshot,
            }
            for k, v in appointments_snapshot:
                copy = v.copy()
                dt = copy.pop("datetime", None)
                if isinstance(dt, s.datetime):
                    if dt.tzinfo is None:
                        dt = s.tz.localize(dt)
                    copy["datetime_iso"] = dt.isoformat()
                else:
                    copy["datetime_iso"] = None

                doc = copy.get("doctor_obj")
                if doc:
                    copy["doctor_id"] = doc.get("id")
                    for c in clinics_snapshot:
                        if any(d.get("id") == doc.get("id") for d in c["doctors"]):
                            copy["clinic_id"] = c["id"]
                            break
                clinic = copy.get("clinic")
                if clinic and "clinic_id" not in copy:
                    copy["clinic_id"] = clinic.get("id")
                copy.pop("doctor_obj", None)
                copy.pop("clinic", None)
                to_save["appointments"][k] = copy

            temp_file = f"{s.DATA_FILE}.{s.os.getpid()}.{s.threading.get_ident()}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                s.json.dump(to_save, f, ensure_ascii=False, indent=2)

            s.os.replace(temp_file, s.DATA_FILE)

            s.logger.debug("Saved data to %s", s.DATA_FILE)
        except Exception:
            s.logger.exception("save_data failed")
